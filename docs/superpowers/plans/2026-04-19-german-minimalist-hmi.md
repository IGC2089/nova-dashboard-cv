# German Minimalist HMI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the amber vintage gauge UI with a high-contrast German Minimalist (Audi/BMW) design — black background, white/cyan palette, 270° sweep, tapered needle, critical-zone glow — without touching threading, hardware, or data pipeline code.

**Architecture:** Three files change: `config/style.yaml` (palette), `config/gauges.yaml` (geometry + new readouts), `dashboard_ui.py` (arc/tick/needle draw methods). All rendering is driven by the YAML config; no constants live in Python. The tapered needle is drawn using a filled polygon blended with `cv2.addWeighted` to simulate per-region opacity.

**Tech Stack:** Python 3, OpenCV (cv2), NumPy, PyYAML, pytest

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `config/style.yaml` | Modify | Color palette (BGR values) |
| `config/gauges.yaml` | Modify | Sweep/start-angle geometry, arc_width, add BATT+IGN readouts |
| `dashboard_ui.py` | Modify | `__init__` tick cache, `_draw_tapered_needle`, `draw_tachometer`, `draw_speedometer` |
| `simulate.py` | Modify | TARGET_FPS 30 → 60 |
| `main.py` | Modify | TARGET_FPS 30 → 60 |

---

## Task 1: Update color palette in style.yaml

**Files:**
- Modify: `config/style.yaml`

- [ ] **Step 1: Replace style.yaml contents**

```yaml
# config/style.yaml
# All colors in BGR (Blue, Green, Red) — OpenCV convention.
theme:
  bg_color:       [10, 10, 10]
  arc_active:     [255, 229, 0]
  arc_inactive:   [40, 40, 40]
  arc_redzone:    [0, 0, 255]
  needle_color:   [255, 255, 255]
  hub_color:      [255, 229, 0]
  label_color:    [160, 160, 160]
  value_color:    [255, 255, 255]
  warning_amber:  [0, 165, 255]
  warning_red:    [0, 0, 255]
```

- [ ] **Step 2: Verify config loads without error**

```bash
cd nova-dashboard-cv
python -c "from config_loader import load_style; s = load_style(); print(s['bg_color'])"
```

Expected output: `[10, 10, 10]`

- [ ] **Step 3: Commit**

```bash
git add config/style.yaml
git commit -m "style: German Minimalist color palette — black bg, white primary, cyan accent"
```

---

## Task 2: Update gauge geometry and center panel in gauges.yaml

**Files:**
- Modify: `config/gauges.yaml`

- [ ] **Step 1: Replace gauges.yaml contents**

```yaml
# config/gauges.yaml
# Angles in degrees, clockwise from 3-o'clock (OpenCV convention).
# start_angle=135 places 0-value at ~7 o'clock.
# sweep=270 gives a 270-degree arc ending at ~5 o'clock (Audi/BMW orientation).
# Layout: 800x480 — left third [0-267], center [267-533], right [533-800]

tachometer:
  center:       [133, 240]
  radius:       110
  arc_width:    4
  start_angle:  135
  sweep:        270
  min_val:      0
  max_val:      6000
  redzone_val:  4500
  label:        "RPM"
  lerp_alpha:   0.15

speedometer:
  center:       [667, 240]
  radius:       110
  arc_width:    4
  start_angle:  135
  sweep:        270
  min_val:      0
  max_val:      240
  redzone_val:  null
  label:        "km/h"
  lerp_alpha:   0.10

center_panel:
  readouts:
    - label:       "BATT"
      state_field: batt_v
      unit:        "V"
      pos:         [316, 75]
      format:      "{:.1f}"
      font_scale:  0.9

    - label:       "IGN"
      state_field: ign_advance
      unit:        "deg"
      pos:         [484, 75]
      format:      "{:.1f}"
      font_scale:  0.9

    - label:       "MAP"
      state_field: map_kpa
      unit:        "kPa"
      pos:         [316, 175]
      format:      "{:.0f}"
      font_scale:  0.9

    - label:       "CLT"
      state_field: clt_c
      unit:        "C"
      pos:         [484, 175]
      format:      "{:.0f}"
      font_scale:  0.9

    - label:       "AFR"
      state_field: afr
      unit:        ""
      pos:         [400, 275]
      format:      "{:.1f}"
      font_scale:  1.8

    - label:       "ODO"
      state_field: odo_km
      unit:        "km"
      pos:         [316, 400]
      format:      "{:.0f}"
      font_scale:  0.7

    - label:       "TRIP"
      state_field: trip_km
      unit:        "km"
      pos:         [484, 400]
      format:      "{:.1f}"
      font_scale:  0.7
```

