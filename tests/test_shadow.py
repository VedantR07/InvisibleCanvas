"""Fingertip shadow measurement (vision/shadow.py, D35) on synthetic frames with a known shift.

Scene model from the 2026-10-10 frames at canvas grey 128: unlit surround and shadow ~21 (black
level), lit canvas ~140, lit skin 63-120.
"""

import numpy as np
import pytest

from invisible_canvas.vision.shadow import ALL_BONES, PALM, finger_width, find_shadow, outline_mask

SHAPE = (1080, 1920)
BLACK, CANVAS_LUMA, SKIN = 21.0, 140.0, 90.0


def hand(wrist=(900.0, 760.0), scale=1.0):
    """21 landmarks of an open right hand pointing up (camera px), wrist -> middle tip ~215 px."""
    w = np.array(wrist)
    pts = np.zeros((21, 2))
    pts[0] = w
    pts[1:5] = w + scale * np.array([(-40, -25), (-70, -55), (-92, -80), (-110, -100)])          # thumb
    for k, (dx, ang) in enumerate([(-30, -12), (-5, -3), (20, 6), (42, 15)]):                  # index..pinky
        base = w + scale * np.array([dx, -95.0])
        d = np.array([np.sin(np.radians(ang)), -np.cos(np.radians(ang))])
        lengths = (0, 45, 30, 25) if k != 3 else (0, 34, 24, 20)
        acc = 0.0
        for j, ln in enumerate(lengths):
            acc += ln
            pts[5 + 4 * k + j] = base + scale * d * acc
    return pts


def scene(landmarks, shift, canvas_box=(300, 100, 1800, 980), shadow=True):
    grey = np.full(SHAPE, BLACK, np.float32)
    x0, y0, x1, y1 = canvas_box
    grey[y0:y1, x0:x1] = CANVAS_LUMA
    canvas = np.zeros(SHAPE, bool)
    canvas[y0:y1, x0:x1] = True
    width = finger_width(landmarks)
    import cv2
    if shadow:   # the hand's outline shifted, at black level, only where the projector lights the canvas
        sh = outline_mask(SHAPE, landmarks + shift, ALL_BONES, width)
        cv2.fillPoly(sh, [np.round((landmarks + shift)[list(PALM)]).astype(np.int32)], 1)
        grey[(sh > 0) & canvas] = BLACK
    skin = outline_mask(SHAPE, landmarks, ALL_BONES, width)
    cv2.fillPoly(skin, [np.round(landmarks[list(PALM)]).astype(np.int32)], 1)
    grey[skin > 0] = SKIN
    rng = np.random.default_rng(1)
    grey = np.clip(grey + rng.normal(0, 3, SHAPE), 0, 255).astype(np.uint8)
    return grey, canvas


@pytest.mark.parametrize("shift", [(-14.0, -45.0), (25.0, -30.0), (0.0, -60.0), (-40.0, 10.0)])
def test_recovers_a_known_shadow_shift(shift):
    lm = hand()
    grey, canvas = scene(lm, np.array(shift))
    s = find_shadow(grey, lm, canvas, BLACK, CANVAS_LUMA)
    assert s is not None
    assert s.offset == pytest.approx(shift, abs=1.5)
    assert s.tip == pytest.approx(tuple(lm[8] + shift), abs=1.5)
    assert s.score > 0.7


def test_no_visible_shadow_is_not_invented():
    """Finger on the surface: the shadow is hidden under the hand."""
    lm = hand()
    grey, canvas = scene(lm, np.array([0.0, 0.0]))
    assert find_shadow(grey, lm, canvas, BLACK, CANVAS_LUMA) is None


def test_darkness_outside_the_canvas_is_not_a_shadow():
    """A hand at the left canvas edge, the unlit surround next to it, no shadow drawn."""
    lm = hand(wrist=(380.0, 600.0))
    grey, canvas = scene(lm, np.array([-30.0, 0.0]), shadow=False)
    assert find_shadow(grey, lm, canvas, BLACK, CANVAS_LUMA) is None


def test_a_broad_dark_area_does_not_match_the_finger_outline():
    """E.g. the body's shadow next to the hand: dark everywhere, so the lit ring test fails."""
    lm = hand()
    grey, canvas = scene(lm, np.array([0.0, 0.0]), shadow=False)
    grey[150:700, 950:1500] = int(BLACK)                       # a large dark patch beside the hand
    assert find_shadow(grey, lm, canvas, BLACK, CANVAS_LUMA) is None


# -- shadow centre at the target (D36) ----------------------------------------------------------------

import cv2  # noqa: E402

from invisible_canvas.vision.shadow import shadow_tip_near  # noqa: E402


