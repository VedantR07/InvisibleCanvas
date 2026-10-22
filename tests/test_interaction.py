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
    GESTURE_MODES,
    EngineParams,
    HandInput,
    InteractionEngine,
)
from invisible_canvas.vision.gestures import OPEN, OTHER, PINCH, POINT

DT = 1 / 54


def make():
    """The engine mechanics with the D44 gesture modes, 4 enter frames and no pen-lift delay (D46, D47 and D49
    defaults are tested below)."""
    return InteractionEngine(EngineParams(enter_frames=4, lift_s=0.0), mode_of=GESTURE_MODES)


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
    e = make()
    s = e.update(0.0, hand(OTHER))
    assert s.mode == HOVER and s.cursor == (100.0, 200.0) and s.events == ()


def test_drawing_starts_after_the_enter_frames_and_keeps_the_first_point():
    e = make()
    steps = run(e, [OTHER, POINT, POINT, POINT, POINT, POINT])
    assert [s.mode for s in steps] == [HOVER, HOVER, HOVER, HOVER, DRAW, DRAW]
    events = [ev for s in steps for ev in s.events]
    assert events[0].kind == STROKE_START and events[0].point == (110.0, 200.0)   # the FIRST point frame
    assert [ev.kind for ev in events] == [STROKE_START, STROKE_POINT, STROKE_POINT, STROKE_POINT, STROKE_POINT]
    assert [ev.point[0] for ev in events] == [110.0, 120.0, 130.0, 140.0, 150.0]   # nothing lost


@pytest.mark.parametrize("glitch", [[POINT], [POINT, POINT], [POINT, POINT, POINT]])
def test_short_point_glitches_never_draw(glitch):
    e = make()
    steps = run(e, [OTHER] + glitch + [OTHER] * 5)
    assert DRAW not in [s.mode for s in steps]
    assert kinds(steps) == []


def test_a_misread_frame_inside_a_stroke_neither_ends_it_nor_adds_its_point():
    e = make()
    steps = run(e, [POINT] * 5 + [OPEN] + [POINT] * 3)
    assert all(s.mode == DRAW for s in steps[3:])
    assert kinds(steps).count(STROKE_START) == 1 and STROKE_END not in kinds(steps)
    drawn = [ev.point[0] for s in steps for ev in s.events]
    assert 150.0 not in drawn                     # the misread frame (index 5) adds nothing


def test_stroke_end_drops_the_changing_frames():
    e = make()
    steps = run(e, [POINT] * 6 + [OTHER] * 3 + [OTHER])
    k = kinds(steps)
    assert k.count(STROKE_END) == 1
    end_step = next(i for i, s in enumerate(steps) if any(ev.kind == STROKE_END for ev in s.events))
    assert end_step == 8                          # after 3 frames of the new shape
    points = [ev.point[0] for s in steps for ev in s.events if ev.kind in (STROKE_START, STROKE_POINT)]
    assert max(points) == 150.0                   # the last POINT frame; no point from the changing frames
    assert steps[-1].mode == HOVER


def test_switching_from_draw_to_erase_ends_the_stroke_first():
    e = make()
    steps = run(e, [POINT] * 5 + [OPEN] * 5)
    k = kinds(steps)
    assert k.index(STROKE_END) < k.index(ERASE_AT)
    assert steps[-1].mode == ERASE
    erase_points = [ev.point for s in steps for ev in s.events if ev.kind == ERASE_AT]
    assert erase_points[0] == (140.0 + 50.0, 230.0)       # the first OPEN frame's palm (index 5)
    assert all(ev.radius == 50.0 for s in steps for ev in s.events if ev.kind == ERASE_AT)


def test_erase_and_pinch_have_end_events():
    e = make()
    k = kinds(run(e, [OPEN] * 5 + [OTHER] * 3 + [PINCH] * 5 + [OTHER] * 3))
    assert k.count(ERASE_END) == 1 and k.count(PINCH_DOWN) == 1 and k.count(PINCH_UP) == 1
    assert k.index(ERASE_END) < k.index(PINCH_DOWN) < k.index(PINCH_UP)
    assert PINCH_MOVE in k


