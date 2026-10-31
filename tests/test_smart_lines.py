"""Smart Lines, Phase 1 (brain.md D62): the LINES tool writes one line at a time in a fixed zone, COMPLETE LINE (D64:
DONE) moves it unchanged into the numbered notes area (which scrolls), with its own undo; the unfinished line
survives tool, page and view changes; everything is saved with the board; Pen and the other tools are unchanged.
The D64 layout: corner guides and a baseline, a compact DONE, a slim scroll track, the review bar."""

import copy
import json
import tomllib

import cv2
import numpy as np
import pytest

from invisible_canvas.canvas import lines as lines_module
from invisible_canvas.canvas import text as typeset
from invisible_canvas.canvas.board import Board
from invisible_canvas.canvas.lines import (DEFAULT_NOTES, DEFAULT_ZONE, LineSheet, LinesLayout, render_controls,
                                          render_sheet)
from invisible_canvas.canvas.model import Canvas
from invisible_canvas.canvas.panel import BoardPanel
from invisible_canvas.canvas.reference import Reference
from invisible_canvas.canvas.render import ZONE_HINT, CanvasRenderer
from invisible_canvas.canvas.toolbar import Toolbar
from invisible_canvas.config import DEFAULT_CONFIG_PATH, ConfigError, config_from_dict, load_config
from invisible_canvas.interaction.drawing import DrawingController
from invisible_canvas.interaction.engine import DRAW, HOVER, STROKE_END, STROKE_POINT, STROKE_START, Event

SIZE = (1280, 720)
TOP = Toolbar(SIZE).top
Y = 480                                                   # inside the default writing zone (y 400-590)


def stroke(ctl, points, end=True):
    events = [Event(STROKE_START, 0.0, points[0])] + [Event(STROKE_POINT, 0.0, p) for p in points[1:]]
    ctl.handle(events + ([Event(STROKE_END, 0.0)] if end else []))


def letter(ctl, x, y=Y):
    stroke(ctl, [(x, y - 30), (x + 5, y), (x, y + 30)])


def lines_controller(ai=False):
    ctl = DrawingController(Canvas(SIZE), Toolbar(SIZE, ai=ai))
    ctl.press("lines")
    return ctl


def dwell(ctl, name, t0=0.0):
    """Hold the cursor on a Smart Lines button (or a toolbar button) until it fires, then leave it."""
    b = next((b for b in ctl.lines_layout.buttons if b.name == name), None) or ctl.toolbar.button(name)
    ctl.update_pointer(t0, b.centre)
    ctl.update_pointer(t0 + 1.05, b.centre)
    ctl.update_pointer(t0 + 1.1, None)


def complete_lines(ctl, n):
    for k in range(n):
        letter(ctl, 200 + 40 * k)
        dwell(ctl, "lines:complete", 10.0 * k)


def drawn_texts(monkeypatch, fn):
    """The texts typeset (Pillow, D64) while `fn` runs."""
    texts, real = [], typeset.draw
    monkeypatch.setattr(typeset, "draw", lambda img, ops: (texts.extend(op[2] for op in ops if op[0] == "text"),
                                                          real(img, ops))[1])
    fn()
    monkeypatch.setattr(typeset, "draw", real)
    return texts


def put_texts(monkeypatch, module, fn):
    """The texts drawn with OpenCV's putText in `module` while `fn` runs (the toolbar, hints and panels)."""
    texts, real = [], cv2.putText
    monkeypatch.setattr(module.cv2, "putText", lambda img, text, *a, **k: (texts.append(text), real(img, text, *a, **k))[1])
    fn()
    monkeypatch.setattr(module.cv2, "putText", real)
    return texts


# -- layout and configuration -------------------------------------------------------------------------------------

