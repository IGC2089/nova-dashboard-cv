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

    def __init__(self, style: dict, gauges: dict):
        self._s = style
        self._g = gauges

    def val_to_angle(self, value: float, gauge_name: str) -> float:
        """Map value to needle angle (degrees, clockwise from 3-o'clock). Clamps to range."""
        cfg = self._g[gauge_name]
        pct = max(0.0, min(1.0, (value - cfg['min_val']) /
                           (cfg['max_val'] - cfg['min_val'])))
        return cfg['start_angle'] + pct * cfg['sweep']

    def _angle_to_xy(self, cx: int, cy: int, radius: int,
                     angle_deg: float) -> tuple[int, int]:
        rad = math.radians(angle_deg)
        return (int(cx + radius * math.cos(rad)),
                int(cy + radius * math.sin(rad)))

    def _draw_arc_track(self, canvas: np.ndarray, gauge_name: str,
                        active_angle: float) -> None:
        cfg = self._g[gauge_name]
        cx, cy = cfg['center']
        r = cfg['radius']
        w = cfg['arc_width']
        sa = cfg['start_angle']
        ea = sa + cfg['sweep']
        axes = (r, r)

        cv2.ellipse(canvas, (cx, cy), axes, 0, sa, ea,
                    tuple(self._s['arc_inactive']), w, cv2.LINE_AA)
        cv2.ellipse(canvas, (cx, cy), axes, 0, sa, active_angle,
                    tuple(self._s['arc_active']), w, cv2.LINE_AA)

        if cfg.get('redzone_val') is not None:
            redzone_angle = self.val_to_angle(cfg['redzone_val'], gauge_name)
            cv2.ellipse(canvas, (cx, cy), axes, 0, redzone_angle, ea,
                        tuple(self._s['arc_redzone']), w, cv2.LINE_AA)

    def _draw_needle(self, canvas: np.ndarray, gauge_name: str,
                     needle_angle: float) -> None:
        cfg = self._g[gauge_name]
        cx, cy = cfg['center']
        r = cfg['radius']
        tip  = self._angle_to_xy(cx, cy, int(r * 0.88), needle_angle)
        tail = self._angle_to_xy(cx, cy, int(r * 0.15), needle_angle + 180)
        cv2.line(canvas, tail, tip,
                 tuple(self._s['needle_color']), 3, cv2.LINE_AA)
        cv2.circle(canvas, (cx, cy), 7,
                   tuple(self._s['hub_color']), -1, cv2.LINE_AA)
        cv2.circle(canvas, (cx, cy), 3,
                   tuple(self._s['arc_inactive']), -1, cv2.LINE_AA)

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
                        needle_angle: float) -> None:
        cfg = self._g['tachometer']
        cx, cy = cfg['center']
        active_angle = self.val_to_angle(rpm, 'tachometer')
        self._draw_arc_track(canvas, 'tachometer', active_angle)
        self._draw_needle(canvas, 'tachometer', needle_angle)
        rpm_str = f"{int(rpm):,}"
        self._put_centered_text(canvas, rpm_str, cx, cy + 42,
                                self._s['value_color'], font_scale=0.8, thickness=2)
        self._put_centered_text(canvas, cfg['label'], cx, cy + 60,
                                self._s['label_color'], font_scale=0.4)
        for pct, label in [(0, '0'), (0.33, '2K'), (0.67, '4K'), (1.0, '6K')]:
            angle = cfg['start_angle'] + pct * cfg['sweep']
            lx, ly = self._angle_to_xy(cx, cy, cfg['radius'] + 10, angle)
            self._put_centered_text(canvas, label, lx, ly,
                                    self._s['label_color'], font_scale=0.35)

    def draw_speedometer(self, canvas: np.ndarray, speed_mph: float,
                         needle_angle: float, gps_fix: bool) -> None:
        cfg = self._g['speedometer']
        cx, cy = cfg['center']
        active_angle = self.val_to_angle(speed_mph, 'speedometer')
        self._draw_arc_track(canvas, 'speedometer', active_angle)
        self._draw_needle(canvas, 'speedometer', needle_angle)
        if gps_fix:
            speed_str = f"{int(speed_mph)}"
            color = self._s['value_color']
        else:
            speed_str = "---"
            color = self._s['label_color']
        self._put_centered_text(canvas, speed_str, cx, cy + 42,
                                color, font_scale=0.8, thickness=2)
        self._put_centered_text(canvas, cfg['label'], cx, cy + 60,
                                self._s['label_color'], font_scale=0.4)
        dot_color = self._s['arc_active'] if gps_fix else self._s['arc_redzone']
        cv2.circle(canvas, (cx, cy + 78), 4, tuple(dot_color), -1, cv2.LINE_AA)
        self._put_centered_text(canvas, 'GPS', cx + 10, cy + 80,
                                self._s['label_color'], font_scale=0.35)
        for pct, label in [(0, '0'), (0.25, '60'), (0.5, '120'),
                           (0.75, '180'), (1.0, '240')]:
            angle = cfg['start_angle'] + pct * cfg['sweep']
            lx, ly = self._angle_to_xy(cx, cy, cfg['radius'] + 10, angle)
            self._put_centered_text(canvas, label, lx, ly,
                                    self._s['label_color'], font_scale=0.35)

    def draw_readout(self, canvas: np.ndarray, label: str, value_str: str,
                     unit: str, pos: list, font_scale: float) -> None:
        x, y = pos
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
        col = tuple(self._s['arc_inactive'])
        cv2.line(canvas, (267, 20), (267, 460), col, 1)
        cv2.line(canvas, (533, 20), (533, 460), col, 1)

    def draw_warning_overlay(self, canvas: np.ndarray, message: str,
                             color: list, pulse_alpha: float = 1.0) -> None:
        overlay = canvas.copy()
        h, w = canvas.shape[:2]
        alpha = 0.35 * pulse_alpha
        cv2.rectangle(overlay, (0, 0), (w, h), tuple(color), -1)
        cv2.addWeighted(overlay, alpha, canvas, 1 - alpha, 0, canvas)
        self._put_centered_text(canvas, message, w // 2, h // 2,
                                self._s['value_color'], font_scale=1.2, thickness=2)

    def render_frame(self, canvas: np.ndarray, state, interp: dict) -> None:
        canvas[:] = tuple(self._s['bg_color'])
        self.draw_tachometer(canvas, state.rpm, interp['tach_angle'])
        self.draw_speedometer(canvas, state.speed_mph,
                              interp['speedo_angle'],
                              getattr(state, 'gps_fix', True))
        self.draw_center_panel(canvas, state)
        warnings = self._collect_warnings(state)
        pulse = abs(math.sin(time.monotonic() * 2.5))
        for i, (msg, color) in enumerate(warnings):
            self.draw_warning_overlay(canvas, msg, color,
                                      pulse_alpha=pulse if i == 0 else 0.8)

    def _collect_warnings(self, state) -> list:
        warnings = []
        if state.clt_c > 99:
            warnings.append(
                (f"TEMP HIGH  {state.clt_c:.0f}C", self._s['warning_amber'])
            )
        if state.afr < 11.0:
            warnings.append(("RICH", self._s['warning_amber']))
        elif state.afr > 16.5:
            warnings.append(("LEAN  CHECK ENGINE", self._s['warning_red']))
        return warnings
