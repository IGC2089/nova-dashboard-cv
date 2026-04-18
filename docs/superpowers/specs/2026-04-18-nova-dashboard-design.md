# Nova Dashboard — Design Spec
**Date:** 2026-04-18
**Project:** Real-time Digital Instrument Cluster — 1974 Chevrolet Nova
**Target Hardware:** Raspberry Pi 5 (Raspberry Pi OS 64-bit)
**ECU:** Speeduino Dropbear v2 (Teensy 4.1)

---

## 1. Overview

A full-screen, low-latency digital instrument cluster rendered in Python 3 with OpenCV. Three concurrent data sources (CAN bus, GPS, render loop) feed a shared vehicle state object. The render loop targets 60 FPS with linear interpolation for fluid needle motion. The system is designed for automotive deployment: read-only root filesystem, atomic ODO persistence, and systemd autostart.

---

## 2. Hardware & Connectivity

| Component | Details |
|-----------|---------|
| Raspberry Pi 5 | Main computer, Raspberry Pi OS 64-bit |
| CAN HAT / USB adapter | SocketCAN via `/dev/can0`, 500 kbps |
| u-blox GPS receiver | USB, managed by `gpsd` daemon |
| HDMI display | 1920×720, full-screen |
| Speeduino Dropbear v2 | Teensy 4.1, CAN broadcast IDs `0x320` / `0x321` |

**Engine:** GM 250 cubic inch inline-6
- Tachometer scale: 0–6,000 RPM
- Red zone starts: 4,500 RPM
- Speedometer scale: 0–160 MPH

---

## 3. Architecture

### 3.1 Threading Model

Three daemon threads feed one shared `VehicleState` object protected by `threading.Lock`. The main thread owns the 60 FPS render loop.

```
┌─────────────────┐     ┌──────────────────────┐     ┌─────────────────┐
│  CANListener    │     │    VehicleState       │     │  GPSListener    │
│  Thread         │────▶│  (threading.Lock)     │◀────│  Thread         │
│  /dev/can0      │     │                       │     │  gpsd / u-blox  │
│  500 kbps       │     │  rpm, map_kpa, clt_f  │     │  1–5 Hz updates │
└─────────────────┘     │  afr, speed_mph       │     └─────────────────┘
                        │  odo_mi, trip_mi      │
         ┌──────────────│  warning_flags        │
         ▼              └──────────────────────┘
┌─────────────────┐
│  RenderLoop     │  ← main thread, 60 FPS target
│  double-buffer  │  OpenCV draws to offscreen Mat,
│  OpenCV         │  then atomic flip to display window
└─────────────────┘
```

### 3.2 Needle Interpolation

The render loop tracks a `current_angle` per gauge and applies linear interpolation every frame toward the `target_angle` derived from live state. This decouples render rate from data rate — needles sweep smoothly at 60 FPS regardless of whether CAN updates arrive at 20 Hz or GPS at 1 Hz.

```python
# Per frame, per gauge:
current_angle += (target_angle - current_angle) * LERP_ALPHA
```

`LERP_ALPHA` is tunable per gauge in `config/gauges.yaml` (e.g. tach responds faster than speedo).

### 3.3 Double Buffering

Each frame is drawn onto an offscreen `numpy` array (OpenCV Mat). On completion the buffer is presented via `cv2.imshow()`. This prevents any partial-draw flickering.

---

## 4. File Structure

```
nova-dashboard-cv/
├── main.py                        # Startup, thread orchestration, 60 FPS render loop
├── can_handler.py                 # SocketCAN listener + Speeduino frame decoder
├── gps_handler.py                 # gpsd client, speed/ODO accumulation, atomic persist
├── dashboard_ui.py                # GaugeRenderer class, all OpenCV drawing logic
├── vehicle_state.py               # VehicleState dataclass + threading.Lock
├── requirements.txt               # opencv-python, python-can, numpy, gpsd-py3
├── config/
│   ├── style.yaml                 # Theme: all colors, font sizes
│   └── gauges.yaml                # Gauge geometry: centers, radii, arc angles, ranges
├── scripts/
│   ├── setup_can.sh               # ip link set can0 up at 500kbps
│   ├── setup_readonly.sh          # Enable overlayfs + /data partition fstab entry
│   └── nova-dashboard.service     # systemd unit for autostart
└── docs/
    └── superpowers/specs/
        └── 2026-04-18-nova-dashboard-design.md
```

### 4.1 Module Responsibilities