def test_the_layout_fits_the_canvas_next_to_the_panels_and_matches_the_config():
    tb = Toolbar(SIZE, ai=True)
    layout = LinesLayout(SIZE, tb.top)
    assert layout.zone == DEFAULT_ZONE and layout.notes == DEFAULT_NOTES and layout.visible == 5
    board = BoardPanel(SIZE).rect
    column = layout.controls.column
    for name, r in [("zone", layout.zone), ("notes", layout.notes), ("column", column)] + \
            [(b.name, b.rect) for b in layout.buttons]:
        assert 0 <= r[0] < r[2] <= SIZE[0] and 0 <= r[1] < r[3] <= tb.top, name
    assert layout.notes[2] < column[0] and column[1::2] == layout.notes[1::2]   # D71: the scroll column right of
    for r in [b.rect for b in layout.buttons[1:]] + [layout.track]:             # the notes, its buttons and track in it
        assert column[0] < r[0] < r[2] < column[2] and column[1] < r[1] < r[3] < column[3]
    assert layout.buttons[2].rect[1] - layout.buttons[1].rect[3] > layout.track[3] - layout.track[1] > 100
    assert layout.buttons[0].rect[1] >= board[3]                            # DONE below the PAGES panel
    assert layout.buttons[0].rect == (1112, 465, 1244, 525)                 # D71: right of the zone, centred on it
    bx0, by0, bx1, by1 = layout.bar                                         # D64: the review bar between them
    assert layout.notes[3] <= by0 and by1 < layout.zone[1] and bx1 == column[2]
    assert [b.name for b in layout.review_buttons] == ["lines:ok", "lines:written", "lines:edit", "lines:ink",
                                                       "lines:retry"]
    for b in layout.review_buttons:
        x0, y0, x1, y1 = b.rect
        assert bx0 < x0 < x1 <= bx1 and by0 < y0 < y1 < by1 and x0 > layout.bar_text_right and y1 - y0 == 46
    assert len(layout.rows) == 5 and layout.rows[-1].rect[3] < layout.notes[3]
    above, below = layout.rows[0].rect[1] - layout.notes[1], layout.notes[3] - layout.rows[-1].rect[3]
    assert abs(above - below) <= 1                                          # D71: the rows centred in the panel
    assert layout.zone[1] < layout.baseline < layout.zone[3]
    cfg = load_config().smart_lines
    same = LinesLayout(SIZE, tb.top, cfg.zone, cfg.notes, cfg.line_height, cfg.line_spacing, cfg.numbering,
                       cfg.font, cfg.text_size)
    assert (same.zone, same.notes, same.visible, same.numbering, same.text_size) == \
        (layout.zone, layout.notes, 5, "1.", 30)
    with pytest.raises(ValueError):
        LinesLayout(SIZE, tb.top, zone=(24, 400, 1080, 700))               # into the toolbar
    with pytest.raises(ValueError):
        LinesLayout(SIZE, tb.top, notes=(24, 300, 900, 450))               # overlaps the zone
    with pytest.raises(ValueError, match="review bar"):
        LinesLayout(SIZE, tb.top, notes=(40, 40, 900, 360))               # no room left for the review bar
    with pytest.raises(ValueError, match="text_size"):
        LinesLayout(SIZE, tb.top, text_size=48)                            # taller than a line
    with pytest.raises(ValueError):
        LinesLayout(SIZE, tb.top, numbering="#")
    assert [LinesLayout(SIZE, tb.top, numbering=n).number_label(3) for n in ("1.", "1)", "(1)", "none")] == \
        ["3.", "3)", "(3)", ""]


@pytest.mark.parametrize("key, value", [("numbering", "#1"), ("zone", [24, 360, 1080]), ("line_height", 8),
                                        ("notes", [24.0, 16, 900, 336]), ("text_size", 45), ("text_size", 30.0),
                                        ("font", "segoeui.png")])
def test_a_wrong_smart_lines_config_is_refused(key, value):
    with open(DEFAULT_CONFIG_PATH, "rb") as f:
        data = copy.deepcopy(tomllib.load(f))
    data["smart_lines"][key] = value
    with pytest.raises(ConfigError, match="smart_lines"):
        config_from_dict(data)


# -- writing, completing, undo -----------------------------------------------------------------------------------

def test_lines_writes_only_inside_the_zone_and_pen_is_unchanged():
    ctl = lines_controller()
    letter(ctl, 300)
    assert len(ctl.sheet().canvas.strokes) == 1 and ctl.canvas.strokes == {} and ctl.log["line_strokes"] == 1
    stroke(ctl, [(300, 150), (400, 150)], end=False)                        # starts in the notes area: no ink
    assert ctl.blocked == "zone" and ctl.log["line_starts_outside_zone"] == 1 and len(ctl.sheet().canvas.strokes) == 1
    ctl.handle([Event(STROKE_POINT, 0.0, (320, Y)), Event(STROKE_POINT, 0.0, (360, Y)),   # D66: the same pointing
                Event(STROKE_END, 0.0)])                                    # goes on into the zone: ink from there
    strokes = list(ctl.sheet().canvas.strokes.values())
    assert ctl.blocked is None and len(strokes) == 2 and strokes[1].points[0] == (320, Y) and ctl.canvas.strokes == {}
    ctl.press("pen")
    stroke(ctl, [(300, 150), (400, 150)])                                   # PEN draws anywhere, as before
    stroke(ctl, [(300, Y), (400, Y)])
    assert len(ctl.canvas.strokes) == 2 and len(ctl.sheet().canvas.strokes) == 2 and ctl.log["strokes"] == 2


