import pytest

from invisible_canvas.interaction.engine import (
    DRAW,
    ERASE,
    ERASE_AT,
    ERASE_END,
    HOVER,
    IDLE,
    PINCH_DOWN,
    PINCH_MOVE,
    PINCH_UP,
    SELECT,
    STROKE_END,
    STROKE_POINT,
    STROKE_START,
    EngineParams,
    HandInput,
    InteractionEngine,
)
from invisible_canvas.vision.gestures import OPEN, OTHER, PINCH, POINT

DT = 1 / 54


def hand(shape, x=100.0, y=200.0):
    return HandInput(shape, pointer=(x, y), pinch=(x + 5, y + 5), palm=(x + 40, y + 30), eraser_radius=50.0)


def run(engine, shapes, start=0.0):
    """Feed a sequence of shapes (None = no hand), moving 10 px per frame; return all steps."""
    steps = []
    for i, s in enumerate(shapes):
        t = start + i * DT
        steps.append(engine.update(t, None if s is None else hand(s, 100.0 + 10 * i)))
    return steps


def kinds(steps):
    return [e.kind for s in steps for e in s.events]


def test_a_hand_appearing_hovers_at_once_and_shows_the_cursor():
    e = InteractionEngine()
    s = e.update(0.0, hand(OTHER))
    assert s.mode == HOVER and s.cursor == (100.0, 200.0) and s.events == ()


def test_drawing_starts_after_the_enter_frames_and_keeps_the_first_point():
    e = InteractionEngine()
    steps = run(e, [OTHER, POINT, POINT, POINT, POINT, POINT])
    assert [s.mode for s in steps] == [HOVER, HOVER, HOVER, HOVER, DRAW, DRAW]
    events = [ev for s in steps for ev in s.events]
    assert events[0].kind == STROKE_START and events[0].point == (110.0, 200.0)   # the FIRST point frame
    assert [ev.kind for ev in events] == [STROKE_START, STROKE_POINT, STROKE_POINT, STROKE_POINT, STROKE_POINT]
    assert [ev.point[0] for ev in events] == [110.0, 120.0, 130.0, 140.0, 150.0]   # nothing lost


@pytest.mark.parametrize("glitch", [[POINT], [POINT, POINT], [POINT, POINT, POINT]])
def test_short_point_glitches_never_draw(glitch):
    e = InteractionEngine()
    steps = run(e, [OTHER] + glitch + [OTHER] * 5)
    assert DRAW not in [s.mode for s in steps]
    assert kinds(steps) == []


def test_a_misread_frame_inside_a_stroke_neither_ends_it_nor_adds_its_point():
    e = InteractionEngine()
    steps = run(e, [POINT] * 5 + [OPEN] + [POINT] * 3)
    assert all(s.mode == DRAW for s in steps[3:])
    assert kinds(steps).count(STROKE_START) == 1 and STROKE_END not in kinds(steps)
    drawn = [ev.point[0] for s in steps for ev in s.events]
    assert 150.0 not in drawn                     # the misread frame (index 5) adds nothing


def test_stroke_end_drops_the_changing_frames():
    e = InteractionEngine()
    steps = run(e, [POINT] * 6 + [OTHER] * 3 + [OTHER])
    k = kinds(steps)
    assert k.count(STROKE_END) == 1
    end_step = next(i for i, s in enumerate(steps) if any(ev.kind == STROKE_END for ev in s.events))
    assert end_step == 8                          # after 3 frames of the new shape
    points = [ev.point[0] for s in steps for ev in s.events if ev.kind in (STROKE_START, STROKE_POINT)]
    assert max(points) == 150.0                   # the last POINT frame; no point from the changing frames
    assert steps[-1].mode == HOVER


def test_switching_from_draw_to_erase_ends_the_stroke_first():
    e = InteractionEngine()
    steps = run(e, [POINT] * 5 + [OPEN] * 5)
    k = kinds(steps)
    assert k.index(STROKE_END) < k.index(ERASE_AT)
    assert steps[-1].mode == ERASE
    erase_points = [ev.point for s in steps for ev in s.events if ev.kind == ERASE_AT]
    assert erase_points[0] == (140.0 + 50.0, 230.0)       # the first OPEN frame's palm (index 5)
    assert all(ev.radius == 50.0 for s in steps for ev in s.events if ev.kind == ERASE_AT)


def test_erase_and_pinch_have_end_events():
    e = InteractionEngine()
    k = kinds(run(e, [OPEN] * 5 + [OTHER] * 3 + [PINCH] * 5 + [OTHER] * 3))
    assert k.count(ERASE_END) == 1 and k.count(PINCH_DOWN) == 1 and k.count(PINCH_UP) == 1
    assert k.index(ERASE_END) < k.index(PINCH_DOWN) < k.index(PINCH_UP)
    assert PINCH_MOVE in k


def test_pinch_release_is_where_the_pinch_was():
    e = InteractionEngine()
    steps = run(e, [PINCH] * 6 + [OTHER] * 3)
    up = [ev for s in steps for ev in s.events if ev.kind == PINCH_UP][0]
    assert up.point == (155.0, 205.0)              # the last PINCH frame (index 5), not an opening frame


def test_a_short_dropout_keeps_the_stroke():
    e = InteractionEngine()
    steps = run(e, [POINT] * 6 + [None] * 5 + [POINT] * 3)       # 5 frames = 93 ms < 150 ms
    assert STROKE_END not in kinds(steps)
    assert all(s.mode == DRAW for s in steps[4:])
    assert steps[7].cursor is not None                           # held at the last position


def test_a_long_dropout_ends_the_stroke_and_hides_the_cursor():
    e = InteractionEngine()
    steps = run(e, [POINT] * 6 + [None] * 12)                    # 222 ms > 150 ms
    assert kinds(steps).count(STROKE_END) == 1
    assert steps[-1].mode == IDLE and steps[-1].cursor is None


def test_returning_after_a_long_dropout_needs_the_enter_frames_again():
    e = InteractionEngine()
    steps = run(e, [POINT] * 6 + [None] * 12 + [POINT] * 2)
    assert steps[-1].mode == HOVER and kinds(steps).count(STROKE_START) == 1


def test_cursor_point_per_mode():
    e = InteractionEngine()
    assert run(e, [POINT] * 5)[-1].cursor == (140.0, 200.0)               # fingertip
    e = InteractionEngine()
    assert run(e, [OPEN] * 5)[-1].cursor == (180.0, 230.0)                # palm
    e = InteractionEngine()
    assert run(e, [PINCH] * 5)[-1].cursor == (145.0, 205.0)               # pinch point


def test_statistics_and_pending():
    e = InteractionEngine()
    steps = run(e, [POINT] * 5 + [OTHER])
    assert steps[-1].pending == HOVER and steps[-1].mode == DRAW
    assert e.entries[DRAW] == 1 and e.mode_frames[HOVER] == 3 and e.mode_frames[DRAW] == 3   # draw from frame 3


def test_parameters_are_validated():
    with pytest.raises(ValueError):
        InteractionEngine(EngineParams(enter_frames=0))
