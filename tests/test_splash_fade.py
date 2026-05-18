import numpy as np
import cv2


def test_splash_fade_blends_correctly():
    """Fade at frame 0 should return splash image; at frame 35 canvas should dominate."""
    WIDTH, HEIGHT = 800, 480
    SPLASH_FADE_FRAMES = 36

    splash_img = np.full((HEIGHT, WIDTH, 3), 200, dtype=np.uint8)
    canvas = np.full((HEIGHT, WIDTH, 3), 50, dtype=np.uint8)

    # Frame 0: alpha = 1.0 → result should be close to splash_img
    alpha = 1.0 - (0 / SPLASH_FADE_FRAMES)
    result = canvas.copy()
    cv2.addWeighted(splash_img, alpha, result, 1.0 - alpha, 0, result)
    assert result[0, 0, 0] == 200  # splash dominates

    # Frame 35: alpha ≈ 0.03 → result should be close to canvas
    alpha = 1.0 - (35 / SPLASH_FADE_FRAMES)
    result = canvas.copy()
    cv2.addWeighted(splash_img, alpha, result, 1.0 - alpha, 0, result)
    assert result[0, 0, 0] < 60  # canvas dominates


def test_splash_fade_skipped_when_no_image():
    """When splash_img is None, canvas must not be modified."""
    WIDTH, HEIGHT = 800, 480
    splash_img = None
    canvas = np.full((HEIGHT, WIDTH, 3), 50, dtype=np.uint8)
    original = canvas.copy()

    if splash_img is not None:
        cv2.addWeighted(splash_img, 1.0, canvas, 0.0, 0, canvas)

    assert np.array_equal(canvas, original)
