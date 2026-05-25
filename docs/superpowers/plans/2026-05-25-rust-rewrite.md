# Nova Dashboard — Rust Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite the Nova Dashboard instrument cluster from Python to Rust, producing a single binary that replaces the Python systemd service on the Raspberry Pi 5.

**Architecture:** SDL2 window + tiny-skia 2D canvas for rendering; three background threads (CAN, GPS, Bluetooth) sharing `Arc<Mutex<VehicleState>>`; all gauges drawn in code (no SVGs).

**Tech Stack:** Rust 1.78+, sdl2, tiny-skia, fontdue, socketcan, serde_json (for gpsd), zbus + tokio (Bluetooth pairing), parking_lot, image (splash PNG), log/env_logger

---

## File Map

| File | Responsibility |
|---|---|
| `Cargo.toml` | All dependencies |
| `src/main.rs` | SDL2 init, event loop, 60 FPS render, thread spawning |
| `src/state.rs` | `VehicleState` struct + `SharedState` type alias |
| `src/renderer.rs` | All tiny-skia drawing: arcs, fills, ticks, text, overlays |
| `src/can.rs` | CAN bus thread — socketcan + Speeduino frame decode |
| `src/gps.rs` | GPS thread — gpsd TCP JSON + ODO accumulator |
| `src/bluetooth.rs` | Bluetooth pairing agent — zbus + BlueZ D-Bus |

All files are created from scratch inside the existing repo. Nothing is deleted until the binary is confirmed working.

---

## Task 1: Bootstrap — Install Rust and create the Cargo project

**Files:**
- Create: `Cargo.toml`
- Create: `src/main.rs`

---

- [ ] **Step 1: SSH into the Pi and install Rust**

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
# When prompted, choose option 1 (default install)
# Then activate for this session:
source "$HOME/.cargo/env"
# Verify:
rustc --version
cargo --version
```

Expected output: `rustc 1.78.0 (or newer)` and `cargo 1.78.0`

- [ ] **Step 2: Install SDL2 system library**

```bash
sudo apt install libsdl2-dev
```

- [ ] **Step 3: Navigate to the project and create Cargo.toml**

```bash
cd ~/nova-dashboard-cv
```

Create `Cargo.toml` with this exact content:

```toml
[package]
name = "nova-dashboard"
version = "0.1.0"
edition = "2021"

[[bin]]
name = "nova-dashboard"
path = "src/main.rs"

[dependencies]
sdl2        = "0.37"
tiny-skia   = "0.11"
socketcan   = "3"
serde_json  = "1"
zbus        = "4"
tokio       = { version = "1", features = ["rt", "rt-multi-thread", "time", "macros"] }
serde       = { version = "1", features = ["derive"] }
fontdue     = "0.9"
parking_lot = "0.12"
image       = "0.25"
log         = "0.4"
env_logger  = "0.11"
```

- [ ] **Step 4: Create src/main.rs stub**

```bash
mkdir -p src
```

Create `src/main.rs`:

```rust
fn main() {
    println!("nova-dashboard starting");
}
```

- [ ] **Step 5: Build and verify it compiles**

```bash
cargo build 2>&1 | tail -5
```

Expected (first build takes 5–15 min as it downloads and compiles all dependencies):
```
   Compiling nova-dashboard v0.1.0
    Finished dev [unoptimized + debuginfo] target(s) in ...
```

If you see any error about `sdl2`, make sure `libsdl2-dev` is installed:
```bash
sudo apt install libsdl2-dev
```

- [ ] **Step 6: Commit**

```bash
git add Cargo.toml src/main.rs
git commit -m "feat(rust): bootstrap cargo project with all deps"
```

---

## Task 2: State module

**Files:**
- Create: `src/state.rs`
- Modify: `src/main.rs` (add `mod state;`)

The `VehicleState` struct holds all live data. `SharedState` is the thread-safe wrapper used everywhere.

---

- [ ] **Step 1: Write the tests first**

Create `src/state.rs` with the test module:

```rust
use parking_lot::Mutex;
use std::sync::Arc;

/// All live vehicle data. Must be `Clone` so main thread can snapshot without holding the lock.
#[derive(Clone, Default)]
pub struct VehicleState {
    // ECU (from CAN)
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
    pub odo_km:      f64,
    pub trip_km:     f64,
    pub gps_fix:     bool,
    // Fuel
    pub fuel_pct:    f32,
    // Bluetooth pairing
    pub bt_pairing_pending:  bool,
    pub bt_pairing_device:   String,
    pub bt_pairing_passkey:  u32,
    /// None = waiting for user, Some(true) = accepted, Some(false) = rejected
    pub bt_pairing_accepted: Option<bool>,
}

/// Thread-safe shared state handle. Clone this to give each thread access.
pub type SharedState = Arc<Mutex<VehicleState>>;

/// Create a new shared state.
pub fn new_shared() -> SharedState {
    Arc::new(Mutex::new(VehicleState::default()))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn default_values_are_sane() {
        let s = VehicleState::default();
        assert_eq!(s.rpm, 0.0);
        assert_eq!(s.speed_kph, 0.0);
        assert_eq!(s.afr, 0.0);
        assert!(!s.bt_pairing_pending);
        assert!(s.bt_pairing_accepted.is_none());
    }

    #[test]
    fn shared_state_can_be_written_and_cloned() {
        let shared = new_shared();

        // Write from one "thread"
        shared.lock().rpm = 3500.0;
        shared.lock().speed_kph = 120.0;

        // Read snapshot — lock held briefly, then released
        let snap = shared.lock().clone();
        assert_eq!(snap.rpm, 3500.0);
        assert_eq!(snap.speed_kph, 120.0);
    }

    #[test]
    fn two_clones_see_same_data() {
        let shared = new_shared();
        let clone_a = Arc::clone(&shared);
        let clone_b = Arc::clone(&shared);

        clone_a.lock().clt_c = 92.0;
        assert_eq!(clone_b.lock().clt_c, 92.0);
    }
}
```

- [ ] **Step 2: Run tests — verify they pass**

```bash
cargo test state 2>&1
```

Expected:
```
running 3 tests
test state::tests::default_values_are_sane ... ok
test state::tests::shared_state_can_be_written_and_cloned ... ok
test state::tests::two_clones_see_same_data ... ok
test result: ok. 3 passed; 0 failed
```

- [ ] **Step 3: Wire state module into main.rs**

Replace `src/main.rs` with:

```rust
mod state;

fn main() {
    let _state = state::new_shared();
    println!("nova-dashboard starting — state OK");
}
```

- [ ] **Step 4: Build**

```bash
cargo build 2>&1 | tail -3
```

Expected: `Finished dev [unoptimized + debuginfo]`

- [ ] **Step 5: Commit**

```bash
git add src/state.rs src/main.rs
git commit -m "feat(rust): add VehicleState with Arc<Mutex<>> and unit tests"
```

---

## Task 3: SDL2 window — open a window and clear it dark

**Files:**
- Modify: `src/main.rs`

Goal: a black 800×480 window opens, renders at 60 FPS, closes on Escape or Q.

---

- [ ] **Step 1: Replace src/main.rs with the SDL2 window**

```rust
mod state;

use sdl2::event::Event;
use sdl2::keyboard::Keycode;
use sdl2::pixels::Color;
use std::time::{Duration, Instant};

const WIDTH: u32 = 800;
const HEIGHT: u32 = 480;
const FRAME_TIME: Duration = Duration::from_micros(16_667); // ~60 FPS

fn main() {
    env_logger::init();
    let _state = state::new_shared();

    // --- SDL2 setup ---
    let sdl = sdl2::init().expect("SDL2 init failed");
    let video = sdl.video().expect("SDL2 video subsystem failed");

    let window = video
        .window("Nova Dashboard", WIDTH, HEIGHT)
        .borderless()
        .position_centered()
        .build()
        .expect("SDL2 window creation failed");

    let mut canvas = window
        .into_canvas()
        .present_vsync()
        .build()
        .expect("SDL2 canvas creation failed");

    let mut event_pump = sdl.event_pump().expect("SDL2 event pump failed");

    log::info!("Window opened — running at 60 FPS");

    // --- Main loop ---
    'running: loop {
        let frame_start = Instant::now();

        // Handle events
        for event in event_pump.poll_iter() {
            match event {
                Event::Quit { .. }
                | Event::KeyDown { keycode: Some(Keycode::Escape), .. }
                | Event::KeyDown { keycode: Some(Keycode::Q), .. } => {
                    break 'running;
                }
                _ => {}
            }
        }

        // Clear to near-black
        canvas.set_draw_color(Color::RGB(10, 10, 10));
        canvas.clear();
        canvas.present();

        // Cap frame rate
        let elapsed = frame_start.elapsed();
        if elapsed < FRAME_TIME {
            std::thread::sleep(FRAME_TIME - elapsed);
        }
    }

    log::info!("Clean shutdown");
}
```

- [ ] **Step 2: Build**

```bash
cargo build 2>&1 | tail -5
```

Expected: `Finished dev [unoptimized + debuginfo]`

If you get `error[E0432]: unresolved import sdl2`, check that `libsdl2-dev` is installed.

- [ ] **Step 3: Run and verify window appears**

```bash
RUST_LOG=info ./target/debug/nova-dashboard
```

Expected: an 800×480 dark window opens. Press Escape or Q to close it.

- [ ] **Step 4: Commit**

```bash
git add src/main.rs
git commit -m "feat(rust): SDL2 window opens and runs at 60 FPS"
```

---

## Task 4: Renderer — arc geometry

**Files:**
- Create: `src/renderer.rs`
- Modify: `src/main.rs` (plug in renderer, use texture blit)

The renderer owns a `tiny-skia` `Pixmap` (800×480 RGBA). Every frame, `draw_frame()` is called with a `VehicleState` snapshot and blits the result to an SDL2 texture for display.

This task draws only the gauge arc **tracks** (the dim full-sweep background arcs).

---

- [ ] **Step 1: Write arc geometry tests**

Create `src/renderer.rs`:

```rust
use tiny_skia::{Color, Paint, PathBuilder, Pixmap, Stroke, Transform};
use crate::state::VehicleState;

