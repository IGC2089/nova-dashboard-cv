from __future__ import annotations
import math
import time
import xml.etree.ElementTree as ET
import numpy as np
import cv2
from typing import Optional


class GaugeRenderer:
    """
    Layer-based SVG dashboard renderer.
    Layer order: background → media player → gauge panels → fills → warnings.
    """

    def __init__(self, style: dict, gauges: dict, width: int = 800, height: int = 480):
        self._s = style
        self._g = gauges
        self._w = width
        self._h = height
        self._bg = self._init_background()
        self._panels = {
            key: self._init_panel(key)
            for key in ('left_panel', 'right_panel')
            if key in self._g.get('layers', {})
        }
        self._fills = self._init_fill_svgs()

    # ------------------------------------------------------------------ init

    def _init_background(self) -> np.ndarray:
        import cairosvg
        cfg = self._g['layers']['background']
        png_bytes = cairosvg.svg2png(url=cfg['path'],
                                     output_width=self._w,
                                     output_height=self._h)
        arr = cv2.imdecode(np.frombuffer(png_bytes, np.uint8), cv2.IMREAD_COLOR)
        if arr is None:
            raise RuntimeError(f"Failed to decode background SVG: {cfg['path']}")
        return arr

    def _init_panel(self, key: str) -> dict:
        """Pre-render a gauge panel SVG as a full-screen RGBA layer."""
        import cairosvg
        cfg = self._g['layers'][key]
        nw, nh = cfg['native_width'], cfg['native_height']
        ax, aw = cfg['anchor_x'], cfg['anchor_width']
        scale = min(aw / nw, self._h / nh)
        rw = int(nw * scale)
        rh = int(nh * scale)
        ox = ax + (aw - rw) // 2   # center within allocated width
        oy = (self._h - rh) // 2   # center vertically
        png_bytes = cairosvg.svg2png(url=cfg['path'],
                                     output_width=rw,
                                     output_height=rh)
        img = cv2.imdecode(np.frombuffer(png_bytes, np.uint8), cv2.IMREAD_UNCHANGED)
        if img is None:
            raise RuntimeError(f"Failed to decode panel SVG: {cfg['path']}")
        if img.shape[2] == 3:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
        layer = np.zeros((self._h, self._w, 4), dtype=np.uint8)
        y2 = min(oy + rh, self._h)
        x2 = min(ox + rw, self._w)
        layer[oy:y2, ox:x2] = img[:y2 - oy, :x2 - ox]
        return {'layer': layer, 'scale': scale, 'ox': ox, 'oy': oy}

    def _init_fill_svgs(self) -> dict:
        import cairosvg
        fills = {}
        for name, cfg in self._g.get('fill_svgs', {}).items():
            path = cfg['path']
            root = ET.parse(path).getroot()
            svg_w = int(root.get('width'))
            svg_h = int(root.get('height'))
            panel_key = cfg.get('panel', 'left_panel')
            p = self._panels.get(panel_key, {'scale': 1.0, 'ox': 0, 'oy': 0})
            scale = p['scale']
            ox, oy = p['ox'], p['oy']
            sw = max(1, int(svg_w * scale))
            sh = max(1, int(svg_h * scale))
            png_bytes = cairosvg.svg2png(url=path, output_width=sw, output_height=sh)
            img = cv2.imdecode(np.frombuffer(png_bytes, np.uint8), cv2.IMREAD_UNCHANGED)
            # anchor_x, anchor_y = BOTTOM-LEFT in panel SVG coordinates
            sx = int(cfg['anchor_x'] * scale + ox)
            sy = int((cfg['anchor_y'] - svg_h) * scale + oy)  # top-left
            fills[name] = {
                'img': img, 'sx': sx, 'sy': sy, 'sw': sw, 'sh': sh,
                'opacity': cfg.get('opacity', 1.0),
            }
        return fills

    # ---------------------------------------------------- composite helpers

    def _composite_rgba(self, canvas: np.ndarray, layer: np.ndarray) -> None:
        """Alpha-composite a full-screen RGBA layer onto a BGR canvas in-place."""
        alpha = layer[:, :, 3:4].astype(np.float32) / 255.0
        canvas[:] = np.clip(
            canvas.astype(np.float32) * (1.0 - alpha) +
            layer[:, :, :3].astype(np.float32) * alpha,
            0, 255
        ).astype(np.uint8)

    def _draw_fill_svg(self, canvas: np.ndarray, name: str, pct: float) -> None:
        if name not in self._fills:
            return
        pct = max(0.0, min(1.0, pct))
        if pct <= 0:
            return
        f = self._fills[name]
        img, sx, sy, sw, sh = f['img'], f['sx'], f['sy'], f['sw'], f['sh']
        rows_show = max(1, int(sh * pct))
        y_clip = sh - rows_show
        dst_y1 = sy + y_clip
        dst_y2 = sy + sh
        dst_x1, dst_x2 = sx, sx + sw
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
        opacity = f['opacity']
        if img.shape[2] == 4:
            alpha = src[:, :, 3:4].astype(np.float32) / 255.0 * opacity
            canvas[dst_y1:dst_y2, dst_x1:dst_x2] = (
                dst * (1.0 - alpha) + src[:, :, :3] * alpha
            ).astype(np.uint8)
        else:
            canvas[dst_y1:dst_y2, dst_x1:dst_x2] = src[:, :, :3]

    # --------------------------------------------------------- text helpers

    def _put_centered_text(self, canvas: np.ndarray, text: str,
                           cx: int, cy: int, color: list,
                           font_scale: float = 1.0,
                           thickness: int = 1) -> None:
        font = cv2.FONT_HERSHEY_SIMPLEX
        (tw, th), _ = cv2.getTextSize(text, font, font_scale, thickness)
        cv2.putText(canvas, text,
                    (cx - tw // 2, cy + th // 2),
                    font, font_scale, tuple(color), thickness, cv2.LINE_AA)

    def _panel_pt(self, panel_key: str, svg_x: float, svg_y: float) -> tuple[int, int]:
        """Convert panel-local SVG coordinates to screen pixels."""
        p = self._panels[panel_key]
        return (int(svg_x * p['scale'] + p['ox']),
                int(svg_y * p['scale'] + p['oy']))

    # ---------------------------------------------------------- fill drawing

    def _draw_all_fills(self, canvas: np.ndarray, state) -> None:
        for name, cfg in self._g.get('fill_svgs', {}).items():
            field = cfg.get('state_field')
            val = getattr(state, field, None) if field else None
            if val is None:
                continue
            mn, mx = cfg['min_val'], cfg['max_val']
            pct = max(0.0, min(1.0, (val - mn) / (mx - mn)))
            self._draw_fill_svg(canvas, name, pct)

    def _draw_speed_text(self, canvas: np.ndarray, state) -> None:
        cfg = self._g['layers'].get('left_panel', {})
        dp = cfg.get('speed_display')
        if not dp or 'left_panel' not in self._panels:
            return
        cx, cy = self._panel_pt('left_panel', dp[0], dp[1])
        gps_fix = getattr(state, 'gps_fix', True)
        speed_str = f"{int(state.speed_kph)}" if gps_fix else "---"
        color = self._s['value_color'] if gps_fix else self._s['label_color']
        self._put_centered_text(canvas, speed_str, cx, cy, color,
                                font_scale=1.0, thickness=2)

    # ------------------------------------------------------ public renderers

    def draw_readout(self, canvas: np.ndarray, label: str, value_str: str,
                     unit: str, pos: list, font_scale: float) -> None:
        cx, cy = pos[0], pos[1]  # screen pixel coordinates
        spacing = int(font_scale * 15) + 12
        self._put_centered_text(canvas, label, cx, cy - spacing,
                                self._s['label_color'], font_scale=0.4)
        self._put_centered_text(canvas, value_str, cx, cy,
                                self._s['value_color'], font_scale=font_scale,
                                thickness=2)
        if unit:
            self._put_centered_text(canvas, unit, cx, cy + spacing,
                                    self._s['label_color'], font_scale=0.35)

    def draw_center_panel(self, canvas: np.ndarray, state, page: int = 0) -> None:
        if page != 1:
            return
        for rd in self._g['center_panel']['readouts']:
            field = rd['state_field']
            raw_val = getattr(state, field, None)
            if raw_val is None or (field in ('odo_km', 'trip_km')
                                   and not getattr(state, 'gps_fix', True)):
                value_str = 'NO GPS'
            else:
                value_str = rd['format'].format(raw_val)
            self.draw_readout(canvas, rd['label'], value_str, rd['unit'],
                              rd['pos'], rd['font_scale'])

    def draw_media_player(self, canvas: np.ndarray, state) -> None:
        """Render Bluetooth media player in center zone x=200..600."""
        colors = self._s.get("colors", {})
        amber = tuple(colors.get("amber",
                      self._s.get("warning_amber", [43, 179, 235])))
        white = tuple(colors.get("white",
                      self._s.get("value_color", [255, 255, 255])))
        gray = tuple(colors.get("gray",
                     self._s.get("label_color", [170, 170, 170])))

        canvas[:, 200:600] = (10, 10, 10)

        if not state.bt_connected:
            self._draw_no_bt(canvas, gray, amber)
            return

        self._put_centered_text(canvas, "MEDIA", 400, 24, list(amber), font_scale=0.5)

        art_x1, art_y1, art_x2, art_y2 = 260, 40, 540, 320
        cv2.rectangle(canvas, (art_x1, art_y1), (art_x2, art_y2), (40, 40, 40), -1)
        cv2.rectangle(canvas, (art_x1, art_y1), (art_x2, art_y2), amber, 1)
        self._put_centered_text(canvas, "( music )", 400, 185, list(amber), font_scale=0.7)

        title = (state.bt_title or "Unknown")[:28]
        self._put_centered_text(canvas, title, 400, 345, list(white), font_scale=0.65)

        artist = (state.bt_artist or "")[:28]
        if artist:
            self._put_centered_text(canvas, artist, 400, 370, list(gray), font_scale=0.55)

        cv2.line(canvas, (220, 390), (580, 390), amber, 1)

        play_label = "||" if state.bt_playing else " >"
        for label, cx in [("<|", 300), (play_label, 400), ("|>", 500)]:
            self._put_centered_text(canvas, label, cx, 445, list(amber),
                                    font_scale=0.9, thickness=2)

    def _draw_no_bt(self, canvas: np.ndarray, gray: tuple, amber: tuple) -> None:
        self._put_centered_text(canvas, "BLUETOOTH", 400, 220, list(amber), font_scale=0.7)
        self._put_centered_text(canvas, "Pair your phone", 400, 256, list(gray), font_scale=0.55)

    def draw_page_dots(self, canvas: np.ndarray, page: int, total: int = 2) -> None:
        cy = self._h - 10
        spacing = 16
        cx0 = self._w // 2 - (total - 1) * spacing // 2
        for i in range(total):
            color = tuple(self._s['value_color']) if i == page else (70, 70, 70)
            cv2.circle(canvas, (cx0 + i * spacing, cy), 4, color, -1, cv2.LINE_AA)

    def draw_warning_icon(self, canvas: np.ndarray, cx: int, cy: int,
                          label: str, color: list, pulse: float = 1.0) -> None:
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

    def draw_warnings(self, canvas: np.ndarray, state) -> None:
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

    # --------------------------------------------------------- main render

    def render_frame(self, canvas: np.ndarray, state, interp: dict,
                     page: int = 0) -> None:
        # Layer 1: background
        np.copyto(canvas, self._bg)

        # Layer 2: media player (sits under gauge panels)
        if page == 0:
            self.draw_media_player(canvas, state)

        # Layer 3: gauge panels (RGBA, transparent centers let media show through)
        for panel in self._panels.values():
            self._composite_rgba(canvas, panel['layer'])

        # Value fills on top of panels
        self._draw_all_fills(canvas, state)

        # Speed readout
        self._draw_speed_text(canvas, state)

        # Detail readouts (page 1)
        self.draw_center_panel(canvas, state, page)

        # Page indicator dots
        self.draw_page_dots(canvas, page)

        # Warnings always on top
        self.draw_warnings(canvas, state)
