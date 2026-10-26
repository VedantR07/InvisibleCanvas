"""Draw diagnostics (brain.md §9.12, Stage 3 item 1): geometry, frame states read from the engine's own state,
the controller's recorded outcomes, and bounded timing histograms. Observation only: every test that drives the
controller also checks the decisions the code already made (strokes, log)."""

import numpy as np
import pytest

from invisible_canvas.canvas.model import Canvas, Stroke
from invisible_canvas.canvas.toolbar import Toolbar
from invisible_canvas.interaction.drawing import DrawingController
from invisible_canvas.interaction.engine import (
    DRAW, HOVER, STROKE_END, STROKE_POINT, STROKE_START, EngineParams, Event, HandInput, InteractionEngine, Step,
)
from invisible_canvas.mapping.mapper import CoordinateMapper
from invisible_canvas.tools.draw_diagnostics import DrawDiagnostics, Histogram, band, frame_state, where
from invisible_canvas.vision.gestures import OTHER, POINT

SIZE = (1280, 720)
TOP = Toolbar(SIZE).top                     # 648


# -- geometry: the code's own definitions --------------------------------------------------------------

def test_where_follows_the_canvas_and_toolbar_definitions_of_the_code():
    assert TOP == 648
    cases = {(640, 300): "canvas", (640, 647.99): "canvas", (640, 648): "toolbar", (640, 719.49): "toolbar",
             (640, 719.5): "below", (640, 900): "below", (-0.5, 300): "canvas", (-0.51, 300): "left",
             (1279.49, 300): "canvas", (1279.5, 300): "right", (640, -0.5): "canvas", (640, -0.51): "above",
             (-10, 800): "below", (-10, -10): "above", (-10, 660): "left", (1300, 300): "right"}
    for p, expected in cases.items():
        assert where(p, SIZE, TOP) == expected, p
    assert where(None, SIZE, TOP) is None


def test_where_agrees_with_inside_canvas_and_in_band():
    mapper = CoordinateMapper(np.eye(3), SIZE)
    toolbar = Toolbar(SIZE)
    rng = np.random.default_rng(3)
    pts = rng.uniform([-60, -60], [1340, 800], (5000, 2))
    inside = mapper.inside_canvas(pts)
    for p, ins in zip(pts, inside):
        w = where(p, SIZE, TOP)
        assert (w in ("canvas", "toolbar")) == bool(ins)
        if ins:                                   # on the canvas, "toolbar" is exactly the controller's band test
            assert (w == "toolbar") == toolbar.in_band(p)


def test_band_uses_the_baseline_height_bands():
    assert [band((640, y), SIZE, TOP) for y in (100, 300, 500, 600, 660, 760)] == \
        ["top", "middle", "lower", "bottom", "toolbar", "below"]


def test_histogram_is_bounded_and_accurate_to_one_bin():
    h = Histogram(0.05, 10.0)
    values = np.random.default_rng(1).uniform(0, 4, 20000)
    for v in values:
        h.add(v)
    h.add(500.0)                                  # beyond the limit: the overflow bin, max exact
    assert len(h.bins) == 201 and h.count == 20001 and h.max == 500.0
    assert abs(h.percentile(50) - np.median(values)) <= 0.05
    assert abs(h.percentile(95) - np.percentile(values, 95)) <= 0.05
    assert h.percentile(100) == 500.0 and Histogram().summary() is None


# -- frame states ---------------------------------------------------------------------------------------

def step(mode, *kinds, cursor=(300.0, 300.0)):
    return Step(mode, cursor, tuple(Event(k, 0.0, cursor) for k in kinds), None)


def test_frame_state_cases():
    assert frame_state("ok", DRAW, step(DRAW, STROKE_START).events, HOVER, DRAW) == "start"
    assert frame_state("ok", HOVER, step(HOVER, STROKE_END).events, DRAW, HOVER) == "lifted"
    assert frame_state("ok", DRAW, step(DRAW, STROKE_POINT).events, DRAW, DRAW) == "drawing"
    assert frame_state("ok", DRAW, (), DRAW, HOVER) == "gap"
    assert frame_state("no-hand", DRAW, (), DRAW, DRAW) == "held"
    assert frame_state("ok", DRAW, step(DRAW, STROKE_POINT).events, DRAW, DRAW, blocked=True) == "blocked"   # D56
    assert frame_state("no-hand", DRAW, (), DRAW, DRAW, blocked=True) == "held"       # the hand comes first
    assert frame_state("ok", HOVER, (), DRAW, HOVER) == "start-unconfirmed"
    assert frame_state("no-hand", HOVER, (), DRAW, None) == "start-unconfirmed"
    assert frame_state("ok", HOVER, (), HOVER, DRAW) == "pending-start"
    assert frame_state("no-hand", HOVER, (), DRAW, DRAW) == "pending-start"     # a held dropout keeps the buffer
    assert frame_state("tip-outside-view", "idle", (), None, None) == "tip-outside-view"
    assert frame_state("ok", HOVER, (), HOVER, HOVER) == "hover"