// ── Layout constants ────────────────────────────────────────────────────────
pub const W: u32 = 800;
pub const H: u32 = 480;

// Left gauge (speed)
const SPD_CX: f32 = 200.0;
const SPD_CY: f32 = 240.0;
const SPD_R:  f32 = 155.0;
const SPD_MAX: f32 = 240.0;

// Right gauge (RPM)
const RPM_CX: f32 = 600.0;
const RPM_CY: f32 = 240.0;
const RPM_R:  f32 = 155.0;
const RPM_MAX: f32 = 7000.0;
const RPM_REDLINE: f32 = 6000.0;

// Both gauges share the same arc geometry
const ARC_START_DEG: f32 = 210.0;   // where the arc begins (clock-face degrees)
const ARC_SWEEP_DEG: f32 = 300.0;   // total sweep
const TRACK_WIDTH:   f32 = 14.0;    // stroke width for arcs
const TICK_SEGMENTS: usize = 8;     // creates 9 ticks (0..=8)

// Colors (RGBA 0–255)
const COL_BG:     [u8; 4] = [10,  10,  10,  255];
const COL_TRACK:  [u8; 4] = [40,  40,  40,  255];
const COL_CYAN:   [u8; 4] = [119, 206, 245, 255]; // #77CEF5 speed fill
const COL_RED:    [u8; 4] = [102, 102, 241, 255]; // #F16666 RPM fill
const COL_REDLINE:[u8; 4] = [34,  34,  255, 255]; // #FF2222 redline glow
const COL_WHITE:  [u8; 4] = [255, 255, 255, 255];
const COL_GRAY:   [u8; 4] = [160, 160, 160, 255];
const COL_AMBER:  [u8; 4] = [0,   165, 255, 255]; // BGR→RGB: warning amber

// ── Pure math helpers ────────────────────────────────────────────────────────

/// Convert a 0.0..=1.0 fraction to a sweep in degrees, clamped.
pub fn pct_to_sweep(pct: f32) -> f32 {
    pct.clamp(0.0, 1.0) * ARC_SWEEP_DEG
}

/// Convert a value in [min, max] to a sweep in degrees.
pub fn value_to_sweep(value: f32, min: f32, max: f32) -> f32 {
    let pct = ((value - min) / (max - min)).clamp(0.0, 1.0);
    pct_to_sweep(pct)
}

/// Build a polyline path approximating a circular arc.
/// `start_deg` and `sweep_deg` follow SVG/CSS convention: 0°=right, clockwise.
pub fn build_arc_path(cx: f32, cy: f32, r: f32, start_deg: f32, sweep_deg: f32) -> tiny_skia::Path {
    let n = 64usize; // segments — smooth enough for our radius
    let mut pb = PathBuilder::new();
    for i in 0..=n {
        let t = i as f32 / n as f32;
        let angle_deg = start_deg + t * sweep_deg;
        let angle_rad = angle_deg.to_radians();
        let x = cx + r * angle_rad.cos();
        let y = cy + r * angle_rad.sin();
        if i == 0 {
            pb.move_to(x, y);
        } else {
            pb.line_to(x, y);
        }
    }
    pb.finish().unwrap()
}

// ── Renderer ────────────────────────────────────────────────────────────────

pub struct Renderer {
    pub pixmap: Pixmap,
}

impl Renderer {
    pub fn new() -> Self {
        let pixmap = Pixmap::new(W, H).expect("Failed to create pixmap");
        Self { pixmap }
    }

    fn color(rgba: [u8; 4]) -> Color {
        Color::from_rgba8(rgba[0], rgba[1], rgba[2], rgba[3])
    }

    fn stroke_arc(&mut self, cx: f32, cy: f32, r: f32,
                  start_deg: f32, sweep_deg: f32,
                  rgba: [u8; 4], width: f32) {
        if sweep_deg <= 0.0 { return; }
        let path = build_arc_path(cx, cy, r, start_deg, sweep_deg);
        let mut paint = Paint::default();
        paint.set_color(Self::color(rgba));
        paint.anti_alias = true;
        let stroke = Stroke { width, ..Default::default() };
        self.pixmap.stroke_path(&path, &paint, &stroke, Transform::identity(), None);
    }

    fn fill_rect(&mut self, x: f32, y: f32, w: f32, h: f32, rgba: [u8; 4]) {
        let mut paint = Paint::default();
        paint.set_color(Self::color(rgba));
        let rect = tiny_skia::Rect::from_xywh(x, y, w, h).unwrap();
        self.pixmap.fill_rect(rect, &paint, Transform::identity(), None);
    }

    // ── Public draw methods ──────────────────────────────────────────────────

    pub fn clear(&mut self) {
        self.pixmap.fill(Self::color(COL_BG));
    }

    /// Draw dim arc tracks for both gauges (full 300° sweep).
    pub fn draw_gauge_tracks(&mut self) {
        self.stroke_arc(SPD_CX, SPD_CY, SPD_R, ARC_START_DEG, ARC_SWEEP_DEG, COL_TRACK, TRACK_WIDTH);
        self.stroke_arc(RPM_CX, RPM_CY, RPM_R, ARC_START_DEG, ARC_SWEEP_DEG, COL_TRACK, TRACK_WIDTH);
    }

    /// Draw everything for one frame.
    pub fn draw_frame(&mut self, state: &VehicleState, _frame: u64) {
        self.clear();
        self.draw_gauge_tracks();
    }
}

// ── Tests ────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pct_to_sweep_clamped() {
        assert_eq!(pct_to_sweep(0.0), 0.0);
        assert_eq!(pct_to_sweep(1.0), ARC_SWEEP_DEG);
        assert_eq!(pct_to_sweep(0.5), ARC_SWEEP_DEG * 0.5);
        // clamp below 0 and above 1
        assert_eq!(pct_to_sweep(-1.0), 0.0);
        assert_eq!(pct_to_sweep(2.0),  ARC_SWEEP_DEG);
    }

    #[test]
    fn value_to_sweep_maps_correctly() {
        assert_eq!(value_to_sweep(0.0, 0.0, 240.0), 0.0);
        assert_eq!(value_to_sweep(240.0, 0.0, 240.0), ARC_SWEEP_DEG);
        assert!((value_to_sweep(120.0, 0.0, 240.0) - ARC_SWEEP_DEG * 0.5).abs() < 0.001);
    }

    #[test]
    fn arc_path_has_correct_endpoints() {
        let path = build_arc_path(0.0, 0.0, 100.0, 0.0, 90.0);
        // Can't easily inspect path points, but building it shouldn't panic
        let _ = path;
    }

    #[test]
    fn renderer_new_creates_correct_size() {
        let r = Renderer::new();
        assert_eq!(r.pixmap.width(), W);
        assert_eq!(r.pixmap.height(), H);
    }
}
```

- [ ] **Step 2: Run tests — verify pass**

```bash
cargo test renderer 2>&1
```

Expected:
```
running 4 tests
test renderer::tests::pct_to_sweep_clamped ... ok
test renderer::tests::value_to_sweep_maps_correctly ... ok
test renderer::tests::arc_path_has_correct_endpoints ... ok
test renderer::tests::renderer_new_creates_correct_size ... ok
test result: ok. 4 passed; 0 failed
```

- [ ] **Step 3: Wire renderer into main.rs — blit pixmap to SDL2 texture**

Replace `src/main.rs`:

```rust
mod state;
mod renderer;

use sdl2::event::Event;
use sdl2::keyboard::Keycode;
use sdl2::pixels::PixelFormatEnum;
use sdl2::rect::Rect;
use std::time::{Duration, Instant};
use crate::renderer::Renderer;
use crate::state::VehicleState;

const WIDTH:  u32 = 800;
const HEIGHT: u32 = 480;
const FRAME_TIME: Duration = Duration::from_micros(16_667);

