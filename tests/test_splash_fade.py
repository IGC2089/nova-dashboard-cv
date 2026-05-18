import numpy as np
import cv2


def test_splash_fade_blends_correctly():
    """Blend math: verify addWeighted produces correct values at frame 0 and frame 35."""
    WIDTH, HEIGHT = 800, 480
    SPLASH_FADE_FRAMES = 36
    splash_val, canvas_val = 200, 50

    splash_img = np.full((HEIGHT, WIDTH, 3), splash_val, dtype=np.uint8)

    # Frame 0: alpha = 1.0 → output should equal splash_val
    alpha = 1.0 - (0 / SPLASH_FADE_FRAMES)
    canvas = np.full((HEIGHT, WIDTH, 3), canvas_val, dtype=np.uint8)
    blended = cv2.addWeighted(splash_img, alpha, canvas, 1.0 - alpha, 0)
    canvas[:] = blended
    expected = int(splash_val * alpha + canvas_val * (1.0 - alpha))
    assert abs(int(canvas[0, 0, 0]) - expected) <= 1

    # Frame 35: alpha ≈ 0.028 → output should be close to canvas_val
    alpha = 1.0 - (35 / SPLASH_FADE_FRAMES)
    canvas = np.full((HEIGHT, WIDTH, 3), canvas_val, dtype=np.uint8)
    blended = cv2.addWeighted(splash_img, alpha, canvas, 1.0 - alpha, 0)
    canvas[:] = blended
    expected = int(splash_val * alpha + canvas_val * (1.0 - alpha))
    assert abs(int(canvas[0, 0, 0]) - expected) <= 1


def test_splash_fade_skipped_when_no_image():
    """When splash_img is None the guard must not modify canvas."""
    WIDTH, HEIGHT = 800, 480
    SPLASH_FADE_FRAMES = 36
    canvas_val = 50

    splash_img = None
    splash_frame = 0
    canvas = np.full((HEIGHT, WIDTH, 3), canvas_val, dtype=np.uint8)
    original = canvas.copy()

    # Replicate the exact guard from main.py
    if splash_img is not None and splash_frame < SPLASH_FADE_FRAMES:
        alpha = 1.0 - (splash_frame / SPLASH_FADE_FRAMES)
        blended = cv2.addWeighted(splash_img, alpha, canvas, 1.0 - alpha, 0)
        canvas[:] = blended
        splash_frame += 1

    assert np.array_equal(canvas, original)
    assert splash_frame == 0
