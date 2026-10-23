import json

import numpy as np
import pytest

from invisible_canvas.canvas.history import AddStroke, History, MoveStrokes, ReplaceStrokes
from invisible_canvas.canvas.model import MAX_STEP, Canvas, Stroke
from invisible_canvas.canvas.render import CanvasRenderer
from invisible_canvas.canvas.toolbar import CLEAR_DWELL_S, COLOURS, DWELL_S, TOOLS, WIDTHS, Toolbar
from invisible_canvas.interaction.drawing import ERASER_RADIUS, DrawingController
from invisible_canvas.interaction.engine import (
    DRAW,
    HOVER,
    STROKE_END,
    STROKE_POINT,
    STROKE_START,
    Event,
    HandInput,
    InteractionEngine,
)
from invisible_canvas.vision.gestures import OTHER, POINT

SIZE = (1280, 720)


def line(canvas, x0, x1, y, sid=None, width=8.0):
    s = Stroke(sid or canvas.new_id(), (0, 0, 0), width)
    s.append((x0, y))
    s.append((x1, y))
    canvas.add(s)
    return s


# -- model ------------------------------------------------------------------------------------------------

def test_points_are_densified():
    s = Stroke(1, (0, 0, 0), 4.0)
    s.append((0, 0))
    s.append((10, 0))
    gaps = np.linalg.norm(np.diff(s.array(), axis=0), axis=1)
    assert gaps.max() <= MAX_STEP + 1e-9 and s.points[-1] == (10.0, 0.0)
    s.append((10, 0))                     # a repeated point adds nothing
    s.append((float("nan"), 3))           # a non-finite point is ignored
    assert len(s.points) == 6


def test_partial_erase_splits_a_stroke_in_place():
    c = Canvas(SIZE)
    a = line(c, 100, 300, 200)
    b = line(c, 100, 300, 400)
    removed, created = c.erase((200, 200), 20)
    assert [s.id for s in removed] == [a.id] and len(created) == 2
    left, right = created
    assert max(x for x, _ in left.points) < 200 - 20 and min(x for x, _ in right.points) > 200 + 20
    assert list(c.strokes) == [left.id, right.id, b.id]          # drawing order kept
    assert c.strokes[b.id] is b                                   # untouched stroke unchanged


def test_erasing_a_whole_stroke_and_nothing():
    c = Canvas(SIZE)
    a = line(c, 100, 120, 200)
    v = c.version
    assert c.erase((500, 500), 30) == ([], []) and c.version == v
    removed, created = c.erase((110, 200), 40)
    assert removed == [a] and created == [] and c.strokes == {}


def test_hit_test_prefers_the_top_stroke_and_respects_tolerance():
    c = Canvas(SIZE)
    a = line(c, 100, 300, 200)
    b = line(c, 100, 300, 205)
    assert c.hit_test((200, 203)) == b.id
    assert c.hit_test((200, 260)) is None
    assert c.hit_test((200, 214), tolerance=12) == b.id


def test_move_and_json_round_trip():
    c = Canvas(SIZE)
    a = line(c, 100, 300, 200)
    c.move([a.id], 10, -5)
    assert c.strokes[a.id].points[0] == (110.0, 195.0)
    d = json.loads(json.dumps(c.to_dict()))
    c2 = Canvas.from_dict(d)
    assert list(c2.strokes) == [a.id] and c2.strokes[a.id].points == c.strokes[a.id].points
    assert c2.new_id() > a.id
    with pytest.raises(ValueError):
        Canvas.from_dict({"format": "other"})


def test_add_refuses_empty_and_duplicate_strokes():
    c = Canvas(SIZE)
    with pytest.raises(ValueError):
        c.add(Stroke(1, (0, 0, 0), 4.0))
    a = line(c, 0, 10, 10)
    with pytest.raises(ValueError):
        c.add(Stroke(a.id, (0, 0, 0), 4.0, [(1, 1)]))


# -- history ----------------------------------------------------------------------------------------------

def snapshot(c):
    return [(s.id, tuple(s.points)) for s in c.strokes.values()]