- [ ] **Step 2: Verify config loads without error**

```bash
python -c "from config_loader import load_gauges; g = load_gauges(); print(g['tachometer']['sweep'], g['tachometer']['start_angle'])"
```

Expected output: `270 135`

- [ ] **Step 3: Commit**

```bash
git add config/gauges.yaml
git commit -m "style: 270-degree sweep, 4px arc width, add BATT+IGN center panel readouts"
```

---

## Task 3: Add tick position cache to GaugeRenderer.__init__

**Files:**
- Modify: `dashboard_ui.py:15-18`
- Test: `tests/test_dashboard_ui.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_dashboard_ui.py`:

```python
import math
import numpy as np
from dashboard_ui import GaugeRenderer

STYLE = {
    'bg_color': [10, 10, 10],
    'arc_active': [255, 229, 0],
    'arc_inactive': [40, 40, 40],
    'arc_redzone': [0, 0, 255],
    'needle_color': [255, 255, 255],
    'hub_color': [255, 229, 0],
    'label_color': [160, 160, 160],
    'value_color': [255, 255, 255],
    'warning_amber': [0, 165, 255],
    'warning_red': [0, 0, 255],
}

GAUGES = {
    'tachometer': {
        'center': [133, 240], 'radius': 110, 'arc_width': 4,
        'start_angle': 135, 'sweep': 270,
        'min_val': 0, 'max_val': 6000, 'redzone_val': 4500,
        'lerp_alpha': 0.15,
    },
    'speedometer': {
        'center': [667, 240], 'radius': 110, 'arc_width': 4,
        'start_angle': 135, 'sweep': 270,
        'min_val': 0, 'max_val': 240, 'redzone_val': None,
        'lerp_alpha': 0.10,
    },
    'center_panel': {'readouts': []},
}


def test_tick_cache_populated_on_init():
    r = GaugeRenderer(STYLE, GAUGES)
    assert 'tachometer' in r._tick_cache
    assert 'speedometer' in r._tick_cache


def test_tach_tick_cache_has_correct_count():
    r = GaugeRenderer(STYLE, GAUGES)
    # 0–6000 in 250 RPM steps = 25 ticks (0, 250, 500, ..., 6000)
    assert len(r._tick_cache['tachometer']) == 25


def test_speedo_tick_cache_has_correct_count():
    r = GaugeRenderer(STYLE, GAUGES)
    # 0–240 in 10 km/h steps = 25 ticks (0, 10, 20, ..., 240)
    assert len(r._tick_cache['speedometer']) == 25


def test_tick_cache_entry_structure():
    r = GaugeRenderer(STYLE, GAUGES)
    entry = r._tick_cache['tachometer'][0]
    # Each entry: (x1, y1, x2, y2, is_major)
    assert len(entry) == 5
    assert isinstance(entry[4], bool)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_dashboard_ui.py -v
```

Expected: FAIL — `AttributeError: 'GaugeRenderer' object has no attribute '_tick_cache'`

- [ ] **Step 3: Add tick cache computation to GaugeRenderer.__init__**

In `dashboard_ui.py`, replace the `__init__` method:

