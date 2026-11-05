import logging
import queue
import struct
import time

from backend.comms.crc import crc16_ccitt
from backend.recording.raw_logger import RawLogger
from backend.telemetry.decoder import Decoder
from backend.telemetry.models import APID_BARO, K_SPP_PKT_VERSION
from groundstation.source import DiscardReport, TelemetrySource


def baro_frame(seq: int = 1, t_ms: int = 1000) -> bytes:
    """Trama completa de 64 bytes, con su CRC, como la manda el firmware."""
    payload = struct.pack("<3f", 10.0, 101325.0, 20.0).ljust(50, b"\xff")
    body = struct.pack("<BHHHIB", K_SPP_PKT_VERSION, APID_BARO, seq, 12, t_ms, 0) + payload
    return body + struct.pack("<H", crc16_ccitt(body))


class Broken:
    def __getattr__(self, name):
        def fail(*args, **kwargs):
            raise OSError("disco lleno")
        return fail


def drain(source) -> list:
    out = []
    while True:
        try:
            out.append(source.packets.get_nowait())
        except queue.Empty:
            return out


def make_source():
    s = TelemetrySource.__new__(TelemetrySource)   # Sin hilo ni puerto: solo el procesado
    s.packets = queue.SimpleQueue()
    return s


def test_packet_reaches_the_screen_even_if_logging_and_routing_fail():
    s = make_source()
    s._handle_frame(baro_frame(), Decoder(), Broken(), Broken(), DiscardReport())
    assert len(drain(s)) == 1


def test_undecodable_frames_are_summarised(caplog):
    caplog.set_level(logging.WARNING)
    s, report = make_source(), DiscardReport()
    bad = bytearray(baro_frame())
    bad[0] = 9                                      # Versión desconocida
    for _ in range(50):
        s._handle_frame(bytes(bad), Decoder(), None, None, report)
    assert drain(s) == []
    assert caplog.text.count("Paquete descartado") == 1   # Uno, no cincuenta
    assert report.count == 49


def test_raw_logger_survives_an_unwritable_directory(tmp_path, caplog):
    blocker = tmp_path / "logs"
    blocker.write_text("esto es un fichero, no una carpeta")
    logger = RawLogger(log_dir=str(blocker))
    logger.log_frame(baro_frame())                  # No lanza
    logger.log_frame(baro_frame())
    assert caplog.text.count("No se puede escribir") == 1
    logger.close()


class FakeUART:
    """Entrega media trama, "reconecta" y entrega una trama entera."""

    def __init__(self):
        self.connections = 1
        self.connected, self.connected_port = True, "fake"
        frame = baro_frame()
        self.reads = [frame[:30], "reconnect", frame, frame]

    def read(self):
        if not self.reads:
            time.sleep(0.01)
            return b""
        item = self.reads.pop(0)
        if item == "reconnect":
            self.connections += 1
            return b""
        return item


def test_reconnect_discards_the_half_frame_from_before(caplog):
    caplog.set_level(logging.WARNING)
    s = TelemetrySource(replay=None)
    s.reader = FakeUART()
    s.replay = True                                 # Sin router ni logs/ en el test
    s.start()
    time.sleep(0.3)
    s.stop()
    assert len(drain(s)) == 2
    # Los 30 bytes de antes de reconectar se tiran al reconectar, sin tener que resincronizar
    assert "Resincronizado" not in caplog.text
