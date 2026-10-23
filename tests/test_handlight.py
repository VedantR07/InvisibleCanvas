import cv2
import numpy as np
import pytest

from invisible_canvas.display.handlight import HandLight, LightParams, grown_hull, paint

P = LightParams()


def hand_at(x, y):
    """21 points shaped roughly like a hand pointing up, ~60 x 120 projector px."""
    rng = np.random.default_rng(1)
    return np.column_stack([x + rng.uniform(-30, 30, 21), y + rng.uniform(-60, 60, 21)])


def inside(poly, pt):
    return cv2.pointPolygonTest(poly.astype(np.float32), (float(pt[0]), float(pt[1])), True)


def test_the_light_covers_every_landmark_with_the_margin():
    light = HandLight()
    pts = hand_at(640, 360)
    poly = light.update(0.0, pts)
    assert all(inside(poly, p) >= P.margin_px - 1.5 for p in pts)
    assert inside(poly, (640, 360 - 60 - P.margin_px - 5)) < 0          # not much beyond the margin


def test_the_light_looks_ahead_along_the_motion_and_is_capped():
    light = HandLight()
    for k in range(7):                                                  # 500 px/s to the right
        poly = light.update(k * 0.02, hand_at(400 + 10 * k, 360))
    lead = 400 + 10 * 6 + 30
    assert inside(poly, (lead + 0.9 * 500 * P.lookahead_s, 360)) > 0   # ~0.26 s ahead of the leading edge
    assert inside(poly, (400 + 60 - 30 - P.margin_px - 10, 360)) < 0   # behind: only the margin
    fast = HandLight()
    for k in range(7):                                                  # 5000 px/s: the cap holds
        poly = fast.update(k * 0.02, hand_at(100 + 100 * k, 360))
    assert inside(poly, (100 + 600 + 30 + P.max_shift_px + P.margin_px + 5, 360)) < 0


def test_the_light_is_held_after_a_loss_then_removed():
    light = HandLight()
    pts = hand_at(640, 360)
    light.update(0.0, pts)
    held = light.update(0.5, None)
    right = pts[np.argmax(pts[:, 0])]
    assert held is not None and inside(held, (right[0] + P.lost_margin_px - 3, right[1])) > 0   # wider margin
    assert light.update(0.5 + P.hold_s + 0.01, None) is None
    assert light.update(2.0, None) is None


def test_bad_points_count_as_no_hand_and_paint_fills_white():
    light = HandLight()
    assert light.update(0.0, np.full((21, 2), np.nan)) is None
    img = np.zeros((720, 1280, 3), np.uint8)
    paint(img, grown_hull(hand_at(640, 360), 10))
    assert img[360, 640].tolist() == [255, 255, 255] and img[10, 10].tolist() == [0, 0, 0]
    paint(img, None)                                                    # no light: nothing changes
