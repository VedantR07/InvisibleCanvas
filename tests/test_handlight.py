"""Light on the hand (D50; D70: fitted to the hand's own shape). Pure tests, no camera or projector."""

import cv2
import numpy as np
import pytest

from invisible_canvas.display.handlight import HandLight, LightParams, contains, finger_radius, grown_hull, paint

P = LightParams()


def hand_at(x, y):
    """21 points shaped roughly like a hand pointing up, ~60 x 120 projector px."""
    rng = np.random.default_rng(1)
    return np.column_stack([x + rng.uniform(-30, 30, 21), y + rng.uniform(-60, 60, 21)])


def pointing_hand(x, y):
    """MediaPipe's 21 landmarks of a hand pointing up, the index fingertip at (x, y), in projector px: the other
    fingers curled, the thumb out to the side."""
    return np.array([(x + 10, y + 140),                                                          # 0 wrist
                     (x - 25, y + 115), (x - 40, y + 95), (x - 45, y + 75), (x - 42, y + 60),   # thumb 1-4
                     (x, y + 70), (x, y + 45), (x, y + 20), (x, y),                             # index 5-8
                     (x + 20, y + 72), (x + 22, y + 55), (x + 18, y + 65), (x + 15, y + 78),   # middle 9-12
                     (x + 38, y + 78), (x + 40, y + 63), (x + 35, y + 72), (x + 31, y + 84),   # ring 13-16
                     (x + 52, y + 88), (x + 54, y + 76), (x + 50, y + 83), (x + 46, y + 92)],  # little 17-20
                    dtype=np.float64)


def lit_area(shape, size=(1280, 720)):
    mask = np.zeros(size[::-1], np.uint8)
    paint(mask, shape, 1)
    return int(mask.sum())


def test_the_light_fits_the_hand_and_covers_every_landmark():
    # D70: the hand's own shape (finger capsules and the palm) + 8 px, not D50's convex outline + 25 px
    hand = pointing_hand(640, 300)
    shape = HandLight().update(0.0, hand)
    r = finger_radius(hand, P) + P.margin_px
    assert all(contains(shape, q) for q in hand)                              # every landmark lit
    assert contains(shape, (640, 300 - r + 2)) and not contains(shape, (640, 300 - r - 4))    # above the fingertip
    gap = (610, 320)                                     # between the pointing finger and the thumb: not the hand
    old = grown_hull(hand, 25.0)
    assert contains(old, gap) and not contains(shape, gap)                    # D50 lit it, D70 does not
    assert lit_area(shape) < 0.75 * lit_area(old)                              # (62 % here, still)


def test_the_light_moves_ahead_with_the_hand_and_covers_back_only_part_of_the_way():
    light = HandLight()
    for k in range(7):                                                        # 500 px/s to the right
        shape = light.update(k * 0.02, pointing_hand(400 + 10 * k, 300))
    tip, ahead = np.array([460.0, 300.0]), min(500 * P.lookahead_s, P.max_shift_px)
    r = finger_radius(pointing_hand(0, 0), P) + P.margin_px
    assert contains(shape, tip + (ahead, 0)) and contains(shape, tip + (P.sweep_from * ahead, 0))   # where it goes
    assert not contains(shape, tip - (P.sweep_from * ahead - r - 4, 0) + (0, -r + 2))   # not the whole way back
    assert not contains(shape, tip + (ahead + r + 4, 0))                      # nor beyond
    still = HandLight()
    for k in range(7):                                                        # 40 px/s: as good as still
        shape = still.update(k * 0.02, pointing_hand(400 + 0.8 * k, 300))
    assert contains(shape, (404.8, 300)) and not contains(shape, (404.8 + r + 6, 300 - r + 2))
    fast = HandLight()
    for k in range(7):                                                        # 5000 px/s: the cap holds
        shape = fast.update(k * 0.02, pointing_hand(100 + 100 * k, 300))
    assert not contains(shape, (700 + P.max_shift_px + r + 4, 300))


def test_the_light_is_held_briefly_after_a_loss_then_removed():
    light = HandLight()
    hand = pointing_hand(640, 300)
    light.update(0.0, hand)
    held = light.update(0.3, None)
    r = finger_radius(hand, P) + P.margin_px
    assert held is not None and contains(held, (640, 300 - r - P.lost_extra_px + 2))      # a little wider
    assert light.update(P.hold_s + 0.05, None) is None
    assert light.update(2.0, None) is None


