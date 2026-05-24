# main.py
"""Nova Dashboard — instrument cluster.
Launches CAN and GPS daemon threads, then runs the 60 FPS render loop.
Uses pygame with SDL Wayland backend under the Weston compositor.
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

os.environ.setdefault('SDL_VIDEODRIVER', 'wayland')
os.environ.setdefault('WAYLAND_DISPLAY', 'wayland-1')
import pygame

from vehicle_state import VehicleState
from can_handler import CANListener
from gps_handler import GPSListener
from dashboard_ui import GaugeRenderer, PAIRING_ACCEPT_RECT, PAIRING_REJECT_RECT
from bluetooth_handler import BluetoothHandler
from pairing_agent import PairingAgent
from config_loader import load_style, load_gauges

# Must run before any dbus.SystemBus() call (including bluetooth_handler)
# so the singleton is created with the GLib main loop attached.
try:
    import dbus.mainloop.glib
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
except ImportError:
    pass

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
WIDTH, HEIGHT = 800, 480


def main() -> None:
    style = load_style()
    gauges = load_gauges()

    state = VehicleState()
    renderer = GaugeRenderer(style=style, gauges=gauges, width=WIDTH, height=HEIGHT)

    can_thread = CANListener(state, channel='can0')
    gps_thread = GPSListener(state)
    bt_thread = BluetoothHandler(state)

    running = True

    def _shutdown(sig, frame):
        nonlocal running
        log.info("Shutdown signal received")
        running = False

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    _quit_plymouth()
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.NOFRAME)
    pygame.mouse.set_visible(False)
    clock = pygame.time.Clock()

    canvas = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    SPLASH_FADE_FRAMES = 36
    splash_path = os.path.join(os.path.dirname(__file__), 'assets', 'splash_logo.png')
    splash_img = cv2.imread(splash_path)
    if splash_img is not None:
        splash_img = cv2.resize(splash_img, (WIDTH, HEIGHT))
    splash_frame = 0

    pairing_agent = PairingAgent(state)
    pairing_agent.start()
    log.info("Pairing agent started")

    can_thread.start()
    gps_thread.start()
    bt_thread.start()
    log.info("Dashboard started — targeting %d FPS", TARGET_FPS)

    snap = VehicleState()
    try:
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.MOUSEBUTTONUP:
                    # Pairing dialog taps only
                    if snap.bt_pairing_pending:
                        tx, ty = event.pos
                        x1a, y1a, x2a, y2a = PAIRING_ACCEPT_RECT
                        x1r, y1r, x2r, y2r = PAIRING_REJECT_RECT
                        if x1a <= tx <= x2a and y1a <= ty <= y2a:
                            state.bt_pairing_accepted = True
                            state.bt_pairing_response.set()
                        elif x1r <= tx <= x2r and y1r <= ty <= y2r:
                            state.bt_pairing_accepted = False
                            state.bt_pairing_response.set()

            snap = state.snapshot()

            if '--simulate' in sys.argv:
                t = time.monotonic()
                snap.rpm       = 3000 + 2500 * math.sin(t * 0.4)
                snap.speed_kph = 120  + 100  * math.sin(t * 0.3)
                snap.clt_c     = 85 + 15 * abs(math.sin(t * 0.05))
                snap.fuel_pct  = 0.3 + 0.5 * abs(math.sin(t * 0.05))
                snap.afr       = 14.0 + 2.0 * math.sin(t * 0.25)
                snap.gps_fix   = True

            renderer.render_frame(canvas, snap)

            if splash_img is not None and splash_frame < SPLASH_FADE_FRAMES:
                alpha = 1.0 - (splash_frame / SPLASH_FADE_FRAMES)
                blended = cv2.addWeighted(splash_img, alpha, canvas, 1.0 - alpha, 0)
                canvas[:] = blended
                splash_frame += 1

            rgb = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)
            surf = pygame.surfarray.make_surface(rgb.transpose(1, 0, 2))
            screen.blit(surf, (0, 0))
            pygame.display.flip()

            clock.tick(TARGET_FPS)

    finally:
        log.info("Stopping threads...")
        pairing_agent.stop()
        pairing_agent.join(timeout=2.0)
        can_thread.stop()
        gps_thread.stop()
        bt_thread.stop()
        bt_thread.join(timeout=2.0)
        can_thread.join(timeout=2.0)
        gps_thread.join(timeout=2.0)
        pygame.quit()
        log.info("Clean shutdown complete")


if __name__ == '__main__':
    main()