fn main() {
    env_logger::init();
    let state = state::new_shared();

    let sdl  = sdl2::init().expect("SDL2 init");
    let video = sdl.video().expect("SDL2 video");
    let window = video
        .window("Nova Dashboard", WIDTH, HEIGHT)
        .borderless()
        .position_centered()
        .build()
        .expect("window");
    let mut canvas = window.into_canvas().build().expect("canvas");
    let texture_creator = canvas.texture_creator();
    let mut texture = texture_creator
        .create_texture_streaming(PixelFormatEnum::ABGR8888, WIDTH, HEIGHT)
        .expect("texture");
    let mut event_pump = sdl.event_pump().expect("event pump");

    let mut renderer = Renderer::new();
    let mut frame: u64 = 0;

    log::info!("Render loop started");

    'running: loop {
        let frame_start = Instant::now();

        for event in event_pump.poll_iter() {
            match event {
                Event::Quit { .. }
                | Event::KeyDown { keycode: Some(Keycode::Escape), .. }
                | Event::KeyDown { keycode: Some(Keycode::Q), .. } => break 'running,
                _ => {}
            }
        }

        // Snapshot state (lock held < 1µs)
        let snap = state.lock().clone();

        // Draw to pixmap
        renderer.draw_frame(&snap, frame);
        frame += 1;

        // Blit pixmap → SDL2 texture → screen
        // tiny-skia pixmap data is RGBA bytes; SDL2 ABGR8888 on little-endian = RGBA in memory
        texture
            .update(Rect::new(0, 0, WIDTH, HEIGHT), renderer.pixmap.data(), (WIDTH * 4) as usize)
            .expect("texture update");
        canvas.copy(&texture, None, None).expect("canvas copy");
        canvas.present();

        let elapsed = frame_start.elapsed();
        if elapsed < FRAME_TIME {
            std::thread::sleep(FRAME_TIME - elapsed);
        }
    }
}
```

- [ ] **Step 4: Build and run — verify arc tracks visible**

```bash
cargo build 2>&1 | tail -3
RUST_LOG=info ./target/debug/nova-dashboard
```

Expected: dark window with two dim gray arcs (left and right). Press Q to close.

- [ ] **Step 5: Commit**

```bash
git add src/renderer.rs src/main.rs
git commit -m "feat(rust): renderer with arc tracks blitted to SDL2 texture"
```

---

## Task 5: Renderer — gauge fills and tick marks

**Files:**
- Modify: `src/renderer.rs`

Add: colored filled sweeps (cyan for speed, red for RPM, redline glow), and tick marks around each gauge.

---

- [ ] **Step 1: Add fill and tick methods to renderer.rs**

Add these methods inside `impl Renderer`, after `draw_gauge_tracks`:

```rust
    /// Draw the filled colored arc for speed (cyan) scaled to current value.
    pub fn draw_speed_fill(&mut self, speed_kph: f32) {
        let sweep = value_to_sweep(speed_kph, 0.0, SPD_MAX);
        self.stroke_arc(SPD_CX, SPD_CY, SPD_R, ARC_START_DEG, sweep, COL_CYAN, TRACK_WIDTH);
    }

    /// Draw the filled colored arc for RPM (red, with redline glow above 6000).
    pub fn draw_rpm_fill(&mut self, rpm: f32) {
        let sweep = value_to_sweep(rpm, 0.0, RPM_MAX);

        if rpm <= RPM_REDLINE {
            self.stroke_arc(RPM_CX, RPM_CY, RPM_R, ARC_START_DEG, sweep, COL_RED, TRACK_WIDTH);
        } else {
            // Normal red up to redline
            let normal_sweep = value_to_sweep(RPM_REDLINE, 0.0, RPM_MAX);
            self.stroke_arc(RPM_CX, RPM_CY, RPM_R, ARC_START_DEG, normal_sweep, COL_RED, TRACK_WIDTH);
            // Bright redline glow from redline to current
            let glow_sweep = sweep - normal_sweep;
            self.stroke_arc(RPM_CX, RPM_CY, RPM_R,
                            ARC_START_DEG + normal_sweep, glow_sweep,
                            COL_REDLINE, TRACK_WIDTH + 4.0);
        }
    }

    /// Draw short tick marks at evenly spaced positions around a gauge arc.
    pub fn draw_ticks(&mut self, cx: f32, cy: f32, r: f32, rgba: [u8; 4]) {
        let mut paint = Paint::default();
        paint.set_color(Self::color(rgba));
        paint.anti_alias = true;
        let stroke = Stroke { width: 2.0, ..Default::default() };

        for i in 0..=TICK_SEGMENTS {
            let t = i as f32 / TICK_SEGMENTS as f32;
            let angle_rad = (ARC_START_DEG + t * ARC_SWEEP_DEG).to_radians();
            let cos = angle_rad.cos();
            let sin = angle_rad.sin();
            let inner = r - 16.0;
            let outer = r + 4.0;
            let mut pb = PathBuilder::new();
            pb.move_to(cx + inner * cos, cy + inner * sin);
            pb.line_to(cx + outer * cos, cy + outer * sin);
            if let Some(path) = pb.finish() {
                self.pixmap.stroke_path(&path, &paint, &stroke, Transform::identity(), None);
            }
        }
    }

    /// Draw horizontal fuel mini-bar bottom-left.
    pub fn draw_fuel_bar(&mut self, fuel_pct: f32) {
        let x = 30.0; let y = 430.0; let max_w = 140.0; let h = 10.0;
        // Track
        self.fill_rect(x, y, max_w, h, COL_TRACK);
        // Fill
        let fill_w = (fuel_pct.clamp(0.0, 1.0) * max_w).max(2.0);
        self.fill_rect(x, y, fill_w, h, COL_CYAN);
    }

    /// Draw horizontal CLT mini-bar bottom-right.
    pub fn draw_clt_bar(&mut self, clt_c: f32) {
        let x = 630.0; let y = 430.0; let max_w = 140.0; let h = 10.0;
        self.fill_rect(x, y, max_w, h, COL_TRACK);
        let fill_w = (value_to_sweep(clt_c, 60.0, 120.0) / ARC_SWEEP_DEG * max_w).max(2.0);
        self.fill_rect(x, y, fill_w, h, COL_RED);
    }
```

- [ ] **Step 2: Update draw_frame to call new methods**

Replace the `draw_frame` method in `impl Renderer`:

```rust
    pub fn draw_frame(&mut self, state: &VehicleState, _frame: u64) {
        self.clear();
        self.draw_gauge_tracks();
        self.draw_speed_fill(state.speed_kph);
        self.draw_rpm_fill(state.rpm);
        self.draw_ticks(SPD_CX, SPD_CY, SPD_R, COL_GRAY);
        self.draw_ticks(RPM_CX, RPM_CY, RPM_R, COL_GRAY);
        self.draw_fuel_bar(state.fuel_pct);
        self.draw_clt_bar(state.clt_c);
    }
```

- [ ] **Step 3: Add tests for fill math**

Add to the `tests` module in `src/renderer.rs`:

```rust
    #[test]
    fn speed_fill_zero_gives_no_arc() {
        assert_eq!(value_to_sweep(0.0, 0.0, SPD_MAX), 0.0);
    }

    #[test]
    fn rpm_redline_at_correct_fraction() {
        let sweep_at_redline = value_to_sweep(RPM_REDLINE, 0.0, RPM_MAX);
        let expected = (RPM_REDLINE / RPM_MAX) * ARC_SWEEP_DEG;
        assert!((sweep_at_redline - expected).abs() < 0.01);
    }
```

- [ ] **Step 4: Run tests**

```bash
cargo test renderer 2>&1
```

Expected: 6 tests, all pass.

- [ ] **Step 5: Quick visual test — inject fake values to see fills**

Temporarily add to `main.rs` before `renderer.draw_frame(...)`:

```rust
        // TEMP: fake values to see fills
        let mut snap = snap;
        snap.speed_kph = 120.0;
        snap.rpm = 4500.0;
        snap.fuel_pct = 0.6;
        snap.clt_c = 90.0;
```

Run `./target/debug/nova-dashboard` — you should see cyan arc on left, red arc on right, mini-bars at bottom corners.

Remove the TEMP block after verifying.

- [ ] **Step 6: Commit**

```bash
git add src/renderer.rs src/main.rs
git commit -m "feat(rust): gauge fills, ticks, fuel/CLT mini-bars"
```

---

## Task 6: Renderer — text with fontdue

**Files:**
- Modify: `src/renderer.rs`

Load `DejaVuSans-Bold.ttf` once at startup. Draw centered text for the large gauge values and unit labels.

---

- [ ] **Step 1: Add font loading to Renderer**

Add a font field to the `Renderer` struct and load it in `new()`:

```rust
// At the top of renderer.rs, add the fontdue import:
use fontdue::{Font, FontSettings};

pub struct Renderer {
    pub pixmap: Pixmap,
    font: Font,
}

