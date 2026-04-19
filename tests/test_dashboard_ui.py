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
    r._draw_needle(canvas, 'tachometer', needle_angle=270.0)
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


def test_draw_speedometer_no_crash():
    r = make_renderer()
    canvas = make_canvas()
    r.draw_speedometer(canvas, speed_mph=65.0, needle_angle=250.0, gps_fix=True)
    assert canvas.shape == (720, 1920, 3)


def test_draw_speedometer_no_gps_no_crash():
    r = make_renderer()
    canvas = make_canvas()
    r.draw_speedometer(canvas, speed_mph=0.0, needle_angle=150.0, gps_fix=False)
    assert canvas.shape == (720, 1920, 3)


def test_draw_center_panel_no_crash():
    r = make_renderer()
    canvas = make_canvas()
    state = make_state(map_kpa=98.0, clt_f=195.0, afr=14.7,
                       odo_mi=48231.0, trip_mi=127.4, gps_fix=True)
    r.draw_center_panel(canvas, state)
    assert canvas.shape == (720, 1920, 3)
