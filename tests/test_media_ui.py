# tests/test_media_ui.py
import sys
import types
import numpy as np
import cv2
import pytest
from vehicle_state import VehicleState
from dashboard_ui import GaugeRenderer


# Prevent cairosvg from being called during unit tests — return a black 800x480 PNG.
@pytest.fixture(autouse=True)
def _patch_cairosvg(monkeypatch):
    fake = types.ModuleType('cairosvg')
    def _fake_svg2png(**kwargs):
        w = kwargs.get('output_width', 800)
        h = kwargs.get('output_height', 480)
        arr = np.zeros((h, w, 3), dtype=np.uint8)
        _, buf = cv2.imencode('.png', arr)
        return buf.tobytes()
    fake.svg2png = _fake_svg2png
    monkeypatch.setitem(sys.modules, 'cairosvg', fake)


STYLE = {
    'bg_color':      [10, 10, 10],
    'arc_inactive':  [40, 40, 40],
    'needle_color':  [255, 255, 255],
    'label_color':   [160, 160, 160],
    'value_color':   [255, 255, 255],
    'warning_amber': [43, 179, 235],
    'warning_red':   [0, 0, 255],
}

GAUGES = {
    'svg': {'path': 'assets/cluster.svg', 'native_width': 800, 'native_height': 480},
    'fill_svgs': {},
    'tachometer': {
        'center': [200, 240], 'radius': 180, 'arc_width': 14,
        'start_angle': 150, 'sweep': 240,
        'min_val': 0, 'max_val': 8000, 'redzone_val': 6000,
        'label': 'RPM', 'lerp_alpha': 0.15,
        'arc_color': [235, 179, 43], 'arc_bright_color': [251, 226, 42],
        'redzone_color': [0, 0, 255], 'hub_color': [235, 179, 43],
    },
    'speedometer': {
        'center': [600, 240], 'display_center': [600, 240],
        'radius': 110, 'arc_width': 8,
        'start_angle': 150, 'sweep': 240,
        'min_val': 0, 'max_val': 260, 'redzone_val': None,
        'label': 'km/h', 'lerp_alpha': 0.10,
        'arc_color': [56, 22, 241], 'arc_bright_color': [56, 70, 252],
        'hub_color': [56, 22, 241],
    },
    'center_panel': {
        'readouts': [],
    },
}


def _make_renderer():
    return GaugeRenderer(style=STYLE, gauges=GAUGES, width=800, height=480)


def _blank_canvas():
    return np.zeros((480, 800, 3), dtype=np.uint8)


def test_draw_media_player_no_crash_disconnected():
    renderer = _make_renderer()
    canvas = _blank_canvas()
    snap = VehicleState()
    snap.bt_connected = False
    renderer.draw_media_player(canvas, snap)  # must not raise


def test_draw_media_player_no_crash_playing():
    renderer = _make_renderer()
    canvas = _blank_canvas()
    snap = VehicleState()
    snap.bt_connected = True
    snap.bt_playing = True
    snap.bt_title = "Bohemian Rhapsody"
    snap.bt_artist = "Queen"
    snap.bt_album = "A Night at the Opera"
    renderer.draw_media_player(canvas, snap)  # must not raise


def test_draw_media_player_writes_to_center_zone():
    renderer = _make_renderer()
    canvas = _blank_canvas()
    snap = VehicleState()
    snap.bt_connected = True
    snap.bt_playing = False
    snap.bt_title = "Yesterday"
    snap.bt_artist = "Beatles"
    renderer.draw_media_player(canvas, snap)
    # Center zone must not be all zeros (something was drawn)
    center = canvas[:, 200:600]
    assert center.max() > 0