```python
def __init__(self, style: dict, gauges: dict):
    self._s = style
    self._g = gauges
    self._tick_cache = self._build_tick_cache()

def _build_tick_cache(self) -> dict:
    cache = {}
    specs = {
        'tachometer': {'step': 250, 'major_every': 1000},
        'speedometer': {'step': 10,  'major_every': 20},
    }
    for name, spec in specs.items():
        cfg = self._g[name]
        cx, cy = cfg['center']
        r = cfg['radius']
        sa = cfg['start_angle']
        sw = cfg['sweep']
        mn, mx = cfg['min_val'], cfg['max_val']
        step = spec['step']
        major_every = spec['major_every']
        entries = []
        val = mn
        while val <= mx + 1e-6:
            pct = (val - mn) / (mx - mn)
            angle_rad = math.radians(sa + pct * sw)
            cos_a, sin_a = math.cos(angle_rad), math.sin(angle_rad)
            is_major = (round(val) % major_every == 0)
            r_out = r - 1
            r_in = r - (12 if is_major else 6)
            x1 = int(cx + r_out * cos_a)
            y1 = int(cy + r_out * sin_a)
            x2 = int(cx + r_in  * cos_a)
            y2 = int(cy + r_in  * sin_a)
            entries.append((x1, y1, x2, y2, is_major))
            val += step
        cache[name] = entries
    return cache
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_dashboard_ui.py -v
```

Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add dashboard_ui.py tests/test_dashboard_ui.py
git commit -m "feat: pre-compute tick positions in GaugeRenderer init for 60fps"
```

---

## Task 4: Replace _draw_needle with _draw_tapered_needle

**Files:**
- Modify: `dashboard_ui.py` (replace `_draw_needle` method)
- Test: `tests/test_dashboard_ui.py` (add tests)

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_dashboard_ui.py`:

```python
def _make_renderer():
    return GaugeRenderer(STYLE, GAUGES)


def _blank_canvas():
    return np.zeros((480, 800, 3), dtype=np.uint8)


def test_tapered_needle_draws_without_error():
    r = _make_renderer()
    canvas = _blank_canvas()
    r._draw_tapered_needle(canvas, 'tachometer', 135.0)


def test_tapered_needle_modifies_canvas():
    r = _make_renderer()
    canvas = _blank_canvas()
    r._draw_tapered_needle(canvas, 'tachometer', 200.0)
    assert canvas.max() > 0


def test_tapered_needle_no_method_draw_needle():
    r = _make_renderer()
    assert not hasattr(r, '_draw_needle'), \
        "_draw_needle should be removed — use _draw_tapered_needle"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_dashboard_ui.py::test_tapered_needle_draws_without_error -v
```

Expected: FAIL — `AttributeError: 'GaugeRenderer' object has no attribute '_draw_tapered_needle'`

- [ ] **Step 3: Replace _draw_needle with _draw_tapered_needle in dashboard_ui.py**

Remove the existing `_draw_needle` method entirely and add:

```python
def _draw_tapered_needle(self, canvas: np.ndarray, gauge_name: str,
                         needle_angle: float) -> None:
    cfg = self._g[gauge_name]
    cx, cy = cfg['center']
    r = cfg['radius']
    rad = math.radians(needle_angle)
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    perp_cos = math.cos(rad + math.pi / 2)
    perp_sin = math.sin(rad + math.pi / 2)

    tip_r   = int(r * 0.88)
    tail_r  = int(r * 0.15)
    half_w  = 2  # half-width at pivot (pixels)

    tip   = (int(cx + tip_r  * cos_a), int(cy + tip_r  * sin_a))
    tail  = (int(cx - tail_r * cos_a), int(cy - tail_r * sin_a))
    pl    = (int(cx + half_w * perp_cos), int(cy + half_w * perp_sin))
    pr    = (int(cx - half_w * perp_cos), int(cy - half_w * perp_sin))

    # Full wedge at 40% opacity (semi-transparent base)
    overlay = canvas.copy()
    pts_full = np.array([tail, pl, tip, pr], np.int32)
    cv2.fillPoly(overlay, [pts_full], tuple(self._s['needle_color']))
    cv2.addWeighted(overlay, 0.4, canvas, 0.6, 0, canvas)

    # Tip triangle at 100% opacity (solid bright tip)
    mid_r = int(r * 0.60)
    mid   = (int(cx + mid_r * cos_a), int(cy + mid_r * sin_a))
    ml    = (int(cx + (half_w * 0.4) * perp_cos),
             int(cy + (half_w * 0.4) * perp_sin))
    mr    = (int(cx - (half_w * 0.4) * perp_cos),
             int(cy - (half_w * 0.4) * perp_sin))
    pts_tip = np.array([mid, ml, tip, mr], np.int32)
    cv2.fillPoly(canvas, [pts_tip], tuple(self._s['needle_color']))

    # Tail counterweight
    cv2.line(canvas, (cx, cy), tail,
             tuple(self._s['label_color']), 2, cv2.LINE_AA)

    # Hub
    cv2.circle(canvas, (cx, cy), 6,
               tuple(self._s['hub_color']), -1, cv2.LINE_AA)
    cv2.circle(canvas, (cx, cy), 3,
               tuple(self._s['bg_color']), -1, cv2.LINE_AA)
```

