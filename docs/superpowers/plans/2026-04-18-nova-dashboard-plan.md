# Nova Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a full-screen, 60 FPS digital instrument cluster for a 1974 Chevrolet Nova — tachometer left, digital readouts center, GPS speedometer right — rendered in OpenCV on a Raspberry Pi 5.

**Architecture:** Three daemon threads (CAN listener, GPS listener, render loop) share a single `VehicleState` dataclass protected by `threading.Lock`. The main thread runs the 60 FPS render loop, applying per-frame linear interpolation to needle angles for fluid motion. All visual parameters are config-driven (YAML) so the UI can be modified without touching Python code.

**Tech Stack:** Python 3.11+, OpenCV 4.9+, python-can 4.4+, gpsd-py3, numpy, PyYAML, pytest (dev)

---

## File Map

| File | Role |
|------|------|
| `vehicle_state.py` | `VehicleState` dataclass + `threading.Lock` + `snapshot()` |
| `can_handler.py` | `SpeeduinoDecoder` (pure logic) + `CANListener` thread |
| `gps_handler.py` | `OdometerAccumulator` (pure logic) + `GPSListener` thread + atomic save |
| `dashboard_ui.py` | `GaugeRenderer` class — all OpenCV drawing, config-driven |
| `main.py` | Thread orchestration, 60 FPS render loop, clean shutdown |
| `config/style.yaml` | All colors, font scales — no color constants in Python |
| `config/gauges.yaml` | Gauge geometry, center panel readout list |
| `requirements.txt` | Runtime dependencies |
| `requirements-dev.txt` | pytest |
| `scripts/setup_can.sh` | Bring up can0 at 500 kbps |
| `scripts/setup_readonly.sh` | Enable overlayfs + /data fstab entry |
| `scripts/nova-dashboard.service` | systemd unit |
| `tests/test_vehicle_state.py` | VehicleState tests |
| `tests/test_can_handler.py` | SpeeduinoDecoder tests |
| `tests/test_gps_handler.py` | OdometerAccumulator tests |
| `tests/test_dashboard_ui.py` | GaugeRenderer angle math + no-crash tests |

---

## Task 1: Project Scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `.gitignore`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create virtual environment and requirements**

```bash
cd /c/Users/cigcg/nova-dashboard-cv
python3 -m venv .venv
source .venv/bin/activate
```

Write `requirements.txt`:
```
opencv-python>=4.9.0
python-can>=4.4.0
numpy>=1.26.0
gpsd-py3>=0.3.0
PyYAML>=6.0.2
```

Write `requirements-dev.txt`:
```
pytest>=8.0.0
```

- [ ] **Step 2: Create directory structure**

```bash
mkdir -p config scripts tests
touch tests/__init__.py
```

- [ ] **Step 3: Install dependencies**

```bash
pip install -r requirements.txt -r requirements-dev.txt
```

Expected: all packages install without error.

- [ ] **Step 4: Update .gitignore**

```
.venv/
__pycache__/
*.pyc
.superpowers/
/data/
```

- [ ] **Step 5: Commit**

```bash
git add requirements.txt requirements-dev.txt .gitignore tests/__init__.py
git commit -m "feat: project scaffolding"
```

---

## Task 2: Config Files

**Files:**
- Create: `config/style.yaml`
- Create: `config/gauges.yaml`

- [ ] **Step 1: Write style.yaml**

Note: OpenCV uses BGR channel order, not RGB.

```yaml
# config/style.yaml
# All colors in BGR (Blue, Green, Red) — OpenCV convention.
theme:
  bg_color:       [1, 6, 8]          # near-black warm background
  arc_active:     [0, 122, 196]      # amber arc fill
  arc_inactive:   [0, 18, 26]        # dark arc track
  arc_redzone:    [0, 20, 140]       # red zone (BGR: dark red)
  needle_color:   [128, 210, 255]    # warm white needle
  hub_color:      [0, 122, 196]      # needle pivot circle
  label_color:    [0, 66, 90]        # dim amber labels (unit / name text)
  value_color:    [128, 210, 255]    # bright readout values
  warning_amber:  [0, 165, 255]      # CLT / rich warning overlay
  warning_red:    [0, 0, 220]        # lean warning overlay
```

- [ ] **Step 2: Write gauges.yaml**

```yaml
# config/gauges.yaml
# Angles in degrees, clockwise from 3-o'clock (OpenCV convention).
# start_angle=150 places 0-value at ~8 o'clock.
# sweep=240 gives a 240-degree arc ending at ~4 o'clock.

tachometer:
  center:       [480, 360]
  radius:       280
  arc_width:    18
  start_angle:  150
  sweep:        240
  min_val:      0
  max_val:      6000
  redzone_val:  4500
  label:        "RPM"
  lerp_alpha:   0.15       # higher = snappier needle

speedometer:
  center:       [1440, 360]
  radius:       280
  arc_width:    18
  start_angle:  150
  sweep:        240
  min_val:      0
  max_val:      160
  redzone_val:  null       # no redzone on speedo
  label:        "MPH"
  lerp_alpha:   0.10

# Center panel: ordered list of readouts rendered top-to-bottom.
# state_field must match a field name on VehicleState.
# font_scale is relative to cv2.FONT_HERSHEY_SIMPLEX.
center_panel:
  readouts:
    - label:       "MAP"
      state_field: map_kpa
      unit:        "kPa"
      pos:         [760, 160]
      format:      "{:.0f}"
      font_scale:  1.8

    - label:       "CLT"
      state_field: clt_f
      unit:        "F"
      pos:         [1160, 160]
      format:      "{:.0f}"
      font_scale:  1.8

    - label:       "AFR"
      state_field: afr
      unit:        ""
      pos:         [960, 360]
      format:      "{:.1f}"
      font_scale:  3.5

    - label:       "ODO"
      state_field: odo_mi
      unit:        "mi"
      pos:         [760, 580]
      format:      "{:.0f}"
      font_scale:  1.4

    - label:       "TRIP"
      state_field: trip_mi
      unit:        "mi"
      pos:         [1160, 580]
      format:      "{:.1f}"
      font_scale:  1.4
```

- [ ] **Step 3: Commit**

```bash
git add config/
git commit -m "feat: add style and gauge config files"
```

---

## Task 3: VehicleState

**Files:**
- Create: `vehicle_state.py`
- Create: `tests/test_vehicle_state.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_vehicle_state.py
import threading
from vehicle_state import VehicleState


def test_default_values():
    s = VehicleState()
    assert s.rpm == 0.0
    assert s.afr == 14.7
    assert s.gps_fix is False
    assert s.trip_mi == 0.0


def test_has_lock():
    s = VehicleState()
    assert isinstance(s.lock, type(threading.Lock()))


def test_snapshot_copies_values():
    s = VehicleState()
    s.rpm = 3400.0
    s.clt_f = 195.0
    snap = s.snapshot()
    assert snap.rpm == 3400.0
    assert snap.clt_f == 195.0


def test_snapshot_is_independent():
    s = VehicleState()
    s.rpm = 3400.0
    snap = s.snapshot()
    s.rpm = 5000.0
    assert snap.rpm == 3400.0  # snap is not affected by later writes


def test_snapshot_has_no_lock():
    s = VehicleState()
    snap = s.snapshot()
    assert snap.lock is None
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
pytest tests/test_vehicle_state.py -v
```

