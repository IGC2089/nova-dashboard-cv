# SVG Pixel-Perfect Cluster Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace programmatic gauge backgrounds with a pixel-perfect render of `assets/cluster - map.svg`, letterboxed to any screen, with dynamic elements (arc, needle, readouts) overlaid each frame in OpenCV.

**Architecture:** `cairosvg` renders the SVG once at boot into a numpy array; that array is letterbox-scaled to the screen and stored as `self._bg`. Each frame starts with `canvas[:] = self._bg`, then active arc, tapered needle, hub, and digital readouts are drawn on top using SVG-space coordinates transformed to screen space via `_svg_pt()`. The tick marks and scale labels baked into the SVG are no longer drawn in Python.

**Tech Stack:** Python 3, OpenCV (cv2), cairosvg>=2.7, numpy, PyYAML, pytest

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `requirements.txt` | Modify | Add `cairosvg>=2.7` |
| `config/gauges.yaml` | Modify | SVG block + SVG-space coords + per-gauge color keys |
| `dashboard_ui.py` | Modify | `_init_background()`, `_svg_pt()`, remove tick cache, update all draw methods |
| `main.py` | Modify | Pass `width=WIDTH, height=HEIGHT` to `GaugeRenderer` |
| `tests/test_svg_background.py` | Create | Tests for `_init_background()` shape/dtype and `_svg_pt()` math |
| `tests/test_dashboard_ui.py` | Modify | Update fixtures with new color keys; delete tick cache tests |

---

## Task 1: Add cairosvg dependency

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add cairosvg to requirements.txt**

Open `requirements.txt`. The file currently reads:
```
opencv-python>=4.9.0
python-can>=4.4.0
numpy>=1.26.0
gpsd-py3>=0.3.0
PyYAML>=6.0.2
pygame>=2.5.0
```

Replace with:
```
opencv-python>=4.9.0
python-can>=4.4.0
numpy>=1.26.0
gpsd-py3>=0.3.0
PyYAML>=6.0.2
pygame>=2.5.0
cairosvg>=2.7
```

- [ ] **Step 2: Install and verify**

```bash
pip install cairosvg>=2.7
python -c "import cairosvg; print('cairosvg ok')"
```

Expected output: `cairosvg ok`

If on Raspberry Pi and the install fails with a libcairo error:
```bash
sudo apt install libcairo2-dev libffi-dev
pip install cairosvg>=2.7
```

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "feat: add cairosvg dependency for SVG background rendering"
```

---

## Task 2: Update gauges.yaml — SVG block + SVG-space coords + per-gauge colors

**Files:**
- Modify: `config/gauges.yaml`

All positions in this file are now **SVG coordinate space** (1960×800 native). The renderer converts them to screen coords at draw time via `_svg_pt()`.

- [ ] **Step 1: Replace config/gauges.yaml entirely**

```yaml
# config/gauges.yaml
# ALL positions are in SVG coordinate space (native 1960x800).
# The renderer converts to screen coords using _svg_pt(x, y).
# Angles: clockwise from 3-o'clock (OpenCV convention).
# start_angle=135 places 0-value at ~7 o'clock; sweep=270 ends at ~5 o'clock.

svg:
  path: "assets/cluster - map.svg"
  native_width: 1960
  native_height: 800

tachometer:
  center:            [333, 380]
  radius:            245
  arc_width:         18
  start_angle:       135
  sweep:             270
  min_val:           0
  max_val:           6000
  redzone_val:       4500
  label:             "RPM"
  lerp_alpha:        0.15
  arc_color:         [235, 179, 43]      # BGR of #2BB3EB (blue)
  arc_bright_color:  [251, 226, 42]      # BGR of #2AE2FB (bright blue)
  redzone_color:     [0, 0, 255]
  hub_color:         [235, 179, 43]

