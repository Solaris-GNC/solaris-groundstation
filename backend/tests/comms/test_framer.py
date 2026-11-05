import random
from pathlib import Path

import pytest

from backend.comms.crc import crc16_ccitt
from backend.comms.framer import SPPFramer
from backend.comms.packet_buffer import PacketBuffer

RAW = bytes.fromhex((Path(__file__).resolve().parents[2] / "data" / "log_uart.txt").read_text())
FRAME = SPPFramer.FRAME_SIZE


def valid_frames(data: bytes) -> list[bytes]:
    """Tramas con CRC válido del log real, buscadas byte a byte (el log tiene basura y huecos)."""
    out, i = [], 0
    while i + FRAME <= len(data):
        if crc16_ccitt(data[i:i + FRAME - 2]) == int.from_bytes(data[i + FRAME - 2:i + FRAME], "little"):
            out.append(data[i:i + FRAME])
            i += FRAME
        else:
            i += 1
    return out


VALID = valid_frames(RAW)
DATA = b"".join(VALID)          # Flujo limpio: solo tramas válidas, seguidas


def frames_of(stream: bytes, chunk=lambda: 64, buffer=None) -> list[bytes]:
    """Mete el flujo en el buffer a trozos y saca todas las tramas, como el hilo de lectura."""
    buffer = buffer or PacketBuffer()
    framer, out, i = SPPFramer(), [], 0
    while i < len(stream):
        n = chunk()
        buffer.write(stream[i:i + n])
        i += n
        while (frame := framer.extract(buffer)) is not None:
            out.append(frame)
    return out


@pytest.fixture
def clean():
    return frames_of(DATA)


# ==================================================================
# CRC

def crc_bitwise(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def test_crc_check_value():
    # Valor de comprobación estándar de CRC-16/CCITT-FALSE
    assert crc16_ccitt(b"123456789") == 0x29B1


def test_crc_table_matches_bitwise():
    rng = random.Random(1)
    for _ in range(200):
        data = bytes(rng.randrange(256) for _ in range(rng.randrange(80)))
        assert crc16_ccitt(data) == crc_bitwise(data)


# ==================================================================
# Framer

def test_real_log_is_fully_framed(clean):
    assert len(VALID) > 30
    assert clean == VALID


def test_real_log_with_its_own_garbage():
    # Tal cual se grabó: 3 bytes sueltos al principio y tramas a medias por el medio
    assert frames_of(RAW) == VALID


def test_frames_split_across_reads(clean):
    # El puerto entrega trozos de cualquier tamaño, también de 1 byte
    rng = random.Random(2)
    assert frames_of(DATA, chunk=lambda: rng.randint(1, 100)) == clean
    assert frames_of(DATA, chunk=lambda: 1) == clean


def test_resyncs_after_noise_and_starting_mid_frame(clean):
    rng = random.Random(3)
    noise = bytes(rng.randrange(256) for _ in range(3000))
    # Se empieza a escuchar a mitad de una trama, y entre tramas se cuela ruido
    stream = DATA[FRAME // 2:FRAME * 10] + noise + DATA[FRAME * 10:]
    got = frames_of(stream, chunk=lambda: rng.randint(1, 100))
    # Todas las tramas buenas, en orden. En el ruido puede colarse alguna ventana que por azar
    # cuadra con el CRC (1 de cada 65536 posiciones): la para el decoder (test_decoder.py)
    assert [f for f in got if f in clean] == clean[1:]


def test_a_corrupted_frame_is_dropped_and_the_next_ones_survive(clean):
    stream = bytearray(DATA)
    stream[FRAME * 5 + 20] ^= 0xFF          # Un byte cambiado en la sexta trama
    got = frames_of(bytes(stream))
    assert got == clean[:5] + clean[6:]


def test_lost_bytes_only_lose_that_frame(clean):
    stream = DATA[:FRAME * 3 + 10] + DATA[FRAME * 3 + 17:]   # Se pierden 7 bytes de la cuarta trama
    assert frames_of(stream) == clean[:3] + clean[4:]


def test_resync_is_reported_once(caplog, clean):
    rng = random.Random(4)
    frames_of(bytes(rng.randrange(256) for _ in range(500)) + DATA)
    assert caplog.text.count("Resincronizado") == 1


# ==================================================================
# Buffer

def test_buffer_has_a_size_limit():
    buf = PacketBuffer(max_size=100)
    buf.write(bytes(range(80)))
    buf.write(bytes(range(80)))
    assert buf.size() == 100
    assert buf.dropped == 60
    assert buf.peek(3) == bytes([60, 61, 62])  # Se quedan los más recientes


def test_peek_does_not_consume():
    buf = PacketBuffer()
    buf.write(b"abcdef")
    assert buf.peek(2) == b"ab" and buf.peek() == b"abcdef"
    buf.consume(2)
    assert buf.peek() == b"cdef"