def test_undo_redo_of_every_command_type():
    c, h = Canvas(SIZE), History()
    s = Stroke(c.new_id(), (0, 0, 0), 8.0)
    s.append((100, 100)); s.append((300, 100))
    states = [snapshot(c)]
    h.do(AddStroke(s), c); states.append(snapshot(c))
    removed, created = c.erase((200, 100), 15)
    h.record(ReplaceStrokes(removed, created)); states.append(snapshot(c))
    ids = list(c.strokes)
    c.move(ids, 5, 5); h.record(MoveStrokes(ids, 5, 5)); states.append(snapshot(c))
    gone = c.clear(); h.record(ReplaceStrokes(gone, [], name="clear")); states.append(snapshot(c))
    for expected in reversed(states[:-1]):
        h.undo(c)
        assert sorted(snapshot(c)) == sorted(expected)
    assert h.undo(c) is None
    for expected in states[1:]:
        h.redo(c)
        assert sorted(snapshot(c)) == sorted(expected)
    assert h.redo(c) is None


def test_a_new_action_clears_redo():
    c, h = Canvas(SIZE), History()
    s = Stroke(c.new_id(), (0, 0, 0), 8.0, [(1, 1)])
    h.do(AddStroke(s), c)
    h.undo(c)
    assert h.can_redo
    h.do(AddStroke(Stroke(c.new_id(), (0, 0, 0), 8.0, [(2, 2)])), c)
    assert not h.can_redo


# -- toolbar ----------------------------------------------------------------------------------------------

def test_toolbar_layout_fits_the_bottom_band():
    for tb, n in ((Toolbar(SIZE), 3), (Toolbar(SIZE, ai=True), 4)):          # D51: AI button only when AI is on
        check_toolbar(tb, len(TOOLS) + len(COLOURS) + len(WIDTHS) + n)
    assert "select" in TOOLS and Toolbar(SIZE, ai=True).button("ai").kind == "ai"
    assert not any(b.name == "ai" for b in Toolbar(SIZE).buttons)


def check_toolbar(tb, count):
    assert len(tb.buttons) == count and 60 <= tb.button_w <= 80
    for b in tb.buttons:
        x0, y0, x1, y1 = b.rect
        assert 0 <= x0 < x1 <= SIZE[0] and tb.top <= y0 < y1 <= SIZE[1]
        assert tb.hit(b.centre) is b
    rects = sorted(b.rect for b in tb.buttons)
    assert all(r1[0] >= r0[2] for r0, r1 in zip(rects, rects[1:]))          # no overlap
    assert tb.hit((640, 300)) is None and tb.in_band((640, 700)) and not tb.in_band((640, 300))


# -- controller -------------------------------------------------------------------------------------------

def controller():
    c = Canvas(SIZE)
    return c, Toolbar(SIZE), DrawingController(c, Toolbar(SIZE))


def ev(kind, t=0.0, point=None, radius=0.0):
    return Event(kind, t, point, radius)


def stroke(ctl, points, t=0.0):
    ctl.handle([ev(STROKE_START, t, points[0])] + [ev(STROKE_POINT, t, p) for p in points[1:]] + [ev(STROKE_END, t)])


def hold(ctl, point, t0, seconds, fps=50):
    for k in range(int(seconds * fps) + 1):
        ctl.update_pointer(t0 + k / fps, point)


def test_pen_draws_with_the_current_colour_and_width():
    c, tb, ctl = controller()
    stroke(ctl, [(100, 100), (150, 120)])
    (s,) = c.strokes.values()
    assert s.color == COLOURS["black"] and s.width == WIDTHS["medium"] and ctl.log["strokes"] == 1
    assert ctl.active is None and ctl.history.can_undo


def test_no_stroke_starts_on_the_toolbar():
    c, tb, ctl = controller()
    stroke(ctl, [(100, tb.top + 10), (150, 300)])
    assert c.strokes == {} and ctl.log["strokes_refused_on_toolbar"] == 1


