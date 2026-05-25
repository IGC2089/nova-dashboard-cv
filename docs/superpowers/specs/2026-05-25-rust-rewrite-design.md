# Nova Dashboard — Rust Rewrite Design

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rewrite the Nova Dashboard instrument cluster from Python to Rust, running on Raspberry Pi 5 (Debian Trixie, Wayland/Sway, 800×480).

**Architecture:** Single Rust binary using SDL2 for windowing and tiny-skia for all 2D gauge drawing. Background threads for CAN, GPS, and Bluetooth share state via `Arc<Mutex<VehicleState>>`. SVG assets are replaced entirely with code-drawn gauges.

**Tech Stack:** sdl2, tiny-skia, socketcan, serialport, nmea, zbus, serde_yaml, fontdue, parking_lot

---

## Project Layout

The Rust source lives alongside the existing Python files. Nothing is deleted until the Rust binary is confirmed working on the Pi.

```
nova-dashboard-cv/
  src/
    main.rs        ← SDL2 init, 60 FPS render loop, thread spawning
    state.rs       ← VehicleState struct + Arc<Mutex<>> wrapper
    can.rs         ← CAN bus thread (socketcan)
    gps.rs         ← GPS serial thread (serialport + nmea)
    bluetooth.rs   ← BlueZ D-Bus pairing agent (zbus)
    renderer.rs    ← All gauge drawing (tiny-skia + fontdue)
    config.rs      ← YAML config loading (serde_yaml)
  Cargo.toml
  config/          ← same gauges.yaml and style.yaml (re-used)
  assets/          ← splash_logo.png only (SVGs no longer needed)
```

## Cargo.toml Dependencies

```toml
[package]
name = "nova-dashboard"
version = "0.1.0"
edition = "2021"

[dependencies]
sdl2          = { version = "0.37", features = ["bundled"] }
tiny-skia     = "0.11"
socketcan     = "3"
serialport    = "4"
nmea          = "0.7"
zbus          = { version = "4", default-features = false, features = ["tokio"] }
tokio         = { version = "1", features = ["rt", "rt-multi-thread", "macros"] }
serde         = { version = "1", features = ["derive"] }
serde_yaml    = "0.9"
fontdue       = "0.9"
parking_lot   = "0.12"
image         = "0.25"   # splash PNG loading
```

**Pi system dep (one-time):**
```bash
sudo apt install libsdl2-dev
```

## State Module (`src/state.rs`)

```rust
#[derive(Clone, Default)]
pub struct VehicleState {
    // ECU
    pub rpm:         f32,
    pub map_kpa:     f32,
    pub clt_c:       f32,
    pub afr:         f32,
    pub tps_pct:     f32,
    pub iat_c:       f32,
    pub batt_v:      f32,
    pub ign_advance: f32,
    // GPS
    pub speed_kph:   f32,
    pub odo_km:      f32,
    pub trip_km:     f32,
    pub gps_fix:     bool,
    // Fuel
    pub fuel_pct:    f32,
    // Bluetooth pairing
    pub bt_pairing_pending: bool,
    pub bt_pairing_device:  String,
    pub bt_pairing_passkey: u32,
    pub bt_pairing_accepted: Option<bool>,  // None = waiting, Some(true/false) = decided
}

pub type SharedState = Arc<parking_lot::Mutex<VehicleState>>;
```

## Concurrency Model

Three background threads each receive a cloned `Arc<Mutex<VehicleState>>`:

- **CAN thread** — opens `socketcan::CanSocket::open("can0")`, reads frames in a loop, decodes by frame ID, writes `rpm`, `clt_c`, `afr`, `map_kpa`, `tps_pct`, `iat_c`, `batt_v`, `ign_advance`, `fuel_pct`
- **GPS thread** — opens serial port (default `/dev/ttyUSB0`), parses NMEA GGA/RMC sentences via `nmea` crate, writes `speed_kph`, `gps_fix`, accumulates `odo_km`, `trip_km`
- **BT thread** — registers as BlueZ agent via `zbus`, handles `RequestConfirmation` D-Bus method, sets `bt_pairing_pending = true` + passkey, waits for `bt_pairing_accepted` to be set by main thread, replies to BlueZ accordingly

Main thread reads state each frame:
```rust
let snap = state.lock().clone();  // lock held for ~1µs
renderer.draw_frame(&mut pixmap, &snap);
```

