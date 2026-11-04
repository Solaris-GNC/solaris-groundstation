import math
import struct
from backend.comms.crc import crc16_ccitt
from backend.telemetry.models import APID_BARO, APID_IMU

PAYLOAD_SIZE = 50   # el payload SIEMPRE ocupa 50 bytes (con padding)


def build_frame(apid: int, seq: int, payload: bytes,
                timestamp_ms: int = 0, drop_counter: int = 0) -> bytes:
    header = (
        (1).to_bytes(1, "little")                 # version
        + apid.to_bytes(2, "little")              # apid
        + seq.to_bytes(2, "little")               # seq
        + len(payload).to_bytes(2, "little")      # payload_len (bytes ÚTILES)
        + timestamp_ms.to_bytes(4, "little")      # timestamp
        + drop_counter.to_bytes(1, "little")      # drop_counter
    )
    payload_padded = payload.ljust(PAYLOAD_SIZE, b"\x00")   # rellenar a 50 bytes
    data = header + payload_padded
    crc = crc16_ccitt(data).to_bytes(2, "little")
    return data + crc                                        # 12 + 50 + 2 = 64 bytes


def baro_payload(altitude, pressure, temperature) -> bytes:
    return struct.pack("<3f", altitude, pressure, temperature)


def imu1_payload(ax, ay, az, gx, gy, gz, mx, my, mz, qw, qx, qy) -> bytes:
    # 12 floats: accel xyz, gyro xyz, mag xyz, quat_w, quat_x, quat_y
    return struct.pack("<12f", ax, ay, az, gx, gy, gz, mx, my, mz, qw, qx, qy)


def imu2_payload(qz, accuracy) -> bytes:
    # 4 floats: quat_z, accuracy, y 2 reservados (0.0)
    return struct.pack("<4f", qz, accuracy, 0.0, 0.0)


# def make_test_stream() -> bytes:
#     frames = [
#         build_frame(APID_BARO, seq=1, payload=baro_payload(704.4, 931.4, 27.43)),
#         build_frame(APID_IMU, seq=2, payload=imu1_payload(
#             0.1, 0.2, 9.81,     # accel
#             0.01, 0.02, 0.03,   # gyro
#             10.0, 20.0, 30.0,   # mag
#             1.0, 0.0, 0.0,      # quat_w, quat_x, quat_y
#         )),
#         build_frame(APID_IMU, seq=3, payload=imu2_payload(0.0, 286.0)),
#     ]
#     return b"".join(frames)


# El seq es GLOBAL: un único contador que sube 1 por CADA frame emitido,
# sin importar el sensor ni su frecuencia (como hace el firmware real).
_seq = 0

def _next_seq() -> int:
    global _seq
    s = _seq
    _seq = (_seq + 1) % 65536
    return s


def make_imu_frames(t: float) -> bytes:
    """Una lectura IMU = fragmento 1 + fragmento 2 (cada uno con su seq global)."""
    ts = int(t * 1000)
    imu1 = build_frame(APID_IMU, _next_seq(), imu1_payload(
        math.sin(t), math.cos(t), 9.81,              # accel
        0.1 * math.sin(t), 0.1 * math.cos(t), 0.05,  # gyro
        20 * math.sin(t), 20 * math.cos(t), 40.0,    # mag
        math.cos(t / 2), math.sin(t / 2), math.sin(t / 3),  # quat_w, quat_x, quat_y
    ), timestamp_ms=ts)
    imu2 = build_frame(APID_IMU, _next_seq(), imu2_payload(
        math.sin(t / 4),   # quat_z
        95.0,              # accuracy
    ), timestamp_ms=ts)
    return imu1 + imu2


def make_baro_frame(t: float) -> bytes:
    ts = int(t * 1000)
    return build_frame(APID_BARO, _next_seq(), baro_payload(
        1000 + 200 * math.sin(t),        # altitude (m)
        931 + 5 * math.sin(t),           # pressure (hPa)
        27 + 2 * math.sin(t * 0.5),      # temperature (ºC)
    ), timestamp_ms=ts)