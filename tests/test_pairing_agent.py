import threading
import time
import pytest
from unittest.mock import MagicMock, patch
from vehicle_state import VehicleState


def _import_agent():
    """Import PairingAgent, skipping if dbus unavailable."""
    try:
        from pairing_agent import PairingAgent
        return PairingAgent
    except ImportError:
        pytest.skip("dbus not available")


def test_request_confirmation_accept():
    PairingAgent = _import_agent()
    state = VehicleState()
    agent = PairingAgent.__new__(PairingAgent)
    agent._state = state

    # Simulate user tapping Accept after 0.05s
    def _user_accepts():
        time.sleep(0.05)
        state.bt_pairing_accepted = True
        state.bt_pairing_response.set()

    threading.Thread(target=_user_accepts, daemon=True).start()

    # Should return without raising
    agent._handle_confirmation('iPhone de Carlos', 482918)
    assert state.bt_pairing_pending is False


def test_request_confirmation_reject():
    PairingAgent = _import_agent()
    try:
        import dbus
    except ImportError:
        pytest.skip("dbus not available")
    state = VehicleState()
    agent = PairingAgent.__new__(PairingAgent)
    agent._state = state

    def _user_rejects():
        time.sleep(0.05)
        state.bt_pairing_accepted = False
        state.bt_pairing_response.set()

    threading.Thread(target=_user_rejects, daemon=True).start()

    with pytest.raises(dbus.DBusException) as exc:
        agent._handle_confirmation('Android Device', 111222)
    assert 'Rejected' in str(exc.value)
    assert state.bt_pairing_pending is False


def test_request_confirmation_timeout():
    PairingAgent = _import_agent()
    try:
        import dbus
    except ImportError:
        pytest.skip("dbus not available")
    state = VehicleState()
    agent = PairingAgent.__new__(PairingAgent)
    agent._state = state
    agent._timeout = 0.1  # override timeout for test speed

    with pytest.raises(dbus.DBusException) as exc:
        agent._handle_confirmation('Slow Device', 999999)
    assert 'Canceled' in str(exc.value)
    assert state.bt_pairing_pending is False