speedometer:
  center:            [1627, 380]
  radius:            245
  arc_width:         18
  start_angle:       135
  sweep:             270
  min_val:           0
  max_val:           240
  redzone_val:       null
  label:             "km/h"
  lerp_alpha:        0.10
  arc_color:         [56, 22, 241]       # BGR of #F11630 (red)
  arc_bright_color:  [56, 70, 252]       # BGR of #FC4638 (bright red)
  hub_color:         [56, 22, 241]

center_panel:
  readouts:
    - label:       "BATT"
      state_field: batt_v
      unit:        "V"
      pos:         [850, 180]
      format:      "{:.1f}"
      font_scale:  0.9

    - label:       "IGN"
      state_field: ign_advance
      unit:        "deg"
      pos:         [1115, 180]
      format:      "{:.1f}"
      font_scale:  0.9

    - label:       "MAP"
      state_field: map_kpa
      unit:        "kPa"
      pos:         [850, 330]
      format:      "{:.0f}"
      font_scale:  0.9

    - label:       "CLT"
      state_field: clt_c
      unit:        "C"
      pos:         [1115, 330]
      format:      "{:.0f}"
      font_scale:  0.9

    - label:       "AFR"
      state_field: afr
      unit:        ""
      pos:         [980, 440]
      format:      "{:.1f}"
      font_scale:  1.8

    - label:       "ODO"
      state_field: odo_km
      unit:        "km"
      pos:         [850, 590]
      format:      "{:.0f}"
      font_scale:  0.7

    - label:       "TRIP"
      state_field: trip_km
      unit:        "km"
      pos:         [1115, 590]
      format:      "{:.1f}"
      font_scale:  0.7
```

- [ ] **Step 2: Verify YAML parses**

```bash
python -c "import yaml; d=yaml.safe_load(open('config/gauges.yaml')); print('svg:', d['svg']); print('tacho center:', d['tachometer']['center'])"
```

Expected:
```
svg: {'path': 'assets/cluster - map.svg', 'native_width': 1960, 'native_height': 800}
tacho center: [333, 380]
```

- [ ] **Step 3: Commit**

```bash
git add config/gauges.yaml
git commit -m "feat: update gauges.yaml to SVG-space coordinates and per-gauge colors"
```

---

## Task 3: Add `_init_background()` + `_svg_pt()` to GaugeRenderer; remove tick cache; update main.py

**Files:**
- Modify: `dashboard_ui.py`
- Modify: `main.py`
- Create: `tests/test_svg_background.py`
- Modify: `tests/test_dashboard_ui.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_svg_background.py`:

```python
import numpy as np
import cv2
import pytest


def _make_png_bytes(w: int, h: int) -> bytes:
    """Encode a solid-color WxH RGBA image as PNG bytes."""
    arr = np.zeros((h, w, 4), dtype=np.uint8)
    arr[:, :, 0] = 200  # blue channel
    arr[:, :, 3] = 255  # alpha
    _, buf = cv2.imencode('.png', arr)
    return buf.tobytes()


def _make_renderer(monkeypatch, width=800, height=480):
    import cairosvg
    from dashboard_ui import GaugeRenderer

    monkeypatch.setattr(
        cairosvg, 'svg2png',
        lambda **kwargs: _make_png_bytes(
            kwargs.get('output_width', 1960),
            kwargs.get('output_height', 800),
        )
    )

    style = {
        'bg_color': [0, 0, 0],
        'arc_inactive': [40, 40, 40],
        'needle_color': [255, 255, 255],
        'label_color': [160, 160, 160],
        'value_color': [255, 255, 255],
        'warning_amber': [0, 165, 255],
        'warning_red': [0, 0, 255],
    }
    gauges = {
        'svg': {'path': 'dummy.svg', 'native_width': 1960, 'native_height': 800},
        'tachometer': {
            'center': [333, 380], 'radius': 245, 'arc_width': 18,
            'start_angle': 135, 'sweep': 270,
            'min_val': 0, 'max_val': 6000, 'redzone_val': 4500,
            'lerp_alpha': 0.15,
            'arc_color': [235, 179, 43], 'arc_bright_color': [251, 226, 42],
            'redzone_color': [0, 0, 255], 'hub_color': [235, 179, 43],
        },
        'speedometer': {
            'center': [1627, 380], 'radius': 245, 'arc_width': 18,
            'start_angle': 135, 'sweep': 270,
            'min_val': 0, 'max_val': 240, 'redzone_val': None,
            'lerp_alpha': 0.10,
            'arc_color': [56, 22, 241], 'arc_bright_color': [56, 70, 252],
            'hub_color': [56, 22, 241],
        },
        'center_panel': {'readouts': []},
    }
    return GaugeRenderer(style=style, gauges=gauges, width=width, height=height)