def test_pinch_release_is_where_the_pinch_was():
    e = make()
    steps = run(e, [PINCH] * 6 + [OTHER] * 3)
    up = [ev for s in steps for ev in s.events if ev.kind == PINCH_UP][0]
    assert up.point == (155.0, 205.0)              # the last PINCH frame (index 5), not an opening frame


def test_a_short_dropout_keeps_the_stroke():
    e = make()
    steps = run(e, [POINT] * 6 + [None] * 5 + [POINT] * 3)       # 5 frames = 93 ms < 150 ms
    assert STROKE_END not in kinds(steps)
    assert all(s.mode == DRAW for s in steps[4:])
    assert steps[7].cursor is not None                           # held at the last position


def test_a_long_dropout_ends_the_stroke_and_hides_the_cursor():
    e = make()
    steps = run(e, [POINT] * 6 + [None] * 12)                    # 222 ms > 150 ms
    assert kinds(steps).count(STROKE_END) == 1
    assert steps[-1].mode == IDLE and steps[-1].cursor is None


def test_returning_after_a_long_dropout_needs_the_enter_frames_again():
    e = make()
    steps = run(e, [POINT] * 6 + [None] * 12 + [POINT] * 2)
    assert steps[-1].mode == HOVER and kinds(steps).count(STROKE_START) == 1


def test_cursor_point_per_mode():
    e = make()
    assert run(e, [POINT] * 5)[-1].cursor == (140.0, 200.0)               # fingertip
    e = make()
    assert run(e, [OPEN] * 5)[-1].cursor == (180.0, 230.0)                # palm
    e = make()
    assert run(e, [PINCH] * 5)[-1].cursor == (145.0, 205.0)               # pinch point


def test_statistics_and_pending():
    e = make()
    steps = run(e, [POINT] * 5 + [OTHER])
    assert steps[-1].pending == HOVER and steps[-1].mode == DRAW
    assert e.entries[DRAW] == 1 and e.mode_frames[HOVER] == 3 and e.mode_frames[DRAW] == 3   # draw from frame 3


def test_parameters_are_validated():
    with pytest.raises(ValueError):
        InteractionEngine(EngineParams(enter_frames=0))


def test_default_is_one_gesture_with_seven_enter_frames():
    e = InteractionEngine()
    assert e.params.enter_frames == 7
    for shape in (OPEN, PINCH, OTHER):                      # D46: only pointing does something
        steps = run(InteractionEngine(), [shape] * 20)
        assert {s.mode for s in steps} == {HOVER} and kinds(steps) == []
    steps = run(e, [OTHER] + [POINT] * 10)
    assert [s.mode for s in steps].index(DRAW) == 7         # the 7th POINT frame
    first = next(ev for s in steps for ev in s.events)
    assert first.kind == STROKE_START and first.point == (110.0, 200.0)   # still the first POINT frame


@pytest.mark.parametrize("run_length", [1, 3, 6])
def test_observed_misread_runs_never_draw(run_length):
    # G1 run 1: non-pointing shapes read as POINT for at most 6 frames (pinch-like), open/fist at most 3.
    steps = run(InteractionEngine(), [OPEN] * 5 + [POINT] * run_length + [OPEN] * 10)
    assert DRAW not in [s.mode for s in steps]


def kept(shape, x=100.0, keeps=True):
    return HandInput(shape, pointer=(x, 200.0), pinch=(x, 200.0), palm=(x, 200.0), keeps_draw=keeps)