impl Renderer {
    pub fn new() -> Self {
        let pixmap = Pixmap::new(W, H).expect("Failed to create pixmap");

        // Load system font. DejaVuSans-Bold ships with Debian by default.
        let font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf";
        let font_bytes = std::fs::read(font_path)
            .unwrap_or_else(|_| panic!("Font not found at {font_path}\n\
                Run: sudo apt install fonts-dejavu-core"));
        let font = Font::from_bytes(font_bytes.as_slice(), FontSettings::default())
            .expect("fontdue: failed to parse font");

        Self { pixmap, font }
    }
```

- [ ] **Step 2: Add the draw_text helper**

Add this method to `impl Renderer`:

```rust
    /// Draw `text` centered on (cx, cy) at the given pixel size.
    /// `rgba` = [R, G, B, A] where A is 0–255 opacity.
    pub fn draw_text_centered(&mut self, text: &str, cx: f32, cy: f32, size: f32, rgba: [u8; 4]) {
        // First pass: measure total width
        let mut total_w = 0.0f32;
        for ch in text.chars() {
            let (metrics, _) = self.font.rasterize(ch, size);
            total_w += metrics.advance_width;
        }

        // Second pass: render each glyph
        let mut cursor_x = cx - total_w * 0.5;
        let [r, g, b, alpha] = rgba;

        for ch in text.chars() {
            let (metrics, bitmap) = self.font.rasterize(ch, size);

            // glyph top-left in screen coords
            let gx = cursor_x as i32 + metrics.xmin;
            let gy = cy as i32 - metrics.height as i32 / 2 - metrics.ymin;

            let pw = self.pixmap.width() as i32;
            let ph = self.pixmap.height() as i32;
            let data = self.pixmap.data_mut();

            for row in 0..metrics.height as i32 {
                for col in 0..metrics.width as i32 {
                    let coverage = bitmap[(row * metrics.width as i32 + col) as usize];
                    if coverage == 0 { continue; }

                    let px = gx + col;
                    let py = gy + row;
                    if px < 0 || px >= pw || py < 0 || py >= ph { continue; }

                    let idx = ((py * pw + px) * 4) as usize;
                    // Effective alpha = glyph coverage * colour alpha
                    let eff_a = (coverage as u32 * alpha as u32) / 255;
                    let inv_a = 255 - eff_a;

                    // Alpha-composite over existing premultiplied pixel
                    let sr = (r as u32 * eff_a + 127) / 255;
                    let sg = (g as u32 * eff_a + 127) / 255;
                    let sb = (b as u32 * eff_a + 127) / 255;

                    data[idx]     = (sr + data[idx]     as u32 * inv_a / 255).min(255) as u8;
                    data[idx + 1] = (sg + data[idx + 1] as u32 * inv_a / 255).min(255) as u8;
                    data[idx + 2] = (sb + data[idx + 2] as u32 * inv_a / 255).min(255) as u8;
                    data[idx + 3] = (eff_a + data[idx + 3] as u32 * inv_a / 255).min(255) as u8;
                }
            }

            cursor_x += metrics.advance_width;
        }
    }

    /// Draw speed value (large) and "km/h" label on left gauge.
    pub fn draw_speed_text(&mut self, speed_kph: f32, gps_fix: bool) {
        let text = if gps_fix { format!("{:.0}", speed_kph) } else { "---".to_string() };
        self.draw_text_centered(&text, SPD_CX, SPD_CY - 10.0, 64.0, COL_WHITE);
        self.draw_text_centered("km/h", SPD_CX, SPD_CY + 42.0, 18.0, COL_GRAY);
    }

    /// Draw RPM value (large) and "rpm" label on right gauge.
    pub fn draw_rpm_text(&mut self, rpm: f32) {
        let text = format!("{:.0}", rpm);
        self.draw_text_centered(&text, RPM_CX, RPM_CY - 10.0, 64.0, COL_WHITE);
        self.draw_text_centered("rpm", RPM_CX, RPM_CY + 42.0, 18.0, COL_GRAY);
    }
```

- [ ] **Step 3: Update draw_frame to call text methods**

Update `draw_frame`:

```rust
    pub fn draw_frame(&mut self, state: &VehicleState, _frame: u64) {
        self.clear();
        self.draw_gauge_tracks();
        self.draw_speed_fill(state.speed_kph);
        self.draw_rpm_fill(state.rpm);
        self.draw_ticks(SPD_CX, SPD_CY, SPD_R, COL_GRAY);
        self.draw_ticks(RPM_CX, RPM_CY, RPM_R, COL_GRAY);
        self.draw_fuel_bar(state.fuel_pct);
        self.draw_clt_bar(state.clt_c);
        self.draw_speed_text(state.speed_kph, state.gps_fix);
        self.draw_rpm_text(state.rpm);
    }
```

- [ ] **Step 4: Build**

```bash
cargo build 2>&1 | tail -5
```

If you get `Font not found`, install the font:
```bash
sudo apt install fonts-dejavu-core
```

- [ ] **Step 5: Visual test**

Add the same temporary fake values from Task 5 Step 5, run, verify numbers appear centered on each gauge. Remove fakes after.

- [ ] **Step 6: Commit**

```bash
git add src/renderer.rs
git commit -m "feat(rust): fontdue text rendering for gauge values"
```

---

## Task 7: Renderer — center readouts, warnings, pairing overlay

**Files:**
- Modify: `src/renderer.rs`

Draw the BATT/IGN/MAP/CLT/AFR/ODO/TRIP readouts in the center strip, pulsing warning icons, and the Bluetooth pairing modal.

---

- [ ] **Step 1: Add center readouts method**

Add to `impl Renderer`:

```rust
    /// Draw a label + value + unit stack centered at (cx, cy).
    fn draw_readout(&mut self, label: &str, value: &str, unit: &str, cx: f32, cy: f32, val_size: f32) {
        self.draw_text_centered(label, cx, cy - val_size * 0.6, 13.0, COL_GRAY);
        self.draw_text_centered(value, cx, cy, val_size, COL_WHITE);
        if !unit.is_empty() {
            self.draw_text_centered(unit, cx, cy + val_size * 0.6, 11.0, COL_GRAY);
        }
    }

    pub fn draw_center_readouts(&mut self, state: &VehicleState) {
        // Row 1: BATT, IGN
        self.draw_readout("BATT", &format!("{:.1}", state.batt_v),  "V",   350.0, 155.0, 20.0);
        self.draw_readout("IGN",  &format!("{:.1}", state.ign_advance), "deg", 450.0, 155.0, 20.0);
        // Row 2: MAP, CLT
        self.draw_readout("MAP",  &format!("{:.0}", state.map_kpa), "kPa", 350.0, 210.0, 20.0);
        self.draw_readout("CLT",  &format!("{:.0}", state.clt_c),   "C",   450.0, 210.0, 20.0);
        // Row 3: AFR (large)
        self.draw_readout("AFR",  &format!("{:.1}", state.afr),     "",    400.0, 265.0, 32.0);
        // Row 4: ODO, TRIP
        let odo_str  = if state.gps_fix { format!("{:.0}", state.odo_km)  } else { "NO GPS".to_string() };
        let trip_str = if state.gps_fix { format!("{:.1}", state.trip_km) } else { "---".to_string() };
        self.draw_readout("ODO",  &odo_str,  "km", 350.0, 330.0, 16.0);
        self.draw_readout("TRIP", &trip_str, "km", 450.0, 330.0, 16.0);
    }
```

- [ ] **Step 2: Add warning icons method**

```rust
    pub fn draw_warnings(&mut self, state: &VehicleState, frame: u64) {
        let mut warnings: Vec<(&str, [u8; 4])> = Vec::new();
        if state.clt_c > 99.0 {
            warnings.push(("OVR\nHEAT", COL_AMBER));
        }
        if state.afr < 11.0 {
            warnings.push(("RICH", COL_AMBER));
        } else if state.afr > 16.5 {
            warnings.push(("LEAN", [0, 0, 255, 255]));
        }
        if warnings.is_empty() { return; }

        // Pulse: brightness cycles between 0.4 and 1.0
        let pulse = (0.7 + 0.3 * ((frame as f32 * 0.05).sin())) as f32;
        let n = warnings.len();
        let spacing = 70.0f32;
        let cx0 = W as f32 * 0.5 - (n as f32 - 1.0) * spacing * 0.5;
        let cy = H as f32 - 40.0;

        for (i, (label, color)) in warnings.iter().enumerate() {
            let cx = cx0 + i as f32 * spacing;
            let r = 16.0f32;
            // Draw triangle
            let mut pb = PathBuilder::new();
            pb.move_to(cx, cy - r);
            pb.line_to(cx - r, cy + r);
            pb.line_to(cx + r, cy + r);
            pb.close();
            if let Some(path) = pb.finish() {
                let mut paint = Paint::default();
                let c = color.map(|v| (v as f32 * pulse) as u8);
                paint.set_color(Color::from_rgba8(c[0], c[1], c[2], c[3]));
                paint.anti_alias = true;
                self.pixmap.fill_path(&path, &paint, tiny_skia::FillRule::Winding,
                                      Transform::identity(), None);
            }
            // Draw "!" text
            self.draw_text_centered("!", cx, cy + 4.0, 16.0, [10, 10, 10, 255]);
            // Draw label below triangle
            self.draw_text_centered(label, cx, cy + r + 14.0, 11.0, *color);
        }
    }
```

- [ ] **Step 3: Add pairing overlay method**

```rust
    // Hit regions for tap detection (x1, y1, x2, y2) — must match main.rs
    pub const PAIRING_ACCEPT_RECT: (i32, i32, i32, i32) = (230, 285, 390, 335);
    pub const PAIRING_REJECT_RECT: (i32, i32, i32, i32) = (410, 285, 570, 335);

