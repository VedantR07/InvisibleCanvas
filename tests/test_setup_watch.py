"""In-session setup watch (brain.md D58): the projected canvas found in camera frames, a move told apart from a
person in front of the projection, and the 2026-10-27 recorded move found (local data, skipped without it)."""

import json

import numpy as np
import pytest
from synthetic_camera import CAMERA, H_REAL, moved, truth, warp

from invisible_canvas.calibration.store import Calibration
from invisible_canvas.calibration.watch import SetupWatch, canvas_corners, canvas_quad, expected_corners, moved_by
from invisible_canvas.canvas.model import Canvas, Stroke
from invisible_canvas.canvas.render import CanvasRenderer
from invisible_canvas.canvas.toolbar import Toolbar
from invisible_canvas.config import REPO_ROOT
from invisible_canvas.interaction.drawing import DrawingController
from invisible_canvas.interaction.engine import HOVER
from invisible_canvas.mapping.mapper import CoordinateMapper

SIZE = (1280, 720)


@pytest.fixture(scope="module")
def screen():
    """What the projector shows: the real renderer, with some writing and the toolbar."""
    canvas = Canvas(SIZE)
    for k in range(4):
        s = Stroke(canvas.new_id(), (25, 25, 25), 8.0)
        for x in range(200 + 150 * k, 300 + 150 * k, 4):
            s.append((x, 300 + 40 * np.sin(x / 20)))
        canvas.add(s)
    tb = Toolbar(SIZE, ai=True)
    return CanvasRenderer(SIZE).render(canvas, DrawingController(canvas, tb), tb, mode=HOVER, cursor=None)


def camera_frame(screen, h=H_REAL, dark=(), seed=0):
    """The camera's view: projected light on a room-lit wall, noise; `dark` boxes (x0, y0, x1, y1) are someone in
    front of the projection."""
    rng = np.random.default_rng(seed)
    img = 55.0 + 0.6 * warp(screen, h) + rng.normal(0.0, 2.0, (CAMERA[1], CAMERA[0]))
    for x0, y0, x1, y1 in dark:
        img[y0:y1, x0:x1] = 25.0
    return np.clip(img, 0, 255).astype(np.uint8)


def expected(h=H_REAL):
    return truth(h, canvas_corners(SIZE))


def test_the_canvas_corners_are_found_where_the_calibration_puts_them(screen):
    # the canvas is found on a half-size copy: ~2 camera px per step; on the recorded sessions the static agreement
    # was a median 3-4 camera px, well inside the 8-px move threshold
    q = canvas_quad(camera_frame(screen))
    assert q is not None and np.abs(q - expected()).max() < 4.5
    mapper = CoordinateMapper(H_REAL, SIZE)
    assert np.allclose(expected_corners(mapper, SIZE), expected())


def test_no_canvas_is_found_in_a_frame_without_a_projection():
    rng = np.random.default_rng(1)
    dark = np.clip(30 + rng.normal(0, 3, (CAMERA[1], CAMERA[0])), 0, 255).astype(np.uint8)
    assert canvas_quad(dark) is None


def test_a_move_needs_three_corners_moving_together():
    e = expected()
    assert moved_by(e, e + 3.0) is None                                          # within the static scatter
    assert np.allclose(moved_by(e, e + [20.0, 5.0]), [20.0, 5.0])
    spread = np.array([[96, 13], [96, -14], [95, -3], [97, -1]], float)         # the 2026-10-27 move (projector px)
    assert moved_by(e, e + spread) is not None                                   # a slight rotation still counts
    hidden = e.copy()
    hidden[3] += [60.0, -40.0]                                                   # one corner cut by someone in front
    assert moved_by(e, hidden) is None
    two = e.copy()
    two[[0, 3]] += [80.0, 0.0]                                                   # only the left side cut away
    assert moved_by(e, two) is None