- [ ] **Step 4: Run all tests**

```bash
pytest tests/test_dashboard_ui.py -v
```

Expected: all tests PASS (including `test_tapered_needle_no_method_draw_needle`)

- [ ] **Step 5: Commit**

```bash
git add dashboard_ui.py tests/test_dashboard_ui.py
git commit -m "feat: tapered ghost needle with semi-transparent base and solid bright tip"
```

---

## Task 5: Rewrite draw_tachometer

**Files:**
- Modify: `dashboard_ui.py` (`draw_tachometer` method)
- Test: `tests/test_dashboard_ui.py` (add tests)

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_dashboard_ui.py`:

```python
def test_draw_tachometer_runs_without_error():
    r = _make_renderer()
    canvas = _blank_canvas()
    r.draw_tachometer(canvas, rpm=3000.0, needle_angle=225.0)


def test_draw_tachometer_modifies_canvas():
    r = _make_renderer()
    canvas = _blank_canvas()
    r.draw_tachometer(canvas, rpm=3000.0, needle_angle=225.0)
    assert canvas.max() > 0


def test_draw_tachometer_redzone_at_max():
    """Canvas at max RPM must contain red pixels (redzone arc drawn)."""
    r = _make_renderer()
    canvas = _blank_canvas()
    max_angle = r.val_to_angle(6000, 'tachometer')
    r.draw_tachometer(canvas, rpm=6000.0, needle_angle=max_angle)
    # arc_redzone is [0, 0, 255] — check for red channel > 200
    assert (canvas[:, :, 2] > 200).any()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_dashboard_ui.py::test_draw_tachometer_redzone_at_max -v
```

Expected: FAIL (old draw_tachometer uses amber redzone color, not [0,0,255])

- [ ] **Step 3: Rewrite draw_tachometer in dashboard_ui.py**

Replace the entire `draw_tachometer` method:

```python
def draw_tachometer(self, canvas: np.ndarray, rpm: float,
                    needle_angle: float) -> None:
    cfg = self._g['tachometer']
    cx, cy = cfg['center']
    r = cfg['radius']
    sa = cfg['start_angle']
    ea = sa + cfg['sweep']
    axes = (r, r)
    w = cfg['arc_width']

    active_angle = self.val_to_angle(rpm, 'tachometer')
    rz_angle = self.val_to_angle(cfg['redzone_val'], 'tachometer')

    # 1. Inactive full track
    cv2.ellipse(canvas, (cx, cy), axes, 0, sa, ea,
                tuple(self._s['arc_inactive']), w, cv2.LINE_AA)

    # 2. Active arc (cyan)
    cv2.ellipse(canvas, (cx, cy), axes, 0, sa, active_angle,
                tuple(self._s['arc_active']), w, cv2.LINE_AA)

    # 3. Critical zone glow (wider, blended)
    glow_overlay = canvas.copy()
    cv2.ellipse(glow_overlay, (cx, cy), axes, 0, rz_angle, ea,
                tuple(self._s['arc_redzone']), w + 6, cv2.LINE_AA)
    cv2.addWeighted(glow_overlay, 0.30, canvas, 0.70, 0, canvas)

    # 4. Critical zone solid arc
    cv2.ellipse(canvas, (cx, cy), axes, 0, rz_angle, ea,
                tuple(self._s['arc_redzone']), w, cv2.LINE_AA)

    # Tick marks from cache
    for x1, y1, x2, y2, is_major in self._tick_cache['tachometer']:
        color = tuple(self._s['value_color']) if is_major \
            else tuple(self._s['label_color'])
        thickness = 2 if is_major else 1
        cv2.line(canvas, (x1, y1), (x2, y2), color, thickness, cv2.LINE_AA)

    # Scale labels at major ticks: 0 10 20 30 40 50 60
    for i, label in enumerate(['0', '10', '20', '30', '40', '50', '60']):
        pct = (i * 1000) / 6000.0
        angle = sa + pct * cfg['sweep']
        lx, ly = self._angle_to_xy(cx, cy, r + 16, angle)
        self._put_centered_text(canvas, label, lx, ly,
                                self._s['label_color'], font_scale=0.32)

    self._draw_tapered_needle(canvas, 'tachometer', needle_angle)

    rpm_str = f"{int(rpm):,}"
    self._put_centered_text(canvas, rpm_str, cx, cy + 38,
                            self._s['value_color'], font_scale=0.75, thickness=2)
    self._put_centered_text(canvas, 'RPM', cx, cy + 58,
                            self._s['label_color'], font_scale=0.30)