def test_complete_line_keeps_the_handwriting_exactly_and_numbers_the_lines(monkeypatch):
    ctl = lines_controller()
    letter(ctl, 300)
    letter(ctl, 340)
    written = list(ctl.sheet().canvas.strokes.values())
    snapshot = [(s.id, list(s.points), s.color, s.width) for s in written]
    assert ctl.lines_enabled("lines:complete")
    dwell(ctl, "lines:complete")
    sheet = ctl.sheet()
    assert len(sheet.lines) == 1 and sheet.lines[0].id == 1 and sheet.canvas.strokes == {}
    assert sheet.lines[0].strokes == written and all(a is b for a, b in zip(sheet.lines[0].strokes, written))
    assert [(s.id, s.points, s.color, s.width) for s in sheet.lines[0].strokes] == snapshot
    assert not ctl.lines_enabled("lines:complete")
    dwell(ctl, "lines:complete", 5.0)                                       # nothing written: a message, no line
    assert len(sheet.lines) == 1 and ctl.log["lines:complete_empty"] == 1 and "Nothing written" in ctl.notice["text"]
    letter(ctl, 300)
    dwell(ctl, "lines:complete", 10.0)
    assert [line.id for line in sheet.lines] == [1, 2] and ctl.log["lines:complete"] == 2
    texts = drawn_texts(monkeypatch, lambda: render_sheet(sheet, ctl.lines_layout, True))
    assert "1." in texts and "2." in texts


def test_undo_and_redo_cover_smart_lines_and_never_the_freehand_page():
    ctl = DrawingController(Canvas(SIZE), Toolbar(SIZE))
    stroke(ctl, [(300, 150), (400, 150)])                                   # freehand ink on the page
    ctl.press("lines")
    letter(ctl, 300)
    letter(ctl, 340)
    dwell(ctl, "lines:complete")
    letter(ctl, 300)
    sheet, line = ctl.sheet(), ctl.sheet().lines[0]
    ctl.undo()                                                              # the last unfinished stroke
    assert sheet.canvas.strokes == {} and len(sheet.lines) == 1
    ctl.undo()                                                              # COMPLETE LINE: back to unfinished
    assert sheet.lines == [] and len(sheet.canvas.strokes) == 2 and len(ctl.canvas.strokes) == 1
    ctl.redo()
    assert sheet.lines == [line] and sheet.lines[0].id == 1 and sheet.canvas.strokes == {}
    ctl.redo()
    assert len(sheet.canvas.strokes) == 1
    ctl.press("pen")
    ctl.undo()                                                              # PEN: the page's ink only
    assert ctl.canvas.strokes == {} and sheet.lines == [line] and len(sheet.canvas.strokes) == 1


def test_clear_with_lines_clears_only_the_unfinished_line():
    ctl = DrawingController(Canvas(SIZE), Toolbar(SIZE))
    stroke(ctl, [(300, 150), (400, 150)])
    ctl.press("lines")
    complete_lines(ctl, 1)
    letter(ctl, 300)
    ctl.press("clear")
    sheet = ctl.sheet()
    assert sheet.canvas.strokes == {} and len(sheet.lines) == 1 and len(ctl.canvas.strokes) == 1
    ctl.undo()
    assert len(sheet.canvas.strokes) == 1


