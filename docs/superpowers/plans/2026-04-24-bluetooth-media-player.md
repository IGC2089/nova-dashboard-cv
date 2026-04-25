# Bluetooth AVRCP Media Player Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Bluetooth AVRCP media player to the center zone (x=200–600, 400×480 px) of the dashboard, showing track info and playback controls using data from the phone paired over BlueZ.

**Architecture:** A new `BluetoothHandler` daemon thread (same pattern as `CANListener`/`GPSListener`) polls BlueZ D-Bus every second for the connected phone's `org.bluez.MediaPlayer1` metadata and writes it to five new fields on `VehicleState`. The render thread reads those fields on page 0 and draws the media UI in the center zone via a new `draw_media_player()` method. Media button taps are detected in `main.py` and forwarded to `BluetoothHandler.send_command()` which calls `org.bluez.MediaControl1` methods. Since wireless Android Auto does not work with Android 14, `nova-openauto.service` is disabled from the setup script.

**Tech Stack:** Python 3.11+, BlueZ 5.x (D-Bus), `dbus-python` (pip, needs `libdbus-1-dev`), OpenCV (numpy), pygame (SDL2/Wayland)

---

## File Structure

| File | Status | Purpose |
|------|--------|---------|
| `bluetooth_handler.py` | **Create** | Daemon thread: polls BlueZ D-Bus, writes media state, exposes `send_command()` |
| `vehicle_state.py` | **Modify** | Add 5 media fields + update `snapshot()` |
| `dashboard_ui.py` | **Modify** | Add `draw_media_player()`, call on page 0 center zone |
| `main.py` | **Modify** | Start BT thread, detect media button taps, handle 3 pages |
| `requirements.txt` | **Modify** | Add `dbus-python` with apt-prerequisite comment |
| `scripts/setup-weston.sh` | **Modify** | Add `libdbus-1-dev` apt install, disable nova-openauto |
| `tests/test_bluetooth_handler.py` | **Create** | Unit tests for `AVRCPPoller` parse logic (no hardware) |
| `tests/test_media_ui.py` | **Create** | Smoke test: `draw_media_player()` doesn't crash |

---

### Task 1: Add Media Fields to VehicleState

**Files:**
- Modify: `vehicle_state.py`
- Test: `tests/test_vehicle_state_media.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_vehicle_state_media.py
from vehicle_state import VehicleState

def test_media_fields_exist_with_defaults():
    s = VehicleState()
    assert s.bt_connected is False
    assert s.bt_playing is False
    assert s.bt_title == ""
    assert s.bt_artist == ""
    assert s.bt_album == ""

def test_snapshot_copies_media_fields():
    s = VehicleState()
    with s.lock:
        s.bt_connected = True
        s.bt_playing = True
        s.bt_title = "Bohemian Rhapsody"
        s.bt_artist = "Queen"
        s.bt_album = "A Night at the Opera"
    snap = s.snapshot()
    assert snap.bt_connected is True
    assert snap.bt_playing is True
    assert snap.bt_title == "Bohemian Rhapsody"
    assert snap.bt_artist == "Queen"
    assert snap.bt_album == "A Night at the Opera"
    assert snap.lock is None  # snapshot has no lock
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/pi/nova-dashboard-cv
.venv/bin/pytest tests/test_vehicle_state_media.py -v
```

Expected: FAIL with `AttributeError: 'VehicleState' object has no attribute 'bt_connected'`

- [ ] **Step 3: Add media fields to VehicleState**

In `vehicle_state.py`, add after the `fuel_pct` line and update `snapshot()`:

```python
    # Bluetooth media (AVRCP)
    bt_connected: bool = False
    bt_playing: bool = False
    bt_title: str = ""
    bt_artist: str = ""
    bt_album: str = ""
```

And extend `snapshot()` to include those five fields (add before `lock=None`):

