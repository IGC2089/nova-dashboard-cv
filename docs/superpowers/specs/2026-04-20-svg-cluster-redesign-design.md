# SVG Pixel-Perfect Cluster Redesign — Design Spec

**Date:** 2026-04-20
**Project:** Nova Dashboard CV (1974 Chevrolet Nova, Raspberry Pi 5, 800×480)

---

## Overview

Replace the current programmatically-drawn gauge backgrounds with a pixel-perfect recreation of `assets/cluster - map.svg` (1960×800). The SVG is rendered once at boot into a numpy array and used as a static background every frame. Dynamic elements (active arc, needle, hub, digital readouts) are drawn on top in OpenCV using SVG-space coordinates transformed to screen space.

The result: the dashboard looks exactly like the SVG design at any screen resolution, with correct blue-left / red-right color split and letterboxed black bars on non-matching aspect ratios.

---

## 1. Architecture

**Render pipeline:**

```
Boot
 └─ cairosvg.svg2png(assets/cluster - map.svg, 1960×800)
     └─ cv2.imdecode → numpy array (1960×800×3)
         └─ letterbox_scale → numpy array (800×480×3)  ← self._bg

Per frame
 └─ frame = self._bg.copy()
     ├─ draw active arc        (cv2.ellipse, SVG→screen coords)
     ├─ draw tapered needle    (cv2.fillPoly)
     ├─ draw hub dot           (cv2.circle)
     ├─ draw RPM / speed digit (cv2.putText)
     └─ draw 7 center readouts (cv2.putText)
```

**Letterbox scaling:**

```
scale    = min(800 / 1960, 480 / 800) = 0.408
offset_x = (800 - 1960 * 0.408) / 2  = 0
offset_y = (480 - 800  * 0.408) / 2  = 76.8 ≈ 77
```

SVG → screen coordinate transform helper:
```python
def _svg_pt(self, x: float, y: float) -> tuple[int, int]:
    return (int(x * self._scale + self._offset_x),
            int(y * self._scale + self._offset_y))
```

---

## 2. Static vs Dynamic Elements

**Static (baked into SVG background, rendered once at boot):**
- Gauge bezels, decorative rings
- All tick marks and numeric labels (0–6000 RPM, 0–240 km/h)
- Center panel chrome/bezels and static decorative text

**Dynamic (drawn per frame in OpenCV):**

| Element | Left gauge (tachometer) | Right gauge (speedometer) |
|---|---|---|
| Active arc | Blue `#2BB3EB` / glow `#2AE2FB` | Red `#F11630` / bright `#FC4638` |
| Tapered needle | White, same wedge-polygon logic | White, same |
| Hub dot | Blue | Red |
| Primary digital readout | RPM (large digits) | Speed km/h (large digits) |
| 7 center-panel readouts | BATT, IGN, MAP, CLT, AFR, ODO, TRIP |

---

## 3. Gauge Geometry (SVG coordinate space)

Both gauges share the same geometry:

| Parameter | Value |
|---|---|
| Left center | SVG (333, 380) |
| Right center | SVG (1627, 380) |
| Radius | 245 |
| Arc width | 18 |
| Start angle | 135° (bottom-left, OpenCV convention) |
| Sweep | 270° |
| Redzone start (tacho) | 4500 RPM → angle 270° from start |

OpenCV ellipse angles are clockwise from 3 o'clock. For a gauge starting at 135° sweeping 270°:
- Min value → 135°
- Max value → 405° (= 45°)
- Redzone start (4500/6000 of 270°) → 135° + 202.5° = 337.5°

---

## 4. Configuration (`config/gauges.yaml`)

All positions in SVG coordinate space. The renderer converts to screen coords at draw time.