def test_init_background_shape(monkeypatch):
    r = _make_renderer(monkeypatch)
    assert r._bg.shape == (480, 800, 3)
    assert r._bg.dtype == np.uint8


def test_init_background_non_black(monkeypatch):
    """Background must contain pixels from the SVG, not all zeros."""
    r = _make_renderer(monkeypatch)
    # The mock SVG has blue pixels; after letterbox they must appear in _bg
    assert r._bg.max() > 0


def test_svg_pt_top_left(monkeypatch):
    """SVG (0,0) maps to screen offset (offset_x, offset_y)."""
    r = _make_renderer(monkeypatch)
    sx, sy = r._svg_pt(0, 0)
    assert sx == r._offset_x
    assert sy == r._offset_y


def test_svg_pt_gauge_center_in_screen_bounds(monkeypatch):
    """Tachometer SVG center (333,380) must map within 800x480."""
    r = _make_renderer(monkeypatch)
    sx, sy = r._svg_pt(333, 380)
    assert 0 <= sx < 800
    assert 0 <= sy < 480


def test_no_tick_cache(monkeypatch):
    """_tick_cache must not exist after SVG redesign."""
    r = _make_renderer(monkeypatch)
    assert not hasattr(r, '_tick_cache')
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_svg_background.py -v
```

Expected: all 5 FAIL — `TypeError: __init__() got an unexpected keyword argument 'width'`

- [ ] **Step 3: Rewrite GaugeRenderer.__init__ and add _init_background / _svg_pt**

Replace the `__init__` and `_build_tick_cache` methods in `dashboard_ui.py`. The new `__init__` is:

```python
def __init__(self, style: dict, gauges: dict, width: int = 800, height: int = 480):
    self._s = style
    self._g = gauges
    self._w = width
    self._h = height
    self._scale: float = 1.0
    self._offset_x: int = 0
    self._offset_y: int = 0
    self._bg = self._init_background()
```

Add `_init_background` and `_svg_pt` immediately after `__init__`:

```python
def _init_background(self) -> np.ndarray:
    import cairosvg
    svg_cfg = self._g['svg']
    png_bytes = cairosvg.svg2png(
        url=svg_cfg['path'],
        output_width=svg_cfg['native_width'],
        output_height=svg_cfg['native_height'],
    )
    arr = cv2.imdecode(np.frombuffer(png_bytes, np.uint8), cv2.IMREAD_COLOR)
    self._scale = min(self._w / svg_cfg['native_width'],
                      self._h / svg_cfg['native_height'])
    rw = int(svg_cfg['native_width']  * self._scale)
    rh = int(svg_cfg['native_height'] * self._scale)
    self._offset_x = (self._w - rw) // 2
    self._offset_y = (self._h - rh) // 2
    canvas = np.zeros((self._h, self._w, 3), dtype=np.uint8)
    resized = cv2.resize(arr, (rw, rh), interpolation=cv2.INTER_AREA)
    canvas[self._offset_y:self._offset_y + rh,
           self._offset_x:self._offset_x + rw] = resized
    return canvas

def _svg_pt(self, x: float, y: float) -> tuple[int, int]:
    return (int(x * self._scale + self._offset_x),
            int(y * self._scale + self._offset_y))
