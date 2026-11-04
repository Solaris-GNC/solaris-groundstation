import pytest
import telemetry.decoder as decoder
from telemetry.models import (K_SPP_PKT_VERSION, APID_BARO, APID_IMU,
TelemetryPacket, SPPPrimaryHeader, SPPSecondaryHeader)


@pytest.fixture
def correct_frame():
    version = [K_SPP_PKT_VERSION]
    apid = [APID_IMU, 0]
    seq = [1, 0]
    payload_len = [48, 0]
    timestamp = [255, 0, 0, 0]
    drop_counter = [99]
    payload = [0] * 48
    payload[0] = 255
    crc = [1, 1]                    # 256

    frame = bytes(version + apid + seq + payload_len + timestamp +
                  drop_counter + payload + crc)
    return frame


def test_everything_goes_fine(correct_frame):

    packet = decoder.Decoder()
    packet = decoder.Decoder.frame_to_packet(correct_frame)

    assert packet.primary_header.version == K_SPP_PKT_VERSION and isinstance(packet.primary_header.version, int)
    assert packet.primary_header.apid == APID_IMU and isinstance(packet.primary_header.apid, int)
    assert packet.primary_header.seq == 1 and isinstance(packet.primary_header.seq, int)
    assert packet.primary_header.payload_len == 48 and isinstance(packet.primary_header.payload_len, int)

    assert packet.secondary_header.timestamp_ms == 255 and isinstance(packet.secondary_header.timestamp_ms, int)
    assert packet.secondary_header.drop_counter == 99 and isinstance(packet.secondary_header.drop_counter, int)

    assert packet.payload == 255 and isinstance(packet.payload, int)
    assert packet.crc16 == 256 and isinstance(packet.crc16, int)
















@pytest.fixture
def too_big_baro_payload():

    return




def test_baro_payload_decoder_overflow():
    return