def test_bad_points_count_as_no_hand_and_paint_fills_white():
    light = HandLight()
    assert light.update(0.0, np.full((21, 2), np.nan)) is None
    img = np.zeros((720, 1280, 3), np.uint8)
    paint(img, grown_hull(hand_at(640, 360), 10))                             # one polygon (D50's form) ...
    assert img[360, 640].tolist() == [255, 255, 255] and img[10, 10].tolist() == [0, 0, 0]
    img[:] = 0
    paint(img, HandLight().update(0.0, pointing_hand(640, 300)))              # ... or the hand's shape (D70)
    assert img[300, 640].tolist() == [255, 255, 255] and img[320, 610].tolist() == [0, 0, 0]
    paint(img, None)                                                          # no light: nothing changes


# -- D68: the light over everything drawn since D50, the board itself untouched ------------------------------------

def test_the_light_covers_whatever_lies_under_the_hand_and_the_board_is_unchanged():
    # Smart Lines (notes, review bar), the AI panel and a notice are all under the light; the stored strokes, the
    # Smart Lines and the page are unchanged, and the same frame without a light shows them again
    from invisible_canvas.canvas.model import Canvas
    from invisible_canvas.canvas.render import CanvasRenderer
    from invisible_canvas.canvas.toolbar import Toolbar
    from invisible_canvas.interaction.drawing import DrawingController
    from invisible_canvas.interaction.engine import HOVER, STROKE_END, STROKE_POINT, STROKE_START, Event
    size = (1280, 720)
    ctl = DrawingController(Canvas(size), Toolbar(size, ai=True))
    ctl.recognition = True
    for y in (200, 230, 260):                                            # freehand ink
        ctl.handle([Event(STROKE_START, 0.0, (100, y)), Event(STROKE_POINT, 0.0, (1200, y)), Event(STROKE_END, 0.0)])
    ctl.press("lines")
    ctl.handle([Event(STROKE_START, 0.0, (300, 450)), Event(STROKE_POINT, 0.0, (330, 520)), Event(STROKE_END, 0.0)])
    ctl.press("lines:complete")
    (n, _, _), = ctl.take_line_jobs()
    ctl.line_result(n, {"ok": True, "written": "CAT", "text": "CAT", "error": "", "latency_s": 1.0})   # review bar
    ctl.press("ai")
    ctl.show_notice("A notice on the wall.")
    before = ([(s.id, list(s.points), s.color, s.width) for s in ctl.canvas.strokes.values()],
              ctl.sheet().version, [(s.id, list(s.points)) for s in ctl.sheet().lines[0].strokes])
    r = CanvasRenderer(size)
    plain = r.render(ctl.canvas, ctl, ctl.toolbar, mode=HOVER, cursor=None)
    hand = np.array([[300, 120], [900, 120], [900, 520], [300, 520]], dtype=np.float64)   # over all of them
    poly = grown_hull(hand, P.margin_px)
    lit = r.render(ctl.canvas, ctl, ctl.toolbar, mode=HOVER, cursor=(600, 300), light=poly)
    mask = np.zeros(size[::-1], np.uint8)
    cv2.fillConvexPoly(mask, poly, 1)
    inner = cv2.erode(mask, np.ones((5, 5), np.uint8)).astype(bool)     # away from the anti-aliased edge
    assert (plain[inner] < 200).any()                                  # ink, notes, bar, panel, notice there ...
    assert (lit[inner] == 255).all()                                   # ... all white under the light
    outside = ~cv2.dilate(mask, np.ones((5, 5), np.uint8)).astype(bool)
    assert (lit[outside] == plain[outside]).all()                      # the rest of the board unchanged
    after = ([(s.id, list(s.points), s.color, s.width) for s in ctl.canvas.strokes.values()],
             ctl.sheet().version, [(s.id, list(s.points)) for s in ctl.sheet().lines[0].strokes])
    assert after == before                                             # nothing stored was touched
    again = r.render(ctl.canvas, ctl, ctl.toolbar, mode=HOVER, cursor=None)
    assert (again == plain).all()                                      # the hand gone: all of it back