def test_keep_drawing_band_continues_a_stroke_and_open_hand_ends_it():
    # D47: once drawing, a drifted pointing hand (not a strict POINT) keeps the stroke going and adds its points.
    e = InteractionEngine()
    steps = [e.update(i * DT, kept(POINT, 100.0 + 10 * i)) for i in range(8)]
    assert steps[-1].mode == DRAW
    steps = [e.update((8 + i) * DT, kept(OTHER, 180.0 + 10 * i)) for i in range(10)]
    assert {s.mode for s in steps} == {DRAW} and kinds(steps) == [STROKE_POINT] * 10
    steps = [e.update((18 + i) * DT, kept(PINCH, 280.0 + 10 * i)) for i in range(5)]    # thumb ignored
    assert {s.mode for s in steps} == {DRAW} and STROKE_END not in kinds(steps)
    steps = [e.update((23 + i) * DT, kept(OPEN, 330.0, keeps=False)) for i in range(40)]   # 0.74 s > lift_s
    assert steps[-1].mode == HOVER and kinds(steps) == [STROKE_END]


def test_keep_drawing_band_never_starts_a_stroke():
    e = InteractionEngine()
    steps = [e.update(i * DT, kept(OTHER, 100.0 + i)) for i in range(40)]
    assert {s.mode for s in steps} == {HOVER} and kinds(steps) == []
    shapes = ([POINT] * 4 + [OTHER] * 3) * 5                       # strict runs shorter than 7, band in between
    steps = [e.update((40 + i) * DT, kept(s, 100.0 + i)) for i, s in enumerate(shapes)]
    assert DRAW not in {s.mode for s in steps}


def test_pen_lift_delay_bridges_a_short_interruption():
    # D49: 0.4 s of a non-pointing reading (or no hand) inside a stroke neither ends it nor adds its points.
    for gap in ([OTHER] * 21, [None] * 21, [OPEN] * 10 + [None] * 11):
        e = InteractionEngine()
        steps = run(e, [POINT] * 8 + gap + [POINT] * 5)
        assert STROKE_END not in kinds(steps) and kinds(steps).count(STROKE_START) == 1
        assert all(s.mode == DRAW for s in steps[7:])
        xs = [ev.point[0] for s in steps for ev in s.events if ev.kind == STROKE_POINT]
        assert 100.0 + 10 * 8 not in xs and xs[-1] == 100.0 + 10 * (8 + len(gap) + 4)   # a straight join


def test_pen_lifts_after_the_delay():
    e = InteractionEngine()
    steps = run(e, [POINT] * 8 + [OPEN] * 40)
    end = next(i for i, s in enumerate(steps) if STROKE_END in [ev.kind for ev in s.events])
    assert (end - 7) * DT == pytest.approx(EngineParams().lift_s, abs=2 * DT)   # 0.6 s after the last POINT
    assert kinds(steps).count(STROKE_END) == 1 and steps[-1].mode == HOVER
    e = InteractionEngine()
    steps = run(e, [POINT] * 8 + [None] * 40)
    assert kinds(steps).count(STROKE_END) == 1 and steps[-1].mode == IDLE
    with pytest.raises(ValueError):
        InteractionEngine(EngineParams(lift_s=-1.0))


def test_a_pointing_frame_after_the_window_does_not_resume_the_stroke():
    # R32 (G3 run 4): after a real lift, a pointing-like frame of the hand moving on arrived just as the 0.6-s
    # window closed and resumed the stroke with a long straight tail. The window is checked on every frame.
    e = InteractionEngine()
    steps = run(e, [POINT] * 8 + [OTHER] * 32 + [POINT])           # 32 frames = 0.59 s, then 0.61 s after
    assert [s.mode for s in steps[8:40]] == [DRAW] * 32             # still inside the window
    last = steps[-1]
    assert [ev.kind for ev in last.events] == [STROKE_END] and last.mode == HOVER
    assert last.pending == DRAW                                     # a new stroke needs the enter frames again
    xs = [ev.point[0] for s in steps for ev in s.events if ev.kind == STROKE_POINT]
    assert max(xs) == 100.0 + 10 * 7                                # nothing drawn after the last real POINT