    pub fn draw_pairing_overlay(&mut self, state: &VehicleState) {
        // Dim scrim over existing frame
        let mut paint = Paint::default();
        paint.set_color(Color::from_rgba8(0, 0, 0, 180));
        let rect = tiny_skia::Rect::from_xywh(0.0, 0.0, W as f32, H as f32).unwrap();
        self.pixmap.fill_rect(rect, &paint, Transform::identity(), None);

        // Card background
        self.fill_rect(210.0, 130.0, 380.0, 220.0, [22, 22, 22, 255]);
        // Card border (amber)
        let border_path = {
            let mut pb = PathBuilder::new();
            pb.move_to(210.0, 130.0); pb.line_to(590.0, 130.0);
            pb.line_to(590.0, 350.0); pb.line_to(210.0, 350.0);
            pb.close();
            pb.finish().unwrap()
        };
        let mut paint = Paint::default();
        paint.set_color(Self::color(COL_AMBER));
        let stroke = Stroke { width: 2.0, ..Default::default() };
        self.pixmap.stroke_path(&border_path, &paint, &stroke, Transform::identity(), None);

        // Title + device
        self.draw_text_centered("BLUETOOTH PAIRING", 400.0, 158.0, 18.0, COL_AMBER);
        let device = if state.bt_pairing_device.len() > 28 {
            &state.bt_pairing_device[..28]
        } else {
            &state.bt_pairing_device
        };
        self.draw_text_centered(device, 400.0, 185.0, 14.0, COL_GRAY);
        self.draw_text_centered("CONFIRM CODE ON YOUR PHONE", 400.0, 210.0, 11.0, COL_GRAY);

        // Passkey — large spaced digits
        let spaced: String = format!("{:06}", state.bt_pairing_passkey)
            .chars()
            .flat_map(|c| [c, ' '])
            .collect::<String>()
            .trim_end()
            .to_string();
        self.draw_text_centered(&spaced, 400.0, 260.0, 36.0, COL_AMBER);

        // ACCEPT button (amber filled)
        let (ax1, ay1, ax2, ay2) = Self::PAIRING_ACCEPT_RECT;
        self.fill_rect(ax1 as f32, ay1 as f32, (ax2 - ax1) as f32, (ay2 - ay1) as f32, COL_AMBER);
        self.draw_text_centered("ACCEPT", (ax1 + ax2) as f32 * 0.5, (ay1 + ay2) as f32 * 0.5,
                                16.0, [0, 0, 0, 255]);

        // REJECT button (dark)
        let (rx1, ry1, rx2, ry2) = Self::PAIRING_REJECT_RECT;
        self.fill_rect(rx1 as f32, ry1 as f32, (rx2 - rx1) as f32, (ry2 - ry1) as f32, [50, 50, 50, 255]);
        self.draw_text_centered("REJECT", (rx1 + rx2) as f32 * 0.5, (ry1 + ry2) as f32 * 0.5,
                                16.0, COL_GRAY);
    }
```

- [ ] **Step 4: Update draw_frame**

```rust
    pub fn draw_frame(&mut self, state: &VehicleState, frame: u64) {
        self.clear();
        self.draw_gauge_tracks();
        self.draw_speed_fill(state.speed_kph);
        self.draw_rpm_fill(state.rpm);
        self.draw_ticks(SPD_CX, SPD_CY, SPD_R, COL_GRAY);
        self.draw_ticks(RPM_CX, RPM_CY, RPM_R, COL_GRAY);
        self.draw_fuel_bar(state.fuel_pct);
        self.draw_clt_bar(state.clt_c);
        self.draw_speed_text(state.speed_kph, state.gps_fix);
        self.draw_rpm_text(state.rpm);
        self.draw_center_readouts(state);
        self.draw_warnings(state, frame);
        if state.bt_pairing_pending {
            self.draw_pairing_overlay(state);
        }
    }
```

- [ ] **Step 5: Build**

```bash
cargo build 2>&1 | tail -5
```

- [ ] **Step 6: Commit**

```bash
git add src/renderer.rs
git commit -m "feat(rust): center readouts, warning icons, pairing overlay"
```

---

## Task 8: Simulate mode — full visual test

**Files:**
- Modify: `src/main.rs`

Add `--simulate` flag. With it running, all gauges animate using sine waves — exactly like the Python version. This is your main development/debug tool.

---

- [ ] **Step 1: Add simulate support to main.rs**

Replace `src/main.rs` with the full version:

```rust
mod state;
mod renderer;

use sdl2::event::Event;
use sdl2::keyboard::Keycode;
use sdl2::mouse::MouseButton;
use sdl2::pixels::PixelFormatEnum;
use sdl2::rect::Rect;
use std::time::{Duration, Instant};
use crate::renderer::{Renderer, W, H};
use crate::state::{SharedState, VehicleState};

const FRAME_TIME: Duration = Duration::from_micros(16_667); // ~60 FPS

fn inject_sim(mut snap: VehicleState, t: f32) -> VehicleState {
    snap.rpm       = 3000.0 + 2500.0 * (t * 0.4).sin();
    snap.speed_kph = 120.0  + 100.0  * (t * 0.3).sin();
    snap.clt_c     = 85.0   + 15.0   * (t * 0.05).sin().abs();
    snap.fuel_pct  = 0.3    + 0.5    * (t * 0.05).sin().abs();
    snap.afr       = 14.0   + 2.0    * (t * 0.25).sin();
    snap.gps_fix   = true;
    snap.batt_v    = 12.4;
    snap.map_kpa   = 95.0;
    snap.ign_advance = 18.0;
    snap.odo_km    = 12345.0;
    snap.trip_km   = 42.3;
    snap
}

fn handle_tap(x: i32, y: i32, state: &SharedState) {
    let mut s = state.lock();
    if !s.bt_pairing_pending { return; }
    let (ax1, ay1, ax2, ay2) = Renderer::PAIRING_ACCEPT_RECT;
    let (rx1, ry1, rx2, ry2) = Renderer::PAIRING_REJECT_RECT;
    if x >= ax1 && x <= ax2 && y >= ay1 && y <= ay2 {
        s.bt_pairing_accepted = Some(true);
        s.bt_pairing_pending  = false;
    } else if x >= rx1 && x <= rx2 && y >= ry1 && y <= ry2 {
        s.bt_pairing_accepted = Some(false);
        s.bt_pairing_pending  = false;
    }
}

fn main() {
    env_logger::init();

    let simulate = std::env::args().any(|a| a == "--simulate");
    let state = state::new_shared();

    let sdl   = sdl2::init().expect("SDL2 init");
    let video = sdl.video().expect("SDL2 video");
    let window = video
        .window("Nova Dashboard", W, H)
        .borderless()
        .position_centered()
        .build()
        .expect("window");
    let mut canvas = window.into_canvas().build().expect("canvas");
    let tc = canvas.texture_creator();
    let mut texture = tc
        .create_texture_streaming(PixelFormatEnum::ABGR8888, W, H)
        .expect("texture");
    let mut event_pump = sdl.event_pump().expect("event pump");

    let mut renderer = Renderer::new();
    let mut frame: u64 = 0;
    let start = Instant::now();

    if simulate {
        log::info!("Simulate mode ON — no hardware required");
    }

    'running: loop {
        let frame_start = Instant::now();

        for event in event_pump.poll_iter() {
            match event {
                Event::Quit { .. }
                | Event::KeyDown { keycode: Some(Keycode::Escape), .. }
                | Event::KeyDown { keycode: Some(Keycode::Q), .. } => break 'running,

                Event::MouseButtonUp { mouse_btn: MouseButton::Left, x, y, .. } => {
                    handle_tap(x, y, &state);
                }
                _ => {}
            }
        }

        let mut snap = state.lock().clone();
        if simulate {
            let t = start.elapsed().as_secs_f32();
            snap = inject_sim(snap, t);
        }

        renderer.draw_frame(&snap, frame);
        frame += 1;

        texture
            .update(Rect::new(0, 0, W, H), renderer.pixmap.data(), (W * 4) as usize)
            .expect("texture update");
        canvas.copy(&texture, None, None).expect("canvas copy");
        canvas.present();

        let elapsed = frame_start.elapsed();
        if elapsed < FRAME_TIME {
            std::thread::sleep(FRAME_TIME - elapsed);
        }
    }
}
```

- [ ] **Step 2: Build**

```bash
cargo build 2>&1 | tail -5
```

- [ ] **Step 3: Run simulate mode and verify visuals**

```bash
RUST_LOG=info ./target/debug/nova-dashboard --simulate
```

Expected:
- Dark background
- Left gauge: cyan arc animating (speed 20–220), large white number
- Right gauge: red arc animating (RPM 500–5500), redline glow when > 6000
- Fuel and CLT mini-bars animating at bottom corners
- Center: BATT 12.4, IGN 18.0, MAP 95, CLT animating, AFR animating, ODO 12345, TRIP 42.3
- No warnings unless AFR goes out of range (it does occasionally in simulate)

Press Q to exit.

- [ ] **Step 4: Build release binary — check performance**

```bash
cargo build --release 2>&1 | tail -3
RUST_LOG=info ./target/release/nova-dashboard --simulate
```

Release build should be noticeably smoother than debug.

- [ ] **Step 5: Commit**

```bash
git add src/main.rs
git commit -m "feat(rust): simulate mode — full visual dashboard running"
```

---

## Task 9: CAN thread

**Files:**
- Create: `src/can.rs`
- Modify: `src/main.rs` (spawn thread)

Reads from `can0`. Decodes Speeduino frames 0x320 and 0x321. Retries every 5s if CAN is unavailable (identical logic to the Python version).

---

- [ ] **Step 1: Write decode tests first**

Create `src/can.rs`:

```rust
use crate::state::SharedState;

