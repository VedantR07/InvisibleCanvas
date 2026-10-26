"""Whiteboard pages (brain.md D59): the board, the controller on the current page (content, undo / redo,
selection, AI, eraser, clear), the board panel, saving and loading, rendering."""

import numpy as np
import pytest

from invisible_canvas.canvas.board import Board
from invisible_canvas.canvas.model import Canvas, Stroke
from invisible_canvas.canvas.render import CanvasRenderer
from invisible_canvas.canvas.toolbar import Toolbar
from invisible_canvas.interaction.drawing import DrawingController
from invisible_canvas.interaction.engine import DRAW, HOVER, STROKE_END, STROKE_POINT, STROKE_START, Event

SIZE = (1280, 720)


def ev(kind, point=None):
    return Event(kind, 0.0, point)


def stroke(ctl, points):
    ctl.handle([ev(STROKE_START, points[0])] + [ev(STROKE_POINT, p) for p in points[1:]] + [ev(STROKE_END)])


def ids(canvas):
    return sorted(canvas.strokes)


def test_a_board_starts_with_one_blank_page_and_adds_pages_after_the_current_one():
    b = Board(SIZE)
    assert b.count == 1 and b.label() == "Page 1 of 1" and not b.can_previous and not b.can_next
    first = b.page
    assert b.add_page() == 1 and b.label() == "Page 2 of 2" and b.page.canvas.strokes == {}
    assert b.previous() and b.page is first and b.label() == "Page 1 of 2"
    b.add_page()                                                  # inserted after page 1, not at the end
    assert b.label() == "Page 2 of 3" and b.can_previous and b.can_next
    assert b.next() and b.label() == "Page 3 of 3" and not b.next() and b.label() == "Page 3 of 3"
    assert b.previous() and b.previous() and not b.previous() and b.current == 0


def test_every_page_keeps_its_own_drawing_and_new_pages_start_blank():
    ctl = DrawingController(Canvas(SIZE), Toolbar(SIZE))
    stroke(ctl, [(100, 100), (300, 100)])
    page1 = ctl.canvas
    ctl.press("board:add")
    assert ctl.canvas is not page1 and ctl.canvas.strokes == {}           # blank
    stroke(ctl, [(100, 400), (300, 400)])
    stroke(ctl, [(500, 400), (700, 400)])
    page2_ids = ids(ctl.canvas)
    ctl.press("board:prev")
    assert ctl.canvas is page1 and len(page1.strokes) == 1                # untouched by page 2
    ctl.press("board:next")
    assert ids(ctl.canvas) == page2_ids and ctl.log["page:add"] == 1 and ctl.log["page:prev"] == 1


def test_undo_and_redo_never_reach_another_page():
    ctl = DrawingController(Canvas(SIZE), Toolbar(SIZE))
    stroke(ctl, [(100, 100), (300, 100)])
    ctl.press("board:add")
    stroke(ctl, [(100, 400), (300, 400)])
    ctl.undo()
    assert ctl.canvas.strokes == {}                                        # page 2's stroke only
    ctl.press("board:prev")
    assert len(ctl.canvas.strokes) == 1
    ctl.undo()
    assert ctl.canvas.strokes == {}
    ctl.redo()
    assert len(ctl.canvas.strokes) == 1
    ctl.press("board:next")
    ctl.redo()                                                             # page 2 still has its own redo
    assert len(ctl.canvas.strokes) == 1 and ctl.canvas.strokes[next(iter(ctl.canvas.strokes))].points[0][1] == 400


def test_erase_and_clear_act_on_the_current_page_only():
    ctl = DrawingController(Canvas(SIZE), Toolbar(SIZE))
    stroke(ctl, [(100, 300), (500, 300)])
    page1 = ctl.canvas
    ctl.press("board:add")
    stroke(ctl, [(100, 300), (500, 300)])
    ctl.press("eraser")
    stroke(ctl, [(300, 300), (300, 310)])
    assert len(ctl.canvas.strokes) == 2 and len(page1.strokes) == 1      # page 2 split, page 1 whole
    ctl.clear()
    assert ctl.canvas.strokes == {} and len(page1.strokes) == 1


def test_selection_and_the_ai_read_the_current_page():
    ctl = DrawingController(Canvas(SIZE), Toolbar(SIZE, ai=True))
    stroke(ctl, [(300, 200), (340, 200)])
    ctl.press("select")
    stroke(ctl, [(250, 150), (400, 150), (400, 250), (250, 250), (250, 160)])
    assert ctl.selection != []
    ctl.press("pages")
    ctl.press("board:add")
    assert ctl.selection == [] and ctl.board_open                          # a new page: nothing selected
    ctl.press("ai")                                                        # the AI panel replaces the board panel
    assert ctl.panel is not None and not ctl.board_open
    ctl.press("ai:summarize")
    assert ctl.panel["state"] == "error" and "Nothing written" in ctl.panel["message"] and ctl.take_ai_jobs() == []
    ctl.press("pages")
    ctl.press("board:prev")
    ctl.press("ai")
    ctl.press("ai:summarize")
    (action, png, context), = ctl.take_ai_jobs()                           # page 1's writing
    assert action == "summarize" and png[:4] == b"\x89PNG" and context == {"source": "canvas"}