| File | Owns | Reads | Writes |
|------|------|-------|--------|
| `vehicle_state.py` | `VehicleState` dataclass, `threading.Lock` | — | — |
| `can_handler.py` | CAN listener thread, Speeduino frame decode | `/dev/can0` | `VehicleState` |
| `gps_handler.py` | GPS listener thread, ODO accumulation | `gpsd` socket | `VehicleState`, `/data/odo.json` |
| `dashboard_ui.py` | `GaugeRenderer` class, per-component draw methods | `VehicleState`, config YAMLs | OpenCV Mat (offscreen) |
| `main.py` | Thread launch, render loop, shutdown | — | Orchestrates all |

---

## 5. Display Layout

**Resolution:** 1920×720, full-screen, no window decorations

```
┌─────────────────┬──────────────────────┬─────────────────┐
│                 │      MAP  │  CLT     │                 │
│   TACHOMETER    │──────────────────────│   SPEEDOMETER   │
│   (arc, amber)  │         AFR          │   (arc, amber)  │
│   0–6000 RPM    │──────────────────────│   0–160 MPH     │
│   redzone 4500+ │      ODO  │  TRIP    │   (GPS driven)  │
└─────────────────┴──────────────────────┴─────────────────┘
```

- **Left third** (0–640px): Tachometer — amber arc, amber needle, warm white digits
- **Center third** (640–1280px): Digital readouts — MAP, CLT, AFR (large), ODO, TRIP
- **Right third** (1280–1920px): Speedometer — amber arc, amber needle, GPS speed

---

## 6. Visual Theme

All visual parameters live in `config/style.yaml`. No color or size constants in Python code.

```yaml
theme:
  bg_color:       [8, 6, 1]          # BGR — near-black warm background
  arc_active:     [0, 122, 196]      # BGR — amber arc fill
  arc_inactive:   [0, 18, 26]        # BGR — dark arc track
  arc_redzone:    [0, 20, 140]       # BGR — red zone
  needle_color:   [128, 210, 255]    # BGR — warm white needle
  hub_color:      [0, 122, 196]      # BGR — needle pivot
  label_color:    [0, 66, 90]        # BGR — dim amber labels
  value_color:    [128, 210, 255]    # BGR — bright readout values
  warning_amber:  [0, 165, 255]      # BGR — CLT / rich warning overlay
  warning_red:    [0, 0, 220]        # BGR — lean warning overlay
  font:           FONT_HERSHEY_SIMPLEX
```

---

## 7. GaugeRenderer API

`dashboard_ui.py` exposes one class with focused methods — one per visual component. Adding a new gauge in the future means adding one method and one `gauges.yaml` entry.

```python
class GaugeRenderer:
    def __init__(self, style: dict, gauges: dict): ...

    def draw_tachometer(self, canvas, rpm: float, needle_angle: float) -> None
    def draw_speedometer(self, canvas, speed: float, needle_angle: float) -> None
    def draw_center_panel(self, canvas, state: VehicleState) -> None
    def draw_readout(self, canvas, label: str, value: str, unit: str,
                     pos: tuple, color: tuple) -> None
    def draw_warning_overlay(self, canvas, message: str, color: tuple) -> None
    def render_frame(self, canvas, state: VehicleState, interp: dict) -> None
```

`render_frame()` is the single entry point called by the main loop each tick. It calls all sub-methods in order and handles the interpolated needle angles.

---

## 8. CAN Signal Map

**Base ID:** `0x320` (Speeduino Dropbear v2 broadcast base address)

### Frame 0x320 — Engine Vitals

| Bytes | Signal | Type | Scale | Offset | Unit |
|-------|--------|------|-------|--------|------|
| 0–1 | RPM | uint16-LE | ×1 | 0 | RPM |
| 2 | MAP | uint8 | ×1 | 0 | kPa |
| 3 | TPS | uint8 | ×1 | 0 | % |
| 4 | IAT | uint8 | ×1 | −40 | °C |
| 5 | CLT | uint8 | ×1 | −40 | °C → ×1.8+32 → °F |
| 6 | AFR (O2) | uint8 | ×0.0068 | 0 | λ → ×14.7 → AFR |
| 7 | BATT | uint8 | ×0.1 | 0 | V |

### Frame 0x321 — Fuelling / Ignition

| Bytes | Signal | Type | Scale | Offset | Unit |
|-------|--------|------|-------|--------|------|
| 0–1 | PW1 | uint16-LE | ×1 | 0 | µs |
| 2 | INJ duty | uint8 | ×0.5 | 0 | % |
| 3 | IGN advance | int8 | ×1 | −40 | °BTDC |
| 4 | Engine flags | uint8 | — | — | bitmask |

All signals are decoded and held in `VehicleState`. Only RPM, MAP, CLT, and AFR are rendered; the rest are available for future gauges at zero additional CAN cost.

---

## 9. GPS Integration

**Daemon:** `gpsd` (system package). The u-blox receiver connects via USB and appears as `/dev/ttyACM0`. `gpsd` handles device detection automatically.

