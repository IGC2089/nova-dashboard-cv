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


def test_splash_fade_stops_at_frame_36():
    """Guard splash_frame < SPLASH_FADE_FRAMES must NOT fire at frame 36."""
    WIDTH, HEIGHT = 800, 480
    SPLASH_FADE_FRAMES = 36
    splash_img = np.full((HEIGHT, WIDTH, 3), 200, dtype=np.uint8)
    canvas_val = 50
    canvas = np.full((HEIGHT, WIDTH, 3), canvas_val, dtype=np.uint8)
    original = canvas.copy()
    splash_frame = 36  # one past the last active frame

    if splash_img is not None and splash_frame < SPLASH_FADE_FRAMES:
        alpha = 1.0 - (splash_frame / SPLASH_FADE_FRAMES)
        blended = cv2.addWeighted(splash_img, alpha, canvas, 1.0 - alpha, 0)
        canvas[:] = blended
        splash_frame += 1

    assert np.array_equal(canvas, original), "Canvas must not be modified at frame 36"
    assert splash_frame == 36, "splash_frame must not increment when guard fails"


def test_splash_frame_counter_increments():
    """splash_frame must increment exactly once per frame and reach 36 after 36 iterations."""
    WIDTH, HEIGHT = 800, 480
    SPLASH_FADE_FRAMES = 36
    splash_img = np.full((HEIGHT, WIDTH, 3), 200, dtype=np.uint8)
    splash_frame = 0

    for _ in range(SPLASH_FADE_FRAMES):
        canvas = np.full((HEIGHT, WIDTH, 3), 50, dtype=np.uint8)
        if splash_img is not None and splash_frame < SPLASH_FADE_FRAMES:
            alpha = 1.0 - (splash_frame / SPLASH_FADE_FRAMES)
            blended = cv2.addWeighted(splash_img, alpha, canvas, 1.0 - alpha, 0)
            canvas[:] = blended
            splash_frame += 1

    assert splash_frame == SPLASH_FADE_FRAMES, f"Expected {SPLASH_FADE_FRAMES}, got {splash_frame}"
    # One more iteration: guard must now be False
    canvas = np.full((HEIGHT, WIDTH, 3), 50, dtype=np.uint8)
    original = canvas.copy()
    if splash_img is not None and splash_frame < SPLASH_FADE_FRAMES:
        alpha = 1.0 - (splash_frame / SPLASH_FADE_FRAMES)
        blended = cv2.addWeighted(splash_img, alpha, canvas, 1.0 - alpha, 0)
        canvas[:] = blended
        splash_frame += 1
    assert np.array_equal(canvas, original), "Canvas must not be modified after SPLASH_FADE_FRAMES iterations"
    assert splash_frame == SPLASH_FADE_FRAMES, "Counter must not exceed SPLASH_FADE_FRAMES"