def test_the_board_panel_buttons_and_their_limits():
    ctl = DrawingController(Canvas(SIZE), Toolbar(SIZE))
    tb = ctl.toolbar
    for t in np.arange(0.0, 1.2, 0.05):                                    # PAGES by dwell
        ctl.update_pointer(float(t), tb.button("pages").centre)
    assert ctl.board_open and ctl.log["press:pages"] == 1
    prev = next(b for b in ctl.board_layout.buttons if b.name == "board:prev")
    assert not ctl.board_enabled("board:prev") and not ctl.board_enabled("board:next")
    for t in np.arange(2.0, 3.2, 0.05):
        ctl.update_pointer(float(t), prev.centre)
    assert ctl.log["page_limit"] == 1 and ctl.board.current == 0          # page 1: nothing happens
    ctl.press("board:add")
    assert ctl.board_enabled("board:prev") and ctl.board_open              # stays open while flipping
    ctl.press("board:close")
    assert not ctl.board_open


def test_strokes_are_refused_under_the_board_panel_and_a_page_change_mid_stroke_draws_nothing():
    ctl = DrawingController(Canvas(SIZE), Toolbar(SIZE))
    ctl.press("pages")
    x0, y0, x1, y1 = ctl.board_layout.rect
    ctl.handle([ev(STROKE_START, ((x0 + x1) / 2, y1 - 5)), ev(STROKE_END)])
    assert ctl.log["strokes_refused_on_panel"] == 1 and ctl.canvas.strokes == {}
    ctl.handle([ev(STROKE_START, (200, 300)), ev(STROKE_POINT, (300, 300))])   # drawing while the panel is open
    page1 = ctl.canvas
    ctl.press("board:add")                                                 # e.g. pressed by a second hand / key
    assert len(page1.strokes) == 1 and ctl.blocked == "panel"              # finished on page 1
    ctl.handle([ev(STROKE_POINT, (400, 300)), ev(STROKE_END)])
    assert ctl.canvas.strokes == {} and ctl.blocked is None                # nothing on page 2


def test_the_board_is_saved_and_loaded_with_every_page():
    ctl = DrawingController(Canvas(SIZE), Toolbar(SIZE))
    stroke(ctl, [(100, 100), (300, 100)])
    ctl.press("board:add")
    stroke(ctl, [(100, 400), (300, 400)])
    stroke(ctl, [(500, 400), (700, 400)])
    ctl.press("board:prev")
    data = ctl.board.to_dict()
    back = Board.from_dict(data)
    assert back.count == 2 and back.current == 0 and back.size == SIZE
    assert [len(p.canvas.strokes) for p in back.pages] == [1, 2]
    assert back.pages[1].canvas.strokes[2].points == ctl.board.pages[1].canvas.strokes[2].points
    single = Board.from_dict(Canvas(SIZE).to_dict())                      # a canvas-*.json from before D59
    assert single.count == 1
    with pytest.raises(ValueError):
        Board.from_dict({"format": "invisible-canvas/board", "version": 99, "pages": []})


def test_rendering_shows_the_current_page_its_label_and_the_board_panel():
    ctl = DrawingController(Canvas(SIZE), Toolbar(SIZE))
    stroke(ctl, [(100, 300), (500, 300)])
    r = CanvasRenderer(SIZE)
    page1 = r.render(ctl.canvas, ctl, ctl.toolbar, mode=HOVER, cursor=None)
    assert (page1[15:35, 10:150] < 200).any()                              # "Page 1 of 1" top left
    ctl.press("board:add")
    page2 = r.render(ctl.canvas, ctl, ctl.toolbar, mode=HOVER, cursor=None)
    assert page1[300, 300].tolist() != [255, 255, 255] and page2[300, 300].tolist() == [255, 255, 255]
    ctl.press("pages")
    shown = r.render(ctl.canvas, ctl, ctl.toolbar, mode=DRAW, cursor=(640, 360))
    x0, y0, x1, y1 = ctl.board_layout.rect
    assert (shown[y0 + 5:y1 - 5, x0 + 5:x1 - 5] != page2[y0 + 5:y1 - 5, x0 + 5:x1 - 5]).any()