def test_holding_the_cursor_on_a_button_presses_it_once():
    c, tb, ctl = controller()
    red = tb.button("red").centre
    hold(ctl, red, 0.0, DWELL_S * 0.9)
    assert ctl.colour == "black" and ctl.dwell_progress[0] == "red" and 0.8 < ctl.dwell_progress[1] < 1.0
    hold(ctl, red, DWELL_S * 0.9, 2.0)                      # keeps resting there: still one press
    assert ctl.colour == "red" and ctl.log["press:red"] == 1 and ctl.dwell_progress is None
    ctl.update_pointer(5.0, (640, 300))                     # leave and come back: a second press
    hold(ctl, red, 5.1, DWELL_S + 0.05)
    assert ctl.log["press:red"] == 2


def test_choosing_a_colour_selects_the_pen():
    c, tb, ctl = controller()
    hold(ctl, tb.button("eraser").centre, 0.0, DWELL_S + 0.05)
    assert ctl.tool == "eraser"
    ctl.update_pointer(2.0, None)
    hold(ctl, tb.button("blue").centre, 2.1, DWELL_S + 0.05)
    assert (ctl.tool, ctl.colour) == ("pen", "blue")


def test_moving_between_buttons_or_losing_the_hand_restarts_the_dwell():
    c, tb, ctl = controller()
    hold(ctl, tb.button("red").centre, 0.0, 0.6)
    hold(ctl, tb.button("green").centre, 0.62, 0.6)         # 0.6 s each: neither fires
    ctl.update_pointer(1.3, None)
    hold(ctl, tb.button("green").centre, 1.32, 0.6)
    assert ctl.colour == "black" and not any(k.startswith("press:") for k in ctl.log)


def test_clear_needs_two_seconds():
    c, tb, ctl = controller()
    stroke(ctl, [(100, 100), (200, 100)])
    clear = tb.button("clear").centre
    hold(ctl, clear, 0.0, 1.5)
    assert len(c.strokes) == 1 and ctl.dwell_progress[0] == "clear"
    hold(ctl, clear, 1.52, CLEAR_DWELL_S - 1.5)
    assert c.strokes == {} and ctl.log["clear"] == 1
    ctl.undo()
    assert len(c.strokes) == 1


def test_undo_and_redo_buttons():
    c, tb, ctl = controller()
    stroke(ctl, [(100, 100), (200, 100)])
    hold(ctl, tb.button("undo").centre, 0.0, DWELL_S + 0.05)
    assert c.strokes == {} and ctl.log["undo"] == 1
    ctl.update_pointer(2.0, None)
    hold(ctl, tb.button("redo").centre, 2.1, DWELL_S + 0.05)
    assert len(c.strokes) == 1 and ctl.log["redo"] == 1


def test_eraser_tool_erases_along_the_path_as_one_undo_step():
    c, tb, ctl = controller()
    for y in (100, 200, 300):
        stroke(ctl, [(100, y), (500, y)])
    before = sorted(snapshot(c))
    ctl.tool = "eraser"
    stroke(ctl, [(300, 60 + 10 * k) for k in range(30)])     # a vertical swipe across the three lines
    assert len(c.strokes) == 6 and ctl.log["erase_strokes"] == 1
    r = ERASER_RADIUS["medium"] + WIDTHS["medium"] / 2
    for s in c.strokes.values():
        assert all(abs(x - 300) > r for x, _ in s.points)
    ctl.undo()
    assert sorted(snapshot(c)) == before
    ctl.redo()
    assert len(c.strokes) == 6


def test_move_tool_drags_the_drawing_under_the_fingertip():
    c, tb, ctl = controller()
    stroke(ctl, [(100, 100), (200, 100)])
    (sid,) = c.strokes
    ctl.tool = "move"
    ctl.handle([ev(STROKE_START, 1, (150, 102)), ev(STROKE_POINT, 1.1, (170, 122))])
    assert ctl.selected == sid
    ctl.handle([ev(STROKE_POINT, 1.2, (190, 142)), ev(STROKE_END, 1.3)])
    assert c.strokes[sid].points[0] == (140.0, 140.0) and ctl.log["moves"] == 1 and ctl.selected is None
    ctl.undo()
    assert c.strokes[sid].points[0] == (100.0, 100.0)