def test_the_unfinished_line_is_kept_across_tools_pages_and_documents(tmp_path):
    ctl = lines_controller()
    letter(ctl, 300)
    letter(ctl, 340)
    draft = dict(ctl.sheet().canvas.strokes)
    ctl.press("pen")
    stroke(ctl, [(250, Y), (450, Y)])                                       # freehand over the zone
    ctl.press("eraser")
    stroke(ctl, [(300, Y - 40), (340, Y + 40)])                             # erases page ink, never the line
    assert ctl.sheet().canvas.strokes == draft
    ctl.press("lines")
    letter(ctl, 380)
    assert len(ctl.sheet().canvas.strokes) == 3
    ctl.press("pages")
    ctl.press("board:add")                                                  # page 2 has its own Smart Lines
    assert ctl.sheet().canvas.strokes == {} and ctl.tool == "lines"
    letter(ctl, 300)
    ctl.press("board:prev")
    assert len(ctl.sheet().canvas.strokes) == 3
    path = tmp_path / "photo.png"
    cv2.imencode(".png", np.full((200, 300, 3), 90, np.uint8))[1].tofile(str(path))
    ctl.set_reference(Reference.open(path))                                 # a document: LINES pauses
    assert ctl.tool == "pen" and not ctl.lines_active and "paused" in ctl.notice["text"]
    ctl.press("lines")
    assert ctl.tool == "pen" and ctl.log["lines:refused_doc"] == 1
    ctl.press("board:view")                                                 # back to the whiteboard
    ctl.press("lines")
    assert ctl.lines_active and len(ctl.sheet().canvas.strokes) == 3 and len(ctl.board.pages[1].lines.canvas.strokes) == 1
    page_ink = dict(ctl.canvas.strokes)
    stroke(ctl, [(500, Y), (520, Y)], end=False)                            # a line stroke still going on ...
    ctl.press("pen")                                                        # ... ends in the line when PEN is pressed
    assert len(ctl.sheet().canvas.strokes) == 4 and ctl.blocked == "panel"
    ctl.handle([Event(STROKE_POINT, 0.0, (560, Y)), Event(STROKE_END, 0.0)])
    assert ctl.canvas.strokes == page_ink and len(ctl.sheet().canvas.strokes) == 4    # nothing more drawn anywhere


def test_a_colour_keeps_lines_and_selects_pen_otherwise():
    ctl = lines_controller()
    ctl.press("red")
    assert ctl.tool == "lines" and ctl.colour == "red"
    letter(ctl, 300)
    assert next(iter(ctl.sheet().canvas.strokes.values())).color == (40, 40, 215)
    ctl.press("eraser")
    ctl.press("blue")
    assert ctl.tool == "lines"                                              # D78: the Smart Lines eraser -> LINES
    ctl.press("pen")
    ctl.press("eraser")
    ctl.press("blue")
    assert ctl.tool == "pen"                                                # unchanged outside LINES


def test_the_notes_area_scrolls_when_it_fills_up(monkeypatch):
    ctl = lines_controller()
    complete_lines(ctl, 9)
    sheet, layout = ctl.sheet(), ctl.lines_layout
    assert layout.visible == 5 and sheet.first_shown(5) == 4                # the newest line in view
    assert ctl.lines_enabled("lines:up") and not ctl.lines_enabled("lines:down")
    texts = drawn_texts(monkeypatch, lambda: render_sheet(sheet, layout, True))
    assert "5." in texts and "9." in texts and "4." not in texts
    texts = drawn_texts(monkeypatch, lambda: render_controls(layout, ctl.lines_view()))
    assert texts[:4] == ["DONE", "9", "/", "9"]                             # D71: the counter, last shown / all
    dwell(ctl, "lines:up", 100.0)
    assert sheet.first_shown(5) == 3 and ctl.lines_enabled("lines:down")
    assert drawn_texts(monkeypatch, lambda: render_controls(layout, ctl.lines_view()))[1:4] == ["8", "/", "9"]
    dwell(ctl, "lines:down", 110.0)
    dwell(ctl, "lines:down", 120.0)
    assert sheet.first_shown(5) == 4 and ctl.log["lines:scroll_limit"] == 1
    ctl.undo()                                                              # a line goes: still the newest in view
    assert len(sheet.lines) == 8 and sheet.first_shown(5) == 3


# -- the wall ------------------------------------------------------------------------------------------------------