```python
                bt_connected=self.bt_connected,
                bt_playing=self.bt_playing,
                bt_title=self.bt_title,
                bt_artist=self.bt_artist,
                bt_album=self.bt_album,
```

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/pytest tests/test_vehicle_state_media.py -v
```

Expected: 2 PASSED

- [ ] **Step 5: Commit**

```bash
git add vehicle_state.py tests/test_vehicle_state_media.py
git commit -m "feat: add Bluetooth media fields to VehicleState"
```

---

### Task 2: Create BluetoothHandler Daemon Thread

**Files:**
- Create: `bluetooth_handler.py`
- Create: `tests/test_bluetooth_handler.py`

The handler uses `dbus-python` to find the first connected BlueZ device that exposes `org.bluez.MediaPlayer1`, polls its properties every second, and writes them to `VehicleState`. It also exposes `send_command(cmd)` for the render thread to request playback actions.

- [ ] **Step 1: Add dbus-python to requirements.txt**

```
# Requires: sudo apt install libdbus-1-dev python3-dev
dbus-python>=1.3.2
```

Full updated `requirements.txt`:
```
opencv-python>=4.9.0
python-can>=4.4.0
numpy>=1.26.0
gpsd-py3>=0.3.0
PyYAML>=6.0.2
pygame>=2.5.0
cairosvg>=2.7
# Requires: sudo apt install libdbus-1-dev python3-dev
dbus-python>=1.3.2
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_bluetooth_handler.py
"""Tests for AVRCPPoller — pure logic, no D-Bus hardware required."""
from bluetooth_handler import AVRCPPoller


def test_parse_properties_connected_playing():
    props = {
        "Status": "playing",
        "Track": {
            "Title": "Bohemian Rhapsody",
            "Artist": "Queen",
            "Album": "A Night at the Opera",
        },
    }
    result = AVRCPPoller.parse_properties(props)
    assert result["bt_connected"] is True
    assert result["bt_playing"] is True
    assert result["bt_title"] == "Bohemian Rhapsody"
    assert result["bt_artist"] == "Queen"
    assert result["bt_album"] == "A Night at the Opera"


def test_parse_properties_paused():
    props = {
        "Status": "paused",
        "Track": {"Title": "Yesterday", "Artist": "Beatles", "Album": "Help!"},
    }
    result = AVRCPPoller.parse_properties(props)
    assert result["bt_connected"] is True
    assert result["bt_playing"] is False


def test_parse_properties_empty_track():
    props = {"Status": "playing", "Track": {}}
    result = AVRCPPoller.parse_properties(props)
    assert result["bt_title"] == ""
    assert result["bt_artist"] == ""
    assert result["bt_album"] == ""


def test_parse_properties_missing_track_key():
    props = {"Status": "stopped"}
    result = AVRCPPoller.parse_properties(props)
    assert result["bt_connected"] is True
    assert result["bt_playing"] is False
    assert result["bt_title"] == ""


def test_parse_empty_gives_disconnected():
    result = AVRCPPoller.parse_properties({})
    assert result["bt_connected"] is False
    assert result["bt_playing"] is False
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_bluetooth_handler.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'bluetooth_handler'`

- [ ] **Step 4: Create bluetooth_handler.py**

```python
# bluetooth_handler.py
"""Daemon thread that polls BlueZ AVRCP for media metadata and controls."""
from __future__ import annotations
import logging
import threading
import time
from typing import Optional

from vehicle_state import VehicleState

log = logging.getLogger(__name__)

POLL_INTERVAL = 1.0  # seconds between D-Bus polls


class AVRCPPoller:
    """Pure parse logic — no D-Bus dependency, fully unit-testable."""

    @staticmethod
    def parse_properties(props: dict) -> dict:
        """Convert raw MediaPlayer1 properties dict to media state dict."""
        if not props:
            return {
                "bt_connected": False,
                "bt_playing": False,
                "bt_title": "",
                "bt_artist": "",
                "bt_album": "",
            }
        status = str(props.get("Status", "")).lower()
        track = props.get("Track", {}) or {}
        return {
            "bt_connected": True,
            "bt_playing": status == "playing",
            "bt_title": str(track.get("Title", "")),
            "bt_artist": str(track.get("Artist", "")),
            "bt_album": str(track.get("Album", "")),
        }


