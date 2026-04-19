# simulate.py
"""Run the dashboard with simulated data. No hardware required.
On Pi (no display): writes directly to /dev/fb0.
On desktop: falls back to cv2.imshow window.
Usage: python simulate.py
"""
from __future__ import annotations
import mmap
import math
import os
import time
import threading
import numpy as np
import cv2

from vehicle_state import VehicleState
from dashboard_ui import GaugeRenderer
from config_loader import load_style, load_gauges

TARGET_FPS = 30
FRAME_TIME = 1.0 / TARGET_FPS
WIDTH, HEIGHT = 800, 480
FB_DEVICE = '/dev/fb0'


def _simulate_state(state: VehicleState) -> None:
    while True:
        t = time.monotonic()
        with state.lock:
            state.rpm       = 800 + 2600 * abs(math.sin(t * 0.3))
            state.speed_mph = 30 + 50 * abs(math.sin(t * 0.2))
            state.map_kpa   = 60 + 40 * abs(math.sin(t * 0.4))
            state.clt_f     = 185 + 30 * abs(math.sin(t * 0.05))
            state.afr       = 13.0 + 4.0 * abs(math.sin(t * 0.25))
            state.batt_v    = 13.8
            state.odo_mi    = 48231 + t / 60.0
            state.trip_mi   = t / 60.0
            state.gps_fix   = True
        time.sleep(0.05)


def main() -> None:
    style  = load_style()
    gauges = load_gauges()
    state  = VehicleState()

    sim_thread = threading.Thread(target=_simulate_state, args=(state,), daemon=True)
    sim_thread.start()

    renderer = GaugeRenderer(style=style, gauges=gauges)
    interp = {
        'tach_angle':   float(gauges['tachometer']['start_angle']),
        'speedo_angle': float(gauges['speedometer']['start_angle']),
    }
    tach_alpha   = gauges['tachometer']['lerp_alpha']
    speedo_alpha = gauges['speedometer']['lerp_alpha']

    canvas = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)

    use_fb = os.path.exists(FB_DEVICE) and not os.environ.get('DISPLAY')
    if use_fb:
        fb_file = open(FB_DEVICE, 'rb+')
        mm = mmap.mmap(fb_file.fileno(), WIDTH * HEIGHT * 4)
        fb_buf = np.frombuffer(mm, dtype=np.uint8).reshape(HEIGHT, WIDTH, 4)
        print(f"Rendering to {FB_DEVICE}")
    else:
        cv2.namedWindow('Nova Dashboard — SIMULATION', cv2.WINDOW_NORMAL)
        cv2.resizeWindow('Nova Dashboard — SIMULATION', WIDTH, HEIGHT)
        print("Rendering to window")

    try:
        while True:
            frame_start = time.monotonic()
            snap = state.snapshot()

            tach_target   = renderer.val_to_angle(snap.rpm,       'tachometer')
            speedo_target = renderer.val_to_angle(snap.speed_mph, 'speedometer')
            interp['tach_angle']   += (tach_target   - interp['tach_angle'])   * tach_alpha
            interp['speedo_angle'] += (speedo_target - interp['speedo_angle']) * speedo_alpha

            renderer.render_frame(canvas, snap, interp)

            if use_fb:
                cv2.cvtColor(canvas, cv2.COLOR_BGR2BGRA, dst=fb_buf)
            else:
                cv2.imshow('Nova Dashboard — SIMULATION', canvas)
                if cv2.waitKey(1) & 0xFF in (ord('q'), 27):
                    break

            elapsed = time.monotonic() - frame_start
            time.sleep(max(0.005, FRAME_TIME - elapsed))
    finally:
        if use_fb:
            mm.close()
            fb_file.close()
        else:
            cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
