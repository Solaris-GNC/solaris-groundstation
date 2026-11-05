import struct

import pytest

import telemetry.router as router_module
from telemetry.decoder import Decoder
from telemetry.models import APID_IMU, K_SPP_PKT_VERSION
from telemetry.state import TelemetryState


class NullLogger:
    """Sustituye al logger de CSV: el router no tiene que escribir en logs/ durante los tests."""

    def __getattr__(self, name):
        return lambda *args, **kwargs: None


@pytest.fixture
def router(monkeypatch):
    state = TelemetryState()
    monkeypatch.setattr(router_module, "global_state", state)
    monkeypatch.setattr(router_module, "telemetry_logger", NullLogger())
    r = router_module.TelemetryRouter()
    r.state = state
    return r


def imu(seq: int, t_ms: int, crc: int = 1):
    payload = struct.pack("<11f", 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 0)
    frame = (struct.pack("<BHHHIB", K_SPP_PKT_VERSION, APID_IMU, seq, len(payload), t_ms, 0)
             + payload + struct.pack("<H", crc))
    return Decoder().frame_to_packet(frame)


def messages(r):
    return [log.message for log in r.state.logs]


def test_decimated_seq_is_not_counted_as_lost(router):
    # Como en los logs reales: el seq salta de 30 en 30 cada 130 ms sin que falte nada
    for k in range(20):
        assert router.route_packet(imu(seq=30 * k, t_ms=130 * k))
    assert router.state.packets_lost == 0
    assert messages(router) == []


def test_gaps_in_time_are_counted_as_lost_without_flooding_events(router):
    t = 0
    for gap in [130, 130, 260, 130, 390, 130]:   # Faltan 1 y 2 paquetes
        t += gap
        router.route_packet(imu(seq=t // 130 * 30, t_ms=t))
    assert router.state.packets_lost == 3
    assert messages(router) == []                # Pérdidas sueltas: solo el contador


def test_long_silence_is_reported(router):
    router.route_packet(imu(0, 0))
    router.route_packet(imu(30, 130))
    router.route_packet(imu(900, 3130))
    assert any("3.0 s sin paquetes" in m for m in messages(router))


def test_exact_duplicate_is_dropped(router):
    assert router.route_packet(imu(0, 100))
    assert not router.route_packet(imu(0, 100))  # Mismo seq, timestamp y CRC
    assert router.state.packets_lost == 0


def test_board_reboot_is_reported_and_not_counted_as_lost(router):
    router.route_packet(imu(3000, 50_000))
    router.route_packet(imu(3030, 50_130))
    router.route_packet(imu(0, 200))             # El tiempo vuelve a empezar
    router.route_packet(imu(30, 330))
    assert any("reinicio" in m for m in messages(router))
    assert router.state.packets_lost == 0