class BluetoothHandler(threading.Thread):
    """Daemon thread: polls BlueZ MediaPlayer1 every second, updates VehicleState."""

    def __init__(self, state: VehicleState):
        super().__init__(daemon=True, name="BluetoothHandler")
        self._state = state
        self._running = False
        self._cmd_lock = threading.Lock()
        self._pending_cmd: Optional[str] = None

    def send_command(self, cmd: str) -> None:
        """Thread-safe: queue a playback command (Next/Previous/Play/Pause)."""
        with self._cmd_lock:
            self._pending_cmd = cmd

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        self._running = True
        # Import dbus lazily so the module loads without dbus on dev machines
        try:
            import dbus
        except ImportError:
            log.warning("dbus-python not available — Bluetooth media disabled")
            return

        bus = dbus.SystemBus()
        poller = AVRCPPoller()

        while self._running:
            try:
                self._poll_once(bus, poller, dbus)
            except Exception:
                log.debug("BT poll error", exc_info=True)
                self._write_disconnected()

            time.sleep(POLL_INTERVAL)

    def _poll_once(self, bus, poller: AVRCPPoller, dbus) -> None:
        """Find first MediaPlayer1 object and read its properties."""
        manager = dbus.Interface(
            bus.get_object("org.bluez", "/"),
            "org.freedesktop.DBus.ObjectManager",
        )
        objects = manager.GetManagedObjects()

        player_path = None
        for path, ifaces in objects.items():
            if "org.bluez.MediaPlayer1" in ifaces:
                player_path = path
                break

        if player_path is None:
            self._write_disconnected()
            return

        # Send any pending command before reading state
        with self._cmd_lock:
            cmd = self._pending_cmd
            self._pending_cmd = None

        if cmd:
            try:
                ctrl_path = str(player_path).rsplit("/player", 1)[0]
                ctrl = dbus.Interface(
                    bus.get_object("org.bluez", ctrl_path),
                    "org.bluez.MediaControl1",
                )
                getattr(ctrl, cmd)()
                log.debug("BT command sent: %s", cmd)
            except Exception:
                log.debug("BT command failed: %s", cmd, exc_info=True)

        props_iface = dbus.Interface(
            bus.get_object("org.bluez", player_path),
            "org.freedesktop.DBus.Properties",
        )
        raw = props_iface.GetAll("org.bluez.MediaPlayer1")
        media = poller.parse_properties(dict(raw))
        self._write(media)

    def _write(self, media: dict) -> None:
        with self._state.lock:
            self._state.bt_connected = media["bt_connected"]
            self._state.bt_playing = media["bt_playing"]
            self._state.bt_title = media["bt_title"]
            self._state.bt_artist = media["bt_artist"]
            self._state.bt_album = media["bt_album"]

    def _write_disconnected(self) -> None:
        with self._state.lock:
            self._state.bt_connected = False
            self._state.bt_playing = False
            self._state.bt_title = ""
            self._state.bt_artist = ""
            self._state.bt_album = ""
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/test_bluetooth_handler.py -v
```

Expected: 5 PASSED (no dbus needed — tests only hit `AVRCPPoller.parse_properties`)

- [ ] **Step 6: Commit**

```bash
git add bluetooth_handler.py requirements.txt tests/test_bluetooth_handler.py
git commit -m "feat: add BluetoothHandler daemon thread with AVRCP polling"
```

---

### Task 3: Add draw_media_player() to GaugeRenderer

**Files:**
- Modify: `dashboard_ui.py`
- Create: `tests/test_media_ui.py`

Center zone layout (x=200..600, y=0..480 — all coordinates are in screen pixels):
- Dark background fill: (10, 10, 10) BGR
- "MEDIA" label: x=400 center, y=24, amber `(43, 179, 235)` BGR
- Album art placeholder: 280×280 rect, x=260..540, y=40..320, dark gray border
- Music note `♪` drawn inside placeholder in amber when no art
- Track title: centered at x=400, y=345, white, fontScale=0.65
- Artist: centered at x=400, y=370, gray (170,170,170), fontScale=0.55
- Divider line: x=220..580, y=390, amber, 1px
- Control buttons (Unicode text via cv2.putText):
  - ⏮  at x=300, y=445 (Previous)
  - ⏸/⏵ at x=400, y=445 (Play/Pause toggle)
  - ⏭  at x=500, y=445 (Next)
- "No device" state: shows "BLUETOOTH" label + "Pair your phone" in gray

**Note on Unicode glyphs:** `cv2.putText` with Hershey fonts cannot render Unicode. Use ASCII substitutes: `|<` for Previous, `||` / `>` for Pause/Play, `>|` for Next, drawn with `cv2.FONT_HERSHEY_SIMPLEX`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_media_ui.py
import numpy as np
from unittest.mock import MagicMock, patch
from vehicle_state import VehicleState


def _make_renderer():
    """Build a GaugeRenderer with mocked SVG loading."""
    with patch("dashboard_ui.cairosvg") as mock_cairo:
        import cv2
        # Return a valid PNG-encoded black image for all SVG loads
        dummy = np.zeros((480, 800, 3), dtype=np.uint8)
        _, buf = cv2.imencode(".png", dummy)
        mock_cairo.svg2png.return_value = bytes(buf)
        from dashboard_ui import GaugeRenderer
        style = {
            "colors": {
                "background": [10, 10, 10],
                "amber": [43, 179, 235],
                "white": [255, 255, 255],
                "gray": [170, 170, 170],
                "warning": [0, 0, 255],
            }
        }
        gauges = {
            "svg": {"path": "assets/cluster.svg", "native_width": 800, "native_height": 480},
            "fill_svgs": {},
            "gauges": {},
            "center_panel": {"readouts": []},
        }
        return GaugeRenderer(style=style, gauges=gauges, width=800, height=480)


def test_draw_media_player_no_crash_disconnected():
    renderer = _make_renderer()
    canvas = np.zeros((480, 800, 3), dtype=np.uint8)
    snap = VehicleState()
    snap.bt_connected = False
    renderer.draw_media_player(canvas, snap)  # must not raise


def test_draw_media_player_no_crash_playing():
    renderer = _make_renderer()
    canvas = np.zeros((480, 800, 3), dtype=np.uint8)
    snap = VehicleState()
    snap.bt_connected = True
    snap.bt_playing = True
    snap.bt_title = "Bohemian Rhapsody"
    snap.bt_artist = "Queen"
    snap.bt_album = "A Night at the Opera"
    renderer.draw_media_player(canvas, snap)  # must not raise


def test_draw_media_player_writes_to_center_zone():
    renderer = _make_renderer()
    canvas = np.zeros((480, 800, 3), dtype=np.uint8)
    snap = VehicleState()
    snap.bt_connected = True
    snap.bt_playing = False
    snap.bt_title = "Yesterday"
    snap.bt_artist = "Beatles"
    renderer.draw_media_player(canvas, snap)
    # Center zone must not be all zeros (something was drawn)
    center = canvas[:, 200:600]
    assert center.max() > 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_media_ui.py -v
```