Expected: `ModuleNotFoundError: No module named 'vehicle_state'`

- [ ] **Step 3: Implement vehicle_state.py**

```python
# vehicle_state.py
from __future__ import annotations
import threading
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class VehicleState:
    # ECU signals
    rpm: float = 0.0
    map_kpa: float = 0.0
    clt_f: float = 0.0        # Celsius converted to Fahrenheit
    afr: float = 14.7
    tps_pct: float = 0.0
    iat_c: float = 0.0
    batt_v: float = 12.0
    ign_advance: float = 0.0

    # GPS signals
    speed_mph: float = 0.0
    odo_mi: float = 0.0
    trip_mi: float = 0.0      # resets to 0 each ignition cycle
    gps_fix: bool = False

    # Threading (excluded from snapshot)
    lock: Optional[threading.Lock] = field(
        default_factory=threading.Lock, repr=False, compare=False
    )

    def snapshot(self) -> VehicleState:
        """Return a lock-free copy of current state for the render thread."""
        with self.lock:
            return VehicleState(
                rpm=self.rpm,
                map_kpa=self.map_kpa,
                clt_f=self.clt_f,
                afr=self.afr,
                tps_pct=self.tps_pct,
                iat_c=self.iat_c,
                batt_v=self.batt_v,
                ign_advance=self.ign_advance,
                speed_mph=self.speed_mph,
                odo_mi=self.odo_mi,
                trip_mi=self.trip_mi,
                gps_fix=self.gps_fix,
                lock=None,
            )
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
pytest tests/test_vehicle_state.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add vehicle_state.py tests/test_vehicle_state.py
git commit -m "feat: VehicleState dataclass with thread-safe snapshot"
```

---

## Task 4: Speeduino Decoder

**Files:**
- Create: `can_handler.py` (decoder class only — thread added in Task 5)
- Create: `tests/test_can_handler.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_can_handler.py
import struct
from can_handler import SpeeduinoDecoder


def _make_0x320(rpm=0, map_kpa=101, tps=0, iat_c=25, clt_c=90,
                o2_raw=147, batt_raw=138):
    """Build a valid 8-byte 0x320 frame."""
    data = bytearray(8)
    struct.pack_into('<H', data, 0, rpm)
    data[2] = map_kpa
    data[3] = tps
    data[4] = iat_c + 40   # wire format: value + 40 offset
    data[5] = clt_c + 40
    data[6] = o2_raw
    data[7] = batt_raw
    return bytes(data)


def _make_0x321(pw1=1200, inj_duty=25, ign_advance=10):
    data = bytearray(8)
    struct.pack_into('<H', data, 0, pw1)
    data[2] = inj_duty * 2   # wire: duty * 0.5 → raw = duty / 0.5
    data[3] = ign_advance + 40
    return bytes(data)


def test_decode_rpm():
    d = SpeeduinoDecoder()
    result = d.decode_0x320(_make_0x320(rpm=3400))
    assert result['rpm'] == 3400.0


def test_decode_clt_fahrenheit():
    d = SpeeduinoDecoder()
    result = d.decode_0x320(_make_0x320(clt_c=90))
    expected_f = 90 * 1.8 + 32   # 194.0
    assert abs(result['clt_f'] - expected_f) < 0.01


def test_decode_afr_stoich():
    # o2_raw=147 → lambda = 147 * 0.0068 ≈ 1.0 → AFR ≈ 14.7
    d = SpeeduinoDecoder()
    result = d.decode_0x320(_make_0x320(o2_raw=147))
    assert abs(result['afr'] - 14.7) < 0.1


def test_decode_map():
    d = SpeeduinoDecoder()
    result = d.decode_0x320(_make_0x320(map_kpa=98))
    assert result['map_kpa'] == 98.0


def test_decode_battery():
    d = SpeeduinoDecoder()
    result = d.decode_0x320(_make_0x320(batt_raw=138))
    assert abs(result['batt_v'] - 13.8) < 0.01


def test_short_frame_returns_none():
    d = SpeeduinoDecoder()
    assert d.decode_0x320(b'\x00\x01\x02') is None


def test_decode_0x321_ignition_advance():
    d = SpeeduinoDecoder()
    result = d.decode_0x321(_make_0x321(ign_advance=10))
    assert result['ign_advance'] == 10.0


def test_decode_0x321_short_frame_returns_none():
    d = SpeeduinoDecoder()
    assert d.decode_0x321(b'\x00') is None
```

- [ ] **Step 2: Run — verify failure**

```bash
pytest tests/test_can_handler.py -v
```

Expected: `ModuleNotFoundError: No module named 'can_handler'`

- [ ] **Step 3: Implement SpeeduinoDecoder in can_handler.py**

```python
# can_handler.py
from __future__ import annotations
import struct
import logging
from typing import Optional

log = logging.getLogger(__name__)

CAN_ID_0 = 0x320
CAN_ID_1 = 0x321


class SpeeduinoDecoder:
    """
    Pure decode logic for Speeduino Dropbear v2 CAN broadcast frames.
    No hardware dependency — fully unit-testable.
    """

    def decode_0x320(self, data: bytes) -> Optional[dict]:
        """Decode frame 0x320 — engine vitals."""
        if len(data) < 8:
            return None
        rpm = struct.unpack_from('<H', data, 0)[0]
        map_kpa = data[2]
        tps_pct = data[3]
        iat_c = data[4] - 40
        clt_c = data[5] - 40
        clt_f = clt_c * 1.8 + 32
        afr = data[6] * 0.0068 * 14.7
        batt_v = data[7] * 0.1
        return {
            'rpm':    float(rpm),
            'map_kpa': float(map_kpa),
            'tps_pct': float(tps_pct),
            'iat_c':  float(iat_c),
            'clt_f':  clt_f,
            'afr':    afr,
            'batt_v': batt_v,
        }

    def decode_0x321(self, data: bytes) -> Optional[dict]:
        """Decode frame 0x321 — fuelling / ignition."""
        if len(data) < 4:
            return None
        pw1_us = struct.unpack_from('<H', data, 0)[0]
        inj_duty = data[2] * 0.5
        ign_advance = data[3] - 40
        return {
            'pw1_us':     float(pw1_us),
            'inj_duty':   inj_duty,
            'ign_advance': float(ign_advance),
        }
```

- [ ] **Step 4: Run — verify all pass**

```bash
pytest tests/test_can_handler.py -v
```

Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add can_handler.py tests/test_can_handler.py
git commit -m "feat: SpeeduinoDecoder with full unit tests"
```

---

## Task 5: CANListener Thread

**Files:**
- Modify: `can_handler.py` — append `CANListener` class

- [ ] **Step 1: Append CANListener to can_handler.py**

```python
# Append to can_handler.py (after SpeeduinoDecoder class)
import threading
import can
from vehicle_state import VehicleState


