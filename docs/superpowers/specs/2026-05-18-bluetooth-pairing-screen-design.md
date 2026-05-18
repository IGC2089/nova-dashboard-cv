# Bluetooth Pairing Screen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Show a modal overlay on the dashboard when a phone initiates Bluetooth pairing, displaying the device name and 6-digit passkey with Accept / Reject buttons and a 30-second auto-dismiss countdown.

**Architecture:** A new `PairingAgent` D-Bus object registers as `org.bluez.Agent1` and runs in a daemon thread with its own GLib main loop. When BlueZ calls `RequestConfirmation`, the agent writes the request to `VehicleState` and blocks on a `threading.Event`. The dashboard render loop draws the overlay; the main event loop handles touch; the agent unblocks and returns the decision to BlueZ.

**Tech Stack:** Python 3, dbus-python (already in use), GLib main loop (`dbus.mainloop.glib`), pygame + OpenCV (existing render pipeline).

---

## Components

| File | Change |
|------|--------|
| `pairing_agent.py` | New — `PairingAgent` D-Bus agent thread |
| `vehicle_state.py` | Add 5 pairing fields |
| `dashboard_ui.py` | Draw modal overlay when pairing pending |
| `main.py` | Start agent thread; handle Accept/Reject touch |

---

## Data Flow

1. Phone initiates pairing → BlueZ calls `PairingAgent.RequestConfirmation(device_path, passkey)`
2. Agent resolves `Device1.Alias` for the friendly device name
3. Agent writes `bt_pairing_device`, `bt_pairing_passkey`, sets `bt_pairing_pending = True`, resets `bt_pairing_response` event
4. Agent blocks: `bt_pairing_response.wait(timeout=30)`
5. Dashboard render loop sees `bt_pairing_pending=True`, draws overlay on top of current page
6. User taps Accept or Reject → `main.py` sets `bt_pairing_accepted` and calls `bt_pairing_response.set()`
7. Agent unblocks and acts:
   - Accepted → returns `None` (BlueZ completes pairing)
   - Rejected → raises `dbus.DBusException('org.bluez.Error.Rejected')`
   - Timeout (30s) → raises `dbus.DBusException('org.bluez.Error.Canceled')` (phone can retry)
8. Agent clears `bt_pairing_pending = False`

---

## VehicleState additions

```python
# in vehicle_state.py __init__
import threading
self.bt_pairing_pending: bool = False
self.bt_pairing_device: str = ''
self.bt_pairing_passkey: int = 0
self.bt_pairing_accepted: bool = False
self.bt_pairing_response: threading.Event = threading.Event()
```

These fields are written by `PairingAgent` (under `state.lock` for `pending/device/passkey`) and read by the render loop via `snapshot()`. `bt_pairing_response` and `bt_pairing_accepted` are set by `main.py` touch handling and do not need the lock.

`VehicleState.snapshot()` must copy the 4 scalar pairing fields (the Event is not copied).

---

## pairing_agent.py