Expected: FAIL with `AttributeError: 'GaugeRenderer' object has no attribute 'draw_media_player'`

- [ ] **Step 3: Add draw_media_player() to GaugeRenderer in dashboard_ui.py**

Add this method to the `GaugeRenderer` class (after `draw_center_panel`):

```python
    def draw_media_player(self, canvas: np.ndarray, state) -> None:
        """Render Bluetooth media player in center zone x=200..600, y=0..480."""
        s = self._s["colors"]
        amber = tuple(s["amber"])
        white = tuple(s["white"])
        gray = tuple(s["gray"])
        dark = (10, 10, 10)

        # Dark background for center zone
        canvas[:, 200:600] = dark

        if not state.bt_connected:
            self._draw_no_bt(canvas, gray, amber)
            return

        # "MEDIA" header
        label = "MEDIA"
        (lw, _), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.putText(canvas, label, (400 - lw // 2, 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, amber, 1, cv2.LINE_AA)

        # Album art placeholder (280×280, centered in zone)
        art_x1, art_y1 = 260, 40
        art_x2, art_y2 = 540, 320
        cv2.rectangle(canvas, (art_x1, art_y1), (art_x2, art_y2), (40, 40, 40), -1)
        cv2.rectangle(canvas, (art_x1, art_y1), (art_x2, art_y2), amber, 1)
        # Music note placeholder text
        note = "( music )"
        (nw, nh), _ = cv2.getTextSize(note, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 1)
        cv2.putText(canvas, note, (400 - nw // 2, 185),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, amber, 1, cv2.LINE_AA)

        # Track title (truncated to ~30 chars)
        title = (state.bt_title or "Unknown")[:30]
        (tw, _), _ = cv2.getTextSize(title, cv2.FONT_HERSHEY_SIMPLEX, 0.65, 1)
        cv2.putText(canvas, title, (400 - tw // 2, 345),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, white, 1, cv2.LINE_AA)

        # Artist
        artist = (state.bt_artist or "")[:30]
        if artist:
            (aw, _), _ = cv2.getTextSize(artist, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
            cv2.putText(canvas, artist, (400 - aw // 2, 370),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, gray, 1, cv2.LINE_AA)

        # Divider
        cv2.line(canvas, (220, 390), (580, 390), amber, 1)

        # Controls: |< at x=300, ||/>  at x=400, >| at x=500, y=445
        play_label = "||" if state.bt_playing else " >"
        for label, cx in [("<|", 300), (play_label, 400), ("|>", 500)]:
            (bw, _), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.9, 2)
            cv2.putText(canvas, label, (cx - bw // 2, 445),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, amber, 2, cv2.LINE_AA)

    def _draw_no_bt(self, canvas: np.ndarray, gray: tuple, amber: tuple) -> None:
        """Draw 'no Bluetooth device' placeholder in center zone."""
        lines = ["BLUETOOTH", "", "Pair your phone"]
        y = 220
        for line in lines:
            if not line:
                y += 24
                continue
            color = amber if line == "BLUETOOTH" else gray
            scale = 0.7 if line == "BLUETOOTH" else 0.55
            (w, _), _ = cv2.getTextSize(line, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)
            cv2.putText(canvas, line, (400 - w // 2, y),
                        cv2.FONT_HERSHEY_SIMPLEX, scale, color, 1, cv2.LINE_AA)
            y += 32
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/test_media_ui.py -v
```

Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add dashboard_ui.py tests/test_media_ui.py
git commit -m "feat: add draw_media_player() center zone UI"
```

---

### Task 4: Wire BluetoothHandler into main.py

**Files:**
- Modify: `main.py`

Changes:
1. Import and start `BluetoothHandler`
2. Add page 2 (now 3 pages: 0=gauges+media, 1=center-panel, but center panel already uses center zone which collides with media player — see below)
3. Call `draw_media_player()` on page 0
4. Detect media button taps (not swipes) in center zone on page 0
5. Stop `bt_thread` on shutdown

**Page layout after this change:**
- Page 0: Gauge fills (left/right) + media player (center zone 200–600)
- Page 1: Center panel readouts (ECU diagnostics) — keeps existing behavior
- TOTAL_PAGES stays at 2 (no change to pagination)

**Tap detection logic:** A touch event with `abs(dx) < SWIPE_THRESHOLD` is a tap. On page 0, check if tap y > 410 (control row) and x is within 60px of a button center.

- [ ] **Step 1: Update main.py**

Replace the imports block at the top to add `BluetoothHandler`:

```python
from bluetooth_handler import BluetoothHandler
```

After `gps_thread = GPSListener(state)` line, add:

```python
    bt_thread = BluetoothHandler(state)
