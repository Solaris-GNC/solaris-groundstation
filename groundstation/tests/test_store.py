import math

import pytest

from groundstation.store import Store, attitude

QUAT_UP = (1.0, 0.0, 0.0, 0.0)


def quat_mul(a, b):
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return (w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2, w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
            w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2, w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2)


def axis_angle(axis, deg):
    h = math.radians(deg) / 2
    return (math.cos(h), *(math.sin(h) * a for a in axis))


def add_imu(store, ts, quat=QUAT_UP, accel=(0.0, 0.0, 1.0)):
    store.add_imu(ts, accel, (0.0, 0.0, 0.0), quat, now=ts / 1000)


# ==================================================================
# Actitud

def test_attitude_upright_is_zero():
    assert attitude(*QUAT_UP) == pytest.approx((0, 0, 0))


@pytest.mark.parametrize("tilt", [30, 80])
@pytest.mark.parametrize("spin", [0, 90, 180, 270])
def test_attitude_ignores_spin_about_rocket_axis(tilt, spin):
    # Inclinado `tilt` grados y girado `spin` sobre su propio eje: la inclinación no debe cambiar
    # (con roll/pitch de Euler pasaba de un ángulo al otro)
    q = quat_mul(axis_angle((1, 0, 0), tilt), axis_angle((0, 0, 1), spin))
    t, lean_x, lean_y = attitude(*q)
    assert t == pytest.approx(tilt)
    assert lean_x == pytest.approx(0, abs=1e-9)
    assert lean_y == pytest.approx(-tilt)


# ==================================================================
# Store

def test_duplicate_samples_are_ignored():
    s = Store()
    add_imu(s, 1000)
    add_imu(s, 1000)
    assert len(s.imu) == 1


def test_backwards_timestamp_is_a_reboot():
    s = Store()
    add_imu(s, 5000, accel=(0, 0, 3.0))
    s.add_baro(5000, 100.0, 90000.0, 20.0, now=5)
    s.set_fsm(2000, 0, 0, [])
    add_imu(s, 1000)
    assert s.reboots == 1
    assert len(s.imu) == 1 and len(s.baro) == 0
    assert s.max_g == pytest.approx(1.0)   # El máximo del vuelo anterior no se arrastra
    assert s.apogee is None
    assert s.fsm is not None               # Los init bits del arranque se conservan


def test_vertical_speed_and_apogee():
    s = Store()
    s.add_baro(0, 0.0, 1, 1, now=0)
    s.add_baro(1000, 10.0, 1, 1, now=1)
    s.add_baro(2000, 30.0, 1, 1, now=2)
    s.add_baro(3000, 25.0, 1, 1, now=3)
    vz = s.baro.cols["vz"]
    assert math.isnan(vz[0])
    assert vz[1] == pytest.approx(10)
    assert vz[2] == pytest.approx(15)      # EMA: 10 + 0.5 * (20 - 10)
    assert s.apogee == (2.0, 30.0)


def test_no_vertical_speed_across_long_gaps():
    s = Store()
    s.add_baro(0, 0.0, 1, 1, now=0)
    s.add_baro(60_000, 100.0, 1, 1, now=60)
    assert math.isnan(s.baro.cols["vz"][1])


def test_stale_and_rate():
    s = Store()
    assert s.is_stale(now=0)
    for i in range(10):
        add_imu(s, i * 100)
    assert not s.is_stale(now=1.0)
    assert s.is_stale(now=10.0)
    assert s.sample_rate(now=1.0) == pytest.approx(10 / 5)


def test_window_start():
    s = Store()
    for i in range(10):
        add_imu(s, i * 1000)
    assert s.imu.window_start(None) == 0
    assert s.imu.window_start(4.5) == 5
