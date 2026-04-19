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
        cv2.circle(canvas, (cx, cy), 14,
                   tuple(self._s['hub_color']), -1, cv2.LINE_AA)
        cv2.circle(canvas, (cx, cy), 6,
                   tuple(self._s['arc_inactive']), -1, cv2.LINE_AA)
