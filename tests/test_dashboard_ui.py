import sys
import types
import numpy as np
import cv2
import pytest
from dashboard_ui import GaugeRenderer

# Prevent cairosvg from being called during unit tests — return a black 1960x800 PNG.
@pytest.fixture(autouse=True)
def _patch_cairosvg(monkeypatch):
    fake = types.ModuleType('cairosvg')
    def _fake_svg2png(**kwargs):
        w = kwargs.get('output_width', 1960)
        h = kwargs.get('output_height', 800)
        arr = np.zeros((h, w, 3), dtype=np.uint8)
        _, buf = cv2.imencode('.png', arr)
        return buf.tobytes()
    fake.svg2png = _fake_svg2png
    monkeypatch.setitem(sys.modules, 'cairosvg', fake)


STYLE = {
    'bg_color':      [1, 6, 8],
    'arc_active':    [0, 122, 196],
    'arc_inactive':  [0, 18, 26],
    'arc_redzone':   [0, 0, 255],
    'needle_color':  [128, 210, 255],
    'hub_color':     [0, 122, 196],
    'label_color':   [0, 66, 90],
    'value_color':   [128, 210, 255],
    'warning_amber': [0, 165, 255],
    'warning_red':   [0, 0, 220],
}

GAUGES = {
    'svg': {'path': 'assets/cluster - map.svg', 'native_width': 1960, 'native_height': 800},
    'tachometer': {
        'center': [480, 360], 'radius': 280, 'arc_width': 18,
        'start_angle': 150, 'sweep': 240,
        'min_val': 0, 'max_val': 6000, 'redzone_val': 4500,
        'label': 'RPM', 'lerp_alpha': 0.15,
        'arc_color': [235, 179, 43], 'arc_bright_color': [251, 226, 42],
        'redzone_color': [0, 0, 255], 'hub_color': [235, 179, 43],
    },
    'speedometer': {
        'center': [640, 240], 'radius': 110, 'arc_width': 8,
        'start_angle': 150, 'sweep': 240,
        'min_val': 0, 'max_val': 240, 'redzone_val': None,
        'label': 'km/h', 'lerp_alpha': 0.10,
        'arc_color': [56, 22, 241], 'arc_bright_color': [56, 70, 252],
        'hub_color': [56, 22, 241],
    },
    'center_panel': {
        'readouts': [
            {'label': 'MAP',  'state_field': 'map_kpa', 'unit': 'kPa',
             'pos': [760, 160], 'format': '{:.0f}', 'font_scale': 1.8},
            {'label': 'AFR',  'state_field': 'afr',    'unit': '',
             'pos': [960, 360], 'format': '{:.1f}', 'font_scale': 3.5},
        ]
    },
}


def make_renderer():
    return GaugeRenderer(style=STYLE, gauges=GAUGES)


def test_val_to_angle_at_zero():
    r = make_renderer()
    assert r.val_to_angle(0, 'tachometer') == 150.0


def test_val_to_angle_at_max():
    r = make_renderer()
    assert abs(r.val_to_angle(6000, 'tachometer') - 390.0) < 0.001


def test_val_to_angle_midpoint():
    r = make_renderer()
    assert abs(r.val_to_angle(3000, 'tachometer') - 270.0) < 0.001


def test_val_to_angle_clamped_above_max():
    r = make_renderer()
    assert r.val_to_angle(9999, 'tachometer') <= 390.0


def test_val_to_angle_clamped_below_min():
    r = make_renderer()
    assert r.val_to_angle(-100, 'tachometer') >= 150.0


def make_canvas():
    return np.zeros((720, 1920, 3), dtype=np.uint8)


def test_draw_arc_track_no_crash():
    r = make_renderer()
    canvas = make_canvas()
    r._draw_arc_track(canvas, 'tachometer', active_angle=270.0)
    assert canvas.shape == (720, 1920, 3)


