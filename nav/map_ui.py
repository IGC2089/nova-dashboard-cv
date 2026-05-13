#!/usr/bin/env python3
"""Nova Navigation — PyQt6 + Google Maps heading-up map.

Usage:
    python3 map_ui.py [--port /dev/rfcomm0] [--key YOUR_API_KEY]

Environment variable alternative:
    GOOGLE_MAPS_KEY=xxx python3 map_ui.py
"""
from __future__ import annotations
import argparse
import json
import logging
import os
import sys
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer, QUrl, pyqtSignal, pyqtSlot
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QApplication, QMainWindow

from gps_rfcomm import GpsRfcomm

log = logging.getLogger(__name__)
HTML_PATH = Path(__file__).parent / 'map.html'
UPDATE_INTERVAL_MS = 500


class GpsBridge(QObject):
    """Exposes GPS data to the JavaScript side via QWebChannel."""

    position_changed = pyqtSignal(str)   # emits JSON string

    def __init__(self, gps: GpsRfcomm, parent: QObject | None = None):
        super().__init__(parent)
        self._gps = gps

    def push(self) -> None:
        pos = self._gps.get_position()
        self.position_changed.emit(json.dumps({
            'lat':     pos.lat,
            'lon':     pos.lon,
            'heading': pos.heading,
            'speed':   pos.speed_kmh,
            'fix':     pos.fix,
        }))


class MapWindow(QMainWindow):
    def __init__(self, gps: GpsRfcomm, api_key: str):
        super().__init__()
        self.setWindowTitle('Nova Navigation')
        self.showFullScreen()

        self._view = QWebEngineView()
        self.setCentralWidget(self._view)

        # Wire up Python → JS bridge
        self._bridge = GpsBridge(gps, parent=self)
        self._channel = QWebChannel(self._view.page())
        self._channel.registerObject('gps', self._bridge)
        self._view.page().setWebChannel(self._channel)

        # Load HTML, inject API key
        html = HTML_PATH.read_text(encoding='utf-8').replace('{{API_KEY}}', api_key)
        self._view.setHtml(html, QUrl.fromLocalFile(str(HTML_PATH)))

        # Push GPS state to JS on a timer
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._bridge.push)
        self._timer.start(UPDATE_INTERVAL_MS)

        log.info("MapWindow ready — pushing GPS every %dms", UPDATE_INTERVAL_MS)

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
    parser.add_argument('--port', default='/dev/rfcomm0', help='rfcomm serial port')
    parser.add_argument('--baud', type=int, default=9600)
    parser.add_argument('--key', default=os.environ.get('GOOGLE_MAPS_KEY', ''),
                        help='Google Maps JavaScript API key')
    args = parser.parse_args()

    if not args.key:
        sys.exit('ERROR: Google Maps API key required. Pass --key or set GOOGLE_MAPS_KEY.')

    # Start GPS thread
    gps = GpsRfcomm(port=args.port, baud=args.baud)
    gps.start()
    log.info("GPS thread started on %s", args.port)

    # Qt app — Wayland-friendly flags
    os.environ.setdefault('QT_QPA_PLATFORM', 'wayland')
    app = QApplication(sys.argv)
    window = MapWindow(gps, api_key=args.key)
    ret = app.exec()

    gps.stop()
    gps.join(timeout=3.0)
    sys.exit(ret)


if __name__ == '__main__':
    main()
