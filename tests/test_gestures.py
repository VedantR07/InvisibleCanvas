import numpy as np
import pytest

from invisible_canvas.vision.gestures import (
    OPEN,
    OTHER,
    PINCH,
    POINT,
    GestureParams,
    classify,
    fold_angle,
    palm_centre,
    pinch_point,
)
from synthetic_hand import CURLED, EXTENDED, hand, rotated, to_image

POINTING = dict(index=EXTENDED, middle=CURLED, ring=CURLED, pinky=CURLED, thumb="tucked")


def shape_of(points, **kw):
    return classify(to_image(points), points, **kw).shape


def test_fold_angle_of_straight_and_folded_fingers():
    straight = hand()
    assert fold_angle(straight, (5, 6, 7, 8)) == pytest.approx(0.0, abs=1e-6)
    folded = hand(index=(90, 0, 0))            # folded at the knuckle only, finger itself straight
    assert fold_angle(folded, (5, 6, 7, 8)) == pytest.approx(90.0, abs=1e-6)


@pytest.mark.parametrize("kw,expected", [
    (POINTING, POINT),
    (dict(POINTING, thumb="spread"), POINT),                         # "gun" pose: thumb out still draws
    (dict(POINTING, pinky=(50, 0, 0)), POINT),                      # the user's loose little finger
    (dict(thumb="spread"), OPEN),                                   # all five open
    (dict(index=CURLED, middle=CURLED, ring=CURLED, pinky=CURLED, thumb="tucked"), OTHER),   # fist
    (dict(middle=EXTENDED, ring=CURLED, pinky=CURLED, thumb="tucked"), OTHER),               # two fingers
    (dict(thumb="tucked"), OTHER),                                  # four fingers, thumb across the palm
    (dict(index=(20, 25, 10), thumb="pinch"), PINCH),
])
def test_shapes(kw, expected):
    assert shape_of(hand(**kw)) == expected


def test_a_fist_is_not_a_pinch():
    # The thumb tip lies on the curled index finger, close to its tip: the index fold decides.
    fist = hand(index=CURLED, middle=CURLED, ring=CURLED, pinky=CURLED, thumb="tucked")
    fist[4] = fist[8] + np.array([0.0, 0.01, 0.01])        # thumb tip right next to the curled index tip
    s = classify(None, fist)
    assert s.pinch_ratio < GestureParams().pinch_enter and s.fold_deg["index"] > 110
    assert s.shape == OTHER


def test_knuckle_fold_counts_as_curled():
    # The 2026-10-21 failure of a straightness measure: fingers folded only at the knuckle.
    hook = dict(index=EXTENDED, middle=(95, 0, 0), ring=(100, 0, 0), pinky=(80, 0, 0), thumb="tucked")
    assert shape_of(hand(**hook)) == POINT


def test_a_half_open_hand_is_not_open_and_does_not_draw():
    half = dict(index=(30, 10, 5), middle=(55, 0, 0), ring=(55, 0, 0), pinky=(50, 0, 0), thumb="spread")
    assert shape_of(hand(**half)) == OTHER


@pytest.mark.parametrize("angles", [(0, 0, 0), (40, 0, 0), (0, 55, 0), (0, 0, 70), (120, 30, -40), (-90, -20, 160)])
def test_world_landmarks_make_the_shape_independent_of_the_view(angles):
    for kw, expected in ((POINTING, POINT), (dict(thumb="spread"), OPEN), (dict(index=(20, 25, 10), thumb="pinch"), PINCH)):
        assert shape_of(rotated(hand(**kw), *angles)) == expected


def test_image_fallback_for_a_frontal_view():
    for kw, expected in ((POINTING, POINT), (dict(thumb="spread"), OPEN)):
        pts = hand(**kw)
        # A hand seen side-on in 2-D: the folded fingers are visible as short, bent chains.
        side = rotated(pts, 0, 0, 0)[:, [0, 2]] * 1500 + np.array([900, 500])
        assert classify(to_image(pts)).space == "image"
        assert classify(side).shape in (expected, OTHER)       # 2-D alone is view-dependent: never a wrong mode


def test_pinch_hysteresis():
    params = GestureParams()
    pts = hand(index=(20, 25, 10), thumb="pinch")
    d = np.linalg.norm(pts[9] - pts[0])
    # Move the thumb tip away from the index tip to a ratio between the enter and exit limits.
    between = (params.pinch_enter + params.pinch_exit) / 2
    direction = np.array([1.0, 0.0, 0.0])
    pts[4] = pts[8] + direction * between * d
    assert classify(None, pts, previous=OTHER).shape != PINCH     # not close enough to start
    assert classify(None, pts, previous=PINCH).shape == PINCH     # close enough to stay


def test_measurements_are_reported():
    s = classify(None, hand(**POINTING))
    assert s.space == "world" and set(s.fold_deg) == {"index", "middle", "ring", "pinky"}
    assert s.fold_deg["index"] < 10 and min(s.fold_deg["middle"], s.fold_deg["ring"]) > 100
    d = s.as_dict()
    assert d["shape"] == POINT and "index_fold" in d and "pinch_ratio" in d


@pytest.mark.parametrize("bad", [np.zeros((20, 3)), np.full((21, 3), np.nan), np.zeros((21, 4)), np.zeros((21, 3))])
def test_invalid_landmarks_are_refused(bad):
    with pytest.raises(ValueError):
        classify(None, bad)


def test_palm_centre_and_pinch_point():
    pts = hand()
    assert np.allclose(palm_centre(pts), pts[[0, 5, 9, 13, 17]].mean(axis=0))
    assert np.allclose(pinch_point(pts), (pts[4] + pts[8]) / 2)


def test_keep_drawing_band():
    # D47: looser limits that only keep a stroke going; every strict POINT is inside the band.
    strict = classify(None, hand(**POINTING))
    assert strict.shape == POINT and strict.keeps_point and strict.as_dict()["keeps_point"] is True
    drifted = dict(index=(55, 0, 0), middle=(50, 0, 0), ring=(50, 0, 0), pinky=(35, 0, 0), thumb="tucked")
    s = classify(None, hand(**drifted))
    assert s.shape == OTHER and s.keeps_point                      # not a POINT, but it keeps drawing
    pinching = classify(None, hand(**dict(POINTING, thumb="pinch")))
    assert pinching.shape == PINCH and pinching.keeps_point        # the thumb is ignored by the band
    assert not classify(None, hand(thumb="spread")).keeps_point    # open hand: lifts the pen
    fist = hand(index=CURLED, middle=CURLED, ring=CURLED, pinky=CURLED, thumb="tucked")
    assert not classify(None, fist).keeps_point                    # fist: lifts the pen
    assert not classify(None, hand(**dict(drifted, index=(65, 0, 0)))).keeps_point
    assert not classify(None, hand(**dict(drifted, middle=(40, 0, 0)))).keeps_point
    assert not classify(None, hand(**dict(drifted, pinky=(25, 0, 0)))).keeps_point
