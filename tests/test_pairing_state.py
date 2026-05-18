import threading
import pytest
from vehicle_state import VehicleState


def test_pairing_fields_default():
    s = VehicleState()
    assert s.bt_pairing_pending is False
    assert s.bt_pairing_device == ''
    assert s.bt_pairing_passkey == 0
    assert s.bt_pairing_accepted is False
    assert isinstance(s.bt_pairing_response, threading.Event)


def test_snapshot_copies_pairing_fields():
    s = VehicleState()
    s.bt_pairing_pending = True
    s.bt_pairing_device = 'iPhone de Carlos'
    s.bt_pairing_passkey = 482918
    s.bt_pairing_accepted = True
    snap = s.snapshot()
    assert snap.bt_pairing_pending is True
    assert snap.bt_pairing_device == 'iPhone de Carlos'
    assert snap.bt_pairing_passkey == 482918
    assert snap.bt_pairing_accepted is True


def test_snapshot_excludes_event():
    s = VehicleState()
    snap = s.snapshot()
    # snapshot lock is None; bt_pairing_response should also be None
    assert snap.bt_pairing_response is None
