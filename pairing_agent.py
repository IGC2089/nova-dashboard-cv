"""BlueZ D-Bus pairing agent.

Registers as org.bluez.Agent1. When a phone initiates SSP pairing,
RequestConfirmation is called; we write to VehicleState and block
until the dashboard user responds (or 30s timeout).
"""
from __future__ import annotations
import logging
import threading

log = logging.getLogger(__name__)

AGENT_PATH = '/nova/agent'
CAPABILITY = 'DisplayYesNo'
DEFAULT_TIMEOUT = 30.0


class PairingAgent(threading.Thread):
    def __init__(self, state):
        super().__init__(daemon=True, name='PairingAgent')
        self._state = state
        self._loop = None
        self._timeout = DEFAULT_TIMEOUT

    # ------------------------------------------------------------------ thread

    def run(self) -> None:
        try:
            import dbus
            import dbus.service
            import dbus.mainloop.glib
            from gi.repository import GLib
        except ImportError:
            log.warning("dbus/gi not available — pairing agent disabled")
            return

        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        bus = dbus.SystemBus()

        # Attach as D-Bus service object
        self._dbus_obj = _AgentObject(bus, AGENT_PATH, self._state, self._timeout)

        try:
            manager = dbus.Interface(
                bus.get_object('org.bluez', '/org/bluez'),
                'org.bluez.AgentManager1',
            )
            manager.RegisterAgent(AGENT_PATH, CAPABILITY)
            manager.RequestDefaultAgent(AGENT_PATH)
            log.info("Pairing agent registered (capability=%s)", CAPABILITY)
        except dbus.DBusException as exc:
            log.warning("Failed to register pairing agent: %s", exc)
            return

        try:
            adapter_props = dbus.Interface(
                bus.get_object('org.bluez', '/org/bluez/hci0'),
                'org.freedesktop.DBus.Properties',
            )
            adapter_props.Set('org.bluez.Adapter1', 'Pairable', dbus.Boolean(True))
            log.info("Adapter set to pairable")
        except dbus.DBusException as exc:
            log.warning("Could not set adapter pairable: %s", exc)

        self._loop = GLib.MainLoop()
        self._loop.run()

    def stop(self) -> None:
        if self._loop is not None:
            self._loop.quit()

    # ------------------------------------------------------------------ internal (used by tests)

    def _handle_confirmation(self, device_name: str, passkey: int) -> None:
        """Set state, block until response or timeout, raise on reject/timeout."""
        timeout = getattr(self, '_timeout', DEFAULT_TIMEOUT)
        with self._state.lock:
            self._state.bt_pairing_device = device_name
            self._state.bt_pairing_passkey = passkey
            self._state.bt_pairing_pending = True
            self._state.bt_pairing_response.clear()

        responded = self._state.bt_pairing_response.wait(timeout=timeout)

        with self._state.lock:
            self._state.bt_pairing_pending = False
            accepted = self._state.bt_pairing_accepted

        if not responded:
            import dbus
            raise dbus.DBusException(
                'org.bluez.Error.Canceled',
                'Pairing request timed out',
            )
        if not accepted:
            import dbus
            raise dbus.DBusException(
                'org.bluez.Error.Rejected',
                'User rejected pairing',
            )


class _AgentObject:
    """D-Bus service object — inherits dbus.service.Object at runtime to avoid
    import errors on systems without dbus."""

    def __new__(cls, bus, path, state, timeout):
        import dbus.service

        class _Obj(dbus.service.Object):
            def __init__(self, bus, path, state, timeout):
                super().__init__(bus, path)
                self._state = state
                self._timeout = timeout
                self._agent = PairingAgent.__new__(PairingAgent)
                self._agent._state = state
                self._agent._timeout = timeout

            @dbus.service.method('org.bluez.Agent1',
                                 in_signature='ou', out_signature='')
            def RequestConfirmation(self, device, passkey):
                bus = dbus.SystemBus()
                try:
                    props = dbus.Interface(
                        bus.get_object('org.bluez', device),
                        'org.freedesktop.DBus.Properties',
                    )
                    name = str(props.Get('org.bluez.Device1', 'Alias'))
                except Exception:
                    name = str(device)
                log.info("Pairing request from %r passkey=%s", name, passkey)
                self._agent._handle_confirmation(name, int(passkey))

            @dbus.service.method('org.bluez.Agent1',
                                 in_signature='', out_signature='')
            def Cancel(self):
                log.info("Pairing cancelled by BlueZ")
                with self._state.lock:
                    self._state.bt_pairing_pending = False

            @dbus.service.method('org.bluez.Agent1',
                                 in_signature='o', out_signature='s')
            def RequestPinCode(self, device):
                import dbus
                raise dbus.DBusException('org.bluez.Error.Rejected')

            @dbus.service.method('org.bluez.Agent1',
                                 in_signature='o', out_signature='u')
            def RequestPasskey(self, device):
                import dbus
                raise dbus.DBusException('org.bluez.Error.Rejected')

        return _Obj(bus, path, state, timeout)
