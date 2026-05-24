"""dashboard_ui.py
BMW iDrive 8 cluster-map style renderer for Nova Dashboard (800 × 480).

Layout mirrors the Figma 'cluster - map' frame (node 17:477):
  • Left panel  (200 px) — speed scale + fuel sub-indicator, cyan #77CEF5
  • Center      (400 px) — info / secondary metrics / BT media
  • Right panel (200 px) — RPM scale  + coolant sub-indicator, red #F16666
  • Bottom bar  (40 px)  — clock | GPS/BT status | odo | bat | CLT

Rendered entirely with OpenCV + NumPy into a BGR uint8 canvas.
"""
from __future__ import annotations

import math
import time
import cv2
import numpy as np
from typing import Dict

from vehicle_state import VehicleState

# ── Public constants used by main.py ────────────────────────────────────────
PAIRING_ACCEPT_RECT = (215, 295, 395, 340)
PAIRING_REJECT_RECT = (405, 295, 585, 340)

# ── Color palette (BGR) ──────────────────────────────────────────────────────
_BG    = np.array([ 8, 10, 16], np.float32)   # near-black background
_PANEL = np.array([10, 12, 20], np.float32)   # center area tint
_CYAN  = (245, 206, 119)   # #77CEF5 — speed / primary
_RED   = (102, 102, 241)   # #F16666 — RPM / secondary
_HOT   = ( 35,  35, 255)   # #FF2323 — redline > 6k
_GRAY  = (187, 171, 162)   # #a2abbb — labels / info
_WHITE = (255, 255, 255)
_AMBER = ( 43, 179, 235)   # warning amber
_DIM   = ( 55,  65,  75)   # inactive ticks / disabled

# ── Screen & gauge geometry ───────────────────────────────────────────────────
SW, SH   = 800, 480          # screen dimensions
GW       = 200               # gauge panel width
TAPER    = 38                # diagonal: inner edge shifts by this px top→bottom
TOP_PAD  = 44                # y-start of main tick zone
BOT_PAD  = 44                # space at bottom for fill bar
TICK_H   = SH - TOP_PAD - BOT_PAD   # 392 px tick zone height

SPEED_MAX = 330.0
RPM_MAX   = 7000.0
CLT_MIN, CLT_MAX = 40.0, 160.0

# Speed labels (value, is_major)
_SPEED_LVLS = [
    (330, True), (270, True), (210, True),
    (150, True), (120, True), (90,  True),
    (60,  True), (30,  True), (0,   True),
]

# RPM labels (value, text)
_RPM_LVLS = [
    (7000, '7'), (6000, '6'), (5000, '5'),
    (4000, '4'), (3000, '3'), (2000, '2'), (1000, '1'),
]

# Fuel sub-scale on left panel (fraction 0=empty→1=full, label)
_FUEL_MARKS = [(1.0, '1'), (0.5, '½'), (0.0, '0')]
_FUEL_SUB_X = 82    # x-position of fuel sub-indicator within left panel

# Coolant sub-scale on right panel (°C value, label)
_CLT_MARKS  = [(150, '150'), (100, '100'), (50, '50')]
_CLT_SUB_X  = 110   # local x inside right panel canvas (0 = inner/left edge)

# Fuel & CLT vertical scale extents (y-pixel range)
_SUB_TOP, _SUB_BOT = 245, 415


def _ldx(y: float) -> int:
    """Inner-edge x of left panel at screen y (top=GW, bottom=GW-TAPER)."""
    return round(GW - TAPER * (y / SH))


def _rdx(y: float) -> int:
    """Inner-edge local-x of right panel at y (top=0, bottom=TAPER)."""
    return round(TAPER * (y / SH))


def _smooth(interp: Dict, key: str, target: float, rate: float = 0.18) -> float:
    v = interp.get(key, target)
    v += (target - v) * rate
    interp[key] = v
    return v


def _txt(canvas, text: str, x: int, y: int, scale: float, color,
         thickness: int = 1) -> None:
    cv2.putText(canvas, text, (x, y),
                cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness, cv2.LINE_AA)


