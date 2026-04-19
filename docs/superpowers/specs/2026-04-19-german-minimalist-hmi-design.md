# German Minimalist HMI Redesign — Design Spec

**Date:** 2026-04-19
**Project:** Nova Dashboard CV (1974 Chevrolet Nova, Raspberry Pi 5, 800×480)

---

## Overview

Complete visual redesign of the instrument cluster UI using Audi/BMW German Minimalist design language. High contrast, thin typography, heavy use of negative space, tapered needle pointer. No structural changes to threading model, config system, or hardware interfaces.

**Approach:** Targeted layer swap — update `style.yaml`, `gauges.yaml`, and only the draw methods in `dashboard_ui.py` that handle arcs, ticks, and needle rendering.

---

## 1. Color Palette

All colors stored in `config/style.yaml` in BGR order (OpenCV convention).

| Key | BGR Value | Hex | Purpose |
|---|---|---|---|
| `bg_color` | `[10, 10, 10]` | #0A0A0A | Canvas background |
| `arc_active` | `[255, 229, 0]` | #00E5FF | Active arc, hub dot |
| `arc_inactive` | `[40, 40, 40]` | ~#282828 | Inactive arc track, divider lines |
| `arc_redzone` | `[0, 0, 255]` | #FF0000 | Tach critical zone 4500+ RPM |
| `needle_color` | `[255, 255, 255]` | #FFFFFF | Needle body |
| `hub_color` | `[255, 229, 0]` | #00E5FF | Hub center dot |
| `label_color` | `[160, 160, 160]` | #A0A0A0 | Labels, units, inactive text |
| `value_color` | `[255, 255, 255]` | #FFFFFF | Primary data values |
| `warning_amber` | `[0, 165, 255]` | #FFA500 | Amber warning icon |
| `warning_red` | `[0, 0, 255]` | #FF0000 | Red warning icon |

---

## 2. Gauge Geometry

Changes in `config/gauges.yaml`:

| Parameter | Old | New |
|---|---|---|
| `sweep` | 240° | 270° |
| `start_angle` | 150° | 135° |
| `arc_width` | 8 | 4 |

Both tachometer and speedometer share these geometry changes. The 270° sweep with start at 135° places zero at bottom-left and maximum at bottom-right — standard Audi/BMW orientation.

Tachometer `redzone_val` remains 4500 RPM. Speedometer has no redzone.

---

## 3. Arc & Tick System

### Tachometer (0–6000 RPM)

**Arc layers (drawn in order):**
1. Full inactive track — `arc_inactive`, width 4
2. Active arc (0 → current RPM) — `arc_active` (cyan), width 4
3. Critical zone glow (4500 → 6000) — `arc_redzone` at width 8, blended at 30% opacity (drawn before solid)
4. Critical zone solid (4500 → 6000) — `arc_redzone`, width 4

**Tick marks:**
- Major: every 1,000 RPM (7 ticks, 0–6000) — 12px length, 2px width, `value_color` (white)
- Minor: every 250 RPM (24 additional ticks) — 6px length, 1px width, `label_color` (mid-grey)
- Ticks drawn from outer arc edge inward

**Labels:**
- At major ticks only: `0 10 20 30 40 50 60` (×100 RPM)
- font_scale 0.32, `label_color`, placed 16px outside arc radius

**Removed:** Concentric ring lines (inner/outer ellipses), `ENGINE / RPM / x100` sub-labels.

### Speedometer (0–240 km/h)

**Arc layers:**
1. Full inactive track — `arc_inactive`, width 4
2. Active arc (0 → current speed) — `arc_active` (cyan), width 4
- No redzone arc on speedometer

**Tick marks:**
- Major: every 20 km/h (13 ticks, 0–240) — same style as tach majors
- Minor: every 10 km/h (12 additional per segment) — same style as tach minors

**Labels:**
- At major ticks: `0 20 40 60 80 100 120 140 160 180 200 220 240`
- font_scale 0.28, `label_color`

---

## 4. Tapered Ghost Needle

Replaces `_draw_needle` with `_draw_tapered_needle`. Same interface — takes `(canvas, gauge_name, needle_angle)`.

**Construction:**
- Filled polygon wedge: 4 points — `[tail, pivot_left, tip, pivot_right]`
- Pivot end: 4px wide (±2px perpendicular to needle axis)
- Tip end: converges to a single point
- Needle length: 88% of gauge radius
- Tail (counterweight): solid line, 15% radius in opposite direction, 2px, `label_color`

**Opacity simulation:**
- Draw needle wedge to a temporary same-size zero canvas
- `cv2.addWeighted(temp, alpha, canvas_roi, 1-alpha, 0)` to blend
- Pivot region: alpha 0.4 (semi-transparent)
- Tip region: alpha 1.0 (fully opaque white)
- Implemented as two overlapping polygons: full wedge at 0.4, tip-only triangle at 1.0

**Hub:**
- 6px cyan (`hub_color`) filled circle at center
- 3px `bg_color` inner dot (dark center)

---

## 5. Center Panel

All 7 readouts retained. Layout positions unchanged (from `gauges.yaml` center_panel readouts). Restyled by palette inheritance — no structural code changes needed.

**Readouts:** ODO (km), TRIP (km), CLT (°C), AFR, MAP (kPa), BATT (V), IGN (°)

**Typography:**
- Labels: `label_color`, font_scale 0.35
- Values: `value_color` (white), font_scale per YAML, thickness 2
- Units: `label_color`, font_scale 0.30

**Divider lines:** Two vertical lines at x=267 and x=533, `arc_inactive` color, 1px — already exist, recolored by palette change.

**NO GPS state:** Value renders as `---` in `label_color` — existing behavior, no change.

**Removed:** No horizontal rules, no box borders.

---

## 6. Warning Icons

Small pulsing triangle with `!` — existing `draw_warning_icon` method, no structural changes. Colors updated by palette inheritance (`warning_amber`, `warning_red`).

Triggers:
- CLT > 99°C → amber
- AFR < 11.0 → amber (RICH)
- AFR > 16.5 → red (LEAN)

---

## 7. Files Changed

| File | Change type |
|---|---|
| `config/style.yaml` | Full palette replacement |
| `config/gauges.yaml` | sweep, start_angle, arc_width |
| `dashboard_ui.py` | Rewrite `draw_tachometer`, `draw_speedometer`; replace `_draw_needle` with `_draw_tapered_needle` |

No changes to: `main.py`, `simulate.py`, `vehicle_state.py`, `can_handler.py`, `gps_handler.py`, `config_loader.py`, tests.

---

## 8. Performance

- Target: 60 FPS on Raspberry Pi 5 (up from 30 FPS)
- Pre-compute tick positions at `__init__` time (store in `self._tick_cache`)
- `simulate.py` TARGET_FPS raised from 30 → 60
- `main.py` TARGET_FPS raised from 30 → 60
- No other performance changes — existing numpy/OpenCV pipeline is sufficient
