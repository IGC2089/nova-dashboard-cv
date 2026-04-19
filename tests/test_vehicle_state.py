import threading
from vehicle_state import VehicleState


def test_default_values():
    s = VehicleState()
    assert s.rpm == 0.0
    assert s.afr == 14.7
    assert s.gps_fix is False
    assert s.trip_km == 0.0


def test_has_lock():
    s = VehicleState()
    assert isinstance(s.lock, type(threading.Lock()))


def test_snapshot_copies_values():
    s = VehicleState()
    s.rpm = 3400.0
    s.clt_c = 92.0
    snap = s.snapshot()
    assert snap.rpm == 3400.0
    assert snap.clt_c == 92.0


def test_snapshot_is_independent():
    s = VehicleState()
    s.rpm = 3400.0
    snap = s.snapshot()
    s.rpm = 5000.0
    assert snap.rpm == 3400.0


def test_snapshot_has_no_lock():
    s = VehicleState()
    snap = s.snapshot()
    assert snap.lock is None