class CANListener(threading.Thread):
    """
    Daemon thread: reads SocketCAN frames, decodes via SpeeduinoDecoder,
    and writes results into shared VehicleState under lock.
    """

    def __init__(self, state: VehicleState, channel: str = 'can0'):
        super().__init__(daemon=True, name='CANListener')
        self._state = state
        self._channel = channel
        self._decoder = SpeeduinoDecoder()
        self._running = False

    def run(self) -> None:
        self._running = True
        bus = can.interface.Bus(channel=self._channel, bustype='socketcan')
        log.info("CAN listener started on %s", self._channel)
        try:
            while self._running:
                msg = bus.recv(timeout=0.1)
                if msg is None:
                    continue
                if msg.arbitration_id == CAN_ID_0:
                    result = self._decoder.decode_0x320(bytes(msg.data))
                    if result:
                        self._apply(result)
                elif msg.arbitration_id == CAN_ID_1:
                    result = self._decoder.decode_0x321(bytes(msg.data))
                    if result:
                        self._apply(result)
        finally:
            bus.shutdown()
            log.info("CAN listener stopped")

    def stop(self) -> None:
        self._running = False

    def _apply(self, values: dict) -> None:
        with self._state.lock:
            for key, val in values.items():
                if hasattr(self._state, key):
                    setattr(self._state, key, val)
```

- [ ] **Step 2: Verify existing decoder tests still pass**

```bash
pytest tests/test_can_handler.py -v
```

Expected: 8 passed (no regressions).

- [ ] **Step 3: Commit**

```bash
git add can_handler.py
git commit -m "feat: CANListener daemon thread"
```

---

## Task 6: OdometerAccumulator

**Files:**
- Create: `gps_handler.py` (accumulator class only — thread added in Task 7)
- Create: `tests/test_gps_handler.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_gps_handler.py
from gps_handler import OdometerAccumulator


def test_initial_odo_preserved():
    acc = OdometerAccumulator(initial_odo_mi=48231.5)
    assert acc.odo_mi == 48231.5


def test_trip_always_starts_at_zero():
    acc = OdometerAccumulator(initial_odo_mi=48231.5)
    assert acc.trip_mi == 0.0


def test_accumulate_distance_good_fix():
    acc = OdometerAccumulator(initial_odo_mi=0.0)
    # 60 mph for 1 hour = 60 miles
    acc.update(speed_mph=60.0, dt_s=3600.0, hacc_m=5.0)
    assert abs(acc.odo_mi - 60.0) < 0.001
    assert abs(acc.trip_mi - 60.0) < 0.001


def test_no_accumulation_when_hacc_too_high():
    acc = OdometerAccumulator(initial_odo_mi=0.0)
    acc.update(speed_mph=60.0, dt_s=3600.0, hacc_m=50.0)
    assert acc.odo_mi == 0.0
    assert acc.trip_mi == 0.0


def test_save_triggered_after_threshold():
    saves = []
    acc = OdometerAccumulator(initial_odo_mi=0.0, save_callback=saves.append)
    # accumulate 0.05 mi — below 0.1 mi threshold, no save
    acc.update(speed_mph=60.0, dt_s=180.0, hacc_m=5.0)
    assert len(saves) == 0
    # accumulate another 0.07 mi — crosses 0.1 mi threshold
    acc.update(speed_mph=60.0, dt_s=252.0, hacc_m=5.0)
    assert len(saves) == 1


def test_update_returns_fix_status():
    acc = OdometerAccumulator(initial_odo_mi=0.0)
    valid = acc.update(speed_mph=30.0, dt_s=1.0, hacc_m=3.0)
    assert valid is True
    invalid = acc.update(speed_mph=30.0, dt_s=1.0, hacc_m=99.0)
    assert invalid is False
```

- [ ] **Step 2: Run — verify failure**

```bash
pytest tests/test_gps_handler.py -v
```

Expected: `ModuleNotFoundError: No module named 'gps_handler'`

- [ ] **Step 3: Implement OdometerAccumulator**

```python
# gps_handler.py
from __future__ import annotations
import os
import json
import logging
import threading
from typing import Callable, Optional

log = logging.getLogger(__name__)

ODO_PATH = '/data/odo.json'
HACC_MAX_M = 10.0
SAVE_INTERVAL_MI = 0.1


class OdometerAccumulator:
    """
    Pure ODO/trip accumulation logic. No I/O dependency except an optional
    save_callback so unit tests can verify save triggers without filesystem.
    """

    def __init__(
        self,
        initial_odo_mi: float = 0.0,
        save_callback: Optional[Callable[[float, float], None]] = None,
    ):
        self.odo_mi: float = initial_odo_mi
        self.trip_mi: float = 0.0   # always resets each ignition cycle
        self._last_save_odo: float = initial_odo_mi
        self._save_cb = save_callback

    def update(self, speed_mph: float, dt_s: float, hacc_m: float) -> bool:
        """
        Accumulate distance if fix is valid (hacc < HACC_MAX_M).
        Fires save_callback when ODO crosses SAVE_INTERVAL_MI threshold.
        Returns True if fix was valid.
        """
        if hacc_m >= HACC_MAX_M:
            return False

        delta_mi = speed_mph * (dt_s / 3600.0)
        self.odo_mi += delta_mi
        self.trip_mi += delta_mi

        if self._save_cb and (self.odo_mi - self._last_save_odo) >= SAVE_INTERVAL_MI:
            self._save_cb(self.odo_mi, self.trip_mi)
            self._last_save_odo = self.odo_mi

        return True
```

- [ ] **Step 4: Run — verify all pass**

```bash
pytest tests/test_gps_handler.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add gps_handler.py tests/test_gps_handler.py
git commit -m "feat: OdometerAccumulator with save callback and full tests"
```

---

## Task 7: GPSListener Thread + Atomic Save

**Files:**
- Modify: `gps_handler.py` — append `GPSListener` class and `_atomic_save()`

- [ ] **Step 1: Append to gps_handler.py**

```python
# Append to gps_handler.py (after OdometerAccumulator)
import time
import gps
from vehicle_state import VehicleState

GPS_TIMEOUT_S = 5.0


def _load_odo() -> float:
    try:
        with open(ODO_PATH) as f:
            return float(json.load(f).get('odo_mi', 0.0))
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return 0.0


def _atomic_save(odo_mi: float, trip_mi: float) -> None:
    """Write ODO to /data/odo.json atomically. Power-safe via os.replace()."""
    tmp = ODO_PATH + '.tmp'
    try:
        with open(tmp, 'w') as f:
            json.dump({'odo_mi': odo_mi, 'trip_mi': trip_mi}, f)
        os.replace(tmp, ODO_PATH)
    except OSError as e:
        log.warning("ODO save failed: %s", e)