def test_rendering_with_and_without_smart_lines(monkeypatch):
    plain = DrawingController(Canvas(SIZE), Toolbar(SIZE))
    stroke(plain, [(300, 150), (400, 150)])
    assert plain.background is None                                         # no Smart Lines: as before
    ctl = lines_controller()
    r = CanvasRenderer(SIZE)
    layout = ctl.lines_layout
    img = r.render(ctl.canvas, ctl, ctl.toolbar, mode=HOVER, cursor=None)
    zx0, zy0, zx1, zy1 = layout.zone
    assert (img[zy0:zy0 + 2, zx0 + 2:zx0 + 20] < 230).any(axis=0).all()      # D64: a corner guide ...
    edge = img[zy0:zy0 + 4, zx0 + 60:zx1 - 60].min(axis=(0, 2))
    assert (edge > 225).sum() > 200 and (edge < 200).sum() > 400 and edge.min() >= 140   # D71: a light dashed frame
    assert (img[layout.baseline, zx0 + 40:zx1 - 40] < 255).all()            # the baseline
    cx0, cy0, cx1, cy1 = layout.buttons[0].rect
    assert (img[cy0:cy1, cx0:cx1] < 250).any()                              # DONE
    tx0, ty0, tx1, ty1 = layout.track
    assert (img[ty0 + 4:ty1 - 4, tx0 + 2] < 255).all()                      # the scroll track
    assert (img[layout.bar[1]:layout.bar[3], layout.bar[0]:layout.bar[2]] == 255).all()   # nothing to review
    first = ctl.background
    assert ctl.background is first                                          # cached while nothing changes
    letter(ctl, 300)
    assert ctl.background is not first
    ctl.press("pen")                                                        # PEN with an unfinished line: faint zone
    img = r.render(ctl.canvas, ctl, ctl.toolbar, mode=HOVER, cursor=None)
    assert (img[cy0:cy1, cx0:cx1] == 255).all() and (img[ty0:ty1, tx0:tx1] == 255).all()   # no Smart Lines buttons
    assert tuple(img[layout.baseline, zx0 + 200]) == lines_module.IDLE_BASELINE
    assert (img[zy0:zy0 + 2, zx0 + 2:zx0 + 20] == 255).all()                # no corner guides
    ctl.press("lines")
    stroke(ctl, [(300, 150), (320, 150)], end=False)                        # refused outside the zone
    texts = put_texts(monkeypatch, __import__("invisible_canvas.canvas.render", fromlist=["cv2"]),
                      lambda: r.render(ctl.canvas, ctl, ctl.toolbar, mode=DRAW, cursor=(320, 150)))
    assert ZONE_HINT in texts


def test_a_line_stroke_that_reaches_complete_line_ends_there():
    ctl = lines_controller()
    cx0, cy0, cx1, cy1 = ctl.lines_layout.buttons[0].rect
    y = (cy0 + cy1) / 2                                                     # inside the zone, level with DONE
    stroke(ctl, [(900, y), (1000, y), ((cx0 + cx1) / 2, y), ((cx0 + cx1) / 2 + 5, y)], end=False)
    assert ctl.blocked == "zone" and ctl.log["line_strokes_left_zone"] == 1  # D66: it ended where it left the zone
    s = next(iter(ctl.sheet().canvas.strokes.values()))
    assert max(x for x, _ in s.points) < ctl.lines_layout.zone[2] < cx0     # nothing on the button


# -- the board file ------------------------------------------------------------------------------------------------

def test_the_board_file_keeps_smart_lines_and_older_files_still_load():
    ctl = lines_controller()
    complete_lines(ctl, 7)
    dwell(ctl, "lines:up", 100.0)
    letter(ctl, 300)                                                        # an unfinished line on page 1
    ctl.press("pages")
    ctl.press("board:add")
    letter(ctl, 400)                                                        # and on page 2
    data = json.loads(json.dumps(ctl.board.to_dict()))
    assert [x is not None for x in data["smart_lines"]] == [True, True]
    again = Board.from_dict(data)
    for before, after in zip(ctl.board.pages, again.pages):
        a, b = before.lines, after.lines
        assert [line.id for line in a.lines] == [line.id for line in b.lines] and a.scroll == b.scroll
        for la, lb in zip(a.lines, b.lines):
            assert [(s.id, s.color, s.width) for s in la.strokes] == [(s.id, s.color, s.width) for s in lb.strokes]
            assert all(np.allclose(sa.array(), sb.array(), atol=0.006) for sa, sb in zip(la.strokes, lb.strokes))
        assert a.canvas.strokes.keys() == b.canvas.strokes.keys()
    restored = DrawingController(Canvas(SIZE), Toolbar(SIZE), board=again)
    restored.board.current = 0
    restored.press("lines")
    assert restored.sheet().first_shown(5) == 1 and len(restored.sheet().canvas.strokes) == 1
    letter(restored, 340)
    dwell(restored, "lines:complete")
    sheet = restored.sheet()
    assert sheet.lines[-1].id == 8                                          # ids go on, never reused
    all_ids = [s.id for line in sheet.lines for s in line.strokes]
    assert len(all_ids) == len(set(all_ids))
    plain = DrawingController(Canvas(SIZE), Toolbar(SIZE))
    stroke(plain, [(300, 150), (400, 150)])
    assert "smart_lines" not in plain.board.to_dict()                       # unused: the file is as before
    old = plain.board.to_dict()
    assert Board.from_dict(old).pages[0].lines is None
    assert Board.from_dict(Canvas(SIZE).to_dict()).pages[0].lines is None
    with pytest.raises(ValueError):
        LineSheet.from_dict({"format": "something else", "version": 1}, SIZE)


