#!/usr/bin/env python3
"""Nova Navigation — PyQt6 + Google Maps heading-up map.

Usage:
    python3 map_ui.py [--port /dev/rfcomm0] [--key YOUR_API_KEY]

Environment variable alternative:
    GOOGLE_MAPS_KEY=xxx python3 map_ui.py
"""
from __future__ import annotations
import argparse
import glob
import json
import logging
import os
import subprocess
import sys
from pathlib import Path


def swaymsg(*args: str) -> None:
    socks = glob.glob('/run/user/0/sway-ipc.*.*.sock')
    env = {**os.environ, 'SWAYSOCK': socks[0]} if socks else os.environ
    subprocess.run(['swaymsg', *args], env=env, check=False, capture_output=True)

from PyQt6.QtCore import QObject, QTimer, QUrl, pyqtSignal, pyqtSlot
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QApplication, QMainWindow

from gps_rfcomm import GpsRfcomm

log = logging.getLogger(__name__)
HTML_PATH = Path(__file__).parent / 'map.html'
UPDATE_INTERVAL_MS = 500


class GpsBridge(QObject):
    """Exposes GPS data and dashboard control to the JavaScript side via QWebChannel."""

    position_changed = pyqtSignal(str)   # emits JSON string

    def __init__(self, gps: GpsRfcomm, parent: QObject | None = None):
        super().__init__(parent)
        self._gps = gps

    def push(self) -> None:
        pos = self._gps.get_position()
        # Read live vehicle state written by main.py (~6 Hz)
        vehicle: dict = {'speed_kph': 0.0, 'rpm': 0.0, 'fuel_pct': 0.5, 'clt_c': 85.0}
        try:
            with open('/tmp/nova_vehicle.json') as _vf:
                vehicle = json.load(_vf)
        except (OSError, ValueError):
            pass
        self.position_changed.emit(json.dumps({
            'lat':       pos.lat,
            'lon':       pos.lon,
            'heading':   pos.heading,
            'speed':     pos.speed_kmh,
            'fix':       pos.fix,
            'speed_kph': vehicle.get('speed_kph', 0.0),
            'rpm':       vehicle.get('rpm', 0.0),
            'fuel_pct':  vehicle.get('fuel_pct', 0.5),
            'clt_c':     vehicle.get('clt_c', 85.0),
        }))

    @pyqtSlot()
    def go_home(self) -> None:
        """Switch Sway focus back to the dashboard workspace."""
        swaymsg('workspace', '1')


class MapWindow(QMainWindow):
    def __init__(self, gps: GpsRfcomm, api_key: str):
        super().__init__()
        self.setWindowTitle('Nova Navigation')
        self.showFullScreen()

        self._view = QWebEngineView()
        self.setCentralWidget(self._view)

        # Allow file:// pages to load remote URLs (needed for Google Maps)
        self._view.page().settings().setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)

        # Wire up Python → JS bridge
        self._bridge = GpsBridge(gps, parent=self)
        self._channel = QWebChannel(self._view.page())
        self._channel.registerObject('gps', self._bridge)
        self._view.page().setWebChannel(self._channel)

        # Load HTML, inject API key
        html = HTML_PATH.read_text(encoding='utf-8').replace('{{API_KEY}}', api_key)
        self._view.setHtml(html, QUrl.fromLocalFile(str(HTML_PATH)))

        # Move to workspace 2 only after page has loaded so WebEngine renderer
        # is fully initialised before the window goes to a background workspace
        self._view.loadFinished.connect(self._on_load_finished)

        # Push GPS state to JS on a timer
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._bridge.push)
        self._timer.start(UPDATE_INTERVAL_MS)

        log.info("MapWindow ready — pushing GPS every %dms", UPDATE_INTERVAL_MS)

    def _on_load_finished(self, ok: bool) -> None:
        log.info("Page load finished (ok=%s) — enabling fullscreen", ok)
        QTimer.singleShot(300, self._enable_fullscreen)

    def _enable_fullscreen(self) -> None:
        swaymsg('fullscreen', 'enable')

    def keyPressEvent(self, event):
        from PyQt6.QtCore import Qt
        if event.key() in (Qt.Key.Key_Escape, Qt.Key.Key_Q):
            self.close()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(name)s %(levelname)s %(message)s',
    )

    parser = argparse.ArgumentParser(description='Nova Navigation Map')
    parser.add_argument('--mac', default='94:45:60:47:0F:E0',
                        help='Bluetooth MAC of the GPS device')
    parser.add_argument('--key', default=os.environ.get('GOOGLE_MAPS_KEY', ''),
                        help='Google Maps JavaScript API key')
    args = parser.parse_args()

    if not args.key:
        sys.exit('ERROR: Google Maps API key required. Pass --key or set GOOGLE_MAPS_KEY.')

    # Start GPS thread
    gps = GpsRfcomm(mac=args.mac)
    gps.start()
    log.info("GPS thread started, connecting to %s", args.mac)

    # Qt app — Wayland-friendly flags; --no-sandbox required when running as root
    os.environ.setdefault('QT_QPA_PLATFORM', 'wayland')
    os.environ['QTWEBENGINE_CHROMIUM_FLAGS'] = '--no-sandbox --disable-gpu --in-process-gpu'
    app = QApplication(sys.argv)
    window = MapWindow(gps, api_key=args.key)
    ret = app.exec()

    gps.stop()
    gps.join(timeout=3.0)
    sys.exit(ret)


if __name__ == '__main__':
    main()