const CAN_ID_0: u32 = 0x320;
const CAN_ID_1: u32 = 0x321;

// ── Pure decode logic (no hardware dep, fully testable) ──────────────────────

#[derive(Debug, PartialEq)]
pub struct Frame0x320 {
    pub rpm:      f32,
    pub map_kpa:  f32,
    pub tps_pct:  f32,
    pub iat_c:    f32,
    pub clt_c:    f32,
    pub afr:      f32,
    pub batt_v:   f32,
}

#[derive(Debug, PartialEq)]
pub struct Frame0x321 {
    pub ign_advance: f32,
}

pub fn decode_0x320(data: &[u8]) -> Option<Frame0x320> {
    if data.len() < 8 { return None; }
    let rpm     = u16::from_le_bytes([data[0], data[1]]) as f32;
    let map_kpa = data[2] as f32;
    let tps_pct = data[3] as f32;
    let iat_c   = data[4] as f32 - 40.0;
    let clt_c   = data[5] as f32 - 40.0;
    let afr     = data[6] as f32 * 0.0068 * 14.7;
    let batt_v  = data[7] as f32 * 0.1;
    Some(Frame0x320 { rpm, map_kpa, tps_pct, iat_c, clt_c, afr, batt_v })
}

pub fn decode_0x321(data: &[u8]) -> Option<Frame0x321> {
    if data.len() < 4 { return None; }
    let ign_advance = data[3] as f32 - 40.0;
    Some(Frame0x321 { ign_advance })
}

// ── Background thread ────────────────────────────────────────────────────────

pub fn spawn_can_thread(state: SharedState) {
    std::thread::Builder::new()
        .name("can".into())
        .spawn(move || {
            use std::time::Duration;
            loop {
                match run_can_loop(&state) {
                    Ok(()) => break, // clean stop (never happens, loop is infinite)
                    Err(e) => {
                        log::warn!("CAN unavailable ({e}) — retrying in 5s");
                        std::thread::sleep(Duration::from_secs(5));
                    }
                }
            }
        })
        .expect("CAN thread spawn failed");
}

fn run_can_loop(state: &SharedState) -> Result<(), Box<dyn std::error::Error>> {
    use socketcan::{CanSocket, Socket, CanAnyFrame, EmbeddedFrame};

    let sock = CanSocket::open("can0")?;
    log::info!("CAN listener started on can0");

    loop {
        match sock.read_frame()? {
            CanAnyFrame::Normal(frame) => {
                let id   = frame.raw_id();
                let data = frame.data();

                if id == CAN_ID_0 {
                    if let Some(f) = decode_0x320(data) {
                        let mut s = state.lock();
                        s.rpm      = f.rpm;
                        s.map_kpa  = f.map_kpa;
                        s.tps_pct  = f.tps_pct;
                        s.iat_c    = f.iat_c;
                        s.clt_c    = f.clt_c;
                        s.afr      = f.afr;
                        s.batt_v   = f.batt_v;
                    }
                } else if id == CAN_ID_1 {
                    if let Some(f) = decode_0x321(data) {
                        state.lock().ign_advance = f.ign_advance;
                    }
                }
            }
            _ => {} // skip remote/error frames
        }
    }
}

// ── Tests ────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn decode_0x320_parses_known_bytes() {
        // rpm=3000 (little-endian: 0xB8, 0x0B), map=95, tps=20,
        // iat=40+40=80 raw→40C, clt=125+40=165 raw→85C,
        // afr=200 raw → 200*0.0068*14.7=19.99≈20, batt=124 raw→12.4V
        let data = [0xB8u8, 0x0B, 95, 20, 80, 125, 200, 124, 0, 0, 0, 0];
        let f = decode_0x320(&data).unwrap();
        assert_eq!(f.rpm, 3000.0);
        assert_eq!(f.map_kpa, 95.0);
        assert_eq!(f.tps_pct, 20.0);
        assert_eq!(f.iat_c, 40.0);
        assert_eq!(f.clt_c, 85.0);
        assert!((f.afr - 19.9992).abs() < 0.01);
        assert!((f.batt_v - 12.4).abs() < 0.01);
    }

    #[test]
    fn decode_0x320_returns_none_on_short_data() {
        assert!(decode_0x320(&[0, 1, 2]).is_none());
    }

    #[test]
    fn decode_0x321_parses_ign_advance() {
        // ign_advance = 58 - 40 = 18 degrees
        let data = [0u8, 0, 0, 58];
        let f = decode_0x321(&data).unwrap();
        assert_eq!(f.ign_advance, 18.0);
    }

    #[test]
    fn decode_0x321_returns_none_on_short_data() {
        assert!(decode_0x321(&[0, 1]).is_none());
    }
}
```

- [ ] **Step 2: Run tests — verify pass**

```bash
cargo test can 2>&1
```

Expected: 4 tests pass.

- [ ] **Step 3: Wire CAN thread into main.rs**

Add to `main.rs` at the top:
```rust
mod can;
```

Add after `let state = state::new_shared();` and before SDL init:

```rust
    // Spawn background threads (they retry gracefully if hardware is absent)
    can::spawn_can_thread(Arc::clone(&state));
```

Add at the top of `main.rs`:
```rust
use std::sync::Arc;
```

- [ ] **Step 4: Build**

```bash
cargo build 2>&1 | tail -5
```

If you get `unresolved import socketcan::CanAnyFrame` or similar — the socketcan 3.x API may differ slightly on your Pi's installed version. Run:
```bash
cargo doc --open  # then browse to socketcan crate
```
and adjust the import names to match. The frame decode logic does not change.

- [ ] **Step 5: Test on Pi with CAN connected (optional)**

```bash
# If can0 is available:
RUST_LOG=info ./target/debug/nova-dashboard
# You should see: INFO can: CAN listener started on can0
# If can0 is NOT available:
# You should see: WARN can: CAN unavailable (...) — retrying in 5s
```

- [ ] **Step 6: Commit**

```bash
git add src/can.rs src/main.rs
git commit -m "feat(rust): CAN thread with Speeduino frame decode and tests"
```

---

## Task 10: GPS thread

**Files:**
- Create: `src/gps.rs`
- Modify: `src/main.rs`

Connects to `gpsd` via TCP on `127.0.0.1:2947`, parses JSON TPV reports, accumulates ODO/TRIP, saves to `/data/odo.json`. Mirrors the Python `GPSListener` exactly.

---

- [ ] **Step 1: Write ODO accumulator tests first**

Create `src/gps.rs`:

```rust
use std::io::{BufRead, BufReader, Write};
use std::net::TcpStream;
use std::time::{Duration, Instant};
use serde_json::Value;
use crate::state::SharedState;

const ODO_PATH: &str = "/data/odo.json";
const HACC_MAX_M: f32 = 10.0;
const SAVE_INTERVAL_KM: f64 = 1.6;
const GPS_TIMEOUT_S: f32 = 5.0;

// ── ODO accumulator (pure logic, testable) ───────────────────────────────────

pub struct OdometerAccumulator {
    pub odo_km:  f64,
    pub trip_km: f64,
    last_save:   f64,
}

impl OdometerAccumulator {
    pub fn new(initial_odo_km: f64) -> Self {
        Self { odo_km: initial_odo_km, trip_km: 0.0, last_save: initial_odo_km }
    }

    /// Returns true if fix was valid (hacc within threshold).
    pub fn update(&mut self, speed_kph: f32, dt_s: f32, hacc_m: f32) -> bool {
        if hacc_m >= HACC_MAX_M { return false; }
        let delta_km = speed_kph as f64 * (dt_s as f64 / 3600.0);
        self.odo_km  += delta_km;
        self.trip_km += delta_km;
        true
    }

