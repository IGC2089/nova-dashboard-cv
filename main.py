# main.py
"""Nova Dashboard — main entry point.
Launches CAN and GPS daemon threads, then runs the 30 FPS render loop.
Uses pygame with SDL fbcon backend for reliable Pi framebuffer display.
"""
from __future__ import annotations
import os
import signal
import subprocess
import sys
import time
import math
import logging
import numpy as np
import cv2

os.environ.setdefault('SDL_VIDEODRIVER', 'kmsdrm,fbcon')
os.environ.setdefault('SDL_NOMOUSE', '1')
import pygame

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


def _quit_plymouth() -> None:
    """Signal Plymouth to fade out and release the display."""
    try:
        subprocess.run(['plymouth', 'quit', '--retain-splash'],
                       timeout=2.0, check=False, capture_output=True)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass


TARGET_FPS = 60
FRAME_TIME = 1.0 / TARGET_FPS
WIDTH, HEIGHT = 800, 480


def main() -> None:
    style = load_style()
    gauges = load_gauges()

    state = VehicleState()
    renderer = GaugeRenderer(style=style, gauges=gauges, width=WIDTH, height=HEIGHT)

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

    _quit_plymouth()
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.FULLSCREEN)
    pygame.mouse.set_visible(False)
    clock = pygame.time.Clock()

    canvas = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)

    can_thread.start()
    gps_thread.start()
    log.info("Dashboard started — targeting %d FPS", TARGET_FPS)

    try:
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

            snap = state.snapshot()

            tach_target   = renderer.val_to_angle(snap.rpm,       'tachometer')
            speedo_target = renderer.val_to_angle(snap.speed_kph, 'speedometer')
            interp['tach_angle']   += (tach_target   - interp['tach_angle'])   * tach_alpha
            interp['speedo_angle'] += (speedo_target - interp['speedo_angle']) * speedo_alpha

            renderer.render_frame(canvas, snap, interp)

            rgb = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)
            surf = pygame.surfarray.make_surface(rgb.transpose(1, 0, 2))
            screen.blit(surf, (0, 0))
            pygame.display.flip()

            clock.tick(TARGET_FPS)

    finally:
        log.info("Stopping threads...")
        can_thread.stop()
        gps_thread.stop()
        can_thread.join(timeout=2.0)
        gps_thread.join(timeout=2.0)
        pygame.quit()
        log.info("Clean shutdown complete")


if __name__ == '__main__':
    main()
