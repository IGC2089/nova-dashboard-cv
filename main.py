# main.py
"""Nova Dashboard — main entry point.
Launches CAN and GPS daemon threads, then runs the 60 FPS render loop.
Writes frames directly to /dev/fb0 — no X11 or Qt required.
"""
from __future__ import annotations
import mmap
import signal
import sys
import time
import math
import logging
import numpy as np
import cv2

from vehicle_state import VehicleState
from can_handler import CANListener
from gps_handler import GPSListener
from dashboard_ui import GaugeRenderer
from config_loader import load_style, load_gauges

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(name)s %(levelname)s %(message)s',
    handlers=[logging.StreamHandler(sys.stderr)],
)
log = logging.getLogger('main')

TARGET_FPS = 60
FRAME_TIME = 1.0 / TARGET_FPS
WIDTH, HEIGHT = 800, 480
FB_DEVICE = '/dev/fb0'


class Framebuffer:
    """Write BGR numpy frames directly to the Linux framebuffer."""

    def __init__(self, device: str, width: int, height: int):
        self._fb = open(device, 'rb+')
        self._width = width
        self._height = height
        self._mmap = mmap.mmap(self._fb.fileno(), width * height * 4)

    def write(self, bgr_frame: np.ndarray) -> None:
        bgra = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2BGRA)
        self._mmap.seek(0)
        self._mmap.write(bgra.tobytes())

    def close(self) -> None:
        self._mmap.close()
        self._fb.close()


def main() -> None:
    style = load_style()
    gauges = load_gauges()

    state = VehicleState()
    renderer = GaugeRenderer(style=style, gauges=gauges)

    can_thread = CANListener(state, channel='can0')
    gps_thread = GPSListener(state)

    interp = {
        'tach_angle':   float(gauges['tachometer']['start_angle']),
        'speedo_angle': float(gauges['speedometer']['start_angle']),
    }
    tach_alpha   = gauges['tachometer']['lerp_alpha']
    speedo_alpha = gauges['speedometer']['lerp_alpha']

    running = True

    def _shutdown(sig, frame):
        nonlocal running
        log.info("Shutdown signal received")
        running = False

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    fb = Framebuffer(FB_DEVICE, WIDTH, HEIGHT)
    canvas = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)

    can_thread.start()
    gps_thread.start()
    log.info("Dashboard started — targeting %d FPS", TARGET_FPS)

    try:
        while running:
            frame_start = time.monotonic()

            snap = state.snapshot()

            tach_target   = renderer.val_to_angle(snap.rpm,       'tachometer')
            speedo_target = renderer.val_to_angle(snap.speed_mph, 'speedometer')
            interp['tach_angle']   += (tach_target   - interp['tach_angle'])   * tach_alpha
            interp['speedo_angle'] += (speedo_target - interp['speedo_angle']) * speedo_alpha

            renderer.render_frame(canvas, snap, interp)
            fb.write(canvas)

            elapsed = time.monotonic() - frame_start
            sleep_time = FRAME_TIME - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    finally:
        log.info("Stopping threads...")
        can_thread.stop()
        gps_thread.stop()
        can_thread.join(timeout=2.0)
        gps_thread.join(timeout=2.0)
        fb.close()
        log.info("Clean shutdown complete")


if __name__ == '__main__':
    main()