class GPSListener(threading.Thread):
    """
    Daemon thread: reads speed/position from gpsd, accumulates ODO,
    and writes into shared VehicleState.
    """

    def __init__(self, state: VehicleState):
        super().__init__(daemon=True, name='GPSListener')
        self._state = state
        self._running = False
        self._acc = OdometerAccumulator(
            initial_odo_mi=_load_odo(),
            save_callback=_atomic_save,
        )
        self._last_fix_time = 0.0

    def run(self) -> None:
        self._running = True
        session = gps.gps(mode=gps.WATCH_ENABLE | gps.WATCH_NEWSTYLE)
        last_time = time.monotonic()
        log.info("GPS listener started")

        while self._running:
            try:
                report = session.next()
            except StopIteration:
                break
            except Exception as e:
                log.warning("GPS read error: %s", e)
                continue

            now = time.monotonic()
            dt_s = now - last_time
            last_time = now

            if report['class'] != 'TPV':
                continue

            speed_ms = getattr(report, 'speed', 0.0) or 0.0
            hacc_m = getattr(report, 'epx', 999.0) or 999.0
            speed_mph = speed_ms * 2.23694

            fix_valid = self._acc.update(speed_mph, dt_s, hacc_m)
            if fix_valid:
                self._last_fix_time = now

            gps_ok = (now - self._last_fix_time) < GPS_TIMEOUT_S

            with self._state.lock:
                if fix_valid:
                    self._state.speed_mph = speed_mph
                self._state.odo_mi = self._acc.odo_mi
                self._state.trip_mi = self._acc.trip_mi
                self._state.gps_fix = gps_ok

    def stop(self) -> None:
        self._running = False
        _atomic_save(self._acc.odo_mi, self._acc.trip_mi)
        log.info("GPS listener stopped, ODO saved")
```

- [ ] **Step 2: Verify accumulator tests still pass**

```bash
pytest tests/test_gps_handler.py -v
```

Expected: 6 passed.

- [ ] **Step 3: Commit**

```bash
git add gps_handler.py
git commit -m "feat: GPSListener thread with atomic ODO persistence"
```

---

## Task 8: Config Loader

**Files:**
- Create: `config_loader.py`

No separate test needed — config loader is a thin YAML wrapper; tested implicitly by GaugeRenderer tests.

- [ ] **Step 1: Write config_loader.py**

```python
# config_loader.py
from __future__ import annotations
import yaml
from pathlib import Path

_BASE = Path(__file__).parent / 'config'


def load_style() -> dict:
    with open(_BASE / 'style.yaml') as f:
        return yaml.safe_load(f)['theme']


def load_gauges() -> dict:
    with open(_BASE / 'gauges.yaml') as f:
        return yaml.safe_load(f)
```

- [ ] **Step 2: Smoke-test the loader**

```bash
python3 -c "from config_loader import load_style, load_gauges; s=load_style(); g=load_gauges(); print(s['bg_color'], g['tachometer']['max_val'])"
```

Expected output: `[1, 6, 8] 6000`

- [ ] **Step 3: Commit**

```bash
git add config_loader.py
git commit -m "feat: YAML config loader"
```

---

## Task 9: GaugeRenderer — Init + Angle Math

**Files:**
- Create: `dashboard_ui.py`
- Create: `tests/test_dashboard_ui.py`

- [ ] **Step 1: Write failing angle-math tests**

```python
# tests/test_dashboard_ui.py
import numpy as np
from dashboard_ui import GaugeRenderer

STYLE = {
    'bg_color':      [1, 6, 8],
    'arc_active':    [0, 122, 196],
    'arc_inactive':  [0, 18, 26],
    'arc_redzone':   [0, 20, 140],
    'needle_color':  [128, 210, 255],
    'hub_color':     [0, 122, 196],
    'label_color':   [0, 66, 90],
    'value_color':   [128, 210, 255],
    'warning_amber': [0, 165, 255],
    'warning_red':   [0, 0, 220],
}

GAUGES = {
    'tachometer': {
        'center': [480, 360], 'radius': 280, 'arc_width': 18,
        'start_angle': 150, 'sweep': 240,
        'min_val': 0, 'max_val': 6000, 'redzone_val': 4500,
        'label': 'RPM', 'lerp_alpha': 0.15,
    },
    'speedometer': {
        'center': [1440, 360], 'radius': 280, 'arc_width': 18,
        'start_angle': 150, 'sweep': 240,
        'min_val': 0, 'max_val': 160, 'redzone_val': None,
        'label': 'MPH', 'lerp_alpha': 0.10,
    },
    'center_panel': {
        'readouts': [
            {'label': 'MAP',  'state_field': 'map_kpa', 'unit': 'kPa',
             'pos': [760, 160], 'format': '{:.0f}', 'font_scale': 1.8},
            {'label': 'AFR',  'state_field': 'afr',    'unit': '',
             'pos': [960, 360], 'format': '{:.1f}', 'font_scale': 3.5},
        ]
    },
}


def make_renderer():
    return GaugeRenderer(style=STYLE, gauges=GAUGES)


def test_val_to_angle_at_zero():
    r = make_renderer()
    assert r.val_to_angle(0, 'tachometer') == 150.0


def test_val_to_angle_at_max():
    r = make_renderer()
    assert abs(r.val_to_angle(6000, 'tachometer') - 390.0) < 0.001


def test_val_to_angle_midpoint():
    r = make_renderer()
    # 3000 RPM = 50% of 6000 → 150 + 0.5*240 = 270.0
    assert abs(r.val_to_angle(3000, 'tachometer') - 270.0) < 0.001


def test_val_to_angle_clamped_above_max():
    r = make_renderer()
    assert r.val_to_angle(9999, 'tachometer') <= 390.0


def test_val_to_angle_clamped_below_min():
    r = make_renderer()
    assert r.val_to_angle(-100, 'tachometer') >= 150.0
```

- [ ] **Step 2: Run — verify failure**

```bash
pytest tests/test_dashboard_ui.py -v
```

Expected: `ModuleNotFoundError: No module named 'dashboard_ui'`

- [ ] **Step 3: Implement GaugeRenderer init + val_to_angle**

```python
# dashboard_ui.py
from __future__ import annotations
import math
import time
import numpy as np
import cv2
from typing import Optional


class GaugeRenderer:
    """
    Config-driven OpenCV gauge renderer.
    All colors and geometry come from YAML — no constants in this file.
    """

    def __init__(self, style: dict, gauges: dict):
        self._s = style      # theme dict from style.yaml
        self._g = gauges     # gauges dict from gauges.yaml

    # ── Angle utilities ───────────────────────────────────────────────────────

    def val_to_angle(self, value: float, gauge_name: str) -> float:
        """
        Map a value to a needle angle (degrees, clockwise from 3-o'clock).
        Clamps to [min_val, max_val].
        """
        cfg = self._g[gauge_name]
        pct = max(0.0, min(1.0, (value - cfg['min_val']) /
                           (cfg['max_val'] - cfg['min_val'])))
        return cfg['start_angle'] + pct * cfg['sweep']

    def _angle_to_xy(self, cx: int, cy: int, radius: int,
                     angle_deg: float) -> tuple[int, int]:
        """Convert polar (center + angle) to Cartesian pixel coords."""
        rad = math.radians(angle_deg)
        return (int(cx + radius * math.cos(rad)),
                int(cy + radius * math.sin(rad)))