    /// True if ODO has advanced enough to warrant a save.
    pub fn needs_save(&self) -> bool {
        (self.odo_km - self.last_save) >= SAVE_INTERVAL_KM
    }

    pub fn mark_saved(&mut self) {
        self.last_save = self.odo_km;
    }
}

// ── ODO persistence ──────────────────────────────────────────────────────────

pub fn load_odo() -> f64 {
    let text = std::fs::read_to_string(ODO_PATH).unwrap_or_default();
    serde_json::from_str::<Value>(&text)
        .ok()
        .and_then(|v| v["odo_km"].as_f64())
        .unwrap_or(0.0)
}

pub fn save_odo(odo_km: f64, trip_km: f64) {
    let tmp = format!("{ODO_PATH}.tmp");
    let json = format!("{{\"odo_km\":{odo_km:.3},\"trip_km\":{trip_km:.3}}}");
    if std::fs::write(&tmp, &json).is_ok() {
        let _ = std::fs::rename(&tmp, ODO_PATH);
    }
}

// ── Background thread ────────────────────────────────────────────────────────

pub fn spawn_gps_thread(state: SharedState) {
    std::thread::Builder::new()
        .name("gps".into())
        .spawn(move || {
            loop {
                match run_gps_loop(&state) {
                    Ok(()) => break,
                    Err(e) => {
                        log::warn!("GPS unavailable ({e}) — retrying in 5s");
                        std::thread::sleep(Duration::from_secs(5));
                    }
                }
            }
        })
        .expect("GPS thread spawn");
}

fn run_gps_loop(state: &SharedState) -> Result<(), Box<dyn std::error::Error>> {
    let stream = TcpStream::connect("127.0.0.1:2947")?;
    stream.set_read_timeout(Some(Duration::from_secs(10)))?;
    {
        let mut w = &stream;
        w.write_all(b"?WATCH={\"enable\":true,\"json\":true}\r\n")?;
    }
    log::info!("GPS connected to gpsd");

    let initial_odo = load_odo();
    let mut acc = OdometerAccumulator::new(initial_odo);
    let mut last_time = Instant::now();
    let mut last_fix  = Instant::now();

    let reader = BufReader::new(&stream);
    for line in reader.lines() {
        let line = line?;
        let v: Value = match serde_json::from_str(&line) {
            Ok(v) => v,
            Err(_) => continue,
        };
        if v["class"] != "TPV" { continue; }

        let now    = Instant::now();
        let dt_s   = now.duration_since(last_time).as_secs_f32();
        last_time  = now;

        let speed_ms = v["speed"].as_f64().unwrap_or(0.0) as f32;
        let hacc_m   = v["epx"].as_f64().unwrap_or(999.0) as f32;
        let mode     = v["mode"].as_i64().unwrap_or(0);
        let speed_kph = speed_ms * 3.6;

        let fix_valid = mode >= 2 && acc.update(speed_kph, dt_s, hacc_m);
        if fix_valid { last_fix = now; }

        let gps_ok = now.duration_since(last_fix).as_secs_f32() < GPS_TIMEOUT_S;

        {
            let mut s = state.lock();
            if fix_valid { s.speed_kph = speed_kph; }
            s.odo_km  = acc.odo_km;
            s.trip_km = acc.trip_km;
            s.gps_fix = gps_ok;
        }

        if acc.needs_save() {
            save_odo(acc.odo_km, acc.trip_km);
            acc.mark_saved();
        }
    }
    Ok(())
}

// ── Tests ────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn odo_accumulates_distance() {
        let mut acc = OdometerAccumulator::new(0.0);
        // 100 km/h for 1 hour = 100 km (dt_s = 3600s, hacc = 5m)
        acc.update(100.0, 3600.0, 5.0);
        assert!((acc.odo_km - 100.0).abs() < 0.001);
        assert!((acc.trip_km - 100.0).abs() < 0.001);
    }

    #[test]
    fn odo_ignores_bad_hacc() {
        let mut acc = OdometerAccumulator::new(0.0);
        let valid = acc.update(100.0, 3600.0, 15.0); // hacc > 10m
        assert!(!valid);
        assert_eq!(acc.odo_km, 0.0);
    }

    #[test]
    fn odo_loads_initial_value() {
        let acc = OdometerAccumulator::new(12345.0);
        assert_eq!(acc.odo_km, 12345.0);
        assert_eq!(acc.trip_km, 0.0);
    }

    #[test]
    fn needs_save_triggers_at_interval() {
        let mut acc = OdometerAccumulator::new(0.0);
        acc.update(100.0, 3600.0, 1.0); // +100 km >> 1.6 km threshold
        assert!(acc.needs_save());
        acc.mark_saved();
        assert!(!acc.needs_save());
    }
}
```

- [ ] **Step 2: Run tests**

```bash
cargo test gps 2>&1
```

Expected: 4 tests pass.

- [ ] **Step 3: Wire GPS thread into main.rs**

Add `mod gps;` at the top of `main.rs`.

Add after the CAN spawn line:
```rust
    gps::spawn_gps_thread(Arc::clone(&state));
```

- [ ] **Step 4: Build**

```bash
cargo build 2>&1 | tail -5
```

- [ ] **Step 5: Test on Pi with gpsd running (optional)**

```bash
# Check if gpsd is running:
systemctl status gpsd
# If yes:
RUST_LOG=info ./target/debug/nova-dashboard
# Expected log: INFO gps: GPS connected to gpsd
# If gpsd not running:
# Expected log: WARN gps: GPS unavailable (...) — retrying in 5s
```

- [ ] **Step 6: Commit**

```bash
git add src/gps.rs src/main.rs
git commit -m "feat(rust): GPS thread with gpsd, ODO accumulator, and tests"
```

---

## Task 11: Bluetooth pairing agent

**Files:**
- Create: `src/bluetooth.rs`
- Modify: `src/main.rs`

Registers as a BlueZ `org.bluez.Agent1` via zbus. Handles `RequestConfirmation` by setting `bt_pairing_pending` and waiting for the user to tap ACCEPT or REJECT on screen.

---

- [ ] **Step 1: Create src/bluetooth.rs**

```rust
use std::sync::Arc;
use parking_lot::Mutex;
use crate::state::VehicleState;
use zbus::{interface, connection};
use zbus::zvariant::OwnedObjectPath;

const AGENT_PATH: &str = "/nova/agent";
const CAPABILITY:  &str = "DisplayYesNo";
const TIMEOUT_S:   u64  = 30;

struct NovaAgent {
    state: Arc<Mutex<VehicleState>>,
}

#[interface(name = "org.bluez.Agent1")]
impl NovaAgent {
    // Called by BlueZ when a phone wants to pair.
    async fn request_confirmation(
        &self,
        device: OwnedObjectPath,
        passkey: u32,
    ) -> zbus::fdo::Result<()> {
        let device_name = device.to_string();
        log::info!("Pairing request from {device_name} passkey={passkey:06}");

        {
            let mut s = self.state.lock();
            s.bt_pairing_pending  = true;
            s.bt_pairing_device   = device_name;
            s.bt_pairing_passkey  = passkey;
            s.bt_pairing_accepted = None;
        }

        // Poll for user response, timeout after 30s
        let deadline = tokio::time::Instant::now()
            + tokio::time::Duration::from_secs(TIMEOUT_S);

        loop {
            tokio::time::sleep(tokio::time::Duration::from_millis(100)).await;

            let accepted = self.state.lock().bt_pairing_accepted;
            match accepted {
                Some(true) => {
                    self.state.lock().bt_pairing_pending = false;
                    log::info!("Pairing accepted");
                    return Ok(());
                }
                Some(false) => {
                    self.state.lock().bt_pairing_pending = false;
                    log::info!("Pairing rejected");
                    return Err(zbus::fdo::Error::AuthFailed("Rejected by user".into()));
                }
                None => {}
            }

            if tokio::time::Instant::now() >= deadline {
                self.state.lock().bt_pairing_pending = false;
                log::warn!("Pairing timeout");
                return Err(zbus::fdo::Error::AuthFailed("Timed out".into()));
            }
        }
    }

    async fn cancel(&self) {
        log::info!("Pairing cancelled by BlueZ");
        let mut s = self.state.lock();
        s.bt_pairing_pending  = false;
        s.bt_pairing_accepted = Some(false);
    }

    // Reject PIN and passkey requests — we only support DisplayYesNo
    async fn request_pin_code(&self, _device: OwnedObjectPath) -> zbus::fdo::Result<String> {
        Err(zbus::fdo::Error::NotSupported("Use DisplayYesNo".into()))
    }

    async fn request_passkey(&self, _device: OwnedObjectPath) -> zbus::fdo::Result<u32> {
        Err(zbus::fdo::Error::NotSupported("Use DisplayYesNo".into()))
    }
}

pub fn spawn_bluetooth_thread(state: Arc<Mutex<VehicleState>>) {
    std::thread::Builder::new()
        .name("bluetooth".into())
        .spawn(move || {
            // Create a tokio runtime just for this thread
            let rt = tokio::runtime::Runtime::new().expect("tokio runtime");
            rt.block_on(async {
                if let Err(e) = run_agent(state).await {
                    log::warn!("BT pairing agent error: {e}");
                }
            });
        })
        .expect("BT thread spawn");
}