## Gauge Visual Layout

Screen: 800×480, dark background `#0a0a0a`.

**Left gauge — Speed**
- Center: `(200, 240)`, radius `160px`
- Arc sweep: `210°` start, `300°` total (clockwise)
- Track color: `#282828`
- Fill color: `#77CEF5` (cyan), grows from start to `speed/240 × 300°`
- Large speed value: white, ~72px, centered at `(200, 240)`
- Unit label `km/h`: gray, below value
- Fuel mini-bar: horizontal, bottom-left `(30, 430)–(170, 445)`, cyan fill

**Right gauge — RPM**
- Center: `(600, 240)`, radius `160px`
- Same geometry as speed gauge
- Fill color: `#F16666` (red), grows to `rpm/7000 × 300°`
- Redline glow: last 14% of arc (`rpm > 6000`) glows bright `#FF2222`
- Large RPM value: white, centered at `(600, 240)`
- CLT mini-bar: horizontal, bottom-right `(630, 430)–(770, 445)`, red fill

**Center readouts** (x=400, stacked vertically):
- Row 1 y=140: BATT (x=350), IGN (x=450)
- Row 2 y=200: MAP (x=350), CLT (x=450)
- Row 3 y=265: **AFR** large (x=400)
- Row 4 y=330: ODO (x=350), TRIP (x=450)

Each readout: gray label above, white value, gray unit below.

**Tick marks:** 9 major ticks around each gauge arc, evenly spaced at 300°/8 intervals, short lines radiating from arc.

**Warning icons:** pulsing amber triangle for overtemp (CLT > 99°C) or lean AFR (>16.5), red for rich AFR (<11.0). Centered bottom strip.

**Pairing overlay:** semi-transparent scrim, dark card, amber border. Device name, passkey (large spaced digits), ACCEPT (amber filled) and REJECT (dark) buttons. Same hit regions as Python: ACCEPT `(230,285)–(390,335)`, REJECT `(410,285)–(570,335)`.

## Rendering Pipeline (each frame)

```
1. Fill pixmap with background color
2. Draw gauge arc tracks (full 300° dim arcs, both gauges)
3. Draw filled sweeps (cyan left, red right, clipped to current value)
4. Draw tick marks + value labels around arcs
5. Draw large speed/RPM numbers
6. Draw fuel and CLT mini-bars
7. Draw center readouts
8. Draw warning icons (pulsing via sin(time))
9. Draw pairing overlay if bt_pairing_pending
10. Blit pixmap pixels → SDL2 texture → screen present
```

Splash fade: load `assets/splash_logo.png` at startup, alpha-blend over first 36 frames.

## Render Loop (main.rs sketch)

```rust
let mut event_pump = sdl_ctx.event_pump()?;
let mut clock = Instant::now();

'running: loop {
    for event in event_pump.poll_iter() {
        match event {
            Event::Quit { .. } => break 'running,
            Event::MouseButtonUp { x, y, .. } => handle_tap(x, y, &state),
            _ => {}
        }
    }

    let snap = state.lock().clone();
    let snap = if simulate { inject_sim(snap) } else { snap };

    renderer.draw_frame(&mut pixmap, &snap, frame_count);
    // blit pixmap to SDL2 texture, present
    frame_count += 1;

    // cap at 60 FPS
    let elapsed = clock.elapsed();
    if elapsed < FRAME_TIME { std::thread::sleep(FRAME_TIME - elapsed); }
    clock = Instant::now();
}
```

## Simulate Mode

`cargo run -- --simulate` injects sine-wave values into the snapshot before rendering. No hardware required — lets you develop and tune visuals on the Pi without the car connected.

## Build & Run on Pi

```bash
# Install Rust (once)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Install SDL2 (once)
sudo apt install libsdl2-dev

# Build (first build ~5 min, incremental ~30s)
cargo build --release

# Run
./target/release/nova-dashboard --simulate

# Or as service (replace ExecStart in nova-dashboard-wayland.service)
ExecStart=/home/pi/nova-dashboard-cv/target/release/nova-dashboard
```

## Success Criteria

- `cargo build --release` succeeds on the Pi with no errors
- `--simulate` mode shows both gauges animating smoothly at 60 FPS
- CAN, GPS, BT threads start without panicking (graceful error if hardware absent)
- Pairing overlay appears and ACCEPT/REJECT taps work
- Replaces the Python systemd service cleanly