```python
import dbus
import dbus.service
import dbus.mainloop.glib
from gi.repository import GLib
import threading
import logging

AGENT_PATH = '/nova/agent'
CAPABILITY = 'DisplayYesNo'

class PairingAgent(dbus.service.Object, threading.Thread):
    def __init__(self, state):
        threading.Thread.__init__(self, daemon=True, name='PairingAgent')
        self._state = state
        self._loop = None

    def run(self):
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        bus = dbus.SystemBus()
        dbus.service.Object.__init__(self, bus, AGENT_PATH)
        manager = dbus.Interface(
            bus.get_object('org.bluez', '/org/bluez'),
            'org.bluez.AgentManager1')
        manager.RegisterAgent(AGENT_PATH, CAPABILITY)
        manager.RequestDefaultAgent(AGENT_PATH)
        # Make device pairable
        adapter = dbus.Interface(
            bus.get_object('org.bluez', '/org/bluez/hci0'),
            'org.freedesktop.DBus.Properties')
        adapter.Set('org.bluez.Adapter1', 'Pairable', dbus.Boolean(True))
        self._loop = GLib.MainLoop()
        self._loop.run()

    def stop(self):
        if self._loop:
            self._loop.quit()

    @dbus.service.method('org.bluez.Agent1',
                         in_signature='ou', out_signature='')
    def RequestConfirmation(self, device, passkey):
        bus = dbus.SystemBus()
        props = dbus.Interface(
            bus.get_object('org.bluez', device),
            'org.freedesktop.DBus.Properties')
        name = str(props.Get('org.bluez.Device1', 'Alias'))

        with self._state.lock:
            self._state.bt_pairing_device = name
            self._state.bt_pairing_passkey = int(passkey)
            self._state.bt_pairing_pending = True
            self._state.bt_pairing_response.clear()

        responded = self._state.bt_pairing_response.wait(timeout=30)

        with self._state.lock:
            self._state.bt_pairing_pending = False
            accepted = self._state.bt_pairing_accepted

        if not responded:
            raise dbus.DBusException('org.bluez.Error.Canceled')
        if not accepted:
            raise dbus.DBusException('org.bluez.Error.Rejected')

    @dbus.service.method('org.bluez.Agent1', in_signature='', out_signature='')
    def Cancel(self):
        with self._state.lock:
            self._state.bt_pairing_pending = False

    @dbus.service.method('org.bluez.Agent1', in_signature='o', out_signature='s')
    def RequestPinCode(self, device):
        raise dbus.DBusException('org.bluez.Error.Rejected')

    @dbus.service.method('org.bluez.Agent1', in_signature='o', out_signature='u')
    def RequestPasskey(self, device):
        raise dbus.DBusException('org.bluez.Error.Rejected')
```

---

## dashboard_ui.py — overlay

In `GaugeRenderer.render_frame()`, after the normal page is drawn, check `snap.bt_pairing_pending` and draw the overlay using OpenCV:

```python
if snap.bt_pairing_pending:
    self._draw_pairing_overlay(canvas, snap)
```

`_draw_pairing_overlay(canvas, snap)`:
- Semi-transparent black scrim: `canvas` blended with black at 75% opacity
- Centered card (360×200 px) with amber border `#e8a400`
- Title: "BLUETOOTH PAIRING"
- Device name: `snap.bt_pairing_device`
- Passkey: `f"{snap.bt_pairing_passkey:06d}"` with wide letter-spacing
- ACCEPT button rect: centered-left
- REJECT button rect: centered-right
- Countdown: seconds remaining (computed from when request was received)

Countdown tracking: store `_pairing_start: float` in the renderer, set to `time.monotonic()` when `pending` first becomes True, reset when it becomes False.

---

## main.py — touch handling

Accept/Reject button regions (absolute pixel coordinates on 800×480):
- ACCEPT: `(220, 350, 360, 400)` — (x1, y1, x2, y2)
- REJECT: `(440, 350, 580, 400)`

In the `MOUSEBUTTONUP` handler, before the swipe logic:

```python
if snap.bt_pairing_pending and abs(dx) < SWIPE_THRESHOLD:
    tx, ty = event.pos
    if 220 <= tx <= 360 and 350 <= ty <= 400:
        state.bt_pairing_accepted = True
        state.bt_pairing_response.set()
    elif 440 <= tx <= 580 and 350 <= ty <= 400:
        state.bt_pairing_accepted = False
        state.bt_pairing_response.set()
```

Also start the agent thread in `main()`:

```python
pairing_agent = PairingAgent(state)
pairing_agent.start()
```

And stop it in `finally`:

```python
pairing_agent.stop()
pairing_agent.join(timeout=2.0)
```

---

## BlueZ prerequisites

The system must have `python3-dbus` and `python3-gi` installed (for GLib). On Debian Trixie:

```bash
sudo apt install python3-dbus python3-gi
```

No changes to `/etc/bluetooth/main.conf` are required — the agent sets `Pairable=True` programmatically.

---

## Error handling

- If `dbus` or `gi` not available: log warning and skip agent startup (graceful degradation, same pattern as `bluetooth_handler.py`)
- If `/org/bluez/hci0` not found (no BT adapter): catch `dbus.DBusException`, log and exit agent thread
- If `Device1.Alias` lookup fails: fall back to device path as display name
