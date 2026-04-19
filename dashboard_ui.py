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
        r = cfg['radius']
        sa = cfg['start_angle']
        ea = sa + cfg['sweep']
        axes = (r, r)
        lc = tuple(self._s['label_color'])

        # Arc track layers
        cv2.ellipse(canvas, (cx, cy), axes, 0, sa, ea,
                    tuple(self._s['arc_inactive']), 8, cv2.LINE_AA)
        active_angle = self.val_to_angle(rpm, 'tachometer')
        cv2.ellipse(canvas, (cx, cy), axes, 0, sa, active_angle,
                    tuple(self._s['arc_active']), 8, cv2.LINE_AA)
        rz_angle = self.val_to_angle(cfg['redzone_val'], 'tachometer')
        cv2.ellipse(canvas, (cx, cy), axes, 0, rz_angle, ea,
                    tuple(self._s['arc_redzone']), 8, cv2.LINE_AA)

        # Outer and inner ring lines
        cv2.ellipse(canvas, (cx, cy), (r + 2, r + 2), 0, sa, ea, lc, 1, cv2.LINE_AA)
        cv2.ellipse(canvas, (cx, cy), (r - 10, r - 10), 0, sa, ea, lc, 1, cv2.LINE_AA)

        # Tick marks: 13 positions (0–6000 in steps of 500)
        for i in range(13):
            pct = i / 12.0
            angle_rad = math.radians(sa + pct * cfg['sweep'])
            is_major = (i % 2 == 0)
            r_out = r - 1
            r_in  = r - 10 if is_major else r - 6
            x1 = int(cx + r_out * math.cos(angle_rad))
            y1 = int(cy + r_out * math.sin(angle_rad))
            x2 = int(cx + r_in  * math.cos(angle_rad))
            y2 = int(cy + r_in  * math.sin(angle_rad))
            cv2.line(canvas, (x1, y1), (x2, y2), lc, 2 if is_major else 1, cv2.LINE_AA)

        # Scale labels at major ticks: 0 10 20 30 40 50 60
        for i, label in enumerate(['0', '10', '20', '30', '40', '50', '60']):
            pct = (i * 2) / 12.0
            angle = sa + pct * cfg['sweep']
            lx, ly = self._angle_to_xy(cx, cy, r + 14, angle)
            self._put_centered_text(canvas, label, lx, ly, self._s['label_color'], font_scale=0.28)

        self._draw_needle(canvas, 'tachometer', needle_angle)

        rpm_str = f"{int(rpm):,}"
        self._put_centered_text(canvas, rpm_str, cx, cy + 38,
                                self._s['value_color'], font_scale=0.75, thickness=2)
        self._put_centered_text(canvas, 'ENGINE', cx, cy + 54,
                                self._s['label_color'], font_scale=0.32)
        self._put_centered_text(canvas, 'RPM', cx, cy + 64,
                                self._s['label_color'], font_scale=0.32)
        self._put_centered_text(canvas, 'x100', cx, cy + 76,
                                self._s['label_color'], font_scale=0.28)

    def draw_speedometer(self, canvas: np.ndarray, speed_kph: float,
                         needle_angle: float, gps_fix: bool) -> None:
        cfg = self._g['speedometer']
        cx, cy = cfg['center']
        r = cfg['radius']
        sa = cfg['start_angle']
        ea = sa + cfg['sweep']
        axes = (r, r)
        lc = tuple(self._s['label_color'])

        # Arc track layers
        cv2.ellipse(canvas, (cx, cy), axes, 0, sa, ea,
                    tuple(self._s['arc_inactive']), 8, cv2.LINE_AA)
        active_angle = self.val_to_angle(speed_kph, 'speedometer')
        cv2.ellipse(canvas, (cx, cy), axes, 0, sa, active_angle,
                    tuple(self._s['arc_active']), 8, cv2.LINE_AA)

        # Outer and inner ring lines
        cv2.ellipse(canvas, (cx, cy), (r + 2, r + 2), 0, sa, ea, lc, 1, cv2.LINE_AA)
        cv2.ellipse(canvas, (cx, cy), (r - 10, r - 10), 0, sa, ea, lc, 1, cv2.LINE_AA)

        # Tick marks: 13 positions (0–240 in steps of 20)
        for i in range(13):
            pct = i / 12.0
            angle_rad = math.radians(sa + pct * cfg['sweep'])
            is_major = (i % 2 == 0)
            r_out = r - 1
            r_in  = r - 10 if is_major else r - 6
            x1 = int(cx + r_out * math.cos(angle_rad))
            y1 = int(cy + r_out * math.sin(angle_rad))
            x2 = int(cx + r_in  * math.cos(angle_rad))
            y2 = int(cy + r_in  * math.sin(angle_rad))
            cv2.line(canvas, (x1, y1), (x2, y2), lc, 2 if is_major else 1, cv2.LINE_AA)

        # Scale labels at major ticks: 0 40 80 120 160 200 240
        for i, label in enumerate(['0', '40', '80', '120', '160', '200', '240']):
            pct = (i * 2) / 12.0
            angle = sa + pct * cfg['sweep']
            lx, ly = self._angle_to_xy(cx, cy, r + 14, angle)
            self._put_centered_text(canvas, label, lx, ly, self._s['label_color'], font_scale=0.28)

        self._draw_needle(canvas, 'speedometer', needle_angle)

        if gps_fix:
            speed_str = f"{int(speed_kph)}"
            color = self._s['value_color']
        else:
            speed_str = "---"
            color = self._s['label_color']
        self._put_centered_text(canvas, speed_str, cx, cy + 38,
                                color, font_scale=0.75, thickness=2)
        self._put_centered_text(canvas, 'km/h', cx, cy + 54,
                                self._s['label_color'], font_scale=0.32)
        dot_color = self._s['arc_active'] if gps_fix else self._s['arc_redzone']
        cv2.circle(canvas, (cx, cy + 68), 4, tuple(dot_color), -1, cv2.LINE_AA)
        self._put_centered_text(canvas, 'GPS', cx + 10, cy + 70,
                                self._s['label_color'], font_scale=0.3)

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

    def draw_warning_icon(self, canvas: np.ndarray, cx: int, cy: int,
                          label: str, color: list, pulse: float = 1.0) -> None:
        """Draw a small check-engine style warning triangle with label below."""
        r = 16
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
        canvas[:] = tuple(self._s['bg_color'])
        self.draw_tachometer(canvas, state.rpm, interp['tach_angle'])
        self.draw_speedometer(canvas, state.speed_kph,
                              interp['speedo_angle'],
                              getattr(state, 'gps_fix', True))
        self.draw_center_panel(canvas, state)
        warnings = self._collect_warnings(state)
        pulse = abs(math.sin(time.monotonic() * 2.5))
        total = len(warnings)
        for i, (label, color) in enumerate(warnings):
            offset = (i - (total - 1) / 2) * 70
            self.draw_warning_icon(canvas, int(400 + offset), 435,
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
