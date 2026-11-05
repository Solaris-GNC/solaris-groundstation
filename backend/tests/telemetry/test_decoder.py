import struct

import pytest

from telemetry.decoder import Decoder
from telemetry.models import (
    APID_BARO, APID_IMU, BAROPacket, FSMPacket, IMUPacket, K_SPP_PKT_VERSION, KPID_FSM,
)


def make_frame(apid: int, payload: bytes, seq: int = 1, timestamp_ms: int = 255,
               drop_counter: int = 99, crc: int = 256) -> bytes:
    """Trama SPP: versión, APID, seq, payload_len, timestamp, drop counter, payload, CRC."""
    return (struct.pack("<BHHHIB", K_SPP_PKT_VERSION, apid, seq, len(payload), timestamp_ms, drop_counter)
            + payload + struct.pack("<H", crc))


def test_headers_are_decoded():
    packet = Decoder().frame_to_packet(make_frame(APID_BARO, struct.pack("<3f", 0, 0, 0)))
    assert packet.primary_header.version == K_SPP_PKT_VERSION
    assert packet.primary_header.apid == APID_BARO
    assert packet.primary_header.seq == 1
    assert packet.primary_header.payload_len == 12
    assert packet.secondary_header.timestamp_ms == 255
    assert packet.secondary_header.drop_counter == 99
    assert packet.crc16 == 256


def test_baro_payload():
    packet = Decoder().frame_to_packet(make_frame(APID_BARO, struct.pack("<3f", 704.5, 93140.0, 27.25)))
    assert isinstance(packet.payload, BAROPacket)
    assert (packet.payload.altitude, packet.payload.pressure, packet.payload.temperature) == (704.5, 93140.0, 27.25)


def test_imu_payload():
    values = [0.5, -1.0, 1.0, 10.0, -20.0, 30.0, 1.0, 0.0, 0.0, 0.0, 3.0]
    packet = Decoder().frame_to_packet(make_frame(APID_IMU, struct.pack("<11f", *values)))
    p = packet.payload
    assert isinstance(p, IMUPacket)
    assert [p.accel_x, p.accel_y, p.accel_z, p.gyro_x, p.gyro_y, p.gyro_z,
            p.quat_w, p.quat_x, p.quat_y, p.quat_z, p.accuracy] == values


def test_fsm_payload_lists_failed_bits():
    # Bit 7 de FsmErrors_t (icmInitError) y bit 0 de CommonBitErrors_t (coreInitError)
    packet = Decoder().frame_to_packet(make_frame(KPID_FSM, struct.pack("<2H", 1 << 7, 1), seq=0))
    assert isinstance(packet.payload, FSMPacket)
    assert packet.payload.failed == ["icmInitError", "coreInitError"]


def test_unknown_payload_length_is_rejected():
    with pytest.raises(ValueError):
        Decoder().frame_to_packet(make_frame(APID_IMU, bytes(20)))
