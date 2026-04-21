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

    def __init__(self, style: dict, gauges: dict, width: int = 800, height: int = 480):
        self._s = style
        self._g = gauges
        self._w = width
        self._h = height
        self._scale: float = 1.0
        self._offset_x: int = 0
        self._offset_y: int = 0
        self._bg = self._init_background()

    def _init_background(self) -> np.ndarray:
        import cairosvg
        svg_cfg = self._g['svg']
        png_bytes = cairosvg.svg2png(
            url=svg_cfg['path'],
            output_width=svg_cfg['native_width'],
            output_height=svg_cfg['native_height'],
        )
        arr = cv2.imdecode(np.frombuffer(png_bytes, np.uint8), cv2.IMREAD_COLOR)
        if arr is None:
            raise RuntimeError(f"_init_background: failed to decode SVG PNG from {svg_cfg['path']}")
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

    def val_to_angle(self, value: float, gauge_name: str) -> float:
        cfg = self._g[gauge_name]
        pct = max(0.0, min(1.0, (value - cfg['min_val']) /
                           (cfg['max_val'] - cfg['min_val'])))
        return pct

    def _draw_track_fill(self, canvas: np.ndarray, gauge_name: str, value: float) -> None:
        cfg = self._g[gauge_name]
        track = cfg['track_points']
        pct = max(0.0, min(1.0, (value - cfg['min_val']) / (cfg['max_val'] - cfg['min_val'])))
        if pct <= 0:
            return

        n = len(track)
        STEPS = 80
        top_steps = max(1, int(pct * STEPS))
        hw = max(1, int(cfg['arc_width'] * self._scale / 2))
        color = tuple(cfg['arc_color'])

        pts_right, pts_left = [], []
        for i in range(top_steps + 1):
            t = i / STEPS * (n - 1)
            s = min(int(t), n - 2)
            f = t - s
            x_svg = track[s][0] + f * (track[s+1][0] - track[s][0])
            y_svg = track[s][1] + f * (track[s+1][1] - track[s][1])
            sx, sy = self._svg_pt(x_svg, y_svg)
            pts_right.append([sx + hw, sy])
            pts_left.append([sx - hw, sy])

        polygon = np.array(pts_right + pts_left[::-1], np.int32)
        cv2.fillPoly(canvas, [polygon], color)

    def _put_centered_text(self, canvas: np.ndarray, text: str,
                           cx: int, cy: int, color: list,
                           font_scale: float = 1.0,
                           thickness: int = 1) -> None:
        font = cv2.FONT_HERSHEY_SIMPLEX
        (tw, th), _ = cv2.getTextSize(text, font, font_scale, thickness)
        cv2.putText(canvas, text,
                    (cx - tw // 2, cy + th // 2),
                    font, font_scale, tuple(color), thickness, cv2.LINE_AA)

    def draw_tachometer(self, canvas: np.ndarray, rpm: float,
                        needle_angle: float = 0.0) -> None:
        cfg = self._g['tachometer']
        cx_s, cy_s = self._svg_pt(cfg['center'][0], cfg['center'][1])
        self._draw_track_fill(canvas, 'tachometer', rpm)
        rpm_str = f"{int(rpm):,}"
        self._put_centered_text(canvas, rpm_str, cx_s, cy_s + int(38 * self._scale),
                                self._s['value_color'], font_scale=0.75, thickness=2)
        self._put_centered_text(canvas, 'RPM', cx_s, cy_s + int(58 * self._scale),
                                self._s['label_color'], font_scale=0.30)

    def draw_speedometer(self, canvas: np.ndarray, speed_kph: float,
                         needle_angle: float = 0.0, gps_fix: bool = True) -> None:
        cfg = self._g['speedometer']
        cx_s, cy_s = self._svg_pt(cfg['center'][0], cfg['center'][1])
        self._draw_track_fill(canvas, 'speedometer', speed_kph)

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
        cv2.circle(canvas,
                   (cx_s, cy_s + int(72 * self._scale)),
                   max(2, int(4 * self._scale)),
                   tuple(dot_color), -1, cv2.LINE_AA)
        self._put_centered_text(canvas, 'GPS',
                                cx_s + max(1, int(10 * self._scale)),
                                cy_s + int(74 * self._scale),
                                self._s['label_color'], font_scale=0.3)

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

    def draw_center_panel(self, canvas: np.ndarray, state) -> None:
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

    def draw_warning_icon(self, canvas: np.ndarray, cx: int, cy: int,
                          label: str, color: list, pulse: float = 1.0) -> None:
        """Draw a small check-engine style warning triangle with label below."""
        r = max(8, int(16 * self._scale))
        brightness = max(0.25, pulse)
        c = tuple(int(v * brightness) for v in color)
        pts = np.array([[cx, cy - r], [cx - r, cy + r], [cx + r, cy + r]], np.int32)
        cv2.fillPoly(canvas, [pts], c)
        cv2.polylines(canvas, [pts], True, tuple(color), 1, cv2.LINE_AA)
        cv2.putText(canvas, '!', (cx - 4, cy + r - 3),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                    tuple(self._s['bg_color']), 2, cv2.LINE_AA)
        self._put_centered_text(canvas, label, cx, cy + r + 12,
                                color, font_scale=0.35)

    def render_frame(self, canvas: np.ndarray, state, interp: dict) -> None:
        np.copyto(canvas, self._bg)
        self.draw_tachometer(canvas, state.rpm)
        self.draw_speedometer(canvas, state.speed_kph,
                              gps_fix=getattr(state, 'gps_fix', True))
        self.draw_center_panel(canvas, state)
        warnings = self._collect_warnings(state)
        pulse = abs(math.sin(time.monotonic() * 2.5))
        warn_y = self._h - 45
        warn_cx = self._w // 2
        total = len(warnings)
        for i, (label, color) in enumerate(warnings):
            offset = (i - (total - 1) / 2) * 70
            self.draw_warning_icon(canvas, int(warn_cx + offset), warn_y,
                                   label, color,
                                   pulse=pulse if i == 0 else 1.0)

    def _collect_warnings(self, state) -> list:
        warnings = []
        if state.clt_c > 99:
            warnings.append(
                (f"{state.clt_c:.0f}C", self._s['warning_amber'])
            )
        if state.afr < 11.0:
            warnings.append(("RICH", self._s['warning_amber']))
        elif state.afr > 16.5:
            warnings.append(("LEAN", self._s['warning_red']))
        return warnings