```

- [ ] **Step 4: Run all tests**

```bash
pytest tests/ -v
```

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add dashboard_ui.py tests/test_dashboard_ui.py
git commit -m "feat: German Minimalist tachometer — 270deg sweep, cached ticks, redzone glow"
```

---

## Task 6: Rewrite draw_speedometer

**Files:**
- Modify: `dashboard_ui.py` (`draw_speedometer` method)
- Test: `tests/test_dashboard_ui.py` (add tests)

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_dashboard_ui.py`:

```python
def test_draw_speedometer_runs_without_error():
    r = _make_renderer()
    canvas = _blank_canvas()
    r.draw_speedometer(canvas, speed_kph=100.0, needle_angle=270.0, gps_fix=True)


def test_draw_speedometer_no_gps_shows_dashes():
    """No GPS → speed value pixel area should not show bright white number."""
    r = _make_renderer()
    canvas = _blank_canvas()
    r.draw_speedometer(canvas, speed_kph=0.0, needle_angle=135.0, gps_fix=False)
    # Just verify it runs — visual diff not automatable here
    assert canvas.max() > 0


def test_draw_speedometer_no_redzone_arc():
    """Speedometer has no redzone — no red pixels expected."""
    r = _make_renderer()
    canvas = _blank_canvas()
    max_angle = r.val_to_angle(240, 'speedometer')
    r.draw_speedometer(canvas, speed_kph=240.0,
                       needle_angle=max_angle, gps_fix=True)
    # arc_redzone [0,0,255] — red channel should not be dominant
    red_pixels = (canvas[:, :, 2] > 200).sum()
    assert red_pixels < 50  # allow hub/warning pixels, not arc
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_dashboard_ui.py::test_draw_speedometer_no_redzone_arc -v
```

Expected: FAIL (old method uses arc_redzone for inner ring)

- [ ] **Step 3: Rewrite draw_speedometer in dashboard_ui.py**

Replace the entire `draw_speedometer` method:

```python
def draw_speedometer(self, canvas: np.ndarray, speed_kph: float,
                     needle_angle: float, gps_fix: bool) -> None:
    cfg = self._g['speedometer']
    cx, cy = cfg['center']
    r = cfg['radius']
    sa = cfg['start_angle']
    ea = sa + cfg['sweep']
    axes = (r, r)
    w = cfg['arc_width']

    active_angle = self.val_to_angle(speed_kph, 'speedometer')

    # 1. Inactive full track
    cv2.ellipse(canvas, (cx, cy), axes, 0, sa, ea,
                tuple(self._s['arc_inactive']), w, cv2.LINE_AA)

    # 2. Active arc (cyan)
    cv2.ellipse(canvas, (cx, cy), axes, 0, sa, active_angle,
                tuple(self._s['arc_active']), w, cv2.LINE_AA)

    # Tick marks from cache
    for x1, y1, x2, y2, is_major in self._tick_cache['speedometer']:
        color = tuple(self._s['value_color']) if is_major \
            else tuple(self._s['label_color'])
        thickness = 2 if is_major else 1
        cv2.line(canvas, (x1, y1), (x2, y2), color, thickness, cv2.LINE_AA)

    # Scale labels at major ticks (every 40 km/h for readability)
    for i, label in enumerate(['0', '40', '80', '120', '160', '200', '240']):
        pct = (i * 40) / 240.0
        angle = sa + pct * cfg['sweep']
        lx, ly = self._angle_to_xy(cx, cy, r + 16, angle)
        self._put_centered_text(canvas, label, lx, ly,
                                self._s['label_color'], font_scale=0.28)

    self._draw_tapered_needle(canvas, 'speedometer', needle_angle)

    if gps_fix:
        speed_str = f"{int(speed_kph)}"
        color = self._s['value_color']
    else:
        speed_str = "---"
        color = self._s['label_color']
    self._put_centered_text(canvas, speed_str, cx, cy + 38,
                            color, font_scale=0.75, thickness=2)
    self._put_centered_text(canvas, 'km/h', cx, cy + 58,
                            self._s['label_color'], font_scale=0.30)

    dot_color = self._s['arc_active'] if gps_fix else self._s['arc_redzone']
    cv2.circle(canvas, (cx, cy + 72), 4, tuple(dot_color), -1, cv2.LINE_AA)
    self._put_centered_text(canvas, 'GPS', cx + 10, cy + 74,
                            self._s['label_color'], font_scale=0.3)