```

- [ ] **Step 4: Run — verify angle tests pass**

```bash
pytest tests/test_dashboard_ui.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add dashboard_ui.py tests/test_dashboard_ui.py
git commit -m "feat: GaugeRenderer init and angle math with tests"
```

---

## Task 10: GaugeRenderer — Arc + Needle Primitives

**Files:**
- Modify: `dashboard_ui.py` — add `_draw_arc_track()` and `_draw_needle()`
- Modify: `tests/test_dashboard_ui.py` — add no-crash tests

- [ ] **Step 1: Add no-crash rendering tests to test_dashboard_ui.py**

```python
# Append to tests/test_dashboard_ui.py

def make_canvas():
    return np.zeros((720, 1920, 3), dtype=np.uint8)


def test_draw_arc_track_no_crash():
    r = make_renderer()
    canvas = make_canvas()
    r._draw_arc_track(canvas, 'tachometer', active_angle=270.0)
    assert canvas.shape == (720, 1920, 3)


def test_draw_needle_no_crash():
    r = make_renderer()
    canvas = make_canvas()
    r._draw_needle(canvas, 'tachometer', needle_angle=270.0)
    assert canvas.shape == (720, 1920, 3)
```

- [ ] **Step 2: Run — verify new tests fail**

```bash
pytest tests/test_dashboard_ui.py::test_draw_arc_track_no_crash -v
```

Expected: `AttributeError: 'GaugeRenderer' object has no attribute '_draw_arc_track'`

- [ ] **Step 3: Implement arc and needle primitives in dashboard_ui.py**

```python
# Append methods to GaugeRenderer class in dashboard_ui.py

    # ── Primitives ────────────────────────────────────────────────────────────

    def _draw_arc_track(self, canvas: np.ndarray, gauge_name: str,
                        active_angle: float) -> None:
        """
        Draw the gauge arc: inactive track, then active fill, then optional
        red zone. Uses cv2.ellipse with clockwise angle convention.
        """
        cfg = self._g[gauge_name]
        cx, cy = cfg['center']
        r = cfg['radius']
        w = cfg['arc_width']
        sa = cfg['start_angle']
        ea = sa + cfg['sweep']
        axes = (r, r)

        # 1. Full inactive track
        cv2.ellipse(canvas, (cx, cy), axes, 0, sa, ea,
                    tuple(self._s['arc_inactive']), w, cv2.LINE_AA)

        # 2. Active (value) portion
        cv2.ellipse(canvas, (cx, cy), axes, 0, sa, active_angle,
                    tuple(self._s['arc_active']), w, cv2.LINE_AA)

        # 3. Red zone (if configured)
        if cfg.get('redzone_val') is not None:
            redzone_angle = self.val_to_angle(cfg['redzone_val'], gauge_name)
            cv2.ellipse(canvas, (cx, cy), axes, 0, redzone_angle, ea,
                        tuple(self._s['arc_redzone']), w, cv2.LINE_AA)

    def _draw_needle(self, canvas: np.ndarray, gauge_name: str,
                     needle_angle: float) -> None:
        """Draw the needle line and pivot hub circle."""
        cfg = self._g[gauge_name]
        cx, cy = cfg['center']
        r = cfg['radius']

        tip = self._angle_to_xy(cx, cy, int(r * 0.88), needle_angle)
        tail = self._angle_to_xy(cx, cy, int(r * 0.15), needle_angle + 180)

        cv2.line(canvas, tail, tip,
                 tuple(self._s['needle_color']), 3, cv2.LINE_AA)
        cv2.circle(canvas, (cx, cy), 14,
                   tuple(self._s['hub_color']), -1, cv2.LINE_AA)
        cv2.circle(canvas, (cx, cy), 6,
                   tuple(self._s['arc_inactive']), -1, cv2.LINE_AA)
```

- [ ] **Step 4: Run all dashboard tests**

```bash
pytest tests/test_dashboard_ui.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add dashboard_ui.py tests/test_dashboard_ui.py
git commit -m "feat: arc track and needle drawing primitives"
```

---

## Task 11: GaugeRenderer — Tachometer, Speedometer, Readout

**Files:**
- Modify: `dashboard_ui.py` — add `draw_tachometer()`, `draw_speedometer()`, `draw_readout()`, `draw_center_panel()`
- Modify: `tests/test_dashboard_ui.py` — add no-crash + GPS-loss tests

- [ ] **Step 1: Add tests**

```python
# Append to tests/test_dashboard_ui.py
from vehicle_state import VehicleState


def make_state(**kwargs):
    s = VehicleState(**kwargs)
    s.lock = None
    return s


def test_draw_tachometer_no_crash():
    r = make_renderer()
    canvas = make_canvas()
    r.draw_tachometer(canvas, rpm=3400.0, needle_angle=270.0)
    assert canvas.shape == (720, 1920, 3)


def test_draw_speedometer_no_crash():
    r = make_renderer()
    canvas = make_canvas()
    r.draw_speedometer(canvas, speed_mph=65.0, needle_angle=250.0, gps_fix=True)
    assert canvas.shape == (720, 1920, 3)


def test_draw_speedometer_no_gps_no_crash():
    r = make_renderer()
    canvas = make_canvas()
    r.draw_speedometer(canvas, speed_mph=0.0, needle_angle=150.0, gps_fix=False)
    assert canvas.shape == (720, 1920, 3)


def test_draw_center_panel_no_crash():
    r = make_renderer()
    canvas = make_canvas()
    state = make_state(map_kpa=98.0, clt_f=195.0, afr=14.7,
                       odo_mi=48231.0, trip_mi=127.4, gps_fix=True)
    r.draw_center_panel(canvas, state)
    assert canvas.shape == (720, 1920, 3)