```yaml
svg:
  path: "assets/cluster - map.svg"
  native_width: 1960
  native_height: 800

tachometer:
  center: [333, 380]
  radius: 245
  arc_width: 18
  start_angle: 135
  sweep: 270
  min_val: 0
  max_val: 6000
  redzone_val: 4500
  lerp_alpha: 0.15
  arc_color: [235, 179, 43]      # BGR of #2BB3EB
  arc_bright_color: [251, 226, 42]  # BGR of #2AE2FB
  redzone_color: [0, 0, 255]
  hub_color: [235, 179, 43]

speedometer:
  center: [1627, 380]
  radius: 245
  arc_width: 18
  start_angle: 135
  sweep: 270
  min_val: 0
  max_val: 240
  redzone_val: null
  lerp_alpha: 0.10
  arc_color: [56, 22, 241]       # BGR of #F11630
  arc_bright_color: [56, 70, 252]  # BGR of #FC4638
  hub_color: [56, 22, 241]
```

---

## 5. Code Changes

### New: `_init_background()` in `DashboardUI.__init__`

```python
def _init_background(self) -> np.ndarray:
    import cairosvg, io
    svg_cfg = self._cfg['svg']
    png_bytes = cairosvg.svg2png(
        url=svg_cfg['path'],
        output_width=svg_cfg['native_width'],
        output_height=svg_cfg['native_height'],
    )
    arr = cv2.imdecode(np.frombuffer(png_bytes, np.uint8), cv2.IMREAD_COLOR)
    # letterbox onto screen canvas
    canvas = np.zeros((self._h, self._w, 3), dtype=np.uint8)
    self._scale = min(self._w / svg_cfg['native_width'],
                      self._h / svg_cfg['native_height'])
    rw = int(svg_cfg['native_width']  * self._scale)
    rh = int(svg_cfg['native_height'] * self._scale)
    self._offset_x = (self._w - rw) // 2
    self._offset_y = (self._h - rh) // 2
    resized = cv2.resize(arr, (rw, rh), interpolation=cv2.INTER_AREA)
    canvas[self._offset_y:self._offset_y+rh,
           self._offset_x:self._offset_x+rw] = resized
    return canvas
```

### Modified: `draw_tachometer()` / `draw_speedometer()`

- Remove all hardcoded pixel values
- Read `center`, `radius`, `arc_width`, colors from `self._cfg['tachometer']`
- Call `self._svg_pt(cx, cy)` to get screen center
- Scale radius: `int(cfg['radius'] * self._scale)`
- Scale arc_width: `max(1, int(cfg['arc_width'] * self._scale))`

### Removed

- Tick cache (`_build_tick_cache`, `_tick_cache`) — ticks are part of the SVG background
- All hardcoded `center`, `radius`, `arc_width` values from `dashboard_ui.py`

### `requirements.txt`

Add: `cairosvg>=2.7`

---

## 6. Files Changed

| File | Action |
|---|---|
| `config/gauges.yaml` | Modify — SVG-space coordinates, new `svg:` block, new color keys |
| `dashboard_ui.py` | Modify — add `_init_background()`, `_svg_pt()`, remove tick cache, update draw methods |
| `requirements.txt` | Modify — add `cairosvg>=2.7` |

No changes to: `main.py`, `vehicle_state.py`, `can_listener.py`, `gps_listener.py`, `config/style.yaml`.

---

## 7. Deployment

```bash
pip install cairosvg
# apt install libcairo2 if not already present on Pi
```

On dev machine: `pip install cairosvg` sufficient.
On Pi: `sudo apt install libcairo2-dev` then `pip install cairosvg`.

---

## 8. Testing

- **Unit:** `tests/test_svg_background.py` — verify `_init_background()` returns correct shape `(480, 800, 3)` and dtype `uint8`, using a tiny test SVG to avoid cairosvg dependency on CI.
- **Visual:** Run `sudo python simulate.py` on Pi — inspect that gauge centers, tick marks, and arc overlays align with SVG design.
- **No regression:** Full `pytest tests/` must pass after implementation.