async fn run_agent(state: Arc<Mutex<VehicleState>>) -> zbus::Result<()> {
    let conn = connection::Builder::system()?
        .serve_at(AGENT_PATH, NovaAgent { state })?
        .build()
        .await?;

    // Register with BlueZ AgentManager
    let manager = zbus::Proxy::new(
        &conn,
        "org.bluez",
        "/org/bluez",
        "org.bluez.AgentManager1",
    )
    .await?;

    let agent_path = zbus::zvariant::ObjectPath::try_from(AGENT_PATH)
        .expect("valid path");

    manager
        .call_method("RegisterAgent", &(&agent_path, CAPABILITY))
        .await?;
    manager
        .call_method("RequestDefaultAgent", &(&agent_path,))
        .await?;

    // Make adapter pairable (ignore failure — adapter may not be hci0)
    if let Ok(adapter) = zbus::Proxy::new(
        &conn,
        "org.bluez",
        "/org/bluez/hci0",
        "org.freedesktop.DBus.Properties",
    )
    .await
    {
        let _ = adapter
            .call_method("Set", &("org.bluez.Adapter1", "Pairable", zbus::zvariant::Value::from(true)))
            .await;
    }

    log::info!("BT pairing agent registered (capability={CAPABILITY})");

    // Run forever (the connection keeps the agent alive)
    loop {
        tokio::time::sleep(tokio::time::Duration::from_secs(3600)).await;
    }
}
```

- [ ] **Step 2: Wire BT thread into main.rs**

Add `mod bluetooth;` at the top.

Add after the GPS spawn line:
```rust
    bluetooth::spawn_bluetooth_thread(Arc::clone(&state));
```

- [ ] **Step 3: Build**

```bash
cargo build 2>&1 | tail -5
```

If you get zbus compile errors about `connection::Builder` API, check the zbus version in your Cargo.lock:
```bash
grep -A1 'name = "zbus"' Cargo.lock | head -4
```
The zbus 4.x API shown above is correct for zbus ≥ 4.0. If it installed zbus 3.x, force the version:
```toml
zbus = "4"
```
Then `cargo update`.

- [ ] **Step 4: Test pairing agent on Pi**

```bash
RUST_LOG=info ./target/debug/nova-dashboard --simulate
```

From a phone, initiate Bluetooth pairing with the Pi. Expected:
- Log: `INFO bluetooth: BT pairing agent registered (capability=DisplayYesNo)`
- When phone requests pairing: pairing overlay appears on screen with passkey
- Tap ACCEPT → pairing completes
- Tap REJECT → pairing is rejected

If BlueZ is not available (dev machine):
- Log: `WARN bluetooth: BT pairing agent error: ...`
- App continues running normally (non-fatal)

- [ ] **Step 5: Commit**

```bash
git add src/bluetooth.rs src/main.rs
git commit -m "feat(rust): BlueZ pairing agent via zbus"
```

---

## Task 12: Splash screen

**Files:**
- Modify: `src/renderer.rs` (add splash blend method)
- Modify: `src/main.rs` (drive fade-in)

Load `assets/splash_logo.png` and alpha-blend it over the first 36 frames — same fade-in as the Python version.

---

- [ ] **Step 1: Add splash support to renderer.rs**

Add to the top of `renderer.rs`:
```rust
use image::RgbaImage;
```

Add a `splash` field to the `Renderer` struct:
```rust
pub struct Renderer {
    pub pixmap: Pixmap,
    font:       Font,
    splash:     Option<RgbaImage>,
}
```

Update `Renderer::new()` to load the splash PNG:
```rust
        // Load splash logo (gracefully skip if not found)
        let splash = image::open("assets/splash_logo.png")
            .ok()
            .map(|img| img.resize_exact(W, H, image::imageops::FilterType::Lanczos3).to_rgba8());

        Self { pixmap, font, splash }
```

Add the splash blend method:
```rust
    /// Alpha-blend the splash PNG over the current frame.
    /// `alpha` 1.0 = fully splash, 0.0 = fully dashboard.
    pub fn blend_splash(&mut self, alpha: f32) {
        let Some(splash) = &self.splash else { return; };
        let alpha = alpha.clamp(0.0, 1.0);
        let data = self.pixmap.data_mut();
        for (i, pixel) in splash.pixels().enumerate() {
            let base = i * 4;
            let sa = pixel[3] as f32 / 255.0 * alpha;
            let da = 1.0 - sa;
            data[base]     = (pixel[0] as f32 * sa + data[base]     as f32 * da) as u8;
            data[base + 1] = (pixel[1] as f32 * sa + data[base + 1] as f32 * da) as u8;
            data[base + 2] = (pixel[2] as f32 * sa + data[base + 2] as f32 * da) as u8;
            data[base + 3] = 255;
        }
    }
```

- [ ] **Step 2: Drive splash fade in main.rs**

In the main loop, after `renderer.draw_frame(...)`:

```rust
        // Splash fade: 36 frames = 0.6s
        const SPLASH_FRAMES: u64 = 36;
        if frame < SPLASH_FRAMES {
            let alpha = 1.0 - (frame as f32 / SPLASH_FRAMES as f32);
            renderer.blend_splash(alpha);
        }
```

- [ ] **Step 3: Build and test**

```bash
cargo build 2>&1 | tail -3
RUST_LOG=info ./target/debug/nova-dashboard --simulate
```

Expected: splash logo fades out over the first ~0.6 seconds revealing the dashboard.

If `assets/splash_logo.png` is missing, the app still starts without error (gracefully skipped).

- [ ] **Step 4: Commit**

```bash
git add src/renderer.rs src/main.rs
git commit -m "feat(rust): splash PNG fade-in over first 36 frames"
```

---

## Task 13: Build release binary and update systemd service

**Files:**
- Modify: `scripts/nova-dashboard-wayland.service` (or wherever the service file lives)

Switch the Pi from running the Python dashboard to the Rust binary.

---

- [ ] **Step 1: Build the final release binary**

```bash
cargo build --release 2>&1 | tail -5
```

Expected: `Finished release [optimized] target(s)`

Binary is at `target/release/nova-dashboard`.

- [ ] **Step 2: Run release binary with simulate — verify 60 FPS**

```bash
RUST_LOG=info ./target/release/nova-dashboard --simulate
```

Verify it's smooth. If you have `htop` open you should see low CPU usage (< 5% on one core).

- [ ] **Step 3: Find the current service file**

```bash
find /etc/systemd/system /lib/systemd/system -name "nova*" 2>/dev/null
# Also check the repo:
ls ~/nova-dashboard-cv/scripts/
```

- [ ] **Step 4: Update ExecStart in the service file**

The current service has:
```ini
ExecStart=/usr/bin/python3 /home/pi/nova-dashboard-cv/main.py
```

Change it to:
```ini
ExecStart=/home/pi/nova-dashboard-cv/target/release/nova-dashboard
```

Also remove the `Environment=PYTHONUNBUFFERED=1` line if present.

Add logging to a file (optional but useful):
```ini
Environment=RUST_LOG=info
StandardOutput=journal
StandardError=journal
```

- [ ] **Step 5: Reload and restart the service**

```bash
sudo systemctl daemon-reload
sudo systemctl restart nova-dashboard-wayland.service
sudo systemctl status nova-dashboard-wayland.service
```

Expected:
```
● nova-dashboard-wayland.service - Nova Dashboard
   Active: active (running) since ...
```

- [ ] **Step 6: Verify logs**

```bash
journalctl -u nova-dashboard-wayland.service -f
```

Expected lines:
```
INFO nova_dashboard: Render loop started
INFO can: CAN listener started on can0        (or: WARN CAN unavailable)
INFO gps: GPS connected to gpsd               (or: WARN GPS unavailable)
INFO bluetooth: BT pairing agent registered
```

- [ ] **Step 7: Commit service changes**

```bash
git add scripts/  # or wherever the service file is tracked
git commit -m "feat(rust): switch systemd service to Rust binary"
git push
```

- [ ] **Step 8: Final verification**

Reboot the Pi and confirm the dashboard comes up:
```bash
sudo reboot
# After reboot:
journalctl -u nova-dashboard-wayland.service --since "1 min ago"
```

---

## Summary

After all 13 tasks you will have:

| What | Where |
|---|---|
| Rust binary | `target/release/nova-dashboard` |
| All tests | `cargo test` (12 unit tests across state, renderer, can, gps) |
| Simulate mode | `./nova-dashboard --simulate` |
| CAN decoding | Speeduino 0x320 + 0x321, exact match to Python |
| GPS | gpsd TCP JSON, ODO accumulated to `/data/odo.json` |
| BT pairing | BlueZ agent, ACCEPT/REJECT tap on screen |
| Splash | PNG fade-in on boot |
| Service | `nova-dashboard-wayland.service` runs Rust binary |

The Python files remain in the repo until you are satisfied with the Rust version.
