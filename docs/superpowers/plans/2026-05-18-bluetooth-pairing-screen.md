# Bluetooth Pairing Screen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show a modal overlay on the dashboard when a phone initiates Bluetooth pairing, displaying the device name and 6-digit passkey with Accept / Reject buttons and a 30-second auto-dismiss countdown.

**Architecture:** A new `PairingAgent` class registers as `org.bluez.Agent1` on the D-Bus system bus and runs a GLib main loop in a daemon thread. When BlueZ calls `RequestConfirmation`, the agent writes the request to `VehicleState` and blocks on a `threading.Event`. The dashboard render loop draws a modal overlay; the pygame event loop handles touch on Accept/Reject; the agent unblocks and returns the decision to BlueZ.

**Tech Stack:** Python 3, dbus-python, gi.repository.GLib, OpenCV + NumPy (existing render pipeline), pytest.

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `pairing_agent.py` | Create | D-Bus Agent1 thread — receives pairing requests, manages state |
| `vehicle_state.py` | Modify | Add 5 pairing fields; update `snapshot()` |
| `dashboard_ui.py` | Modify | `_draw_pairing_overlay()` + call in `render_frame()` |
| `main.py` | Modify | Start/stop agent thread; handle Accept/Reject touch |
| `tests/test_pairing_state.py` | Create | Unit tests for state fields and snapshot |
| `tests/test_pairing_agent.py` | Create | Unit tests for agent logic (D-Bus mocked) |

---

## Task 1: VehicleState pairing fields

**Files:**
- Modify: `vehicle_state.py`
- Create: `tests/test_pairing_state.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_pairing_state.py`:

```python
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
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd ~/nova-dashboard-cv
python -m pytest tests/test_pairing_state.py -v
```

Expected: `ImportError` or `AttributeError` — fields don't exist yet.

- [ ] **Step 3: Add pairing fields to VehicleState**

In `vehicle_state.py`, after the `bt_album` field and before the `lock` field:

```python
    # Bluetooth pairing
    bt_pairing_pending: bool = False
    bt_pairing_device: str = ''
    bt_pairing_passkey: int = 0
    bt_pairing_accepted: bool = False
    bt_pairing_response: Optional[threading.Event] = field(
        default_factory=threading.Event, repr=False, compare=False
    )
```

- [ ] **Step 4: Update snapshot() to copy pairing fields**

In the `snapshot()` return statement, add after `bt_album=self.bt_album,`:

```python
                bt_pairing_pending=self.bt_pairing_pending,
                bt_pairing_device=self.bt_pairing_device,
                bt_pairing_passkey=self.bt_pairing_passkey,
                bt_pairing_accepted=self.bt_pairing_accepted,
                bt_pairing_response=None,
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
python -m pytest tests/test_pairing_state.py -v
```