```

In the event loop, replace the `MOUSEBUTTONUP` handler with this expanded version that detects taps vs swipes:

```python
                elif event.type == pygame.MOUSEBUTTONUP:
                    if swipe_start_x is not None:
                        dx = event.pos[0] - swipe_start_x
                        if abs(dx) < SWIPE_THRESHOLD:
                            # Tap — check media controls on page 0
                            if page == 0:
                                tx, ty = event.pos
                                if ty > 410 and 200 <= tx <= 600:
                                    if tx < 350:
                                        bt_thread.send_command("Previous")
                                    elif tx < 450:
                                        bt_thread.send_command("Play") if not state.bt_playing else bt_thread.send_command("Pause")
                                    else:
                                        bt_thread.send_command("Next")
                        elif dx < -SWIPE_THRESHOLD:
                            page = min(TOTAL_PAGES - 1, page + 1)
                        elif dx > SWIPE_THRESHOLD:
                            page = max(0, page - 1)
                    swipe_start_x = None
```

In the render section, after `renderer.render_frame(canvas, snap, interp, page)`, add:

```python
            if page == 0:
                renderer.draw_media_player(canvas, snap)
```

After `can_thread.start()` and `gps_thread.start()`, add:

```python
    bt_thread.start()
    log.info("Bluetooth handler started")