class GaugeRenderer:
    """BMW iDrive 8 cluster-map style renderer."""

    def __init__(self, style: dict, gauges, width: int = 800, height: int = 480):
        self._precompute()

    # ── One-time pre-computation ─────────────────────────────────────────────
    def _precompute(self) -> None:
        H, W = SH, SW

        # Left panel gradient alpha mask (H × GW × 1, float32)
        # Outer (left screen edge) = opaque, inner (diagonal) = transparent
        x_l = np.linspace(1.0, 0.0, GW, dtype=np.float32)
        a_l = 0.93 * np.power(x_l, 0.52) + 0.04
        poly_l = np.array([[0, 0], [GW, 0], [_ldx(H), H], [0, H]], np.int32)
        mask_l = np.zeros((H, GW), np.float32)
        cv2.fillPoly(mask_l, [poly_l], 1.0)
        self._al = (np.outer(np.ones(H, np.float32), a_l) * mask_l)[:, :, np.newaxis]

        # Right panel gradient alpha mask (mirrored)
        a_r = a_l[::-1]   # inner (left of canvas) = transparent, outer = opaque
        poly_r = np.array([[0, 0], [GW, 0], [GW, H], [_rdx(H), H]], np.int32)
        mask_r = np.zeros((H, GW), np.float32)
        cv2.fillPoly(mask_r, [poly_r], 1.0)
        self._ar = (np.outer(np.ones(H, np.float32), a_r) * mask_r)[:, :, np.newaxis]

        # Pre-computed gradient fill bar — left (cyan, grows left→right)
        bl = max(_ldx(H) - 16, 1)
        t  = np.linspace(0.0, 1.0, bl, dtype=np.float32)
        bar_l = np.zeros((4, bl, 3), np.uint8)
        bar_l[:, :, 0] = np.clip(110 + 135 * t, 0, 255).astype(np.uint8)  # B
        bar_l[:, :, 1] = np.clip( 55 + 151 * t, 0, 255).astype(np.uint8)  # G
        bar_l[:, :, 2] = np.clip( 10 + 235 * t, 0, 255).astype(np.uint8)  # R
        self._bar_l  = bar_l
        self._bar_lw = bl
        self._bar_lx = 8   # bar x-start

        # Pre-computed gradient fill bar — right (red, grows right→left)
        inner_r = _rdx(H) + 8
        br = max((GW - 8) - inner_r, 1)
        t  = np.linspace(0.0, 1.0, br, dtype=np.float32)   # 0=inner, 1=outer
        bar_r = np.zeros((4, br, 3), np.uint8)
        bar_r[:, :, 0] = np.clip(  3 +  45 * t, 0, 255).astype(np.uint8)  # B
        bar_r[:, :, 1] = np.clip(  3 +  45 * t, 0, 255).astype(np.uint8)  # G
        bar_r[:, :, 2] = np.clip( 60 + 181 * t, 0, 255).astype(np.uint8)  # R
        self._bar_r  = bar_r
        self._bar_rw = br
        self._bar_rx0 = W - GW + inner_r   # screen x: inner end of right bar
        self._bar_rx1 = W - 8              # screen x: outer end of right bar

    # ── Main entry ────────────────────────────────────────────────────────────
    def render_frame(self, canvas: np.ndarray, snap: VehicleState,
                     interp: Dict, page: int) -> None:
        canvas[:] = (14, 12, 10)   # background

        speed = _smooth(interp, 'spd', snap.speed_kph, 0.15)
        rpm   = _smooth(interp, 'rpm', snap.rpm,       0.20)
        fuel  = _smooth(interp, 'fue', snap.fuel_pct,  0.04)
        clt   = _smooth(interp, 'clt', snap.clt_c,     0.04)

        if page == 0:
            self._center_p0(canvas, snap, speed, clt, fuel)
        else:
            self._center_p1(canvas, snap)

        self._left_panel(canvas, speed, fuel)
        self._right_panel(canvas, rpm, clt)
        self._bottom_bar(canvas, snap)

        if snap.bt_pairing_pending:
            self._pairing_dialog(canvas, snap)

    # ── Left panel ───────────────────────────────────────────────────────────
    def _left_panel(self, canvas: np.ndarray,
                    speed: float, fuel: float) -> None:
        # Gradient background blend
        reg = canvas[:, :GW].astype(np.float32)
        canvas[:, :GW] = np.clip(
            _BG * self._al + reg * (1 - self._al), 0, 255
        ).astype(np.uint8)

        frac = max(0.0, min(1.0, speed / SPEED_MAX))

        # ── Speed tick marks & labels ──
        for lvl, maj in _SPEED_LVLS:
            lf  = lvl / SPEED_MAX
            y   = int(TOP_PAD + TICK_H * (1 - lf))
            dx  = _ldx(y)
            act = lvl > 0 and lvl <= speed
            tl  = 22 if maj else 11
            clr = _CYAN if act else _DIM
            cv2.line(canvas, (dx, y), (dx - tl, y),
                     clr, 2 if maj else 1, cv2.LINE_AA)
            if lvl > 0:
                lbl = str(lvl)
                fs  = 0.38 if maj else 0.28
                tw  = cv2.getTextSize(lbl, cv2.FONT_HERSHEY_SIMPLEX, fs, 1)[0][0]
                _txt(canvas, lbl, dx - tl - 5 - tw, y + 5, fs, clr)

        # "0" at bottom
        y0  = int(TOP_PAD + TICK_H)
        dx0 = _ldx(y0)
        tw0 = cv2.getTextSize('0', cv2.FONT_HERSHEY_SIMPLEX, 0.28, 1)[0][0]
        _txt(canvas, '0', dx0 - 22 - 5 - tw0, y0 + 5, 0.28,
             _CYAN if speed < 3 else _DIM)

        # ── Fuel sub-scale (vertical, inside panel) ──
        fp = max(0.0, min(1.0, fuel))
        sh  = _SUB_BOT - _SUB_TOP
        fy_ind = int(_SUB_BOT - fp * sh)

        # Track line
        cv2.line(canvas,
                 (_FUEL_SUB_X - 3, _SUB_TOP),
                 (_FUEL_SUB_X - 3, _SUB_BOT), _DIM, 1)

        # Fill
        if fp > 0.01:
            fc = (0, 55, 255) if fp < 0.15 else (0, 150, 255) if fp < 0.25 else _CYAN
            cv2.rectangle(canvas,
                          (_FUEL_SUB_X - 4, fy_ind),
                          (_FUEL_SUB_X - 2, _SUB_BOT), fc, -1)

        # Tick marks & labels
        for fval, flbl in _FUEL_MARKS:
            fy  = int(_SUB_BOT - fval * sh)
            act_f = fp >= fval - 0.02
            fc2  = _CYAN if act_f else _DIM
            cv2.line(canvas, (_FUEL_SUB_X - 3, fy),
                     (_FUEL_SUB_X + 10, fy), fc2, 1, cv2.LINE_AA)
            _txt(canvas, flbl, _FUEL_SUB_X + 13, fy + 4, 0.28, fc2)

        # Indicator dot
        dot_c = (0, 55, 255) if fp < 0.15 else _CYAN
        cv2.circle(canvas, (_FUEL_SUB_X - 3, fy_ind), 4, dot_c, -1, cv2.LINE_AA)
        _txt(canvas, 'FUEL', _FUEL_SUB_X - 14, _SUB_TOP - 10, 0.28, _GRAY)

        # ── Speed fill bar (horizontal, near bottom) ──
        bar_y  = SH - BOT_PAD + 22
        bar_x0 = self._bar_lx
        bar_x1 = _ldx(SH) - 8
        bar_w  = bar_x1 - bar_x0
        fill_w = max(0, int(bar_w * frac))

        cv2.rectangle(canvas, (bar_x0, bar_y), (bar_x1, bar_y + 4), (22, 27, 36), -1)
        if fill_w > 0 and self._bar_lw > 0:
            sl = min(fill_w, self._bar_lw)
            canvas[bar_y:bar_y + 4, bar_x0:bar_x0 + sl] = self._bar_l[:, :sl]
            gx = bar_x0 + sl
            if gx < bar_x1:
                canvas[bar_y - 1:bar_y + 5, gx - 2:gx] = [215, 245, 255]

        # ── Header & large speed value ──
        _txt(canvas, 'km/h', 12, 26, 0.38, _GRAY)
        _txt(canvas, str(int(round(speed))), 10, 98, 2.1, _CYAN, 3)

    # ── Right panel ──────────────────────────────────────────────────────────
    def _right_panel(self, canvas: np.ndarray,
                     rpm: float, clt: float) -> None:
        reg = canvas[:, SW - GW:SW].astype(np.float32)
        canvas[:, SW - GW:SW] = np.clip(
            _BG * self._ar + reg * (1 - self._ar), 0, 255
        ).astype(np.uint8)

        frac    = max(0.0, min(1.0, rpm / RPM_MAX))
        redline = rpm >= 6000

        # ── RPM tick marks & labels ──
        for lvl, lbl in _RPM_LVLS:
            lf  = lvl / RPM_MAX
            y   = int(TOP_PAD + TICK_H * (1 - lf))
            sx  = SW - GW + _rdx(y)
            act = lvl <= rpm
            ir  = lvl >= 6000
            clr = (_HOT if ir else _RED) if act else _DIM
            cv2.line(canvas, (sx, y), (sx + 22, y), clr, 2, cv2.LINE_AA)
            _txt(canvas, lbl, sx + 26, y + 5, 0.38, clr)

        # "READY" at bottom
        yr  = int(TOP_PAD + TICK_H)
        sxr = SW - GW + _rdx(yr)
        _txt(canvas, 'READY', sxr + 26, yr + 5, 0.28,
             _RED if rpm < 200 else _DIM)

        # ── Coolant temp sub-scale (vertical, inside right panel) ──
        clt_norm = (max(CLT_MIN, min(CLT_MAX, clt)) - CLT_MIN) / (CLT_MAX - CLT_MIN)
        sh = _SUB_BOT - _SUB_TOP
        cy_ind   = int(_SUB_BOT - clt_norm * sh)
        clt_hot  = clt > 105.0
        clt_warn = clt > 118.0

        # Track
        tx = SW - GW + _CLT_SUB_X
        cv2.line(canvas, (tx, _SUB_TOP), (tx, _SUB_BOT), _DIM, 1)

        # Fill
        if clt_norm > 0.01:
            tc = _AMBER if clt_warn else _RED if clt_hot else _GRAY
            cv2.rectangle(canvas, (tx - 1, cy_ind), (tx + 1, _SUB_BOT), tc, -1)

        # Tick marks
        for cval, clbl in _CLT_MARKS:
            cn  = (cval - CLT_MIN) / (CLT_MAX - CLT_MIN)
            cy  = int(_SUB_BOT - cn * sh)
            act_c = clt >= cval - 1
            cc   = (_AMBER if cval >= 150 else _RED if cval >= 100 else _GRAY) \
                   if act_c else _DIM
            cv2.line(canvas, (tx - 12, cy), (tx, cy), cc, 1, cv2.LINE_AA)
            tw = cv2.getTextSize(clbl, cv2.FONT_HERSHEY_SIMPLEX, 0.28, 1)[0][0]
            _txt(canvas, clbl, tx - 14 - tw, cy + 4, 0.28, cc)

        dot_c = _AMBER if clt_warn else _RED if clt_hot else _GRAY
        cv2.circle(canvas, (tx, cy_ind), 4, dot_c, -1, cv2.LINE_AA)
        _txt(canvas, 'CLT', tx - 18, _SUB_TOP - 10, 0.28, _GRAY)

        # ── RPM fill bar (fills from outer/right edge leftward) ──
        bar_y  = SH - BOT_PAD + 22
        fill_w = max(0, int(self._bar_rw * frac))
        cv2.rectangle(canvas,
                      (self._bar_rx0, bar_y),
                      (self._bar_rx1, bar_y + 4), (22, 27, 36), -1)
        if fill_w > 0 and self._bar_rw > 0:
            sl = min(fill_w, self._bar_rw)
            sx0 = self._bar_rx1 - sl
            canvas[bar_y:bar_y + 4, sx0:self._bar_rx1] = \
                self._bar_r[:, self._bar_rw - sl:]
            if sx0 > self._bar_rx0:
                canvas[bar_y - 1:bar_y + 5, sx0:sx0 + 2] = \
                    [180, 180, 255] if redline else [210, 190, 210]

        # ── Header & large RPM value ──
        _txt(canvas, '1/min x1000', SW - 122, 26, 0.30, _GRAY)
        clr_v   = _HOT if redline else _RED
        rpm_txt = f'{rpm / 1000:.1f}'
        tw      = cv2.getTextSize(rpm_txt, cv2.FONT_HERSHEY_SIMPLEX, 1.9, 3)[0][0]
        _txt(canvas, rpm_txt, SW - tw - 12, 98, 1.9, clr_v, 3)
        _txt(canvas, 'rpm', SW - 50, 118, 0.32, _GRAY)

    # ── Center page 0 ─────────────────────────────────────────────────────────
    def _center_p0(self, canvas: np.ndarray, snap: VehicleState,
                   speed: float, clt: float, fuel: float) -> None:
        CX = 200   # left edge of center zone

        # ─── Row 1: AFR  /  MAP  /  BAT  ───────────────────────────────────
        afr     = snap.afr
        afr_ok  = 13.5 <= afr <= 15.5
        afr_hot = afr < 12.5 or afr > 16.5
        afr_clr = _AMBER if afr_hot else _CYAN if afr_ok else _RED

        _txt(canvas, 'AFR', CX + 20, 38, 0.40, _GRAY)
        _txt(canvas, f'{afr:.1f}', CX + 10, 88, 1.45, afr_clr, 2)
        _txt(canvas, 'target 14.7', CX + 10, 105, 0.28, _DIM)

        _txt(canvas, 'MAP', CX + 148, 38, 0.40, _GRAY)
        map_c = _AMBER if snap.map_kpa > 150 else _WHITE
        _txt(canvas, f'{snap.map_kpa:.0f}', CX + 140, 80, 1.10, map_c, 2)
        _txt(canvas, 'kPa', CX + 152, 96, 0.30, _GRAY)

        _txt(canvas, 'BAT', CX + 272, 38, 0.40, _GRAY)
        bat_c = _AMBER if snap.batt_v < 11.5 else _WHITE
        _txt(canvas, f'{snap.batt_v:.1f}', CX + 260, 80, 1.10, bat_c, 2)
        _txt(canvas, 'V', CX + 278, 96, 0.30, _GRAY)

        # ─── Divider ────────────────────────────────────────────────────────
        cv2.line(canvas, (CX + 8, 118), (CX + 392, 118), _DIM, 1)

        # ─── Coolant bar ────────────────────────────────────────────────────
        _txt(canvas, 'COOLANT', CX + 10, 136, 0.32, _GRAY)
        BX, BY, BW, BH = CX + 10, 144, 378, 7
        cv2.rectangle(canvas, (BX, BY), (BX + BW, BY + BH), (28, 33, 44), -1)
        clt_f = (max(CLT_MIN, min(CLT_MAX, clt)) - CLT_MIN) / (CLT_MAX - CLT_MIN)
        clt_fill = int(BW * clt_f)
        if clt_fill > 0:
            t = clt_f
            b = int(190 * (1 - t)); g = int(40 * (1 - t)); r = int(40 + 210 * t)
            cv2.rectangle(canvas, (BX, BY), (BX + clt_fill, BY + BH), (b, g, r), -1)
        # Optimal zone bracket (80–105 °C)
        ok0 = int(BX + BW * (80 - CLT_MIN) / (CLT_MAX - CLT_MIN))
        ok1 = int(BX + BW * (105 - CLT_MIN) / (CLT_MAX - CLT_MIN))
        cv2.rectangle(canvas, (ok0, BY - 2), (ok1, BY + BH + 2), _CYAN, 1)

        clt_c = _AMBER if clt > 105 else _GRAY
        _txt(canvas, f'{clt:.0f} °C', CX + 10, 175, 0.52, clt_c)
        _txt(canvas, '40', BX - 2, 188, 0.25, _DIM)
        _txt(canvas, '160', BX + BW - 18, 188, 0.25, _DIM)

        # ─── Divider ────────────────────────────────────────────────────────
        cv2.line(canvas, (CX + 8, 200), (CX + 392, 200), _DIM, 1)

        # ─── Row 2: TPS  /  IAT  /  IGN  /  GPS ────────────────────────────
        def metric(label, value, color, lx, ly):
            _txt(canvas, label, CX + lx, ly - 15, 0.34, _GRAY)
            _txt(canvas, value, CX + lx, ly,      0.65, color, 2)

        metric('TPS', f'{snap.tps_pct:.0f}%', _WHITE, 10, 248)
        iat_c = _AMBER if snap.iat_c > 50 else _GRAY
        metric('IAT', f'{snap.iat_c:.0f}°C',  iat_c,  105, 248)
        metric('IGN', f'{snap.ign_advance:.1f}°', _WHITE, 210, 248)
        gps_v = f'{speed:.0f}' if snap.gps_fix else '--'
        metric('GPS', gps_v + ' kmh', _CYAN if snap.gps_fix else _DIM, 300, 248)

        # ─── Divider ────────────────────────────────────────────────────────
        cv2.line(canvas, (CX + 8, 268), (CX + 392, 268), _DIM, 1)

        # ─── Bluetooth media ────────────────────────────────────────────────
        if snap.bt_connected:
            if snap.bt_playing and snap.bt_title:
                _txt(canvas, snap.bt_title[:30],  CX + 12, 298, 0.42, _WHITE)
                _txt(canvas, snap.bt_artist[:30], CX + 12, 320, 0.37, _GRAY)
            else:
                _txt(canvas, 'BT CONNECTED', CX + 12, 302, 0.42, _GRAY)
        else:
            _txt(canvas, 'BLUETOOTH OFF', CX + 12, 302, 0.40, _DIM)

        # Media control buttons
        bt_c = _GRAY if snap.bt_connected else _DIM
        _txt(canvas, '|<', CX + 126, 350, 0.58, bt_c)
        play_lbl = '||' if snap.bt_playing else ' >'
        _txt(canvas, play_lbl, CX + 188, 350, 0.68, _WHITE if snap.bt_connected else _DIM, 2)
        _txt(canvas, '>|', CX + 254, 350, 0.58, bt_c)

        # ─── Divider ────────────────────────────────────────────────────────
        cv2.line(canvas, (CX + 8, 370), (CX + 392, 370), _DIM, 1)

        # ─── ODO / TRIP ─────────────────────────────────────────────────────
        _txt(canvas, f'ODO  {snap.odo_km:.1f} km',  CX + 12, 398, 0.38, _GRAY)
        _txt(canvas, f'TRIP {snap.trip_km:.1f} km', CX + 200, 398, 0.38, _GRAY)

    # ── Center page 1 (diagnostics) ──────────────────────────────────────────
    def _center_p1(self, canvas: np.ndarray, snap: VehicleState) -> None:
        CX = 200
        _txt(canvas, 'DIAGNOSTICS', CX + 118, 28, 0.46, _GRAY)
        cv2.line(canvas, (CX + 8, 38), (CX + 392, 38), _DIM, 1)

        cells = [
            ('RPM',  f'{snap.rpm:.0f}',            _RED,   10,  95),
            ('SPD',  f'{snap.speed_kph:.0f} km/h', _CYAN,  10, 175),
            ('CLT',  f'{snap.clt_c:.1f} C',        _WHITE if snap.clt_c <= 105 else _AMBER, 210, 95),
            ('IAT',  f'{snap.iat_c:.1f} C',        _WHITE, 210, 175),
            ('MAP',  f'{snap.map_kpa:.0f} kPa',    _WHITE,  10, 255),
            ('AFR',  f'{snap.afr:.2f}',            _CYAN,  210, 255),
            ('TPS',  f'{snap.tps_pct:.1f} %',      _WHITE,  10, 335),
            ('IGN',  f'{snap.ign_advance:.1f} deg',_WHITE, 210, 335),
            ('BAT',  f'{snap.batt_v:.2f} V',
             _WHITE if snap.batt_v > 11.5 else _AMBER, 10, 415),
            ('GPS',  f'{snap.speed_kph if snap.gps_fix else 0.0:.0f} km/h',
             _CYAN if snap.gps_fix else _DIM, 210, 415),
        ]
        for label, value, color, lx, ly in cells:
            _txt(canvas, label, CX + lx, ly - 18, 0.34, _GRAY)
            _txt(canvas, value, CX + lx, ly,      0.68, color, 2)

    # ── Bottom status bar ─────────────────────────────────────────────────────
    def _bottom_bar(self, canvas: np.ndarray, snap: VehicleState) -> None:
        BAR_Y = SH - 40
        cv2.rectangle(canvas, (0, BAR_Y), (SW, SH), (10, 10, 18), -1)
        cv2.line(canvas, (0, BAR_Y), (SW, BAR_Y), _DIM, 1)

        t  = time.localtime()
        h12 = t.tm_hour % 12 or 12
        ampm = 'pm' if t.tm_hour >= 12 else 'am'
        _txt(canvas, f'{h12}:{t.tm_min:02d} {ampm}', 208, SH - 12, 0.42, _GRAY)

        # GPS dot
        cv2.circle(canvas, (352, SH - 20), 5,
                   _CYAN if snap.gps_fix else _DIM, -1, cv2.LINE_AA)

        # BT
        _txt(canvas, 'BT', 368, SH - 12, 0.36,
             _CYAN if snap.bt_connected else _DIM)

        # ODO
        _txt(canvas, f'{snap.odo_km:.0f} km', 404, SH - 12, 0.36, _GRAY)

        # Battery
        bat_c = _AMBER if snap.batt_v < 11.5 else _GRAY
        _txt(canvas, f'{snap.batt_v:.1f}V', 510, SH - 12, 0.36, bat_c)

        # CLT summary
        clt_c = _AMBER if snap.clt_c > 105 else _GRAY
        _txt(canvas, f'{snap.clt_c:.0f}C', 568, SH - 12, 0.36, clt_c)

    # ── Pairing dialog overlay ────────────────────────────────────────────────
    def _pairing_dialog(self, canvas: np.ndarray, snap: VehicleState) -> None:
        ov = canvas.copy()
        cv2.rectangle(ov, (148, 138), (652, 358), (18, 18, 28), -1)
        cv2.rectangle(ov, (148, 138), (652, 358), _GRAY, 1)
        canvas[:] = cv2.addWeighted(ov, 0.93, canvas, 0.07, 0)

        _txt(canvas, 'BLUETOOTH PAIRING', 168, 178, 0.52, _WHITE)
        dev = (snap.bt_pairing_device or 'Unknown')[:34]
        _txt(canvas, dev, 168, 212, 0.44, _CYAN)
        if snap.bt_pairing_passkey:
            _txt(canvas, f'Passkey:  {snap.bt_pairing_passkey:06d}',
                 168, 248, 0.50, _WHITE)

        ax1, ay1, ax2, ay2 = PAIRING_ACCEPT_RECT
        cv2.rectangle(canvas, (ax1, ay1), (ax2, ay2), _CYAN, -1)
        _txt(canvas, 'ACCEPT', ax1 + 36, ay2 - 12, 0.52, (12, 12, 20), 2)

        rx1, ry1, rx2, ry2 = PAIRING_REJECT_RECT
        cv2.rectangle(canvas, (rx1, ry1), (rx2, ry2), _DIM, -1)
        _txt(canvas, 'REJECT', rx1 + 36, ry2 - 12, 0.52, _WHITE, 2)
