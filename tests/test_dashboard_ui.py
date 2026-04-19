import numpy as np
from dashboard_ui import GaugeRenderer

STYLE = {
    'bg_color':      [1, 6, 8],
    'arc_active':    [0, 122, 196],
    'arc_inactive':  [0, 18, 26],
    'arc_redzone':   [0, 20, 140],
    'needle_color':  [128, 210, 255],
    'hub_color':     [0, 122, 196],
    'label_color':   [0, 66, 90],
    'value_color':   [128, 210, 255],
    'warning_amber': [0, 165, 255],
    'warning_red':   [0, 0, 220],
}

GAUGES = {
    'tachometer': {
        'center': [480, 360], 'radius': 280, 'arc_width': 18,
        'start_angle': 150, 'sweep': 240,
        'min_val': 0, 'max_val': 6000, 'redzone_val': 4500,
        'label': 'RPM', 'lerp_alpha': 0.15,
    },
    'speedometer': {
        'center': [1440, 360], 'radius': 280, 'arc_width': 18,
        'start_angle': 150, 'sweep': 240,
        'min_val': 0, 'max_val': 160, 'redzone_val': None,
        'label': 'MPH', 'lerp_alpha': 0.10,
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


def test_draw_needle_no_crash():
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
# Task 3: tick-position cache tests
# These use a minimal GAUGES fixture that matches the tick-cache spec exactly.
# ---------------------------------------------------------------------------

_TICK_STYLE = {
    'bg_color': [10, 10, 10],
    'arc_active': [255, 229, 0],
    'arc_inactive': [40, 40, 40],
    'arc_redzone': [0, 0, 255],
    'needle_color': [255, 255, 255],
    'hub_color': [255, 229, 0],
    'label_color': [160, 160, 160],
    'value_color': [255, 255, 255],
    'warning_amber': [0, 165, 255],
    'warning_red': [0, 0, 255],
}

_TICK_GAUGES = {
    'tachometer': {
        'center': [133, 240], 'radius': 110, 'arc_width': 4,
        'start_angle': 135, 'sweep': 270,
        'min_val': 0, 'max_val': 6000, 'redzone_val': 4500,
        'lerp_alpha': 0.15,
    },
    'speedometer': {
        'center': [667, 240], 'radius': 110, 'arc_width': 4,
        'start_angle': 135, 'sweep': 270,
        'min_val': 0, 'max_val': 240, 'redzone_val': None,
        'lerp_alpha': 0.10,
    },
    'center_panel': {'readouts': []},
}


def test_tick_cache_populated_on_init():
    r = GaugeRenderer(_TICK_STYLE, _TICK_GAUGES)
    assert 'tachometer' in r._tick_cache
    assert 'speedometer' in r._tick_cache


def test_tach_tick_cache_has_correct_count():
    r = GaugeRenderer(_TICK_STYLE, _TICK_GAUGES)
    # 0–6000 in 250 RPM steps = 25 ticks (0, 250, 500, ..., 6000)
    assert len(r._tick_cache['tachometer']) == 25


def test_speedo_tick_cache_has_correct_count():
    r = GaugeRenderer(_TICK_STYLE, _TICK_GAUGES)
    # 0–240 in 10 km/h steps = 25 ticks (0, 10, 20, ..., 240)
    assert len(r._tick_cache['speedometer']) == 25


def test_tick_cache_entry_structure():
    r = GaugeRenderer(_TICK_STYLE, _TICK_GAUGES)
    entry = r._tick_cache['tachometer'][0]
    # Each entry: (x1, y1, x2, y2, is_major)
    assert len(entry) == 5
    assert isinstance(entry[4], bool)


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