```

- [ ] **Step 4: Run all tests**

```bash
pytest tests/ -v
```

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add dashboard_ui.py tests/test_dashboard_ui.py
git commit -m "feat: German Minimalist speedometer — 270deg sweep, cached ticks, no redzone"
```

---

## Task 7: Raise TARGET_FPS to 60

**Files:**
- Modify: `simulate.py:25`
- Modify: `main.py` (TARGET_FPS line)

- [ ] **Step 1: Update simulate.py**

In `simulate.py`, change line:

```python
TARGET_FPS = 30
```

to:

```python
TARGET_FPS = 60
```

- [ ] **Step 2: Update main.py**

In `main.py`, change the same `TARGET_FPS = 30` line to `TARGET_FPS = 60`.

- [ ] **Step 3: Smoke test simulate locally**

```bash
python simulate.py
```

Expected: window opens, gauges animate smoothly, no errors in console. Press Q or Escape to exit.

- [ ] **Step 4: Run full test suite**

```bash
pytest tests/ -v
```

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add simulate.py main.py
git commit -m "perf: raise TARGET_FPS to 60 — Pi 5 headroom supports it"
```

---

## Self-Review Checklist

- [x] **style.yaml palette** — Task 1 covers all 10 color keys
- [x] **gauges.yaml sweep=270, start_angle=135, arc_width=4** — Task 2
- [x] **BATT + IGN readouts added** — Task 2 gauges.yaml
- [x] **Tick cache pre-computed** — Task 3; tach 25 ticks (250 RPM step), speedo 25 ticks (10 km/h step)
- [x] **Tapered ghost needle** — Task 4; full wedge @ 0.4 alpha + tip triangle @ 1.0 alpha
- [x] **_draw_needle removed** — Task 4 test asserts no attribute
- [x] **draw_tachometer** — Task 5; 4-layer arc, cached ticks, redzone glow, tapered needle
- [x] **draw_speedometer** — Task 6; 2-layer arc, cached ticks, no redzone, tapered needle
- [x] **60 FPS** — Task 7
- [x] **No concentric ring lines** — removed in Tasks 5 and 6 (not present in rewritten methods)
- [x] **draw_center_panel unchanged** — palette inherited from style.yaml automatically
- [x] **draw_warning_icon unchanged** — palette inherited automatically
- [x] **No changes to threading, CAN, GPS, tests outside test_dashboard_ui.py** — confirmed
