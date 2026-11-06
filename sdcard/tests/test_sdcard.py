import math
import random
import struct

import numpy as np

from backend.comms.crc import crc16_ccitt
from backend.telemetry.models import APID_BARO, APID_IMU, K_SPP_PKT_VERSION, BAROPacket
from sdcard.dump import (
    FRAME_SIZE, SECTOR_SIZE, baro_series, decode_dump, find_apogee, find_frames, frame_is_valid,
)


def make_frame(apid: int, payload: bytes, seq: int, timestamp_ms: int) -> bytes:
    """SPP_Packet_t tal cual lo guarda el firmware: 64 B, payload rellenado con 0xFF y CRC."""
    body = (struct.pack("<BHHHIB", K_SPP_PKT_VERSION, apid, seq, len(payload), timestamp_ms, 0)
            + payload.ljust(50, b"\xff"))
    return body + struct.pack("<H", crc16_ccitt(body))


def flight(duration_s=30.0, t_apogee=12.0, apogee_m=300.0, liftoff_s=5.0, ground=0.0, t0_ms=0):
    """Vuelo sintético: BARO a 20 Hz (parábola de liftoff a tierra) e IMU a 50 Hz."""
    frames = []
    seq = {APID_BARO: 0, APID_IMU: 0}
    for t_ms in range(0, int(duration_s * 1000), 10):
        if t_ms % 50 == 0:
            t = t_ms / 1000
            h = max(0.0, apogee_m * (1 - ((t - t_apogee) / (t_apogee - liftoff_s)) ** 2)) if t >= liftoff_s else 0.0
            frames.append(make_frame(APID_BARO, struct.pack("<3f", ground + h, 101325.0, 20.0), seq[APID_BARO], t0_ms + t_ms))
            seq[APID_BARO] += 1
        if t_ms % 20 == 0:
            frames.append(make_frame(APID_IMU, struct.pack("<11f", *([0.0] * 6), 1, 0, 0, 0, 3), seq[APID_IMU], t0_ms + t_ms))
            seq[APID_IMU] += 1
    return frames


def firmware_write(frames, disk: bytearray) -> bytearray:
    """Lo que deja en la SD el datalogger (datalogger.c): cada 16 paquetes escribe 2 sectores
    seguidos. Los últimos paquetes que no llenan el buffer no llegan a escribirse."""
    for n in range(len(frames) // 16):
        chunk = b"".join(frames[n * 16:(n + 1) * 16])
        disk[n * 2 * SECTOR_SIZE:(n + 1) * 2 * SECTOR_SIZE] = chunk
    return disk


def sd(*sessions) -> bytes:
    """SD sin borrar entre arranques: cada sesión se escribe desde el principio sobre la anterior."""
    disk = bytearray(4096 * SECTOR_SIZE)
    for frames in sessions:
        firmware_write(frames, disk)
    return bytes(disk)


def test_crc_matches_the_backend():
    frame = make_frame(APID_BARO, struct.pack("<3f", 1, 2, 3), seq=7, timestamp_ms=1234)
    assert frame_is_valid(frame)
    assert not frame_is_valid(frame[:20] + bytes([frame[20] ^ 1]) + frame[21:])


def test_frames_are_found_among_garbage_and_misaligned():
    frames = flight(duration_s=1)
    rng = random.Random(2)
    data = bytearray(b"\x00" * 1000)
    for frame in frames:
        data += frame + bytes(rng.randrange(256) for _ in range(rng.randrange(0, 7)))
    data += b"\xff" * 1000
    assert [f for _, f in find_frames(bytes(data))] == frames


def test_clean_log_is_one_session_with_every_packet():
    frames = flight()
    contents = decode_dump(b"".join(frames) + bytes(64 * SECTOR_SIZE))
    assert len(contents.sessions) == 1
    session = contents.sessions[0]
    assert len(session.records) == len(frames)
    assert session.count(BAROPacket) == 600


def test_apogee_ignores_a_single_spike():
    t = np.arange(0, 30000, 50, dtype=float)
    alt = np.array([100 + max(0, 300 * (1 - ((s - 12) / 7) ** 2)) if s >= 5 else 100 for s in t / 1000])
    alt[100] = 5000                # Lectura corrupta del barómetro
    apogee = find_apogee(t, alt)
    assert abs(apogee.ts - 12000) <= 100
    assert math.isclose(apogee.agl, 300, abs_tol=0.5)
    assert math.isclose(apogee.ground, 100)
    assert math.isclose(apogee.t_from_liftoff, 7, abs_tol=0.5)


def test_flight_logged_by_the_firmware():
    frames = flight()
    contents = decode_dump(sd(frames))
    assert len(contents.sessions) == 1
    assert len(contents.sessions[0].records) == len(frames) // 16 * 16
    apogee = find_apogee(*baro_series(contents.sessions[0]))
    assert math.isclose(apogee.agl, 300, abs_tol=1)


def test_leftovers_of_an_older_boot_are_split():
    # La placa tardó más en arrancar en el vuelo que en la prueba anterior: al pasar a los restos
    # de la prueba el tiempo retrocede
    old = flight(duration_s=120, apogee_m=900)
    new = flight(duration_s=60, apogee_m=300, t0_ms=4000)
    contents = decode_dump(sd(old, new))
    assert len(contents.sessions) == 2
    first = contents.sessions[0]
    assert first.t_end < 64000
    assert math.isclose(find_apogee(*baro_series(first)).agl, 300, abs_tol=1)


def test_seq_going_back_is_another_boot():
    # Mismos tiempos que la sesión anterior, pero los seq de la nueva van por delante
    old = flight(duration_s=60, apogee_m=50)
    new = [make_frame(int.from_bytes(f[1:3], "little"), f[12:12 + f[5]], int.from_bytes(f[3:5], "little") + 5000,
                      int.from_bytes(f[7:11], "little")) for f in old[:320]]
    assert len(decode_dump(sd(old, new)).sessions) == 2


def test_leftovers_that_fit_in_time_are_at_least_flagged():
    # Si los restos siguen en tiempo y seq no se pueden separar, pero el salto de tiempo se avisa
    old = flight(duration_s=120, apogee_m=50, t0_ms=3000)
    new = flight(duration_s=60, apogee_m=300)
    contents = decode_dump(sd(old, new))
    assert len(contents.sessions) == 1
    assert len(contents.sessions[0].gaps) == 1
    assert 3000 <= contents.sessions[0].gaps[0][1] <= 3020


def test_duplicates_are_dropped():
    frames = flight(duration_s=1)
    contents = decode_dump(b"".join(frames[:8] + frames[7:]))   # La trama 7, escrita dos veces
    assert len(contents.sessions) == 1
    assert contents.sessions[0].duplicates == 1
    assert len(contents.sessions[0].records) == len(frames)