def test_the_watch_checks_once_a_second_and_needs_two_agreeing_checks(screen):
    still, shifted = camera_frame(screen), camera_frame(screen, moved(H_REAL, -40.0, 6.0), seed=2)  # in view
    watch = SetupWatch(expected())
    assert [watch.update(t, still) for t in (0.0, 0.5, 1.0)] == [None, None, None] and watch.checks == 2
    assert watch.update(2.0, shifted) is None                                    # the first check that saw it
    assert watch.update(2.5, shifted) is None and watch.checks == 3              # not a check yet
    found = watch.update(3.0, shifted)
    assert found is not None and np.abs(found - [-40.0, 6.0]).max() < 3.0
    watch.reset(expected(moved(H_REAL, -40.0, 6.0)))                             # recalibrated: quiet again
    assert [watch.update(t, shifted) for t in (4.0, 5.0, 6.0)] == [None, None, None]


def test_someone_in_front_of_the_projection_is_never_a_move(screen):
    e = expected()
    bl, tl = e[3].astype(int), e[0].astype(int)
    frames = [camera_frame(screen, dark=[(bl[0] - 80, bl[1] - 150, bl[0] + 200, CAMERA[1])], seed=3),   # hides BL
              camera_frame(screen, dark=[(0, 0, int(tl[0]) + 300, CAMERA[1])], seed=4),               # left third
              camera_frame(screen, dark=[(800, 0, 1100, CAMERA[1])], seed=5)]                         # middle, full height
    watch = SetupWatch(e)
    for k in range(12):                                                          # standing there for 12 checks
        assert watch.update(float(k), frames[k % len(frames)] if k < 9 else frames[k % 3]) is None
    assert watch.moved_checks == 0



def test_a_light_on_the_hand_over_busy_writing_never_looks_like_a_move(screen):
    # D68: the D50 light (a white patch over the hand, painted on the projected image) over dense writing, with the
    # dark hand in it, in the middle and near three corners: the canvas corners stay where the calibration puts them
    from invisible_canvas.display.handlight import grown_hull, paint
    busy = screen.copy()
    for y in range(60, 620, 24):                                          # dense writing over the whole canvas
        busy[y:y + 6, 40:1240] = 30
    e, watch = expected(), SetupWatch(expected())
    for k, (x, y) in enumerate([(640, 360), (150, 560), (1130, 140), (180, 150)]):
        lit = busy.copy()
        hand = np.array([[x - 40, y - 80], [x + 40, y - 80], [x + 40, y + 60], [x - 40, y + 60]], dtype=np.float64)
        paint(lit, grown_hull(hand, 25.0))
        box = truth(H_REAL, hand)                                         # the hand itself, in camera px
        dark = [(int(box[:, 0].min()), int(box[:, 1].min()), int(box[:, 0].max()), int(box[:, 1].max()))]
        frame = camera_frame(lit, dark=dark, seed=20 + k)
        q = canvas_quad(frame)
        assert q is not None and np.abs(q - e).max() < 4.5, (x, y)
        assert watch.update(float(k), frame) is None
    assert watch.moved_checks == 0

# -- the recorded 2026-10-27 session (local data) ----------------------------------------------------------------

DATA = REPO_ROOT / "data"


def recorded(session: str, calibration: str):
    folder, cal = DATA / "diagnostics" / session, DATA / "calibration" / "history" / calibration
    if not folder.is_dir() or not cal.is_file():
        pytest.skip("needs the recorded sessions in data/ (local data)")
    import cv2
    mapper = CoordinateMapper.from_calibration(Calibration.from_dict(json.loads(cal.read_text(encoding="utf-8"))))
    frames = [(float(p.name[1:7]), cv2.imread(str(p))) for p in sorted(folder.glob("t[0-9]*.jpg"))]
    return SetupWatch(expected_corners(mapper, SIZE)), frames


def test_the_recorded_move_is_found_two_seconds_after_it():
    # 00:25 session: the projection moved between the frames at 13.2 and 19.3 s (+85 camera px)
    watch, frames = recorded("draw-20261027-002545", "20261027-002601-290.json")
    reports = [(t, d) for t, img in frames if (d := watch.update(t, img)) is not None]
    t, d = reports[0]
    assert 13.2 < t <= 20.3 and abs(d[0] - 88.0) < 5.0 and abs(d[1]) < 5.0


def test_a_recorded_session_without_a_move_gives_no_report():
    # 18:46 session (AI on, people at the wall): no move
    watch, frames = recorded("draw-20261026-184627", "20261026-184240-035.json")
    assert all(watch.update(t, img) is None for t, img in frames) and watch.checks > 250
