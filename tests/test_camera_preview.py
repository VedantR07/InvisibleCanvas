import numpy as np

from invisible_canvas.tools.camera_check import BRIGHTEN, preview_image


def _frame(w, h, value=16):
    return np.full((h, w, 3), value, dtype=np.uint8)


def test_1080p_frame_on_1080p_screen_is_shown_1_to_1():
    frame = np.random.default_rng(0).integers(0, 256, (1080, 1920, 3), dtype=np.uint8)
    image, scale = preview_image(frame, (1920, 1080), brighten=False)
    assert scale == 1.0
    assert np.array_equal(image, frame)


def test_preview_never_modifies_the_captured_frame():
    frame = _frame(1920, 1080)
    image, _ = preview_image(frame, (1920, 1080), brighten=True)
    assert frame.max() == 16          # untouched
    assert image is not frame


def test_brighten_lifts_dark_levels_and_keeps_black_and_white():
    assert BRIGHTEN[0] == 0 and BRIGHTEN[255] == 255
    assert BRIGHTEN[16] == 84         # the unlit wall at exposure -5
    assert np.all(np.diff(BRIGHTEN.astype(int)) >= 0)


def test_smaller_frame_is_enlarged_to_fill_the_screen():
    image, scale = preview_image(_frame(1280, 720), (1920, 1080), brighten=False)
    assert scale == 1.5
    assert image.shape == (1080, 1920, 3)
    assert image.min() == 16          # filled, no bars


def test_other_aspect_ratio_is_letterboxed_not_stretched():
    image, scale = preview_image(_frame(640, 480, 200), (1920, 1080), brighten=False)
    assert scale == 1080 / 480
    assert image.shape == (1080, 1920, 3)
    assert image[:, :240].max() == 0 and image[:, -240:].max() == 0   # black side bars
    assert image[:, 240:1680].min() == 200