# -- the AI --------------------------------------------------------------------------------------------------------

def test_the_ai_stays_available_with_lines():
    ctl = DrawingController(Canvas(SIZE), Toolbar(SIZE, ai=True))
    stroke(ctl, [(300, 150), (400, 150)])                                   # freehand ink
    ctl.press("lines")
    letter(ctl, 300)
    ctl.press("ai")
    assert ctl.panel["state"] == "menu" and ctl.tool == "lines"
    ctl.press("ai:summarize")
    (action, png, context), = ctl.take_ai_jobs()
    assert action == "summarize" and context == {"source": "canvas"}       # the page's ink, as before (Phase 1)
    cx0, cy0, cx1, cy1 = ctl.lines_layout.buttons[0].rect
    ctl.update_pointer(0.0, ((cx0 + cx1) / 2, (cy0 + cy1) / 2))             # DONE's own place: under the AI panel
    #                                                                         (D65: DONE stands beside it, below)
    ctl.update_pointer(1.05, ((cx0 + cx1) / 2, (cy0 + cy1) / 2))
    assert ctl.sheet().lines == [] and len(ctl.sheet().canvas.strokes) == 1


# -- D66: ink only inside the writing zone (wall test run 1) --------------------------------------------------------

def in_zone(ctl, p):
    x0, y0, x1, y1 = ctl.lines_layout.zone
    return x0 <= p[0] < x1 and y0 <= p[1] < y1


def test_a_line_stroke_rising_into_the_zone_from_below_writes_from_where_it_enters():
    # The wall case (R42): pointing already while the hand rises into the zone; the stroke starts just below it
    ctl = lines_controller()
    zy1 = ctl.lines_layout.zone[3]
    stroke(ctl, [(300, zy1 + 50), (300, zy1 + 30), (300, zy1 + 10), (300, zy1 - 5), (305, zy1 - 30), (310, zy1 - 70)])
    (s,) = ctl.sheet().canvas.strokes.values()
    assert s.points[0] == (300, zy1 - 5) and s.points[-1] == (310, zy1 - 70) and all(in_zone(ctl, p) for p in s.points)
    assert ctl.log["line_starts_outside_zone"] == 1 and ctl.log["line_strokes_entered_zone"] == 1
    top = ctl.toolbar.top                                                   # from the toolbar band too, with LINES
    stroke(ctl, [(500, top + 40), (500, top + 10), (500, zy1 + 5), (500, zy1 - 10), (520, zy1 - 40)])
    assert len(ctl.sheet().canvas.strokes) == 2 and ctl.log["line_strokes_entered_zone"] == 2
    ctl.handle([Event(STROKE_START, 0.0, None), Event(STROKE_POINT, 0.0, None),          # no point at the start:
                Event(STROKE_POINT, 0.0, (600, zy1 - 20)), Event(STROKE_END, 0.0)])     # waits, then writes
    assert len(ctl.sheet().canvas.strokes) == 3
    ctl.press("pen")                                                        # PEN keeps D56: a start on the toolbar
    stroke(ctl, [(500, top + 40), (500, top + 10), (500, zy1 - 10), (520, zy1 - 40)], end=False)
    assert ctl.blocked == "toolbar" and ctl.canvas.strokes == {} and ctl.log["strokes_refused_on_toolbar"] == 1
    ctl.handle([Event(STROKE_END, 0.0)])