```

- [ ] **Step 2: Run — verify failures**

```bash
pytest tests/test_dashboard_ui.py -v
```

Expected: new tests fail with `AttributeError`.

- [ ] **Step 3: Implement draw methods in dashboard_ui.py**

```python
# Append methods to GaugeRenderer class in dashboard_ui.py

    # ── Gauge drawing ─────────────────────────────────────────────────────────

    def draw_tachometer(self, canvas: np.ndarray, rpm: float,
                        needle_angle: float) -> None:
        """Draw full tachometer: arc track + needle + RPM value + label."""
        cfg = self._g['tachometer']
        cx, cy = cfg['center']
        active_angle = self.val_to_angle(rpm, 'tachometer')

        self._draw_arc_track(canvas, 'tachometer', active_angle)
        self._draw_needle(canvas, 'tachometer', needle_angle)

        # Digital RPM value below needle pivot
        rpm_str = f"{int(rpm):,}"
        self._put_centered_text(canvas, rpm_str, cx, cy - 60,
                                self._s['value_color'], font_scale=1.6,
                                thickness=2)
        self._put_centered_text(canvas, cfg['label'], cx, cy - 30,
                                self._s['label_color'], font_scale=0.7,
                                thickness=1)

        # Scale tick labels
        for pct, label in [(0, '0'), (0.33, '2K'), (0.67, '4K'), (1.0, '6K')]:
            angle = cfg['start_angle'] + pct * cfg['sweep']
            lx, ly = self._angle_to_xy(cx, cy, cfg['radius'] + 22, angle)
            self._put_centered_text(canvas, label, lx, ly,
                                    self._s['label_color'], font_scale=0.5)

    def draw_speedometer(self, canvas: np.ndarray, speed_mph: float,
                         needle_angle: float, gps_fix: bool) -> None:
        """Draw full speedometer. Shows '---' when GPS fix is lost."""
        cfg = self._g['speedometer']
        cx, cy = cfg['center']
        active_angle = self.val_to_angle(speed_mph, 'speedometer')

        self._draw_arc_track(canvas, 'speedometer', active_angle)
        self._draw_needle(canvas, 'speedometer', needle_angle)

        if gps_fix:
            speed_str = f"{int(speed_mph)}"
            color = self._s['value_color']
        else:
            speed_str = "---"
            color = self._s['label_color']

        self._put_centered_text(canvas, speed_str, cx, cy - 60,
                                color, font_scale=1.6, thickness=2)
        self._put_centered_text(canvas, cfg['label'], cx, cy - 30,
                                self._s['label_color'], font_scale=0.7,
                                thickness=1)

        # GPS indicator dot
        dot_color = self._s['arc_active'] if gps_fix else self._s['arc_redzone']
        cv2.circle(canvas, (cx, cy + 50), 6, tuple(dot_color), -1, cv2.LINE_AA)
        self._put_centered_text(canvas, 'GPS', cx + 16, cy + 55,
                                self._s['label_color'], font_scale=0.45)

        for pct, label in [(0, '0'), (0.25, '40'), (0.5, '80'),
                           (0.75, '120'), (1.0, '160')]:
            angle = cfg['start_angle'] + pct * cfg['sweep']
            lx, ly = self._angle_to_xy(cx, cy, cfg['radius'] + 22, angle)
            self._put_centered_text(canvas, label, lx, ly,
                                    self._s['label_color'], font_scale=0.5)

    def draw_readout(self, canvas: np.ndarray, label: str, value_str: str,
                     unit: str, pos: list, font_scale: float) -> None:
        """Draw a single labeled digital readout at pos = [x, y]."""
        x, y = pos
        self._put_centered_text(canvas, label, x, y - 28,
                                self._s['label_color'], font_scale=0.55)
        self._put_centered_text(canvas, value_str, x, y,
                                self._s['value_color'], font_scale=font_scale,
                                thickness=2)
        if unit:
            self._put_centered_text(canvas, unit, x, y + 28,
                                    self._s['label_color'], font_scale=0.5)

    def draw_center_panel(self, canvas: np.ndarray, state) -> None:
        """
        Draw all center panel readouts defined in gauges.yaml center_panel.
        Reads values dynamically from state by field name — adding a new
        readout only requires a gauges.yaml entry.
        """
        for rd in self._g['center_panel']['readouts']:
            field = rd['state_field']
            raw_val = getattr(state, field, None)

            if raw_val is None or (field in ('odo_mi', 'trip_mi')
                                   and not getattr(state, 'gps_fix', True)):
                value_str = 'NO GPS'
            else:
                value_str = rd['format'].format(raw_val)

            self.draw_readout(canvas, rd['label'], value_str, rd['unit'],
                              rd['pos'], rd['font_scale'])

        # Vertical separator lines
        col = tuple(self._s['arc_inactive'])
        cv2.line(canvas, (640, 40), (640, 680), col, 1)
        cv2.line(canvas, (1280, 40), (1280, 680), col, 1)

    # ── Text helper ───────────────────────────────────────────────────────────

    def _put_centered_text(self, canvas: np.ndarray, text: str,
                           cx: int, cy: int, color: list,
                           font_scale: float = 1.0,
                           thickness: int = 1) -> None:
        font = cv2.FONT_HERSHEY_SIMPLEX
        (tw, th), _ = cv2.getTextSize(text, font, font_scale, thickness)
        cv2.putText(canvas, text,
                    (cx - tw // 2, cy + th // 2),
                    font, font_scale, tuple(color), thickness, cv2.LINE_AA)
```

- [ ] **Step 4: Run all tests**

```bash
pytest tests/test_dashboard_ui.py -v
```

Expected: 12 passed.

- [ ] **Step 5: Commit**

```bash
git add dashboard_ui.py tests/test_dashboard_ui.py
git commit -m "feat: tachometer, speedometer, center panel rendering"
```

---

## Task 12: GaugeRenderer — Warning Overlay + render_frame

**Files:**
- Modify: `dashboard_ui.py` — add `draw_warning_overlay()` and `render_frame()`
- Modify: `tests/test_dashboard_ui.py` — warning no-crash tests

- [ ] **Step 1: Add warning tests**

```python
# Append to tests/test_dashboard_ui.py

def test_draw_warning_overlay_no_crash():
    r = make_renderer()
    canvas = make_canvas()
    r.draw_warning_overlay(canvas, "TEMP HIGH — 215°F",
                           r._s['warning_amber'], pulse_alpha=0.6)
    assert canvas.shape == (720, 1920, 3)


def test_render_frame_no_crash():
    r = make_renderer()
    canvas = make_canvas()
    state = make_state(rpm=3400.0, speed_mph=65.0, map_kpa=98.0,
                       clt_f=195.0, afr=14.7, odo_mi=48231.0,
                       trip_mi=127.4, gps_fix=True)
    interp = {'tach_angle': 270.0, 'speedo_angle': 250.0}
    r.render_frame(canvas, state, interp)
    assert canvas.shape == (720, 1920, 3)


def test_render_frame_high_clt_triggers_warning():
    r = make_renderer()
    canvas = make_canvas()
    state = make_state(clt_f=215.0, gps_fix=True)
    interp = {'tach_angle': 150.0, 'speedo_angle': 150.0}
    before = canvas.copy()
    r.render_frame(canvas, state, interp)
    # Canvas should differ from blank after render
    assert not np.array_equal(canvas, before)
```

- [ ] **Step 2: Run — verify failures**

```bash
pytest tests/test_dashboard_ui.py -v
```

- [ ] **Step 3: Implement warning overlay and render_frame**

```python
# Append methods to GaugeRenderer class in dashboard_ui.py

    # ── Warnings ──────────────────────────────────────────────────────────────

    def draw_warning_overlay(self, canvas: np.ndarray, message: str,
                             color: list, pulse_alpha: float = 1.0) -> None:
        """
        Semi-transparent full-screen warning overlay.
        pulse_alpha comes from sin(time) in the render loop for pulsing effect.
        """
        overlay = canvas.copy()
        h, w = canvas.shape[:2]
        alpha = 0.35 * pulse_alpha
        cv2.rectangle(overlay, (0, 0), (w, h), tuple(color), -1)
        cv2.addWeighted(overlay, alpha, canvas, 1 - alpha, 0, canvas)

        self._put_centered_text(canvas, message, w // 2, h // 2,
                                self._s['value_color'],
                                font_scale=2.5, thickness=3)

    # ── Frame orchestration ───────────────────────────────────────────────────

    def render_frame(self, canvas: np.ndarray, state, interp: dict) -> None:
        """
        Single entry point for the render loop. Clears canvas, draws all
        components, then applies any active warning overlays on top.
        """
        # Clear to background color
        canvas[:] = tuple(self._s['bg_color'])

        # Gauges
        self.draw_tachometer(canvas, state.rpm, interp['tach_angle'])
        self.draw_speedometer(canvas, state.speed_mph,
                              interp['speedo_angle'],
                              getattr(state, 'gps_fix', True))
        self.draw_center_panel(canvas, state)

        # Warnings (stack vertically if multiple)
        warnings = self._collect_warnings(state)
        pulse = abs(math.sin(time.monotonic() * 2.5))
        for i, (msg, color) in enumerate(warnings):
            # Offset each warning so they don't overlap
            self.draw_warning_overlay(canvas, msg, color,
                                      pulse_alpha=pulse if i == 0 else 0.8)

    def _collect_warnings(self, state) -> list[tuple[str, list]]:
        """Return list of (message, color) tuples for active warnings."""
        warnings = []
        if state.clt_f > 210:
            warnings.append(
                (f"TEMP HIGH  {state.clt_f:.0f}F", self._s['warning_amber'])
            )
        if state.afr < 11.0:
            warnings.append(("RICH", self._s['warning_amber']))
        elif state.afr > 16.5:
            warnings.append(("LEAN  CHECK ENGINE", self._s['warning_red']))
        return warnings
```

- [ ] **Step 4: Run all tests**

```bash
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add dashboard_ui.py tests/test_dashboard_ui.py
git commit -m "feat: warning overlay and render_frame orchestration"
```

---

## Task 13: main.py — Render Loop + Shutdown

**Files:**
- Create: `main.py`

No unit tests for main — it wires threads together and owns the OS-level event loop. Tested by running the dashboard.

- [ ] **Step 1: Write main.py**

```python
# main.py
"""
Nova Dashboard — main entry point.
Launches CAN and GPS daemon threads, then runs the 60 FPS OpenCV render loop.
"""
from __future__ import annotations
import signal
import sys
import time
import math
import logging
import numpy as np
import cv2

from vehicle_state import VehicleState
from can_handler import CANListener
from gps_handler import GPSListener
from dashboard_ui import GaugeRenderer
from config_loader import load_style, load_gauges

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(name)s %(levelname)s %(message)s',
    handlers=[logging.StreamHandler(sys.stderr)],
)
log = logging.getLogger('main')