```

Delete `_build_tick_cache` entirely (remove lines 20–51 of the original file).

- [ ] **Step 4: Delete tick cache tests from test_dashboard_ui.py**

In `tests/test_dashboard_ui.py`, delete the following four test functions (and the `_TICK_STYLE` / `_TICK_GAUGES` fixtures above them):

- `test_tick_cache_populated_on_init`
- `test_tach_tick_cache_has_correct_count`
- `test_speedo_tick_cache_has_correct_count`
- `test_tick_cache_entry_structure`

Also delete `_TICK_STYLE` and `_TICK_GAUGES` fixture dicts (lines 111–138 in original).

- [ ] **Step 5: Update GAUGES fixture in test_dashboard_ui.py to include new color keys**

The `GAUGES` dict at the top of `tests/test_dashboard_ui.py` must include the keys that `draw_tachometer` and `draw_speedometer` will read in later tasks. Add them now so tests don't break mid-refactor:

```python
GAUGES = {
    'svg': {'path': 'assets/cluster - map.svg', 'native_width': 1960, 'native_height': 800},
    'tachometer': {
        'center': [480, 360], 'radius': 280, 'arc_width': 18,
        'start_angle': 150, 'sweep': 240,
        'min_val': 0, 'max_val': 6000, 'redzone_val': 4500,
        'label': 'RPM', 'lerp_alpha': 0.15,
        'arc_color': [235, 179, 43], 'arc_bright_color': [251, 226, 42],
        'redzone_color': [0, 0, 255], 'hub_color': [235, 179, 43],
    },
    'speedometer': {
        'center': [640, 240], 'radius': 110, 'arc_width': 8,
        'start_angle': 150, 'sweep': 240,
        'min_val': 0, 'max_val': 240, 'redzone_val': None,
        'label': 'km/h', 'lerp_alpha': 0.10,
        'arc_color': [56, 22, 241], 'arc_bright_color': [56, 70, 252],
        'hub_color': [56, 22, 241],
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
```

Also update `make_renderer()` so it does NOT call `cairosvg` (the `svg` key triggers `_init_background`). Patch cairosvg at the test module level:

Add at the top of `test_dashboard_ui.py` (after imports):

```python
import numpy as np
import cv2
import pytest

# Prevent cairosvg from being called during unit tests — return a black 1960x800 PNG.
@pytest.fixture(autouse=True)
def _patch_cairosvg(monkeypatch):
    import cairosvg
    def _fake_svg2png(**kwargs):
        w = kwargs.get('output_width', 1960)
        h = kwargs.get('output_height', 800)
        arr = np.zeros((h, w, 3), dtype=np.uint8)
        _, buf = cv2.imencode('.png', arr)
        return buf.tobytes()
    monkeypatch.setattr(cairosvg, 'svg2png', _fake_svg2png)
```

- [ ] **Step 6: Update main.py to pass width/height**

In `main.py`, change line:
```python
renderer = GaugeRenderer(style=style, gauges=gauges)
```
to:
```python
renderer = GaugeRenderer(style=style, gauges=gauges, width=WIDTH, height=HEIGHT)
```

- [ ] **Step 7: Run tests**

```bash
pytest tests/test_svg_background.py tests/test_dashboard_ui.py -v
```

Expected: all PASS (the existing `test_draw_arc_track_no_crash` etc. may fail until Task 5 — that's acceptable; note which ones fail and confirm they're only the draw method tests, not the fixture/init tests).

- [ ] **Step 8: Commit**

```bash
git add dashboard_ui.py main.py tests/test_svg_background.py tests/test_dashboard_ui.py
git commit -m "feat: add SVG background init and _svg_pt; remove tick cache"
```

---

## Task 4: Update `render_frame()` — use SVG background; remove divider lines

**Files:**
- Modify: `dashboard_ui.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_svg_background.py`:

```python
def test_render_frame_uses_svg_background(monkeypatch):
    """render_frame must copy _bg into canvas, not fill with bg_color."""
    from vehicle_state import VehicleState
    r = _make_renderer(monkeypatch)
    # _bg has blue pixels (from mock SVG); bg_color is [0,0,0]
    # After render_frame, canvas must not be all bg_color
    canvas = np.zeros((480, 800, 3), dtype=np.uint8)
    state = VehicleState()
    state.lock = None
    interp = {
        'tach_angle': float(r._g['tachometer']['start_angle']),
        'speedo_angle': float(r._g['speedometer']['start_angle']),
    }
    r.render_frame(canvas, state, interp)
    # The mock SVG background has blue pixels in the letterboxed region
    assert canvas.max() > 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_svg_background.py::test_render_frame_uses_svg_background -v
```

Expected: FAIL (canvas stays black because `render_frame` still calls `canvas[:] = tuple(self._s['bg_color'])`)

- [ ] **Step 3: Update render_frame in dashboard_ui.py**

Find `render_frame` (currently line ~291). Change:
```python
def render_frame(self, canvas: np.ndarray, state, interp: dict) -> None:
    canvas[:] = tuple(self._s['bg_color'])
```
to:
```python
def render_frame(self, canvas: np.ndarray, state, interp: dict) -> None:
    np.copyto(canvas, self._bg)
```

- [ ] **Step 4: Remove divider lines from draw_center_panel**

In `draw_center_panel`, delete the three lines at the end that draw the vertical dividers:
```python
col = tuple(self._s['arc_inactive'])
cv2.line(canvas, (267, 20), (267, 460), col, 1)
cv2.line(canvas, (533, 20), (533, 460), col, 1)
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_svg_background.py -v
```

Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add dashboard_ui.py tests/test_svg_background.py
git commit -m "feat: render_frame uses SVG background; remove programmatic dividers"
```

---

## Task 5: Rewrite `draw_tachometer()` — SVG coords, per-gauge colors, no ticks/labels

**Files:**
- Modify: `dashboard_ui.py`

- [ ] **Step 1: Run existing tachometer tests to establish baseline**

```bash
pytest tests/test_dashboard_ui.py -k "tachometer" -v
```

Note which pass and which fail going into this task.

- [ ] **Step 2: Rewrite draw_tachometer in dashboard_ui.py**

Replace the entire `draw_tachometer` method with:

```python
def draw_tachometer(self, canvas: np.ndarray, rpm: float,
                    needle_angle: float) -> None:
    cfg = self._g['tachometer']
    cx_s, cy_s = self._svg_pt(cfg['center'][0], cfg['center'][1])
    r_s   = max(1, int(cfg['radius']    * self._scale))
    w_s   = max(1, int(cfg['arc_width'] * self._scale))
    sa    = cfg['start_angle']
    ea    = sa + cfg['sweep']
    axes  = (r_s, r_s)

    active_angle = self.val_to_angle(rpm, 'tachometer')
    rz_angle     = self.val_to_angle(cfg['redzone_val'], 'tachometer')

    # 1. Inactive full track
    cv2.ellipse(canvas, (cx_s, cy_s), axes, 0, sa, ea,
                tuple(self._s['arc_inactive']), w_s, cv2.LINE_AA)

    # 2. Active arc (blue) — clamped to redzone boundary
    cv2.ellipse(canvas, (cx_s, cy_s), axes, 0, sa, min(active_angle, rz_angle),
                tuple(cfg['arc_color']), w_s, cv2.LINE_AA)

    # 3. Redzone glow (wider, blended)
    glow_overlay = canvas.copy()
    cv2.ellipse(glow_overlay, (cx_s, cy_s), axes, 0, rz_angle, ea,
                tuple(cfg['redzone_color']), w_s + max(1, int(6 * self._scale)),
                cv2.LINE_AA)
    cv2.addWeighted(glow_overlay, 0.30, canvas, 0.70, 0, canvas)

    # 4. Redzone solid arc
    cv2.ellipse(canvas, (cx_s, cy_s), axes, 0, rz_angle, ea,
                tuple(cfg['redzone_color']), w_s, cv2.LINE_AA)

    self._draw_tapered_needle(canvas, 'tachometer', needle_angle)

    rpm_str = f"{int(rpm):,}"
    self._put_centered_text(canvas, rpm_str, cx_s, cy_s + int(38 * self._scale),
                            self._s['value_color'], font_scale=0.75, thickness=2)
    self._put_centered_text(canvas, 'RPM', cx_s, cy_s + int(58 * self._scale),
                            self._s['label_color'], font_scale=0.30)
```

- [ ] **Step 3: Update _draw_tapered_needle to use SVG coords and per-gauge hub_color**

Replace `_draw_tapered_needle` with:

```python
def _draw_tapered_needle(self, canvas: np.ndarray, gauge_name: str,
                         needle_angle: float) -> None:
    cfg = self._g[gauge_name]
    cx, cy = self._svg_pt(cfg['center'][0], cfg['center'][1])
    r = max(1, int(cfg['radius'] * self._scale))
    rad = math.radians(needle_angle)
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    perp_cos = math.cos(rad + math.pi / 2)
    perp_sin = math.sin(rad + math.pi / 2)

    tip_r   = int(r * 0.88)
    tail_r  = int(r * 0.15)
    half_w  = max(1, int(2 * self._scale))

    tip   = (int(cx + tip_r  * cos_a), int(cy + tip_r  * sin_a))
    tail  = (int(cx - tail_r * cos_a), int(cy - tail_r * sin_a))
    pl    = (int(cx + half_w * perp_cos), int(cy + half_w * perp_sin))
    pr    = (int(cx - half_w * perp_cos), int(cy - half_w * perp_sin))

    overlay = canvas.copy()
    pts_full = np.array([tail, pl, tip, pr], np.int32)
    cv2.fillPoly(overlay, [pts_full], tuple(self._s['needle_color']))
    cv2.addWeighted(overlay, 0.4, canvas, 0.6, 0, canvas)

    mid_r   = int(r * 0.60)
    mid     = (int(cx + mid_r * cos_a), int(cy + mid_r * sin_a))
    hw_tip  = max(1, int(half_w * 0.4))
    ml      = (int(mid[0] + hw_tip * perp_cos), int(mid[1] + hw_tip * perp_sin))
    mr      = (int(mid[0] - hw_tip * perp_cos), int(mid[1] - hw_tip * perp_sin))
    pts_tip = np.array([mid, ml, tip, mr], np.int32)
    cv2.fillPoly(canvas, [pts_tip], tuple(self._s['needle_color']))

    cv2.line(canvas, (cx, cy), tail,
             tuple(self._s['label_color']), 2, cv2.LINE_AA)

    hub_r = max(3, int(6 * self._scale))
    cv2.circle(canvas, (cx, cy), hub_r,
               tuple(cfg['hub_color']), -1, cv2.LINE_AA)
    cv2.circle(canvas, (cx, cy), max(1, hub_r // 2),
               tuple(self._s['bg_color']), -1, cv2.LINE_AA)
```

- [ ] **Step 4: Run tachometer tests**

```bash
pytest tests/test_dashboard_ui.py -k "tachometer" -v
```

Expected: all tachometer tests PASS

- [ ] **Step 5: Commit**

```bash
git add dashboard_ui.py
git commit -m "feat: rewrite draw_tachometer with SVG coords and per-gauge colors"
```

---

## Task 6: Rewrite `draw_speedometer()` — SVG coords, per-gauge colors, no ticks/labels

**Files:**
- Modify: `dashboard_ui.py`

- [ ] **Step 1: Run existing speedometer tests to establish baseline**

```bash
pytest tests/test_dashboard_ui.py -k "speedometer" -v
```

- [ ] **Step 2: Rewrite draw_speedometer in dashboard_ui.py**

Replace the entire `draw_speedometer` method with:

```python
def draw_speedometer(self, canvas: np.ndarray, speed_kph: float,
                     needle_angle: float, gps_fix: bool) -> None:
    cfg = self._g['speedometer']
    cx_s, cy_s = self._svg_pt(cfg['center'][0], cfg['center'][1])
    r_s   = max(1, int(cfg['radius']    * self._scale))
    w_s   = max(1, int(cfg['arc_width'] * self._scale))
    sa    = cfg['start_angle']
    ea    = sa + cfg['sweep']
    axes  = (r_s, r_s)

    active_angle = self.val_to_angle(speed_kph, 'speedometer')

    # 1. Inactive full track
    cv2.ellipse(canvas, (cx_s, cy_s), axes, 0, sa, ea,
                tuple(self._s['arc_inactive']), w_s, cv2.LINE_AA)

    # 2. Active arc (red)
    cv2.ellipse(canvas, (cx_s, cy_s), axes, 0, sa, active_angle,
                tuple(cfg['arc_color']), w_s, cv2.LINE_AA)

    self._draw_tapered_needle(canvas, 'speedometer', needle_angle)

    if gps_fix:
        speed_str = f"{int(speed_kph)}"
        color = self._s['value_color']
    else:
        speed_str = "---"
        color = self._s['label_color']
    self._put_centered_text(canvas, speed_str, cx_s, cy_s + int(38 * self._scale),
                            color, font_scale=0.75, thickness=2)
    self._put_centered_text(canvas, 'km/h', cx_s, cy_s + int(58 * self._scale),
                            self._s['label_color'], font_scale=0.30)

    dot_color = cfg['arc_color'] if gps_fix else self._s['warning_red']
    cv2.circle(canvas, (cx_s, cx_s + int(72 * self._scale)), max(2, int(4 * self._scale)),
               tuple(dot_color), -1, cv2.LINE_AA)
    self._put_centered_text(canvas, 'GPS',
                            cx_s + max(1, int(10 * self._scale)),
                            cy_s + int(74 * self._scale),
                            self._s['label_color'], font_scale=0.3)
```

- [ ] **Step 3: Fix GPS dot y-coordinate bug**

The GPS dot line above has a typo: `(cx_s, cx_s + int(72 * self._scale))` — the second `cx_s` should be `cy_s`. Correct it:

```python
    cv2.circle(canvas,
               (cx_s, cy_s + int(72 * self._scale)),
               max(2, int(4 * self._scale)),
               tuple(dot_color), -1, cv2.LINE_AA)
```

- [ ] **Step 4: Run speedometer tests**

```bash
pytest tests/test_dashboard_ui.py -k "speedometer" -v
```

Expected: all speedometer tests PASS

- [ ] **Step 5: Commit**

```bash
git add dashboard_ui.py
git commit -m "feat: rewrite draw_speedometer with SVG coords and per-gauge colors"
```

---

## Task 7: Update `draw_readout()` and `draw_center_panel()` to use `_svg_pt()`; run full suite

**Files:**
- Modify: `dashboard_ui.py`
- Modify: `tests/test_dashboard_ui.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_svg_background.py`:

```python
def test_draw_readout_uses_svg_coords(monkeypatch):
    """draw_readout must transform pos through _svg_pt."""
    r = _make_renderer(monkeypatch)
    canvas = np.zeros((480, 800, 3), dtype=np.uint8)
    # SVG pos (980, 440) → screen ~(400, 257) at scale 0.408, offset_y=77
    r.draw_readout(canvas, 'AFR', '14.7', '', [980, 440], font_scale=1.8)
    assert canvas.max() > 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_svg_background.py::test_draw_readout_uses_svg_coords -v
```

Expected: FAIL — the text is drawn at raw SVG coords (980, 440) which is off-screen for 800×480

- [ ] **Step 3: Update draw_readout in dashboard_ui.py**

Replace the `draw_readout` method body:

```python
def draw_readout(self, canvas: np.ndarray, label: str, value_str: str,
                 unit: str, pos: list, font_scale: float) -> None:
    x, y = self._svg_pt(pos[0], pos[1])
    spacing = int(font_scale * 15) + 12
    self._put_centered_text(canvas, label, x, y - spacing,
                            self._s['label_color'], font_scale=0.4)
    self._put_centered_text(canvas, value_str, x, y,
                            self._s['value_color'], font_scale=font_scale,
                            thickness=2)
    if unit:
        self._put_centered_text(canvas, unit, x, y + spacing,
                                self._s['label_color'], font_scale=0.35)
```

- [ ] **Step 4: Run the new test**

```bash
pytest tests/test_svg_background.py::test_draw_readout_uses_svg_coords -v
```

Expected: PASS

- [ ] **Step 5: Update warning_icon positions to scale with screen**

In `render_frame`, the warning icons use hardcoded screen coords `cx=400+offset, cy=435`. These are outside the SVG letterbox area (SVG occupies y: 77–403 on 800×480) so they can remain as screen coords. However `offset` and `cy` should scale with the screen height:

Find the `render_frame` warning drawing section:
```python
        for i, (label, color) in enumerate(warnings):
            offset = (i - (total - 1) / 2) * 70
            self.draw_warning_icon(canvas, int(400 + offset), 435,
                                   label, color,
                                   pulse=pulse if i == 0 else 1.0)
```

Replace with:
```python
        warn_y = self._h - 45
        warn_cx = self._w // 2
        for i, (label, color) in enumerate(warnings):
            offset = (i - (total - 1) / 2) * 70
            self.draw_warning_icon(canvas, int(warn_cx + offset), warn_y,
                                   label, color,
                                   pulse=pulse if i == 0 else 1.0)
```

- [ ] **Step 6: Run full test suite**

```bash
pytest tests/ -v
```

Expected: all tests PASS. If any test fails, inspect the failure — it should not be a regression from tasks 1–6.

- [ ] **Step 7: Commit**

```bash
git add dashboard_ui.py tests/test_svg_background.py
git commit -m "feat: draw_readout uses _svg_pt; warning icons use relative screen coords"
```

---

## Self-Review Checklist

- [x] **cairosvg dependency** — Task 1: added to requirements.txt, install verified
- [x] **gauges.yaml SVG block** — Task 2: `svg:` section with path, native_width, native_height
- [x] **SVG-space coordinates** — Task 2: all center, radius, arc_width, pos values in SVG space
- [x] **Per-gauge arc colors** — Task 2: `arc_color`, `arc_bright_color`, `hub_color`, `redzone_color` per gauge
- [x] **`_init_background()`** — Task 3: cairosvg → cv2.imdecode → letterbox → `self._bg`
- [x] **`_svg_pt()`** — Task 3: `(int(x*scale+ox), int(y*scale+oy))`
- [x] **Tick cache removed** — Task 3: `_build_tick_cache` deleted, `_tick_cache` gone
- [x] **Tick cache tests deleted** — Task 3: 4 tests removed from test_dashboard_ui.py
- [x] **main.py updated** — Task 3: `width=WIDTH, height=HEIGHT` passed to GaugeRenderer
- [x] **render_frame uses _bg** — Task 4: `np.copyto(canvas, self._bg)` replaces fill
- [x] **Divider lines removed** — Task 4: no `cv2.line` dividers in draw_center_panel
- [x] **draw_tachometer SVG coords** — Task 5: `_svg_pt`, scaled radius/arc_width
- [x] **draw_tachometer per-gauge colors** — Task 5: reads `arc_color`, `redzone_color` from cfg
- [x] **_draw_tapered_needle SVG coords** — Task 5: `_svg_pt`, scaled half_w, hub_r
- [x] **_draw_tapered_needle per-gauge hub_color** — Task 5: reads `cfg['hub_color']`
- [x] **draw_speedometer SVG coords** — Task 6: `_svg_pt`, scaled radius/arc_width
- [x] **draw_speedometer per-gauge colors** — Task 6: reads `arc_color` from cfg
- [x] **draw_readout _svg_pt** — Task 7: pos goes through `_svg_pt`
- [x] **Warning icon screen-relative** — Task 7: uses `self._h`, `self._w` not hardcoded coords
- [x] **No automated test for visual accuracy** — correctly omitted (requires Pi + visual inspection)

## Deployment (after all tasks complete)

```bash
git pull
pip install cairosvg>=2.7          # dev machine
sudo apt install libcairo2-dev     # Pi only (if not already installed)
pip install cairosvg>=2.7          # Pi
sudo python main.py
```
