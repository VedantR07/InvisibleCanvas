import json

import numpy as np
import pytest

from invisible_canvas.canvas.history import AddStroke, History, MoveStrokes, ReplaceStrokes
from invisible_canvas.canvas.model import MAX_STEP, Canvas, Stroke
from invisible_canvas.canvas.render import CanvasRenderer
from invisible_canvas.canvas.toolbar import CLEAR_HOLD_S, COLOURS, WIDTHS, Toolbar
from invisible_canvas.interaction.drawing import DrawingController
from invisible_canvas.interaction.engine import (
    DRAW,
    ERASE_AT,
    ERASE_END,
    PINCH_DOWN,
    PINCH_MOVE,
    PINCH_UP,
    STROKE_END,
    STROKE_POINT,
    STROKE_START,
    Event,
    HandInput,
    InteractionEngine,
)
from invisible_canvas.vision.gestures import OPEN, OTHER, PINCH, POINT

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
    tb = Toolbar(SIZE)
    assert len(tb.buttons) == len(COLOURS) + len(WIDTHS) + 3
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


def test_drawing_a_stroke_uses_the_current_colour_and_width():
    c, tb, ctl = controller()
    ctl.handle([ev(STROKE_START, 0, (100, 100)), ev(STROKE_POINT, 0.02, (150, 120)), ev(STROKE_END, 0.04)])
    (s,) = c.strokes.values()
    assert s.color == COLOURS["black"] and s.width == WIDTHS["medium"] and ctl.log["strokes"] == 1
    assert ctl.active is None and ctl.history.can_undo


def test_no_stroke_starts_on_the_toolbar():
    c, tb, ctl = controller()
    y = tb.top + 10
    ctl.handle([ev(STROKE_START, 0, (100, y)), ev(STROKE_POINT, 0.02, (150, 300)), ev(STROKE_END, 0.04)])
    assert c.strokes == {} and ctl.log["strokes_refused_on_toolbar"] == 1


def test_pinch_presses_colour_width_undo_redo_once():
    c, tb, ctl = controller()
    ctl.handle([ev(STROKE_START, 0, (100, 100)), ev(STROKE_POINT, 0, (200, 100)), ev(STROKE_END, 0)])
    for name in ("red", "thick"):
        b = tb.button(name).centre
        ctl.handle([ev(PINCH_DOWN, 1, b), ev(PINCH_MOVE, 1.1, b), ev(PINCH_UP, 1.2, b)])
    assert (ctl.colour, ctl.width) == ("red", "thick")
    u = tb.button("undo").centre
    ctl.handle([ev(PINCH_DOWN, 2, u)] + [ev(PINCH_MOVE, 2 + k / 50, u) for k in range(100)] + [ev(PINCH_UP, 4, u)])
    assert c.strokes == {} and ctl.log["undo"] == 1                 # held for 2 s: still one undo
    r = tb.button("redo").centre
    ctl.handle([ev(PINCH_DOWN, 5, r), ev(PINCH_UP, 5.1, r)])
    assert len(c.strokes) == 1 and ctl.log["press:redo"] == 1


def test_clear_needs_the_pinch_held_on_it():
    c, tb, ctl = controller()
    ctl.handle([ev(STROKE_START, 0, (100, 100)), ev(STROKE_POINT, 0, (200, 100)), ev(STROKE_END, 0)])
    b = tb.button("clear").centre
    ctl.handle([ev(PINCH_DOWN, 1, b), ev(PINCH_MOVE, 1.5, b)])
    assert len(c.strokes) == 1 and ctl.clear_progress == pytest.approx(0.5)
    ctl.handle([ev(PINCH_UP, 1.6, b)])                                  # released early: nothing cleared
    assert len(c.strokes) == 1 and ctl.clear_progress is None
    ctl.handle([ev(PINCH_DOWN, 2, b), ev(PINCH_MOVE, 2.5, b), ev(PINCH_MOVE, 2.5, (b[0], 300))])   # slid off
    ctl.handle([ev(PINCH_MOVE, 3.5, b), ev(PINCH_UP, 3.6, b)])
    assert len(c.strokes) == 1
    ctl.handle([ev(PINCH_DOWN, 4, b), ev(PINCH_MOVE, 4 + CLEAR_HOLD_S, b), ev(PINCH_UP, 5.2, b)])
    assert c.strokes == {} and ctl.log["clear"] == 1
    ctl.undo()
    assert len(c.strokes) == 1


def test_pinch_moves_a_stroke_as_one_undo_step():
    c, tb, ctl = controller()
    ctl.handle([ev(STROKE_START, 0, (100, 100)), ev(STROKE_POINT, 0, (200, 100)), ev(STROKE_END, 0)])
    (sid,) = c.strokes
    ctl.handle([ev(PINCH_DOWN, 1, (150, 102)), ev(PINCH_MOVE, 1.1, (170, 122))])
    assert ctl.selected == sid
    ctl.handle([ev(PINCH_MOVE, 1.2, (190, 142)), ev(PINCH_UP, 1.3, (190, 142))])
    assert c.strokes[sid].points[0] == (140.0, 140.0) and ctl.log["moves"] == 1 and ctl.selected is None
    ctl.undo()
    assert c.strokes[sid].points[0] == (100.0, 100.0)


def test_pinch_on_empty_canvas_does_nothing():
    c, tb, ctl = controller()
    ctl.handle([ev(PINCH_DOWN, 1, (600, 300)), ev(PINCH_MOVE, 1.1, (650, 300)), ev(PINCH_UP, 1.2, (650, 300))])
    assert c.strokes == {} and not ctl.history.can_undo


def test_one_erase_gesture_is_one_undo_step():
    c, tb, ctl = controller()
    for y in (100, 200, 300):
        ctl.handle([ev(STROKE_START, 0, (100, y)), ev(STROKE_POINT, 0, (500, y)), ev(STROKE_END, 0)])
    before = sorted(snapshot(c))
    ctl.handle([ev(ERASE_AT, 1 + k / 50, (300, 80 + 10 * k), 25) for k in range(25)] + [ev(ERASE_END, 2)])
    assert len(c.strokes) == 6 and ctl.log["erase_gestures"] == 1     # each line cut in two
    for s in c.strokes.values():
        assert all(abs(x - 300) > 25 for x, _ in s.points)
    ctl.undo()
    assert sorted(snapshot(c)) == before
    ctl.redo()
    assert len(c.strokes) == 6


# -- engine + controller together -------------------------------------------------------------------------

def feed(engine, ctl, shapes, path):
    for i, (shape, p) in enumerate(zip(shapes, path)):
        hand = None if shape is None else HandInput(shape, p, p, p, 30.0)
        ctl.handle(engine.update(i / 54, hand).events)


def test_a_drawn_letter_then_a_glitch_free_hover():
    eng, (c, tb, ctl) = InteractionEngine(), controller()
    path = [(100 + 5 * i, 200 + 3 * i) for i in range(40)]
    shapes = [OTHER] * 5 + [POINT] * 20 + [OTHER] * 10 + [POINT] * 2 + [OTHER] * 3
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