def test_a_line_stroke_leaving_the_zone_ends_there_and_begins_again_when_it_comes_back():
    ctl = lines_controller()
    zx0, zy0, zx1, zy1 = ctl.lines_layout.zone
    stroke(ctl, [(300, zy0 + 50), (300, zy0 + 20), (300, zy0 - 20), (300, 150), (320, zy0 + 20), (340, zy0 + 50)])
    a, b = ctl.sheet().canvas.strokes.values()                             # (points are filled in every 2 px)
    assert (a.points[0], a.points[-1], b.points[0], b.points[-1]) == ((300, zy0 + 50), (300, zy0 + 20),
                                                                      (320, zy0 + 20), (340, zy0 + 50))
    assert ctl.log["line_strokes_left_zone"] == 1 and ctl.log["line_strokes_entered_zone"] == 1
    stroke(ctl, [(zx1 - 40, Y), (zx1 + 60, Y), (zx1 + 120, Y)])             # off the right end: nothing beyond it
    assert all(in_zone(ctl, p) for s in ctl.sheet().canvas.strokes.values() for p in s.points)
    ctl.undo()                                                              # each piece is its own undo step
    assert len(ctl.sheet().canvas.strokes) == 2


def test_after_done_pressed_while_pointing_the_next_line_is_written_by_pointing_back_into_the_zone():
    ctl = lines_controller()
    letter(ctl, 300)
    done = ctl.lines_layout.button("lines:complete")
    ctl.handle([Event(STROKE_START, 0.0, (900, Y)), Event(STROKE_POINT, 0.0, (1000, Y)),
                Event(STROKE_POINT, 0.0, done.centre)])                     # pointing on to DONE: the stroke ends
    ctl.update_pointer(0.0, done.centre)
    ctl.update_pointer(1.05, done.centre)                                   # DONE pressed while still pointing
    sheet = ctl.sheet()
    assert len(sheet.lines) == 1 and len(sheet.lines[0].strokes) == 2 and ctl.blocked == "zone"
    ctl.update_pointer(1.1, (400, Y))
    ctl.handle([Event(STROKE_POINT, 0.0, (400, Y)), Event(STROKE_POINT, 0.0, (420, Y + 10)),
                Event(STROKE_END, 0.0)])                                    # back in the zone: the next line
    (s,) = sheet.canvas.strokes.values()
    assert s.points[0] == (400, Y) and len(sheet.lines) == 1
    ctl.handle([Event(STROKE_START, 0.0, (300, 150))])                      # waiting outside the zone ...
    ctl.press("pen")                                                        # ... and LINES left: nothing until
    ctl.handle([Event(STROKE_POINT, 0.0, (300, Y)), Event(STROKE_POINT, 0.0, (320, Y))])   # the lift (D56)
    assert ctl.blocked == "panel" and ctl.canvas.strokes == {} and len(sheet.canvas.strokes) == 1
    ctl.handle([Event(STROKE_END, 0.0)])


def test_undo_redo_and_clear_with_lines_say_when_there_is_nothing_for_them():
    ctl = DrawingController(Canvas(SIZE), Toolbar(SIZE))
    stroke(ctl, [(300, 150), (400, 150)])                                   # the page's ink
    ctl.undo()
    ctl.redo()
    assert ctl.notice is None and len(ctl.canvas.strokes) == 1              # PEN: as before, no message
    ctl.press("lines")
    for action, words in (("undo", "Nothing to undo"), ("redo", "Nothing to redo"), ("clear", "choose PEN")):
        ctl.notice = None
        ctl.press(action)
        assert words in ctl.notice["text"] and ctl.log[f"lines:nothing_to_{action}"] == 1, action
    assert len(ctl.canvas.strokes) == 1                                     # the page's ink untouched
    letter(ctl, 300)
    ctl.notice = None
    ctl.press("clear")                                                      # something to clear: no message
    assert ctl.notice is None and ctl.sheet().canvas.strokes == {} and ctl.log["clear"] == 1
    ctl.press("undo")
    assert ctl.notice is None and len(ctl.sheet().canvas.strokes) == 1


