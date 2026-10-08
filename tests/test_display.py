import cv2
import numpy as np
import pytest

from invisible_canvas.display import patterns
from invisible_canvas.display.monitors import Display
from invisible_canvas.display.operator import OperatorWindow


def screen(w, h):
    return Display(r"\\.\DISPLAY1", "Panel", "TMA2076", "internal", True, 0, 0, w, h, 60.0, 32, 150)


def test_operator_shows_1080p_camera_1_to_1_on_the_laptop_panel():
    op = OperatorWindow((1920, 1080), screen(2560, 1600))
    assert op.scale == 1.0
    assert op.to_camera(100, 200) == (100.0, 200.0)


def test_operator_scaled_view_round_trips_pixel_centres():
    op = OperatorWindow((1920, 1080), screen(1280, 800))
    assert op.scale < 1.0
    for cx, cy in [(0.0, 0.0), (959.5, 539.5), (1919.0, 1079.0)]:
        vx, vy = op.to_view(cx, cy)
        bx, by = op.to_camera(vx, vy)
        assert abs(bx - cx) <= 0.5 / op.scale + 1e-9
        assert abs(by - cy) <= 0.5 / op.scale + 1e-9


def test_loupe_click_maps_to_sub_pixel_camera_coordinates():
    op = OperatorWindow((1920, 1080), screen(2560, 1600))
    raw = np.zeros((1080, 1920, 3), np.uint8)
    center = (812.25, 433.75)
    op._loupe(raw, center)  # sets the loupe origin as when drawn
    received = []
    op.on_mouse = lambda kind, x, y: received.append((kind, x, y))
    lx0, ly0, _ = op._loupe_rect
    ox, oy = op._loupe_origin
    z = op.LOUPE_ZOOM
    # The loupe pixel whose centre shows camera point `center`.
    wx = lx0 + (center[0] - ox + 0.5) * z - 0.5
    wy = ly0 + (center[1] - oy + 0.5) * z - 0.5
    op._mouse(cv2.EVENT_LBUTTONDOWN, int(round(wx)), int(round(wy)), 0, None)
    kind, x, y = received[0]
    assert kind == "click"
    assert x == pytest.approx(center[0], abs=0.5 / z + 1e-9)
    assert y == pytest.approx(center[1], abs=0.5 / z + 1e-9)


def test_mouse_moves_inside_the_loupe_are_ignored():
    op = OperatorWindow((1920, 1080), screen(2560, 1600))
    op._loupe(np.zeros((1080, 1920, 3), np.uint8), (100.0, 100.0))
    received = []
    op.on_mouse = lambda *e: received.append(e)
    lx0, ly0, size = op._loupe_rect
    op._mouse(cv2.EVENT_MOUSEMOVE, lx0 + size // 2, ly0 + size // 2, 0, None)
    assert received == []


@pytest.mark.parametrize("active", [True, False])
def test_target_is_symmetric_about_its_pixel(active):
    img = patterns.blank((400, 300))
    patterns.draw_target(img, (200, 150), active=active)
    ys, xs = np.nonzero(img[:, :, 0])
    assert xs.mean() == pytest.approx(200.0, abs=1e-9)
    assert ys.mean() == pytest.approx(150.0, abs=1e-9)
    assert img[150, 200, 0] > 0


def test_alignment_pattern_has_a_full_one_pixel_border():
    img = patterns.alignment_pattern((1280, 720))
    assert img.shape == (720, 1280, 3)
    for edge in (img[0], img[-1], img[:, 0], img[:, -1]):
        assert np.all(edge == 255)
    assert np.any(img[1, 100:1180] != 255)  # the border is exactly one pixel wide


def test_alignment_pattern_stripe_patches_are_pure():
    img = patterns.alignment_pattern((1280, 720))[:, :, 0]
    cx, cy = 639, 359
    for x0, y0 in ((24, 24), (1280 - 72, 720 - 128), (cx - 160, cy - 52), (cx + 112, cy - 52)):
        vertical = img[y0:y0 + 48, x0:x0 + 48]
        horizontal = img[y0 + 56:y0 + 104, x0:x0 + 48]
        assert np.all(vertical[:, ::2] == 255) and np.all(vertical[:, 1::2] == 0)
        assert np.all(horizontal[::2] == 255) and np.all(horizontal[1::2] == 0)


def test_target_screen_highlights_only_the_active_target():
    targets = np.array([[100.0, 100], [1100, 100], [1100, 600], [100, 600]])
    img = patterns.target_screen((1280, 720), targets, 2, show_others=True)
    assert img[600, 1100].tolist() == list(patterns.WHITE)
    assert img[100, 100].tolist() == list(patterns.DIM)
