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
#[allow(dead_code)]
const TICK_SEGMENTS: usize = 8;     // creates 9 ticks (0..=8)

// Colors (RGBA 0–255)
const COL_BG:     [u8; 4] = [10,  10,  10,  255];
const COL_TRACK:  [u8; 4] = [40,  40,  40,  255];
const COL_CYAN:   [u8; 4] = [119, 206, 245, 255]; // #77CEF5 speed fill
const COL_RED:    [u8; 4] = [241, 102, 102, 255]; // #F16666 RPM fill
#[allow(dead_code)]
const COL_REDLINE:[u8; 4] = [255,  34,  34, 255]; // #FF2222 redline glow
#[allow(dead_code)]
const COL_WHITE:  [u8; 4] = [255, 255, 255, 255];
#[allow(dead_code)]
const COL_GRAY:   [u8; 4] = [160, 160, 160, 255];
#[allow(dead_code)]
const COL_AMBER:  [u8; 4] = [255, 165,   0, 255]; // warning amber

// ── Gauge config ─────────────────────────────────────────────────────────────

/// Per-gauge layout and scale configuration.
#[derive(Copy, Clone)]
pub struct GaugeConfig {
    pub cx: f32,
    pub cy: f32,
    pub r: f32,
    pub min: f32,
    pub max: f32,
    pub redline: Option<f32>,
    pub fill_color: [u8; 4],
}

pub const SPEED_GAUGE: GaugeConfig = GaugeConfig {
    cx: SPD_CX, cy: SPD_CY, r: SPD_R,
    min: 0.0, max: SPD_MAX,
    redline: None,
    fill_color: COL_CYAN,
};

pub const RPM_GAUGE: GaugeConfig = GaugeConfig {
    cx: RPM_CX, cy: RPM_CY, r: RPM_R,
    min: 0.0, max: RPM_MAX,
    redline: Some(RPM_REDLINE),
    fill_color: COL_RED,
};

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
/// Angles follow standard math convention: 0°=right, counter-clockwise positive.
/// Y is negated to match screen coordinates (Y increases downward).
pub fn build_arc_path(cx: f32, cy: f32, r: f32, start_deg: f32, sweep_deg: f32) -> Option<tiny_skia::Path> {
    let n = 64usize;
    let mut pb = PathBuilder::new();
    for i in 0..=n {
        let t = i as f32 / n as f32;
        let angle_rad = (start_deg + t * sweep_deg).to_radians();
        let x = cx + r * angle_rad.cos();
        let y = cy - r * angle_rad.sin();   // Y negated for screen coordinates
        if i == 0 {
            pb.move_to(x, y);
        } else {
            pb.line_to(x, y);
        }
    }
    pb.finish()
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
        let Some(path) = build_arc_path(cx, cy, r, start_deg, sweep_deg) else { return; };
        let mut paint = Paint::default();
        paint.set_color(Self::color(rgba));
        paint.anti_alias = true;
        let stroke = Stroke { width, ..Default::default() };
        self.pixmap.stroke_path(&path, &paint, &stroke, Transform::identity(), None);
    }

    pub fn fill_rect(&mut self, x: f32, y: f32, w: f32, h: f32, rgba: [u8; 4]) {
        let mut paint = Paint::default();
        paint.set_color(Self::color(rgba));
        if let Some(rect) = tiny_skia::Rect::from_xywh(x, y, w, h) {
            self.pixmap.fill_rect(rect, &paint, Transform::identity(), None);
        }
    }

    // ── Public draw methods ──────────────────────────────────────────────────

    pub fn clear(&mut self) {
        self.pixmap.fill(Self::color(COL_BG));
    }

    /// Draw dim arc tracks for both gauges (full 300° sweep).
    pub fn draw_gauge_tracks(&mut self) {
        for cfg in [&SPEED_GAUGE, &RPM_GAUGE] {
            self.stroke_arc(cfg.cx, cfg.cy, cfg.r, ARC_START_DEG, ARC_SWEEP_DEG, COL_TRACK, TRACK_WIDTH);
        }
    }

    /// Draw everything for one frame.
    pub fn draw_frame(&mut self, _state: &VehicleState, _frame: u64) {
        self.clear();
        self.draw_gauge_tracks();
    }
}

impl Default for Renderer {
    fn default() -> Self { Self::new() }
}

// ── Tests ────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pct_to_sweep_clamped() {
        assert_eq!(pct_to_sweep(0.0), 0.0);
        assert_eq!(pct_to_sweep(1.0), ARC_SWEEP_DEG);
        assert!((pct_to_sweep(0.5) - ARC_SWEEP_DEG * 0.5).abs() < 0.001);
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
    fn arc_path_builds_without_panic() {
        let path = build_arc_path(200.0, 240.0, 155.0, 210.0, 300.0);
        assert!(path.is_some());
    }

    #[test]
    fn arc_start_point_is_at_lower_left() {
        // 210° start, tiny sweep just to get one segment
        let path = build_arc_path(200.0, 240.0, 155.0, 210.0, 1.0);
        let bounds = path.unwrap().bounds();
        // With Y negated: start is lower-left of center (200, 240)
        // x < 200 (left of center) and y > 240 (below center)
        assert!(bounds.left() < 200.0, "arc should start left of center");
        assert!(bounds.bottom() > 240.0, "arc should start below center");
    }

    #[test]
    fn renderer_new_creates_correct_size() {
        let r = Renderer::new();
        assert_eq!(r.pixmap.width(), W);
        assert_eq!(r.pixmap.height(), H);
    }
}