TARGET_FPS = 60
FRAME_TIME = 1.0 / TARGET_FPS
WIDTH, HEIGHT = 1920, 720


def main() -> None:
    style = load_style()
    gauges = load_gauges()

    state = VehicleState()
    renderer = GaugeRenderer(style=style, gauges=gauges)

    # Daemon threads
    can_thread = CANListener(state, channel='can0')
    gps_thread = GPSListener(state)

    # Interpolation state — needles start at zero position
    interp = {
        'tach_angle':  float(gauges['tachometer']['start_angle']),
        'speedo_angle': float(gauges['speedometer']['start_angle']),
    }
    tach_alpha   = gauges['tachometer']['lerp_alpha']
    speedo_alpha = gauges['speedometer']['lerp_alpha']

    # Shutdown flag — set by SIGTERM or 'q' key
    running = True

    def _shutdown(sig, frame):
        nonlocal running
        log.info("Shutdown signal received")
        running = False

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    # OpenCV fullscreen window
    cv2.namedWindow('Nova Dashboard', cv2.WINDOW_NORMAL)
    cv2.setWindowProperty('Nova Dashboard',
                          cv2.WND_PROP_FULLSCREEN,
                          cv2.WINDOW_FULLSCREEN)

    canvas = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)

    # Start data threads
    can_thread.start()
    gps_thread.start()
    log.info("Dashboard started — targeting %d FPS", TARGET_FPS)

    try:
        while running:
            frame_start = time.monotonic()

            # Snapshot state (lock held only for copy duration)
            snap = state.snapshot()

            # Update needle interpolation
            tach_target   = renderer.val_to_angle(snap.rpm,       'tachometer')
            speedo_target = renderer.val_to_angle(snap.speed_mph, 'speedometer')
            interp['tach_angle']   += (tach_target   - interp['tach_angle'])   * tach_alpha
            interp['speedo_angle'] += (speedo_target - interp['speedo_angle']) * speedo_alpha

            # Render frame to offscreen buffer
            renderer.render_frame(canvas, snap, interp)

            # Flip to display
            cv2.imshow('Nova Dashboard', canvas)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord('q'), 27):   # q or ESC
                running = False

            # Frame rate cap
            elapsed = time.monotonic() - frame_start
            sleep_ms = FRAME_TIME - elapsed
            if sleep_ms > 0:
                time.sleep(sleep_ms)

    finally:
        log.info("Stopping threads...")
        can_thread.stop()
        gps_thread.stop()
        can_thread.join(timeout=2.0)
        gps_thread.join(timeout=2.0)
        cv2.destroyAllWindows()
        log.info("Clean shutdown complete")


if __name__ == '__main__':
    main()
```

- [ ] **Step 2: Run a full suite check**

```bash
pytest tests/ -v
```

Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "feat: main render loop with thread orchestration and clean shutdown"
```

---

## Task 14: Simulation Mode (Dev-time Testing Without Hardware)

**Files:**
- Create: `simulate.py`

Allows the dashboard to be developed and previewed on any machine without CAN or GPS hardware.

- [ ] **Step 1: Write simulate.py**