```

In the `finally` block, after `gps_thread.stop()`, add:

```python
        bt_thread.stop()
        bt_thread.join(timeout=2.0)
```

- [ ] **Step 2: Verify simulate mode still runs (no hardware needed)**

```bash
.venv/bin/python3 main.py --simulate 2>&1 | head -5
```

Expected: starts without import error (may fail on SDL/Wayland if not in a compositor session — that's OK; the goal is no import/syntax error)

If running headless (SSH), just check for import errors:

```bash
.venv/bin/python3 -c "import main" 2>&1
```

Expected: no output (clean import)

- [ ] **Step 3: Run full test suite**

```bash
.venv/bin/pytest tests/ -v --ignore=tests/test_media_ui.py  # skip SDL tests if headless
```

Expected: all existing tests pass

- [ ] **Step 4: Commit**

```bash
git add main.py
git commit -m "feat: wire BluetoothHandler into render loop and tap detection"
```

---

### Task 5: Disable nova-openauto in setup-weston.sh

**Files:**
- Modify: `scripts/setup-weston.sh`
- Modify: `scripts/rollback-weston.sh`

Since wireless Android Auto does not work with Android 14, `nova-openauto.service` is no longer started. The setup script should not enable it. The rollback script should not disable it (it was never enabled).

- [ ] **Step 1: Update setup-weston.sh**

Add `libdbus-1-dev python3-dev` to the apt install line and remove nova-openauto from the enabled services.

Find this line in `scripts/setup-weston.sh`:
```bash
apt-get install -y sway seatd avahi-daemon hostapd dnsmasq
```

Replace with:
```bash
apt-get install -y sway seatd avahi-daemon hostapd dnsmasq libdbus-1-dev python3-dev
```

Find the block at the bottom that enables services. Remove the `nova-openauto` lines:
```bash
systemctl enable nova-openauto.service   # REMOVE THIS LINE
```

Also remove the install line:
```bash
install -Dm644 "$REPO/scripts/nova-openauto.service"          /etc/systemd/system/nova-openauto.service  # REMOVE THIS LINE
```

Add after `systemctl daemon-reload`:
```bash
systemctl disable nova-openauto.service 2>/dev/null || true
```

And add the pip install for dbus-python after the seatd systemctl block:
```bash
echo "=== Installing Python dbus bindings ==="
"$REPO/.venv/bin/pip" install dbus-python
```

- [ ] **Step 2: Update rollback-weston.sh**

Remove the `nova-openauto` stop/disable lines from `scripts/rollback-weston.sh` since it is no longer enabled:

```bash
# REMOVE these two lines:
systemctl stop nova-openauto.service         2>/dev/null || true
systemctl disable nova-openauto.service      2>/dev/null || true
```

- [ ] **Step 3: Verify scripts are valid bash**

```bash
bash -n scripts/setup-weston.sh && echo "OK"
bash -n scripts/rollback-weston.sh && echo "OK"
```

Expected: `OK` for both

- [ ] **Step 4: Commit**

```bash
git add scripts/setup-weston.sh scripts/rollback-weston.sh
git commit -m "chore: disable nova-openauto, add dbus-python install to setup"
```

---

### Task 6: On-Pi Integration Test

This task runs on the Pi (via SSH). It verifies the full stack: BlueZ visible, dbus-python working, media UI renders.

- [ ] **Step 1: Install dbus-python on Pi**

```bash
sudo apt install -y libdbus-1-dev python3-dev
cd /home/pi/nova-dashboard-cv
.venv/bin/pip install dbus-python
```

Expected: `Successfully installed dbus-python-x.x.x`

- [ ] **Step 2: Verify BlueZ is running and sees the phone**

```bash
bluetoothctl show
bluetoothctl devices Connected
```

Expected: phone device listed as connected

- [ ] **Step 3: Check if MediaPlayer1 interface is visible**

```bash
dbus-send --system --print-reply --dest=org.bluez / \
  org.freedesktop.DBus.ObjectManager.GetManagedObjects 2>&1 | grep -A2 MediaPlayer1