Expected: 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add vehicle_state.py tests/test_pairing_state.py
git commit -m "feat: add Bluetooth pairing fields to VehicleState"
```

---

## Task 2: PairingAgent D-Bus thread

**Files:**
- Create: `pairing_agent.py`
- Create: `tests/test_pairing_agent.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_pairing_agent.py`:

```python
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
    import dbus
    PairingAgent = _import_agent()
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
    import dbus
    PairingAgent = _import_agent()
    state = VehicleState()
    agent = PairingAgent.__new__(PairingAgent)
    agent._state = state
    agent._timeout = 0.1  # override timeout for test speed

    with pytest.raises(dbus.DBusException) as exc:
        agent._handle_confirmation('Slow Device', 999999)
    assert 'Canceled' in str(exc.value)
    assert state.bt_pairing_pending is False
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
python -m pytest tests/test_pairing_agent.py -v
```

Expected: `ImportError: No module named 'pairing_agent'`

- [ ] **Step 3: Create pairing_agent.py**

Create `pairing_agent.py`:

```python
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
        import dbus
        with self._state.lock:
            self._state.bt_pairing_device = device_name
            self._state.bt_pairing_passkey = passkey
            self._state.bt_pairing_pending = True
            self._state.bt_pairing_response.clear()

        responded = self._state.bt_pairing_response.wait(timeout=self._timeout)

        with self._state.lock:
            self._state.bt_pairing_pending = False
            accepted = self._state.bt_pairing_accepted

        if not responded:
            raise dbus.DBusException(
                'org.bluez.Error.Canceled',
                'Pairing request timed out',
            )
        if not accepted:
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
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
python -m pytest tests/test_pairing_agent.py -v
```

Expected: 3 tests PASS (or SKIP if dbus unavailable on dev machine — that's fine).

- [ ] **Step 5: Commit**

```bash
git add pairing_agent.py tests/test_pairing_agent.py
git commit -m "feat: add BlueZ D-Bus pairing agent"
```

---

## Task 3: Pairing overlay in dashboard_ui.py

**Files:**
- Modify: `dashboard_ui.py`

The canvas is BGR, shape `(480, 800, 3)`. All drawing uses OpenCV.

Card geometry (centered on 800×480):
- Card: x1=210, y1=130, x2=590, y2=350  (380×220 px)
- ACCEPT button: x1=230, y1=285, x2=390, y2=335
- REJECT button: x1=410, y1=285, x2=570, y2=335

These constants are also used in Task 4 (main.py touch handling).

- [ ] **Step 1: Add `_draw_pairing_overlay` to GaugeRenderer**

Add these two constants at the top of `dashboard_ui.py`, after the imports:

```python
# Pairing overlay button hit regions (x1, y1, x2, y2) — used by main.py too
PAIRING_ACCEPT_RECT = (230, 285, 390, 335)
PAIRING_REJECT_RECT = (410, 285, 570, 335)
```

Then add the method to `GaugeRenderer` (before `render_frame`):

```python
    def _draw_pairing_overlay(self, canvas: np.ndarray, state) -> None:
        """Draw Bluetooth pairing modal on top of current canvas."""
        # Semi-transparent scrim
        scrim = np.zeros_like(canvas)
        cv2.addWeighted(canvas, 0.30, scrim, 0.70, 0, canvas)

        # Card background and border
        AMBER = (0, 164, 232)   # BGR for #e8a400
        DARK  = (22, 22, 22)
        cv2.rectangle(canvas, (210, 130), (590, 350), DARK, -1)
        cv2.rectangle(canvas, (210, 130), (590, 350), AMBER, 2)

        # Title
        cv2.putText(canvas, 'BLUETOOTH PAIRING',
                    (260, 165), cv2.FONT_HERSHEY_SIMPLEX, 0.55, AMBER, 1, cv2.LINE_AA)

        # Device name (truncate to 28 chars)
        device = state.bt_pairing_device[:28]
        cv2.putText(canvas, device,
                    (260, 195), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1, cv2.LINE_AA)

        # Passkey label
        cv2.putText(canvas, 'CONFIRM CODE ON YOUR PHONE',
                    (240, 225), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (100, 100, 100), 1, cv2.LINE_AA)

        # Passkey value — large, spaced
        passkey_str = f"{state.bt_pairing_passkey:06d}"
        spaced = '  '.join(passkey_str)
        cv2.putText(canvas, spaced,
                    (248, 272), cv2.FONT_HERSHEY_SIMPLEX, 1.1, AMBER, 2, cv2.LINE_AA)

        # ACCEPT button
        ax1, ay1, ax2, ay2 = PAIRING_ACCEPT_RECT
        cv2.rectangle(canvas, (ax1, ay1), (ax2, ay2), AMBER, -1)
        cv2.putText(canvas, 'ACCEPT',
                    (ax1 + 28, ay2 - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 2, cv2.LINE_AA)

        # REJECT button
        rx1, ry1, rx2, ry2 = PAIRING_REJECT_RECT
        cv2.rectangle(canvas, (rx1, ry1), (rx2, ry2), (50, 50, 50), -1)
        cv2.rectangle(canvas, (rx1, ry1), (rx2, ry2), (80, 80, 80), 1)
        cv2.putText(canvas, 'REJECT',
                    (rx1 + 28, ry2 - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (150, 150, 150), 1, cv2.LINE_AA)

        # Countdown
        elapsed = time.monotonic() - self._pairing_start
        remaining = max(0, int(30 - elapsed))
        cv2.putText(canvas, f'AUTO-DISMISS IN {remaining}s',
                    (295, 345), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (80, 80, 80), 1, cv2.LINE_AA)
```

- [ ] **Step 2: Add `_pairing_start` tracking and overlay call in `render_frame`**

In `GaugeRenderer.__init__`, add after `self._fills = self._init_fill_svgs()`:

```python
        self._pairing_start: float = 0.0
```

In `render_frame`, add at the very end (after `draw_warnings`):

```python
        # Pairing overlay — always on top of everything
        if state.bt_pairing_pending:
            if self._pairing_start == 0.0:
                self._pairing_start = time.monotonic()
            self._draw_pairing_overlay(canvas, state)
        else:
            self._pairing_start = 0.0
```

- [ ] **Step 3: Verify it imports cleanly**

```bash
cd ~/nova-dashboard-cv
python -c "from dashboard_ui import GaugeRenderer, PAIRING_ACCEPT_RECT, PAIRING_REJECT_RECT; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add dashboard_ui.py
git commit -m "feat: draw Bluetooth pairing overlay in dashboard renderer"
```

---

## Task 4: Wire agent into main.py

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Import PairingAgent and start the thread**

In `main.py`, add the import alongside the other handler imports:

```python
from pairing_agent import PairingAgent
```

In `main()`, after `bt_thread = BluetoothHandler(state)` add:

```python
    pairing_agent = PairingAgent(state)
```

After `bt_thread.start()` add:

```python
    pairing_agent.start()
    log.info("Pairing agent started")
```

- [ ] **Step 2: Handle Accept/Reject touch**

In the `MOUSEBUTTONUP` handler, add this block **before** the existing swipe/tap logic (so pairing taps are intercepted first):

```python
                elif event.type == pygame.MOUSEBUTTONUP:
```

Replace the existing `elif event.type == pygame.MOUSEBUTTONUP:` block with:

```python
                elif event.type == pygame.MOUSEBUTTONUP:
                    if swipe_start_x is not None:
                        dx = event.pos[0] - swipe_start_x
                        tx, ty = event.pos

                        # Pairing overlay tap — intercept before swipe logic
                        if snap.bt_pairing_pending and abs(dx) < SWIPE_THRESHOLD:
                            ax1, ay1, ax2, ay2 = PAIRING_ACCEPT_RECT
                            rx1, ry1, rx2, ry2 = PAIRING_REJECT_RECT
                            if ax1 <= tx <= ax2 and ay1 <= ty <= ay2:
                                state.bt_pairing_accepted = True
                                state.bt_pairing_response.set()
                            elif rx1 <= tx <= rx2 and ry1 <= ty <= ry2:
                                state.bt_pairing_accepted = False
                                state.bt_pairing_response.set()
                        elif abs(dx) < SWIPE_THRESHOLD:
                            # Tap — check media controls on page 0
                            if page == 0:
                                if ty > 410 and 200 <= tx <= 600:
                                    if tx < 350:
                                        bt_thread.send_command("Previous")
                                    elif tx < 450:
                                        if snap.bt_playing:
                                            bt_thread.send_command("Pause")
                                        else:
                                            bt_thread.send_command("Play")
                                    else:
                                        bt_thread.send_command("Next")
                        elif dx < -SWIPE_THRESHOLD:
                            if page < TOTAL_PAGES - 1:
                                page += 1
                            elif nav_proc is not None:
                                swaymsg('workspace', '2')
                        elif dx > SWIPE_THRESHOLD:
                            page = max(0, page - 1)
                    swipe_start_x = None
```

Also add this import at the top of `main.py` alongside the other handler imports:

```python
from dashboard_ui import GaugeRenderer, PAIRING_ACCEPT_RECT, PAIRING_REJECT_RECT
```

- [ ] **Step 3: Stop the agent in finally block**

In the `finally` block, after `bt_thread.join(timeout=2.0)` add:

```python
        pairing_agent.stop()
        pairing_agent.join(timeout=2.0)
```

- [ ] **Step 4: Verify main.py imports cleanly**

```bash
python -c "import ast, sys; ast.parse(open('main.py').read()); print('syntax OK')"
```

Expected: `syntax OK`

- [ ] **Step 5: Commit**

```bash
git add main.py
git commit -m "feat: start pairing agent thread and handle Accept/Reject touch in main loop"
```

---

## Task 5: Install dependencies and smoke test on Pi

**Files:** none

- [ ] **Step 1: Install system packages on the Pi**

```bash
sudo apt install python3-dbus python3-gi gir1.2-glib-2.0
```

Expected: packages installed (or already newest version).

- [ ] **Step 2: Pull and restart on Pi**

```bash
cd ~/nova-dashboard-cv && git pull
sudo systemctl restart nova-dashboard-wayland
sudo journalctl -u nova-dashboard-wayland -f
```

Expected log lines:
```
Pairing agent registered (capability=DisplayYesNo)
Adapter set to pairable
```

- [ ] **Step 3: Test pairing from a phone**

On a phone, go to Bluetooth settings, scan for devices, and tap the Pi's device name.

Expected: The dashboard shows the pairing overlay with the device name and a 6-digit passkey. The same code appears on the phone.

- [ ] **Step 4: Test Accept**

Tap ACCEPT on the dashboard within 30 seconds.

Expected: Phone connects, overlay disappears, dashboard returns to normal.

- [ ] **Step 5: Test auto-dismiss**

Initiate pairing again but do not tap anything.

Expected: After 30 seconds, overlay disappears automatically. Phone shows pairing failed. Phone can immediately retry pairing (not blocked).

- [ ] **Step 6: Final commit**

```bash
git add -p   # review any stray changes
git commit -m "feat: Bluetooth pairing screen complete"
git push
```