**Client library:** `gpsd-py3`

**Speed source:** TPV (Time-Position-Velocity) sentence → `speed` field (m/s, converted to mph).

**Accuracy gate:** Only accumulate ODO distance if `hacc < 10.0` metres. Rejects bad fixes and stationary GPS drift.

**ODO accumulation:**
```
if fix_valid and hacc < 10.0:
    delta_mi = speed_mph * (elapsed_seconds / 3600.0)
    odo_mi  += delta_mi
    trip_mi += delta_mi
```

**Persistence — atomic write pattern:**
```python
import os, json
def _save_odo(odo_mi: float, trip_mi: float):
    tmp = "/data/odo.tmp"
    dst = "/data/odo.json"
    with open(tmp, "w") as f:
        json.dump({"odo_mi": odo_mi, "trip_mi": trip_mi}, f)
    os.replace(tmp, dst)   # atomic on Linux — power-safe
```

Writes triggered every 0.1 mi accumulated and on clean shutdown signal (SIGTERM).

**GPS failure display:** If no valid TPV fix for > 5 seconds, speedometer shows `---` and ODO panel shows `NO GPS`.

---

## 10. Warning System

| Condition | Trigger | Overlay Color | Message |
|-----------|---------|--------------|---------|
| High coolant temp | CLT > 210°F | Amber, pulsing | `⚠ TEMP HIGH — XXX°F` |
| Rich mixture | AFR < 11.0 | Amber | `⚠ RICH` |
| Lean mixture | AFR > 16.5 | Red | `⚠ LEAN — CHECK ENGINE` |
| GPS signal lost | No fix > 5s | None (speedo `---`) | `NO GPS` in ODO area |

Warnings do **not** block gauge rendering — they overlay on top. Multiple warnings stack vertically. The pulsing effect on the CLT warning is achieved by modulating overlay alpha with `sin(time)`.

---

## 11. Read-Only Filesystem

### 11.1 Strategy

- **Root filesystem:** Read-only via Pi OS overlayfs (`raspi-config` → Performance → Overlay File System). The entire SD root becomes a RAM overlay. No runtime writes reach the SD card.
- **`/data` partition:** A small dedicated FAT32 partition (~64 MB) on the SD card, mounted `rw,sync,noatime`. The `sync` flag ensures every write is flushed to flash immediately — no OS buffer that can be lost on power cut.
- **Logs:** Written to `/tmp` (tmpfs / RAM). Lost on reboot — acceptable for a car instrument cluster.

### 11.2 `/etc/fstab` entry (added by `setup_readonly.sh`)

```
/dev/mmcblk0p3  /data  vfat  rw,sync,noatime,uid=1000,gid=1000  0  2
```

### 11.3 Power-loss safety

The atomic `os.replace()` write pattern means a power cut during an ODO save leaves either the previous complete file or the new complete file — never a half-written corrupt file. FAT32 with `sync` mount flushes the directory entry immediately after the rename.

---

## 12. Boot & Systemd

**Target:** < 8 seconds from power-on to live gauge display on Pi 5.

**Optimisations:**
- `systemd-analyze blame` audit at install time — disable unused services (Bluetooth, avahi, triggerhappy, etc.)
- Dashboard service uses `After=gpsd.service can-setup.service` ordering
- `setup_can.sh` runs as `ExecStartPre` in the systemd unit — no separate service needed

**`nova-dashboard.service`:**
```ini
[Unit]
Description=Nova Dashboard
After=network.target gpsd.service
Wants=gpsd.service

[Service]
ExecStartPre=/usr/local/bin/setup_can.sh
ExecStart=/usr/bin/python3 /home/pi/nova-dashboard-cv/main.py
Restart=always
RestartSec=2
StandardOutput=null
StandardError=journal
Environment=DISPLAY=:0
User=pi

[Install]
WantedBy=graphical.target
```

---

## 13. Dependencies

```
# requirements.txt
opencv-python>=4.9.0
python-can>=4.4.0
numpy>=1.26.0
gpsd-py3>=0.3.0
PyYAML>=6.0.2
```

System packages (installed by `scripts/setup_readonly.sh`):
- `gpsd`, `gpsd-clients`, `can-utils`, `python3-venv`

---

## 14. Future Extensibility

The config-driven UI design means future improvements require:
1. **New gauge:** Add entry to `config/gauges.yaml` + one `draw_X()` method in `dashboard_ui.py` + call it from `render_frame()`
2. **New CAN signal:** Add entry to CAN signal map in `can_handler.py` + field to `VehicleState`
3. **Theme change:** Edit `config/style.yaml` only — zero Python changes
4. **New warning:** Add condition check in `main.py` render loop + row in warning table

No global state, no hardcoded values in drawing code, no monolithic render function.
