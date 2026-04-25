from __future__ import annotations
import math
import time
import xml.etree.ElementTree as ET
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
        self._fills = self._init_fill_svgs()

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

    def _init_fill_svgs(self) -> dict:
        import cairosvg
        fills = {}
        for name, cfg in self._g.get('fill_svgs', {}).items():
            path = cfg['path']
            root = ET.parse(path).getroot()
            svg_w = int(root.get('width'))
            svg_h = int(root.get('height'))
            screen_w = max(1, int(svg_w * self._scale))
            screen_h = max(1, int(svg_h * self._scale))
            png_bytes = cairosvg.svg2png(url=path, output_width=screen_w, output_height=screen_h)
            img = cv2.imdecode(np.frombuffer(png_bytes, np.uint8), cv2.IMREAD_UNCHANGED)
            # anchor_x, anchor_y are BOTTOM-LEFT of fill SVG in cluster-map coords
            sx, sy = self._svg_pt(cfg['anchor_x'], cfg['anchor_y'] - svg_h)
            fills[name] = {'img': img, 'sx': sx, 'sy': sy, 'sw': screen_w, 'sh': screen_h,
                           'opacity': cfg.get('opacity', 1.0)}
        return fills

    def _draw_fill_svg(self, canvas: np.ndarray, name: str, pct: float) -> None:
        if name not in self._fills:
            return
        pct = max(0.0, min(1.0, pct))
        if pct <= 0:
            return
        f = self._fills[name]
        img, sx, sy, sw, sh = f['img'], f['sx'], f['sy'], f['sw'], f['sh']
        rows_show = max(1, int(sh * pct))
        y_clip = sh - rows_show          # first row of img to show
        dst_y1 = sy + y_clip
        dst_y2 = sy + sh
        dst_x1, dst_x2 = sx, sx + sw
        # Clamp to canvas
        ch, cw = canvas.shape[:2]
        src_y1 = y_clip + max(0, -dst_y1)
        src_x1 = max(0, -dst_x1)
        dst_y1 = max(0, dst_y1);  dst_y2 = min(dst_y2, ch)
        dst_x1 = max(0, dst_x1);  dst_x2 = min(dst_x2, cw)
        src_y2 = src_y1 + (dst_y2 - dst_y1)
        src_x2 = src_x1 + (dst_x2 - dst_x1)
        if dst_y1 >= dst_y2 or dst_x1 >= dst_x2:
            return
        src = img[src_y1:src_y2, src_x1:src_x2]
        dst = canvas[dst_y1:dst_y2, dst_x1:dst_x2]
        opacity = f.get('opacity', 1.0)
        if img.shape[2] == 4:
            alpha = src[:, :, 3:4].astype(np.float32) / 255.0 * opacity
            canvas[dst_y1:dst_y2, dst_x1:dst_x2] = (
                dst * (1.0 - alpha) + src[:, :, :3] * alpha
            ).astype(np.uint8)
        else:
            canvas[dst_y1:dst_y2, dst_x1:dst_x2] = src[:, :, :3]

    def _svg_pt(self, x: float, y: float) -> tuple[int, int]:
        return (int(x * self._scale + self._offset_x),
                int(y * self._scale + self._offset_y))

    def val_to_angle(self, value: float, gauge_name: str) -> float:
        cfg = self._g[gauge_name]
        return max(0.0, min(1.0, (value - cfg['min_val']) /
                            (cfg['max_val'] - cfg['min_val'])))

    def _put_centered_text(self, canvas: np.ndarray, text: str,
                           cx: int, cy: int, color: list,
                           font_scale: float = 1.0,
                           thickness: int = 1) -> None:
        font = cv2.FONT_HERSHEY_SIMPLEX
        (tw, th), _ = cv2.getTextSize(text, font, font_scale, thickness)
        cv2.putText(canvas, text,
                    (cx - tw // 2, cy + th // 2),
                    font, font_scale, tuple(color), thickness, cv2.LINE_AA)

    def draw_tachometer(self, canvas: np.ndarray, rpm: float) -> None:
        cfg = self._g['tachometer']
        cx_s, cy_s = self._svg_pt(cfg['center'][0], cfg['center'][1])
        pct = max(0.0, min(1.0, (rpm - cfg['min_val']) / (cfg['max_val'] - cfg['min_val'])))
        self._draw_fill_svg(canvas, 'speedometer', pct)

    def draw_speedometer(self, canvas: np.ndarray, speed_kph: float,
                         gps_fix: bool = True) -> None:
        cfg = self._g['speedometer']
        pct = max(0.0, min(1.0, (speed_kph - cfg['min_val']) / (cfg['max_val'] - cfg['min_val'])))
        self._draw_fill_svg(canvas, 'tachometer', pct)

        dc = cfg.get('display_center', cfg['center'])
        cx_s, cy_s = self._svg_pt(dc[0], dc[1])

        speed_str = f"{int(speed_kph)}" if gps_fix else "---"
        color = tuple(self._s['value_color']) if gps_fix else tuple(self._s['label_color'])

        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 1.0
        thickness = 2
        (tw, th), _ = cv2.getTextSize(speed_str, font, font_scale, thickness)
        cv2.putText(canvas, speed_str,
                    (cx_s - tw // 2, cy_s + th // 2),
                    font, font_scale, color, thickness, cv2.LINE_AA)

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

    def draw_center_panel(self, canvas: np.ndarray, state, page: int = 0) -> None:
        if page != 1:
            return
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

    def draw_media_player(self, canvas: np.ndarray, state) -> None:
        """Render Bluetooth media player in center zone x=200..600, y=0..480."""
        # Resolve colors: support both nested colors dict and flat style dict.
        colors = self._s.get("colors", {})
        amber = tuple(colors.get("amber",
                      self._s.get("warning_amber", [43, 179, 235])))
        white = tuple(colors.get("white",
                      self._s.get("value_color", [255, 255, 255])))
        gray = tuple(colors.get("gray",
                     self._s.get("label_color", [170, 170, 170])))

        # Dark background for center zone
        canvas[:, 200:600] = (10, 10, 10)

        if not state.bt_connected:
            self._draw_no_bt(canvas, gray, amber)
            return

        # "MEDIA" header
        self._put_centered_text(canvas, "MEDIA", 400, 24, list(amber), font_scale=0.5)

        # Album art placeholder (280x280, centered in zone)
        art_x1, art_y1, art_x2, art_y2 = 260, 40, 540, 320
        cv2.rectangle(canvas, (art_x1, art_y1), (art_x2, art_y2), (40, 40, 40), -1)
        cv2.rectangle(canvas, (art_x1, art_y1), (art_x2, art_y2), amber, 1)
        self._put_centered_text(canvas, "( music )", 400, 185, list(amber), font_scale=0.7)

        # Track title (truncated to 28 chars)
        title = (state.bt_title or "Unknown")[:28]
        self._put_centered_text(canvas, title, 400, 345, list(white), font_scale=0.65)

        # Artist
        artist = (state.bt_artist or "")[:28]
        if artist:
            self._put_centered_text(canvas, artist, 400, 370, list(gray), font_scale=0.55)

        # Divider
        cv2.line(canvas, (220, 390), (580, 390), amber, 1)

        # Playback controls
        play_label = "||" if state.bt_playing else " >"
        for label, cx in [("<|", 300), (play_label, 400), ("|>", 500)]:
            self._put_centered_text(canvas, label, cx, 445, list(amber),
                                    font_scale=0.9, thickness=2)

    def _draw_no_bt(self, canvas: np.ndarray, gray: tuple, amber: tuple) -> None:
        """Draw 'no Bluetooth device' placeholder in center zone."""
        self._put_centered_text(canvas, "BLUETOOTH", 400, 220, list(amber), font_scale=0.7)
        self._put_centered_text(canvas, "Pair your phone", 400, 256, list(gray), font_scale=0.55)

    def draw_page_dots(self, canvas: np.ndarray, page: int, total: int = 2) -> None:
        cy = self._h - 10
        spacing = 16
        cx0 = self._w // 2 - (total - 1) * spacing // 2
        for i in range(total):
            color = tuple(self._s['value_color']) if i == page else (70, 70, 70)
            cv2.circle(canvas, (cx0 + i * spacing, cy), 4, color, -1, cv2.LINE_AA)

    def _draw_clt_fuel_fills(self, canvas: np.ndarray, state) -> None:
        fill_cfg = self._g.get('fill_svgs', {})
        for name in ('clt', 'fuel'):
            cfg = fill_cfg.get(name)
            if not cfg:
                continue
            field = 'clt_c' if name == 'clt' else 'fuel_pct'
            val = getattr(state, field, None)
            if val is None:
                continue
            pct = max(0.0, min(1.0, (val - cfg['min_val']) / (cfg['max_val'] - cfg['min_val'])))
            self._draw_fill_svg(canvas, name, pct)

    def draw_warning_icon(self, canvas: np.ndarray, cx: int, cy: int,
                          label: str, color: list, pulse: float = 1.0) -> None:
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

    def render_frame(self, canvas: np.ndarray, state, interp: dict,
                     page: int = 0) -> None:
        np.copyto(canvas, self._bg)
        self.draw_tachometer(canvas, state.rpm)
        self.draw_speedometer(canvas, state.speed_kph,
                              gps_fix=getattr(state, 'gps_fix', True))
        self._draw_clt_fuel_fills(canvas, state)
        self.draw_center_panel(canvas, state, page)
        self.draw_page_dots(canvas, page)
        self.draw_warnings(canvas, state)

    def draw_warnings(self, canvas: np.ndarray, state) -> None:
        """Draw overtemp/AFR warning icons. Call after draw_media_player() so they render on top."""
        warnings = self._collect_warnings(state)
        if not warnings:
            return
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
            warnings.append((f"{state.clt_c:.0f}C", self._s['warning_amber']))
        if state.afr < 11.0:
            warnings.append(("RICH", self._s['warning_amber']))
        elif state.afr > 16.5:
            warnings.append(("LEAN", self._s['warning_red']))
        return warnings