def test_the_writing_guides_and_greyed_buttons_are_dark_enough_for_the_wall():
    # Wall test run 1: greys of 185-235 were barely or not visible in the camera frames
    ctl = lines_controller()
    img = CanvasRenderer(SIZE).render(ctl.canvas, ctl, ctl.toolbar, mode=HOVER, cursor=None)
    layout = ctl.lines_layout
    zx0, zy0, zx1, zy1 = layout.zone
    assert img[zy0:zy0 + 4, zx0 + 5:zx0 + 30].min() <= 130                  # corner guides
    assert img[zy1 - 4:zy1, zx1 - 30:zx1 - 5].min() <= 130
    assert img[layout.baseline - 1:layout.baseline + 2, zx0 + 100:zx0 + 200].min(axis=0).max() <= 180   # baseline
    assert img[zy0 + 16:zy0 + 48, zx0 + 44:zx0 + 160].min() <= 130          # "Write here", in the zone (D71)
    x0, y0, x1, y1 = layout.button("lines:complete").rect                   # DONE, greyed (nothing written)
    assert not ctl.lines_enabled("lines:complete") and img[y0:y1, x0:x1].min() <= 175
    tx0, ty0, tx1, ty1 = layout.track
    assert img[ty0 + 10:ty1 - 10, tx0 + 2:tx1 - 2].max() <= 210             # the scroll track
    x0, y0, x1, y1 = layout.button("lines:up").rect                         # an arrow, greyed
    assert img[y0 + 2:y1 - 2, x0 + 2:x1 - 2].min() <= 175


# -- D78: the eraser on the line being written (wall test 2026-10-31: ERASER did nothing on a Smart Line) ------------

def test_eraser_chosen_while_writing_lines_rubs_out_the_line_and_undo_stays_on_the_smart_lines():
    ctl = DrawingController(Canvas(SIZE), Toolbar(SIZE))
    stroke(ctl, [(200.0, 150.0), (400.0, 150.0)])                           # PEN: ink on the page, above the zone
    ctl.press("lines")
    stroke(ctl, [(200.0, float(Y)), (400.0, float(Y))])                     # the line being written
    sheet = ctl.sheet()
    assert len(sheet.canvas.strokes) == 1 and len(ctl.board.page.canvas.strokes) == 1
    ctl.press("eraser")
    assert ctl.tool == "eraser" and ctl.lines_active and ctl.target is sheet and "Smart Line" in ctl.notice["text"]
    stroke(ctl, [(300.0, Y - 3.0), (300.0, Y + 3.0)])                       # rub out its middle
    assert len(sheet.canvas.strokes) == 2                                   # two pieces of the line are left
    left = sorted(max(x for x, _ in s.points) for s in sheet.canvas.strokes.values())
    assert left[0] < 300 - ctl.eraser_radius + 3 and len(ctl.board.page.canvas.strokes) == 1   # the page untouched
    stroke(ctl, [(300.0, 150.0), (300.0, 152.0)])                           # outside the zone: it waits, nothing gone
    assert len(ctl.board.page.canvas.strokes) == 1 and ctl.log["lines:eraser"] == 1
    ctl.undo()
    assert len(sheet.canvas.strokes) == 1 and len(ctl.board.page.canvas.strokes) == 1   # the Smart Lines' undo
    ctl.redo()
    assert len(sheet.canvas.strokes) == 2
    ctl.press("lines")                                                      # writing again, on the same line
    assert ctl.tool == "lines" and not ctl.lines_eraser
    letter(ctl, 500)
    dwell(ctl, "lines:complete")
    assert len(sheet.lines) == 1 and len(sheet.lines[0].strokes) == 3 and not sheet.canvas.strokes
    ctl.press("pen")
    ctl.press("eraser")                                                     # from PEN: the page's ink, as before
    assert not ctl.lines_active and ctl.target is ctl.board.page
    stroke(ctl, [(300.0, 147.0), (300.0, 153.0)])
    assert len(ctl.board.page.canvas.strokes) == 2 and len(sheet.lines[0].strokes) == 3


def test_from_the_smart_lines_eraser_a_colour_writes_lines_again_and_voice_or_a_document_end_it(tmp_path):
    ctl = lines_controller()
    letter(ctl, 300)
    ctl.press("eraser")
    ctl.press("red")
    assert ctl.tool == "lines" and ctl.colour == "red" and not ctl.lines_eraser
    ctl.press("eraser")
    ctl.press("eraser")                                                     # pressed again: still on the Smart Line
    assert ctl.lines_active and ctl.log["lines:eraser"] == 2                # entered twice, told once each time
    voice = DrawingController(Canvas(SIZE), Toolbar(SIZE, voice=True))
    voice.press("lines")
    voice.press("eraser")
    voice.press("voice")
    assert voice.tool == "pen" and not voice.lines_eraser and voice.voice_open
    img = np.full((300, 400, 3), 200, np.uint8)
    cv2.imwrite(str(tmp_path / "page.png"), img)
    ctl.set_reference(Reference.open(tmp_path / "page.png"))
    assert ctl.view == "doc" and not ctl.lines_active and not ctl.lines_eraser and ctl.target is ctl._layer()
