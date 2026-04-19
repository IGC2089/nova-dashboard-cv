# simulate.py
"""Run the dashboard with simulated data. No hardware required.
On Pi (no DISPLAY): uses pygame SDL fbcon -> /dev/fb0.
On desktop (DISPLAY set): uses pygame window.
Usage: python simulate.py
"""
from __future__ import annotations
import os
import math
import time
import threading
import numpy as np
import cv2

if not os.environ.get('DISPLAY'):
    os.environ.setdefault('SDL_VIDEODRIVER', 'kmsdrm')
    os.environ.setdefault('SDL_NOMOUSE', '1')

import pygame

from vehicle_state import VehicleState
from dashboard_ui import GaugeRenderer
from config_loader import load_style, load_gauges

TARGET_FPS = 30
WIDTH, HEIGHT = 800, 480


def _simulate_state(state: VehicleState) -> None:
    while True:
        t = time.monotonic()
        with state.lock:
            state.rpm       = 800 + 2600 * abs(math.sin(t * 0.3))
            state.speed_kph = 50 + 80 * abs(math.sin(t * 0.2))
            state.map_kpa   = 60 + 40 * abs(math.sin(t * 0.4))
            state.clt_c     = 85 + 15 * abs(math.sin(t * 0.05))
            state.afr       = 13.0 + 4.0 * abs(math.sin(t * 0.25))
            state.batt_v    = 13.8
            state.odo_km    = 77654 + t / 60.0
            state.trip_km   = t / 60.0
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

    pygame.init()
    flags = pygame.FULLSCREEN if not os.environ.get('DISPLAY') else 0
    screen = pygame.display.set_mode((WIDTH, HEIGHT), flags)
    pygame.mouse.set_visible(False)
    clock = pygame.time.Clock()

    canvas = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key in (pygame.K_q, pygame.K_ESCAPE):
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

    pygame.quit()


if __name__ == '__main__':
    main()
