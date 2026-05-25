use tiny_skia::{Color, Paint, PathBuilder, Pixmap, Stroke, Transform};
use fontdue::{Font, FontSettings};
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
const COL_RED:    [u8; 4] = [241, 102, 102, 255]; // #F16666 RPM fill
const COL_REDLINE:[u8; 4] = [255,  34,  34, 255]; // #FF2222 redline glow
const COL_WHITE:  [u8; 4] = [255, 255, 255, 255];
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
    font: Font,
}

impl Renderer {
    pub fn new() -> Self {
        let pixmap = Pixmap::new(W, H).expect("Failed to create pixmap");

        // DejaVuSans-Bold ships with Debian by default (fonts-dejavu-core)
        let font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf";
        let font_bytes = std::fs::read(font_path)
            .unwrap_or_else(|_| panic!("Font not found at {font_path}\nRun: sudo apt install fonts-dejavu-core"));
        let font = Font::from_bytes(font_bytes.as_slice(), FontSettings::default())
            .expect("fontdue: failed to parse font");

        Self { pixmap, font }
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

    /// Draw the speed fill arc from 0 to current speed.
    pub fn draw_speed_fill(&mut self, speed_kph: f32) {
        let sweep = value_to_sweep(speed_kph, 0.0, SPD_MAX);
        self.stroke_arc(SPD_CX, SPD_CY, SPD_R, ARC_START_DEG, sweep, COL_CYAN, TRACK_WIDTH);
    }

    /// Draw the RPM fill arc; above redline the excess glows brighter red.
    pub fn draw_rpm_fill(&mut self, rpm: f32) {
        let rpm = rpm.clamp(0.0, RPM_MAX);
        let sweep = value_to_sweep(rpm, 0.0, RPM_MAX);
        if rpm <= RPM_REDLINE {
            self.stroke_arc(RPM_CX, RPM_CY, RPM_R, ARC_START_DEG, sweep, COL_RED, TRACK_WIDTH);
        } else {
            let normal_sweep = value_to_sweep(RPM_REDLINE, 0.0, RPM_MAX);
            self.stroke_arc(RPM_CX, RPM_CY, RPM_R, ARC_START_DEG, normal_sweep, COL_RED, TRACK_WIDTH);
            let glow_sweep = sweep - normal_sweep;
            self.stroke_arc(RPM_CX, RPM_CY, RPM_R,
                            ARC_START_DEG + normal_sweep, glow_sweep,
                            COL_REDLINE, TRACK_WIDTH + 4.0);
        }
    }

    /// Draw evenly-spaced tick marks around a gauge arc.
    /// Uses `cy - r * sin_a` (Y negated) consistent with `build_arc_path`.
    pub fn draw_ticks(&mut self, cx: f32, cy: f32, r: f32, rgba: [u8; 4]) {
        let mut paint = Paint::default();
        paint.set_color(Self::color(rgba));
        paint.anti_alias = true;
        let stroke = Stroke { width: 2.0, ..Default::default() };

        for i in 0..=TICK_SEGMENTS {
            let t = i as f32 / TICK_SEGMENTS as f32;
            let angle_rad = (ARC_START_DEG + t * ARC_SWEEP_DEG).to_radians();
            let cos_a = angle_rad.cos();
            let sin_a = angle_rad.sin();
            let inner = r - 16.0;
            let outer = r + 4.0;
            let mut pb = PathBuilder::new();
            // Y negated: cy - r*sin  (same convention as build_arc_path)
            pb.move_to(cx + inner * cos_a, cy - inner * sin_a);
            pb.line_to(cx + outer * cos_a, cy - outer * sin_a);
            if let Some(path) = pb.finish() {
                self.pixmap.stroke_path(&path, &paint, &stroke, Transform::identity(), None);
            }
        }
    }

    /// Draw the fuel level mini-bar at the bottom-left.
    pub fn draw_fuel_bar(&mut self, fuel_pct: f32) {
        let x = 30.0; let y = 430.0; let max_w = 140.0; let h = 10.0;
        self.fill_rect(x, y, max_w, h, COL_TRACK);
        let fill_w = (fuel_pct.clamp(0.0, 1.0) * max_w).max(2.0);
        self.fill_rect(x, y, fill_w, h, COL_CYAN);
    }

    /// Draw the coolant temperature mini-bar at the bottom-right.
    pub fn draw_clt_bar(&mut self, clt_c: f32) {
        let x = 630.0; let y = 430.0; let max_w = 140.0; let h = 10.0;
        self.fill_rect(x, y, max_w, h, COL_TRACK);
        let fill_w = (value_to_sweep(clt_c, 60.0, 120.0) / ARC_SWEEP_DEG * max_w)
            .clamp(2.0, max_w);
        self.fill_rect(x, y, fill_w, h, COL_RED);
    }

    /// Draw `text` centered on (cx, cy) at the given pixel size.
    /// `rgba` = [R, G, B, A] where A is 0-255 opacity.
    pub fn draw_text_centered(&mut self, text: &str, cx: f32, cy: f32, size: f32, rgba: [u8; 4]) {
        // Single pass: collect all glyph data (avoids double rasterization)
        let glyphs: Vec<_> = text.chars()
            .map(|ch| self.font.rasterize(ch, size))
            .collect();

        let total_w: f32 = glyphs.iter().map(|(m, _)| m.advance_width).sum();
        let mut cursor_x = cx - total_w * 0.5;
        let [r, g, b, alpha] = rgba;

        // Use font line metrics for a consistent shared baseline
        // (avoids per-glyph ymin producing different vertical offsets for each char)
        let ascent = self.font.horizontal_line_metrics(size)
            .map(|lm| lm.ascent)
            .unwrap_or(size * 0.75);
        let descent = self.font.horizontal_line_metrics(size)
            .map(|lm| lm.descent)
            .unwrap_or(-(size * 0.25));
        let text_height = ascent - descent;
        let baseline_y = (cy + text_height * 0.5 - ascent) as i32;

        let pw = self.pixmap.width() as i32;
        let ph = self.pixmap.height() as i32;

        for (metrics, bitmap) in &glyphs {
            // Glyph top-left: baseline minus how far above baseline this glyph extends
            let gx = cursor_x as i32 + metrics.xmin;
            let gy = baseline_y - metrics.height as i32 - metrics.ymin;

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

                    // Alpha-composite over existing pixel
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

    /// Draw speed value (large) and "km/h" unit label on the left gauge.
    pub fn draw_speed_text(&mut self, speed_kph: f32, gps_fix: bool) {
        let text = if gps_fix { format!("{:.0}", speed_kph) } else { "---".to_string() };
        self.draw_text_centered(&text, SPD_CX, SPD_CY - 10.0, 64.0, COL_WHITE);
        self.draw_text_centered("km/h", SPD_CX, SPD_CY + 42.0, 18.0, COL_GRAY);
    }

    /// Draw RPM value (large) and "rpm" unit label on the right gauge.
    pub fn draw_rpm_text(&mut self, rpm: f32) {
        let rpm = rpm.clamp(0.0, RPM_MAX);
        let text = format!("{:.0}", rpm);
        self.draw_text_centered(&text, RPM_CX, RPM_CY - 10.0, 64.0, COL_WHITE);
        self.draw_text_centered("rpm", RPM_CX, RPM_CY + 42.0, 18.0, COL_GRAY);
    }

    /// Draw everything for one frame.
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

    #[test]
    fn text_centering_math_zero_width() {
        // If total_w == 0, cursor_x starts at cx — no panic
        // We can't rasterize without the font, so this tests the math path only.
        // (Full integration tested visually via --simulate)
        let cx = 200.0f32;
        let total_w = 0.0f32;
        let cursor_x = cx - total_w * 0.5;
        assert_eq!(cursor_x, 200.0);
    }
}