def test_draw_tapered_needle_no_crash():
    r = make_renderer()
    canvas = make_canvas()
    r._draw_tapered_needle(canvas, 'tachometer', needle_angle=270.0)
    assert canvas.shape == (720, 1920, 3)


from vehicle_state import VehicleState


def make_state(**kwargs):
    s = VehicleState(**kwargs)
    s.lock = None
    return s


def test_draw_tachometer_no_crash():
    r = make_renderer()
    canvas = make_canvas()
    r.draw_tachometer(canvas, rpm=3400.0, needle_angle=270.0)
    assert canvas.shape == (720, 1920, 3)




# ---------------------------------------------------------------------------
# Task 4: _draw_tapered_needle tests
# ---------------------------------------------------------------------------

def _make_renderer():
    return GaugeRenderer(STYLE, GAUGES)


def _blank_canvas():
    return np.zeros((480, 800, 3), dtype=np.uint8)


def test_tapered_needle_draws_without_error():
    r = _make_renderer()
    canvas = _blank_canvas()
    r._draw_tapered_needle(canvas, 'tachometer', 135.0)


def test_tapered_needle_modifies_canvas():
    r = _make_renderer()
    canvas = _blank_canvas()
    r._draw_tapered_needle(canvas, 'tachometer', 200.0)
    assert canvas.max() > 0


def test_tapered_needle_no_method_draw_needle():
    r = _make_renderer()
    assert not hasattr(r, '_draw_needle'), \
        "_draw_needle should be removed — use _draw_tapered_needle"


# ---------------------------------------------------------------------------
# Task 5: draw_tachometer rewrite tests
# ---------------------------------------------------------------------------

def test_draw_tachometer_runs_without_error():
    r = _make_renderer()
    canvas = _blank_canvas()
    r.draw_tachometer(canvas, rpm=3000.0, needle_angle=225.0)


def test_draw_tachometer_modifies_canvas():
    r = _make_renderer()
    canvas = _blank_canvas()
    r.draw_tachometer(canvas, rpm=3000.0, needle_angle=225.0)
    assert canvas.max() > 0


def test_draw_tachometer_redzone_at_max():
    """Canvas at max RPM must contain red pixels (redzone arc drawn)."""
    r = _make_renderer()
    canvas = _blank_canvas()
    max_angle = r.val_to_angle(6000, 'tachometer')
    r.draw_tachometer(canvas, rpm=6000.0, needle_angle=max_angle)
    # arc_redzone is [0, 0, 255] — check for red channel > 200
    assert (canvas[:, :, 2] > 200).any()


# ---------------------------------------------------------------------------
# Task 6: draw_speedometer rewrite tests
# ---------------------------------------------------------------------------

def test_draw_speedometer_runs_without_error():
    r = _make_renderer()
    canvas = _blank_canvas()
    r.draw_speedometer(canvas, speed_kph=100.0, needle_angle=270.0, gps_fix=True)


def test_draw_speedometer_no_gps_shows_dashes():
    r = _make_renderer()
    canvas = _blank_canvas()
    r.draw_speedometer(canvas, speed_kph=0.0, needle_angle=135.0, gps_fix=False)
    assert canvas.max() > 0


def test_draw_speedometer_no_redzone_arc():
    """Speedometer has no redzone — no arc_redzone colored pixels expected."""
    r = _make_renderer()
    canvas = _blank_canvas()
    max_angle = r.val_to_angle(240, 'speedometer')
    r.draw_speedometer(canvas, speed_kph=240.0,
                       needle_angle=max_angle, gps_fix=True)
    # arc_redzone is BGR [0, 0, 255]: B~0, G~0, R~255
    # Detect pixels that are purely red (redzone) vs needle/hub (which have G>100)
    pure_red_pixels = (
        (canvas[:, :, 2] > 200) &  # high R channel
        (canvas[:, :, 1] < 20) &   # low G channel (eliminates needle_color [128,210,255])
        (canvas[:, :, 0] < 20)     # low B channel
    ).sum()
    assert pure_red_pixels == 0  # no arc_redzone pixels at all