def test_move_on_empty_canvas_does_nothing():
    c, tb, ctl = controller()
    ctl.tool = "move"
    stroke(ctl, [(600, 300), (650, 300)])
    assert c.strokes == {} and not ctl.history.can_undo


def test_unknown_events_are_refused():
    c, tb, ctl = controller()
    with pytest.raises(ValueError):
        ctl.handle([ev("pinch_down", 0, (1, 1))])


# -- engine + controller together -------------------------------------------------------------------------

def feed(engine, ctl, shapes, path):
    for i, (shape, p) in enumerate(zip(shapes, path)):
        hand = None if shape is None else HandInput(shape, p, p, p, 30.0)
        step = engine.update(i / 54, hand)
        ctl.handle(step.events)
        ctl.update_pointer(i / 54, step.cursor)


def test_a_drawn_letter_then_a_glitch_free_hover():
    eng, (c, tb, ctl) = InteractionEngine(), controller()
    path = [(100 + 5 * i, 200 + 3 * i) for i in range(80)]
    shapes = [OTHER] * 5 + [POINT] * 20 + [OTHER] * 40 + [POINT] * 2 + [OTHER] * 3   # 40 frames > the lift delay
    feed(eng, ctl, shapes, path)
    assert len(c.strokes) == 1                                     # the 2-frame POINT glitch drew nothing
    (s,) = c.strokes.values()
    assert s.points[0] == (125.0, 215.0)                           # starts where the POINT shape began


def test_render_shows_strokes_toolbar_and_cursor():
    c, tb, ctl = controller()
    ctl.handle([ev(STROKE_START, 0, (100, 100)), ev(STROKE_POINT, 0, (300, 100)), ev(STROKE_END, 0)])
    r = CanvasRenderer(SIZE)
    img = r.render(c, ctl, tb, mode=DRAW, cursor=(640, 360))
    assert img.shape == (720, 1280, 3)
    assert img[100, 200].tolist() == list(COLOURS["black"])         # the stroke
    assert img[tb.top + 2, 5].tolist() == [232, 232, 232]           # toolbar band
    assert tuple(img[360, 640]) == COLOURS["black"]                 # draw cursor in the pen colour
    r.render(c, ctl, tb, mode=DRAW, cursor=None)
    assert r.redraws == 1                                           # cached until the canvas changes
    c.move(list(c.strokes), 1, 0)
    r.render(c, ctl, tb, mode=DRAW, cursor=None)
    assert r.redraws == 2


def test_render_with_the_light_on_the_hand():
    # D50: the hand area is plain white even over ink, the cursor is a ring outside the light, a dwell is an arc.
    from invisible_canvas.canvas.render import RING_RADIUS
    from invisible_canvas.display.handlight import grown_hull
    c, tb, ctl = controller()
    ctl.handle([ev(STROKE_START, 0, (500, 300)), ev(STROKE_POINT, 0, (800, 300)), ev(STROKE_END, 0)])
    light = grown_hull(np.array([[620, 280], [660, 280], [660, 380], [620, 380]]), 25)
    r = CanvasRenderer(SIZE)
    img = r.render(c, ctl, tb, mode=HOVER, cursor=(640, 280), light=light)
    assert img[300, 640].tolist() == [255, 255, 255]                   # ink under the hand: lit white
    assert img[300, 520].tolist() == list(COLOURS["black"])             # ink elsewhere unchanged
    assert img[280 - RING_RADIUS, 640].tolist() != [255, 255, 255]     # the ring ahead of the fingertip
    ctl.update_pointer(0.0, tb.button("undo").centre)
    ctl.update_pointer(0.5, tb.button("undo").centre)
    arc = r.render(c, ctl, tb, mode=HOVER, cursor=(640, 280), light=light)
    assert (arc != img).any()                                           # the dwell arc is drawn on the ring