def hand(shape, x=300.0, y=300.0, keeps=None):
    return HandInput(shape, (x, y), (x, y), (x, y), keeps_draw=(shape == POINT) if keeps is None else keeps)


def run_engine(frames, params=EngineParams()):
    """frames: [(t, HandInput | None)] through the real engine; the states as `draw` derives them."""
    engine, diag, states = InteractionEngine(params), DrawDiagnostics(SIZE, TOP), []
    for t, h in frames:
        prev = engine._candidate
        s = engine.update(t, h)
        fields = diag.frame(t=t, action="fake", status="ok" if h is not None else "no-hand", cursor=s.cursor,
                            step=s, prev_candidate=prev, candidate=engine._candidate, outcomes=[], stage_ms={})
        states.append(fields["state"])
    return states


def test_states_from_the_real_engine():
    dt = 1 / 50
    frames = [(k * dt, hand(POINT)) for k in range(3)] + [(3 * dt, hand(OTHER))]          # 3 POINT, then other
    assert run_engine(frames) == ["pending-start"] * 3 + ["start-unconfirmed"]
    frames = [(k * dt, hand(POINT)) for k in range(3)] + [(3 * dt, None)] + \
        [((4 + k) * dt, hand(POINT)) for k in range(4)]                  # a 20-ms dropout inside the 7 frames
    assert run_engine(frames) == ["pending-start"] * 4 + ["pending-start"] * 3 + ["start"]   # not "unconfirmed"
    t = [k * dt for k in range(60)]
    frames = [(t[k], hand(POINT)) for k in range(10)]                   # start at frame 7, then drawing
    frames += [(t[10 + k], hand(OTHER, keeps=False)) for k in range(5)]  # outside the keep band: gap
    frames += [(t[15 + k], None) for k in range(5)]                      # no hand, inside the 0.6-s window: held
    frames += [(t[20] + 0.7, None)]                                       # past the window: the pen lifts
    states = run_engine(frames)
    assert states[:6] == ["pending-start"] * 6 and states[6] == "start" and states[7:10] == ["drawing"] * 3
    assert states[10:15] == ["gap"] * 5 and states[15:20] == ["held"] * 5 and states[20] == "lifted"


# -- the controller's recorded outcomes (decisions unchanged) -----------------------------------------------

def ev(kind, x=None, y=None):
    return Event(kind, 0.0, None if x is None else (float(x), float(y)))


def drive(ctl, *events):
    seen = []
    for e in events:
        ctl.handle([e])
        seen += [(o, None if p is None else where(p, SIZE, TOP)) for o, p, _ in ctl.outcomes]
    return seen


def test_toolbar_trap_records_the_refusal_and_the_ignored_points():
    canvas = Canvas(SIZE)
    ctl = DrawingController(canvas, Toolbar(SIZE))
    seen = drive(ctl, ev(STROKE_START, 300, 690), ev(STROKE_POINT, 300, 600), ev(STROKE_POINT, 300, 400),
                 ev(STROKE_END))
    assert seen == [("refused_band", "toolbar"), ("after_refused_start", "canvas"), ("after_refused_start", "canvas")]
    assert len(canvas.strokes) == 0 and ctl.log["strokes_refused_on_toolbar"] == 1 and "strokes" not in ctl.log
    assert ctl.attempts == 1 and not ctl.stroke_open


def test_a_stroke_that_reaches_the_band_ends_there_and_the_rest_is_recorded_as_not_drawn():
    # D56 (was: band points dropped and the stroke joined across the band when the finger came back)
    canvas = Canvas(SIZE)
    ctl = DrawingController(canvas, Toolbar(SIZE))
    seen = drive(ctl, ev(STROKE_START, 300, 600), ev(STROKE_POINT, 300, 640), ev(STROKE_POINT, 300, 660),
                 ev(STROKE_POINT, 300, 760), ev(STROKE_POINT, 300, 630), ev(STROKE_POINT, 310, 630))
    assert seen == [("added", "canvas"), ("added", "canvas"), ("ended_band", "toolbar"), ("after_ui_end", "below"),
                    ("after_ui_end", "canvas"), ("after_ui_end", "canvas")]
    assert ctl.blocked == "toolbar" and ctl.log["strokes"] == 1 and ctl.log["strokes_ended_on_toolbar"] == 1
    (stroke,) = canvas.strokes.values()            # committed when the band was reached: nothing from after it
    assert stroke.points[-1] == (300.0, 640.0) and all(p[1] < TOP for p in stroke.points)
    drive(ctl, ev(STROKE_END))
    assert ctl.blocked is None and len(canvas.strokes) == 1 and ctl.log["strokes"] == 1