```python
# simulate.py
"""
Run the dashboard with simulated CAN + GPS data.
Usage: python3 simulate.py
No hardware required — useful for UI development on any machine.
"""
from __future__ import annotations
import math
import time
import threading
import numpy as np
import cv2

from vehicle_state import VehicleState
from dashboard_ui import GaugeRenderer
from config_loader import load_style, load_gauges

TARGET_FPS = 60
FRAME_TIME = 1.0 / TARGET_FPS
WIDTH, HEIGHT = 1920, 720


def _simulate_state(state: VehicleState) -> None:
    """Update state with slowly cycling simulated values."""
    while True:
        t = time.monotonic()
        with state.lock:
            state.rpm       = 800 + 2600 * abs(math.sin(t * 0.3))
            state.speed_mph = 30 + 50 * abs(math.sin(t * 0.2))
            state.map_kpa   = 60 + 40 * abs(math.sin(t * 0.4))
            state.clt_f     = 185 + 30 * abs(math.sin(t * 0.05))
            state.afr       = 13.0 + 4.0 * abs(math.sin(t * 0.25))
            state.batt_v    = 13.8
            state.odo_mi    = 48231 + t / 60.0
            state.trip_mi   = t / 60.0
            state.gps_fix   = True
        time.sleep(0.05)   # 20 Hz simulated data rate


def main() -> None:
    style  = load_style()
    gauges = load_gauges()
    state  = VehicleState()

    sim_thread = threading.Thread(target=_simulate_state,
                                  args=(state,), daemon=True)
    sim_thread.start()

    renderer = GaugeRenderer(style=style, gauges=gauges)
    interp = {
        'tach_angle':   float(gauges['tachometer']['start_angle']),
        'speedo_angle': float(gauges['speedometer']['start_angle']),
    }
    tach_alpha   = gauges['tachometer']['lerp_alpha']
    speedo_alpha = gauges['speedometer']['lerp_alpha']

    cv2.namedWindow('Nova Dashboard — SIMULATION', cv2.WINDOW_NORMAL)
    cv2.resizeWindow('Nova Dashboard — SIMULATION', WIDTH, HEIGHT)
    canvas = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)

    while True:
        frame_start = time.monotonic()
        snap = state.snapshot()

        tach_target   = renderer.val_to_angle(snap.rpm,       'tachometer')
        speedo_target = renderer.val_to_angle(snap.speed_mph, 'speedometer')
        interp['tach_angle']   += (tach_target   - interp['tach_angle'])   * tach_alpha
        interp['speedo_angle'] += (speedo_target - interp['speedo_angle']) * speedo_alpha

        renderer.render_frame(canvas, snap, interp)
        cv2.imshow('Nova Dashboard — SIMULATION', canvas)

        if cv2.waitKey(1) & 0xFF in (ord('q'), 27):
            break

        elapsed = time.monotonic() - frame_start
        if FRAME_TIME - elapsed > 0:
            time.sleep(FRAME_TIME - elapsed)

    cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
```

- [ ] **Step 2: Run simulation to visually verify the dashboard**

```bash
python3 simulate.py
```

Expected: fullscreen (or resizable) window appears showing the amber-on-black cluster with animated needles and cycling readouts. Press `q` to exit.

- [ ] **Step 3: Commit**

```bash
git add simulate.py
git commit -m "feat: simulation mode for UI development without hardware"
```

---

## Task 15: Setup Scripts + systemd Service

**Files:**
- Create: `scripts/setup_can.sh`
- Create: `scripts/setup_readonly.sh`
- Create: `scripts/nova-dashboard.service`

- [ ] **Step 1: Write setup_can.sh**

```bash
#!/usr/bin/env bash
# scripts/setup_can.sh
# Bring up SocketCAN interface at 500 kbps.
# Run as root (called by systemd ExecStartPre).
set -euo pipefail

IFACE="${CAN_IFACE:-can0}"
BITRATE="${CAN_BITRATE:-500000}"

ip link set "$IFACE" down 2>/dev/null || true
ip link set "$IFACE" type can bitrate "$BITRATE"
ip link set "$IFACE" up

# Optional: configure u-blox GPS to 5 Hz if device is present
if [ -e /dev/ttyACM0 ]; then
    # UBX-CFG-RATE: set measurement rate to 200ms (5 Hz)
    printf '\xb5\x62\x06\x08\x06\x00\xc8\x00\x01\x00\x01\x00\xde\x6a' \
        > /dev/ttyACM0 2>/dev/null || true
fi

echo "CAN interface $IFACE up at ${BITRATE} bps"
```

- [ ] **Step 2: Write setup_readonly.sh**

```bash
#!/usr/bin/env bash
# scripts/setup_readonly.sh
# One-time setup: enable Pi OS overlayfs (read-only root) and
# create /data partition entry for ODO persistence.
# Run ONCE as root after initial Pi OS setup.
set -euo pipefail

echo "=== Nova Dashboard — Read-Only Filesystem Setup ==="

# 1. Enable overlayfs (requires reboot to take effect)
raspi-config nonint enable_overlayfs

# 2. Create /data mount point
mkdir -p /data

# 3. Append /data partition to fstab if not already present
# Assumes the data partition is /dev/mmcblk0p3 (third SD partition).
# Adjust if your partition layout differs.
if ! grep -q '/data' /etc/fstab; then
    echo '/dev/mmcblk0p3  /data  vfat  rw,sync,noatime,uid=1000,gid=1000  0  2' \
        >> /etc/fstab
    echo "Added /data to /etc/fstab"
fi

# 4. Install systemd service
cp "$(dirname "$0")/nova-dashboard.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable nova-dashboard.service

echo ""
echo "Setup complete. REBOOT to activate read-only root filesystem."
echo "After reboot, verify with: mount | grep 'on / '"
```

- [ ] **Step 3: Write nova-dashboard.service**

```ini
# scripts/nova-dashboard.service
[Unit]
Description=Nova Dashboard — 1974 Chevrolet Nova Instrument Cluster
After=network.target gpsd.service
Wants=gpsd.service

[Service]
Type=simple
User=pi
Environment=DISPLAY=:0
WorkingDirectory=/home/pi/nova-dashboard-cv
ExecStartPre=/bin/bash /home/pi/nova-dashboard-cv/scripts/setup_can.sh
ExecStart=/home/pi/nova-dashboard-cv/.venv/bin/python3 /home/pi/nova-dashboard-cv/main.py
Restart=always
RestartSec=3
StandardOutput=null
StandardError=journal
KillMode=process
TimeoutStopSec=5

[Install]
WantedBy=graphical.target
```

- [ ] **Step 4: Make scripts executable**

```bash
chmod +x scripts/setup_can.sh scripts/setup_readonly.sh
```

- [ ] **Step 5: Final test run**

```bash
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 6: Final commit**

```bash
git add scripts/ main.py simulate.py
git commit -m "feat: setup scripts and systemd service — dashboard complete"
```

---

## Pi 5 Deployment Checklist

After copying the project to the Pi:

```bash
# 1. Install system packages
sudo apt update && sudo apt install -y gpsd gpsd-clients can-utils python3-venv

# 2. Create virtualenv and install deps
cd ~/nova-dashboard-cv
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 3. Enable gpsd for u-blox
sudo systemctl enable --now gpsd
# Verify: cgps -s

# 4. One-time read-only setup (WILL REBOOT)
sudo bash scripts/setup_readonly.sh

# 5. After reboot — verify ODO path is writable
touch /data/test && rm /data/test && echo "OK"

# 6. Verify CAN
sudo bash scripts/setup_can.sh
candump can0   # should show Speeduino frames

# 7. Run dashboard
python3 main.py
```
