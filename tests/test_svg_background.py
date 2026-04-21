import sys
import types
import numpy as np
import cv2
import pytest


def _make_png_bytes(w: int, h: int) -> bytes:
    """Encode a solid-color WxH RGBA image as PNG bytes."""
    arr = np.zeros((h, w, 4), dtype=np.uint8)
    arr[:, :, 0] = 200  # blue channel
    arr[:, :, 3] = 255  # alpha
    _, buf = cv2.imencode('.png', arr)
    return buf.tobytes()


@pytest.fixture(autouse=True)
def _mock_cairosvg(monkeypatch):
    """Stub out cairosvg at the sys.modules level before any import."""
    fake = types.ModuleType('cairosvg')

    def _fake_svg2png(**kwargs):
        w = kwargs.get('output_width', 1960)
        h = kwargs.get('output_height', 800)
        return _make_png_bytes(w, h)

    fake.svg2png = _fake_svg2png
    monkeypatch.setitem(sys.modules, 'cairosvg', fake)


def _make_renderer(monkeypatch, width=800, height=480):
    from dashboard_ui import GaugeRenderer

    style = {
        'bg_color': [0, 0, 0],
        'arc_inactive': [40, 40, 40],
        'needle_color': [255, 255, 255],
        'label_color': [160, 160, 160],
        'value_color': [255, 255, 255],
        'warning_amber': [0, 165, 255],
        'warning_red': [0, 0, 255],
    }
    gauges = {
        'svg': {'path': 'dummy.svg', 'native_width': 1960, 'native_height': 800},
        'tachometer': {
            'center': [333, 380], 'radius': 245, 'arc_width': 18,
            'start_angle': 135, 'sweep': 270,
            'min_val': 0, 'max_val': 6000, 'redzone_val': 4500,
            'lerp_alpha': 0.15,
            'arc_color': [235, 179, 43], 'arc_bright_color': [251, 226, 42],
            'redzone_color': [0, 0, 255], 'hub_color': [235, 179, 43],
        },
        'speedometer': {
            'center': [1627, 380], 'radius': 245, 'arc_width': 18,
            'start_angle': 135, 'sweep': 270,
            'min_val': 0, 'max_val': 240, 'redzone_val': None,
            'lerp_alpha': 0.10,
            'arc_color': [56, 22, 241], 'arc_bright_color': [56, 70, 252],
            'hub_color': [56, 22, 241],
        },
        'center_panel': {'readouts': []},
    }
    return GaugeRenderer(style=style, gauges=gauges, width=width, height=height)


def test_init_background_shape(monkeypatch):
    r = _make_renderer(monkeypatch)
    assert r._bg.shape == (480, 800, 3)
    assert r._bg.dtype == np.uint8


def test_init_background_non_black(monkeypatch):
    """Background must contain pixels from the SVG, not all zeros."""
    r = _make_renderer(monkeypatch)
    # The mock SVG has blue pixels; after letterbox they must appear in _bg
    assert r._bg.max() > 0


def test_svg_pt_top_left(monkeypatch):
    """SVG (0,0) maps to screen offset (offset_x, offset_y)."""
    r = _make_renderer(monkeypatch)
    sx, sy = r._svg_pt(0, 0)
    assert sx == r._offset_x
    assert sy == r._offset_y


def test_svg_pt_gauge_center_in_screen_bounds(monkeypatch):
    """Tachometer SVG center (333,380) must map within 800x480."""
    r = _make_renderer(monkeypatch)
    sx, sy = r._svg_pt(333, 380)
    assert 0 <= sx < 800
    assert 0 <= sy < 480


def test_no_tick_cache(monkeypatch):
    """_tick_cache must not exist after SVG redesign."""
    r = _make_renderer(monkeypatch)
    assert not hasattr(r, '_tick_cache')