def test_points_off_the_left_and_top_are_still_drawn_as_before():
    # unchanged by D56: only the toolbar band (y >= 648, below the canvas too) and the open panel are excluded
    canvas = Canvas(SIZE)
    ctl = DrawingController(canvas, Toolbar(SIZE))
    seen = drive(ctl, ev(STROKE_START, 300, 300), ev(STROKE_POINT, 300, 300), ev(STROKE_POINT, -30, 300),
                 ev(STROKE_POINT, 300, -20), ev(STROKE_POINT, 1300, 300), ev(STROKE_END))
    assert seen == [("added", "canvas"), ("duplicate", "canvas"), ("added", "left"), ("added", "above"),
                    ("added", "right")]
    (stroke,) = canvas.strokes.values()
    assert min(p[0] for p in stroke.points) == -30 and max(p[0] for p in stroke.points) == 1300


def test_panel_exclusions_are_recorded():
    canvas = Canvas(SIZE)
    tb = Toolbar(SIZE, ai=True)
    ctl = DrawingController(canvas, tb)
    ctl.press("ai")                                # the panel opens at x 824..1264, y 16..632
    seen = drive(ctl, ev(STROKE_START, 900, 300), ev(STROKE_POINT, 700, 300), ev(STROKE_END),
                 ev(STROKE_START, 700, 300), ev(STROKE_POINT, 900, 300), ev(STROKE_POINT, 710, 300), ev(STROKE_END))
    assert [o for o, _ in seen] == ["refused_panel", "after_refused_start", "added", "ended_panel", "after_ui_end"]
    assert ctl.log["strokes_refused_on_panel"] == 1 and ctl.log["strokes"] == 1
    assert ctl.log["strokes_ended_on_panel"] == 1 and ctl.blocked is None


def test_other_tools_are_recorded_as_such():
    canvas = Canvas(SIZE)
    s = Stroke(canvas.new_id(), (25, 25, 25), 8.0)
    for x in range(200, 400, 2):
        s.append((x, 300))
    canvas.add(s)
    ctl = DrawingController(canvas, Toolbar(SIZE))
    ctl.press("eraser")
    erase = drive(ctl, ev(STROKE_START, 250, 300), ev(STROKE_POINT, 260, 300), ev(STROKE_END))
    ctl.press("move")
    move = drive(ctl, ev(STROKE_START, 350, 300), ev(STROKE_POINT, 360, 310), ev(STROKE_END),
                 ev(STROKE_START, 600, 500), ev(STROKE_POINT, 610, 500), ev(STROKE_END))
    ctl.press("select")
    select = drive(ctl, ev(STROKE_START, 100, 100), ev(STROKE_POINT, 500, 100), ev(STROKE_END))
    assert [o for o, _ in erase] == ["eraser", "eraser"]
    assert [o for o, _ in move] == ["move", "move", "move_nothing", "ignored_move"]
    assert [o for o, _ in select] == ["select", "select"]
    assert ctl.log["erase_strokes"] == 1 and ctl.log["moves"] == 1 and ctl.log["selections"] == 1
    assert ctl.attempts == 4


def test_diagnostics_count_bands_losses_and_ink():
    diag = DrawDiagnostics(SIZE, TOP)
    s_draw = Step(DRAW, (300.0, 600.0), (), POINT)
    outcomes = [("dropped_band", (300.0, 700.0), 1), ("after_refused_start", (300.0, 400.0), 2)]
    diag.frame(t=0.0, action="track", status="ok", cursor=(300.0, 600.0), step=s_draw, prev_candidate=DRAW,
               candidate=DRAW, outcomes=outcomes, stage_ms={"hand": 0.2})
    diag.frame(t=0.1, action="track-miss", status="no-hand", cursor=None, step=Step("idle", None, (), None),
               prev_candidate=None, candidate=None, outcomes=[], stage_ms={})
    diag.frame(t=0.6, action="search-hit", status="ok", cursor=(300.0, 300.0), step=Step(HOVER, (300.0, 300.0), (), OTHER),
               prev_candidate=None, candidate=HOVER, outcomes=[], stage_ms={})
    r = diag.report(strokes_committed=0, attempts=2)
    assert r["bands"]["bottom"] == {"hand_frames": 1, "losses": 1, "losses_per_1000": 1000.0,
                                    "refind_s": {"median": pytest.approx(0.5), "p95": pytest.approx(0.5),
                                                 "max": pytest.approx(0.5), "count": 1}}
    assert r["bands"]["middle"]["hand_frames"] == 1
    assert r["ink"] == {"after_refused_start:canvas": 1, "dropped_band:toolbar": 1}
    assert r["strokes"]["attempts_with_points_after_refusal"] == 1 and r["strokes"]["points_after_refused_start"] == 1
    assert r["tracker_actions"] == {"track": 1, "track-miss": 1, "search-hit": 1}
    assert r["stage_ms"]["hand"]["count"] == 1 and r["overhead"]["target_ms"] == 0.1