def finger_scene(tip, direction, shadow_end, *, w=18, black=BLACK, lit=CANVAS_LUMA, skin=SKIN, shadow=True,
                 canvas_box=(300, 100, 1800, 980)):
    """A straight finger (skin) ending at `tip`, its shadow strip ending at `shadow_end` (both along
    `direction`, w px wide, 160 px long), on a lit canvas; unlit surround outside."""
    u = np.asarray(direction, float) / np.linalg.norm(direction)
    grey = np.full(SHAPE, black, np.float32)
    x0, y0, x1, y1 = canvas_box
    grey[y0:y1, x0:x1] = lit
    canvas = np.zeros(SHAPE, bool)
    canvas[y0:y1, x0:x1] = True
    def strip(end, value):
        m = np.zeros(SHAPE, np.uint8)
        e = np.asarray(end, float) - u * w / 2           # the round end: a line w px thick ends w/2 beyond
        cv2.line(m, tuple(np.round(e - 160 * u).astype(int)), tuple(np.round(e).astype(int)), 1, w)
        cv2.circle(m, tuple(np.round(e).astype(int)), w // 2, 1, -1)
        return m > 0
    if shadow:
        grey[strip(shadow_end, 0) & canvas] = black
    finger = strip(tip, 0)
    grey[finger] = skin
    hand = cv2.dilate(finger.astype(np.uint8), np.ones((5, 5), np.uint8))
    grey = np.clip(grey + np.random.default_rng(2).normal(0, 3, SHAPE), 0, 255).astype(np.uint8)
    return grey, canvas, hand


@pytest.mark.parametrize("lit_room", [False, True])
def test_shadow_centre_is_found_half_a_width_behind_the_shadow_end(lit_room):
    black, lit = (141.0, 192.0) if lit_room else (BLACK, CANVAS_LUMA)     # measured 2026-10-10 (ceiling light / dark)
    tip, u = np.array([900.0, 500.0]), np.array([-1.0, -0.4])
    end = tip + np.array([10.0, -30.0])                     # shadow beside and above the fingertip
    grey, canvas, hand = finger_scene(tip, u, end, black=black, lit=lit)
    r = shadow_tip_near(grey, end, u, 18, black, lit, hand, canvas)
    assert r.found, r.reason
    un = u / np.linalg.norm(u)
    assert r.end == pytest.approx(tuple(end), abs=1.5)
    assert r.centre == pytest.approx(tuple(end - 9 * un), abs=1.5) and r.width == pytest.approx(18, abs=2)


def test_shadow_centre_is_measured_even_when_the_operator_misses_the_target_a_little():
    tip, u = np.array([900.0, 500.0]), np.array([0.0, -1.0])
    end = tip + np.array([-35.0, -10.0])
    grey, canvas, hand = finger_scene(tip, u, end)
    r = shadow_tip_near(grey, end + np.array([12.0, 15.0]), u, 18, BLACK, CANVAS_LUMA, hand, canvas)
    assert r.found and r.end == pytest.approx(tuple(end), abs=1.5)


def test_a_shadow_hidden_under_the_finger_is_not_established():
    """Small parallax along the finger: the shadow end is behind the fingertip as the camera sees it."""
    tip, u = np.array([900.0, 500.0]), np.array([1.0, 0.0])
    end = tip - 6 * u
    grey, canvas, hand = finger_scene(tip, u, end)
    r = shadow_tip_near(grey, end, u, 18, BLACK, CANVAS_LUMA, hand, canvas)
    assert not r.found


def test_no_shadow_and_darkness_outside_the_canvas_are_not_shadows():
    tip, u = np.array([340.0, 500.0]), np.array([-1.0, 0.0])        # pointing into the unlit surround
    grey, canvas, hand = finger_scene(tip, u, tip + np.array([0.0, -30.0]), shadow=False)
    r = shadow_tip_near(grey, tip + np.array([0.0, -30.0]), u, 18, BLACK, CANVAS_LUMA, hand, canvas)
    assert not r.found


def test_a_shadow_end_far_from_the_target_is_not_taken():
    tip, u = np.array([900.0, 500.0]), np.array([0.0, -1.0])
    end = tip + np.array([40.0, -30.0])
    grey, canvas, hand = finger_scene(tip, u, end)
    r = shadow_tip_near(grey, end + np.array([0.0, -120.0]), u, 18, BLACK, CANVAS_LUMA, hand, canvas)
    assert not r.found


def test_a_steady_shadow_centre_needs_enough_consistent_frames():
    from invisible_canvas.vision.shadow import ShadowTip, steady_shadow_centre
    ok = lambda x, y: ShadowTip(True, "ok", (x, y))                     # noqa: E731
    miss = ShadowTip(False, "shadow end hidden (by the hand, or outside the canvas)")
    c = steady_shadow_centre([ok(100, 50), ok(101, 51), ok(99.5, 50), miss, ok(100.5, 49)])
    assert c.established and c.centre == pytest.approx((100.25, 50.0)) and c.found == 4 and c.frames == 5
    assert not steady_shadow_centre([ok(100, 50), ok(101, 50), miss, miss]).established     # 2 < 3
    jumpy = steady_shadow_centre([ok(100, 50), ok(120, 50), ok(100, 70)])
    assert not jumpy.established and "not steady" in jumpy.reason