```

Expected: output containing `org.bluez.MediaPlayer1` (may require playing music on the phone first)

- [ ] **Step 4: Run dashboard with --simulate to verify media UI renders**

On Pi (in a VT or via sway), start the dashboard:

```bash
WAYLAND_DISPLAY=wayland-1 XDG_RUNTIME_DIR=/run/user/0 \
  /home/pi/nova-dashboard-cv/.venv/bin/python3 main.py --simulate
```

Expected: Dashboard renders. Page 0 shows gauges on left/right and media player in center. If phone is paired and playing music, track info appears.

- [ ] **Step 5: Test swipe navigation still works**

Swipe right→left on screen: should advance to page 1 (center panel diagnostics).
Swipe left→right: return to page 0 (gauges + media player).

- [ ] **Step 6: Test media button tap on page 0**

Tap the `||` (pause) button in the center zone while music is playing on the phone.
Expected: music pauses on the phone.

- [ ] **Step 7: Run full test suite on Pi**

```bash
cd /home/pi/nova-dashboard-cv
.venv/bin/pytest tests/ -v
```

Expected: all tests pass

- [ ] **Step 8: Run setup-weston.sh to deploy updated services**

```bash
sudo bash /home/pi/nova-dashboard-cv/scripts/setup-weston.sh
sudo reboot
```

Expected: after reboot, dashboard starts, media player visible on page 0, nova-openauto does NOT start.

---

## Self-Review

**Spec coverage check:**
- ✅ BlueZ D-Bus AVRCP polling → `bluetooth_handler.py` Tasks 2
- ✅ MediaControl1 commands → `send_command()` in `BluetoothHandler._poll_once`
- ✅ Media fields on VehicleState → Task 1
- ✅ Center zone UI (dark bg, art placeholder, track/artist, controls) → Task 3
- ✅ Always visible on page 0 → Task 4 (`if page == 0: draw_media_player()`)
- ✅ Amber color #EBB32B → BGR `(43, 179, 235)` used throughout
- ✅ "No device" fallback state → `_draw_no_bt()`
- ✅ Tap detection for controls → Task 4 event handler
- ✅ nova-openauto disabled → Task 5
- ✅ dbus-python dependency + apt prereq → Task 2 + Task 5

**Placeholder scan:** No TBD, TODO, or vague steps found.

**Type consistency:**
- `state.bt_playing` used in Task 4 tap handler — matches field added in Task 1 ✅
- `bt_thread.send_command("Play")` calls `BluetoothHandler.send_command()` — defined in Task 2 ✅
- `renderer.draw_media_player(canvas, snap)` — method added in Task 3, snap has `bt_*` fields from Task 1 ✅
- `_draw_no_bt()` called from `draw_media_player()` — both in `dashboard_ui.py` Task 3 ✅
