"""Zoom on a document (brain.md D72): the zoom bar shown with a document, 100 % exactly as before, the page drawn
larger inside the white margin, dragged with MOVE as far as it still covers the window, the annotations kept on the
same place of the page at every zoom, saved with the board."""

import cv2
import numpy as np
from PIL import Image, ImageDraw
from synthetic_camera import CAMERA, H_REAL, truth, warp

from invisible_canvas.calibration.watch import canvas_corners, canvas_quad, moved_by
from invisible_canvas.canvas.lines import LABEL, LABEL_OFF, THUMB
from invisible_canvas.canvas.model import Canvas
from invisible_canvas.canvas.panel import ZoomBar
from invisible_canvas.canvas.reference import MARGIN, ZOOMS, Reference
from invisible_canvas.canvas.render import CanvasRenderer
from invisible_canvas.canvas.toolbar import WIDTHS, Toolbar
from invisible_canvas.interaction.drawing import DrawingController
from invisible_canvas.interaction.engine import HOVER, STROKE_END, STROKE_POINT, STROKE_START, Event

SIZE = (1280, 720)
TOP = Toolbar(SIZE).top
WINDOW = (MARGIN, MARGIN, SIZE[0] - MARGIN, TOP - MARGIN)


def write_image(path, image):
    cv2.imencode(path.suffix, image)[1].tofile(str(path))
    return path


def write_pdf(path, pages=3):
    colours = [(255, 255, 255), (230, 240, 255), (255, 240, 230)][:pages]
    images = [Image.new("RGB", (600, 800), c) for c in colours]       # portrait pages
    for image in images:
        ImageDraw.Draw(image).rectangle((20, 20, 120, 60), fill=(20, 20, 20))   # a dark mark at the top left
    images[0].save(str(path), save_all=True, append_images=images[1:], resolution=100)
    return path


def gradient(w=1200, h=800):
    """A picture whose colour says where its pixel is (blue: across, green: down)."""
    xs, ys = np.meshgrid(np.linspace(0, 255, w), np.linspace(0, 255, h))
    return np.dstack([xs, ys, np.full_like(xs, 128)]).astype(np.uint8)


def stroke(ctl, points):
    ctl.handle([Event(STROKE_START, 0.0, points[0])] + [Event(STROKE_POINT, 0.0, p) for p in points[1:]]
               + [Event(STROKE_END, 0.0)])


def doc_controller(ref, ai=True):
    ctl = DrawingController(Canvas(SIZE), Toolbar(SIZE, ai=ai))
    ctl.set_reference(ref)
    return ctl


def zoom_to(ctl, zoom):
    while ctl.reference.zoom < zoom:
        ctl.press("zoom:in")
    assert ctl.reference.zoom == zoom


def dwell(ctl, name, t0=0.0):
    point = ctl.zoom_bar.button(name).centre
    ctl.update_pointer(t0, point)
    ctl.update_pointer(t0 + 1.05, point)
    ctl.update_pointer(t0 + 1.1, None)


def render(ctl):
    return CanvasRenderer(SIZE).render(ctl.canvas, ctl, ctl.toolbar, mode=HOVER, cursor=None)


def old_display(ref):
    """The page as shown before D72 (brain.md D60), computed here on its own."""
    w, h = SIZE
    box_w, box_h = w - 2 * MARGIN, TOP - 2 * MARGIN
    page = ref.page_image(max(box_w, box_h))
    ph, pw = page.shape[:2]
    scale = min(box_w / pw, box_h / ph)
    fw, fh = max(int(round(pw * scale)), 1), max(int(round(ph * scale)), 1)
    fitted = cv2.resize(page, (fw, fh), interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
    out = np.full((h, w, 3), 255, np.uint8)
    x0, y0 = (w - fw) // 2, (TOP - fh) // 2
    out[y0:y0 + fh, x0:x0 + fw] = fitted
    return out


def test_at_100_percent_a_document_is_shown_exactly_as_before(tmp_path):
    for path in (write_image(tmp_path / "wide.png", gradient()), write_pdf(tmp_path / "lesson.pdf")):
        ref = Reference.open(path)
        before = old_display(ref)
        assert ref.zoom == 1.0 and ref.view(SIZE, TOP).identity
        assert np.array_equal(ref.display(SIZE, TOP), before)
        ref.zoom_in(SIZE, TOP)
        ref.zoom_in(SIZE, TOP)
        assert not ref.view(SIZE, TOP).identity and not np.array_equal(ref.display(SIZE, TOP), before)
        assert ref.set_zoom(1.0, SIZE, TOP) and ref.origin is None
        assert np.array_equal(ref.display(SIZE, TOP), before)          # FIT: the page whole, as before
        ctl = doc_controller(ref)
        assert ctl.page_view is None                                    # page coordinates are the wall's
        ref.close()


def test_the_zoom_steps_keep_the_window_centre_on_the_same_place_and_stop_at_the_limits(tmp_path):
    ref = Reference.open(write_image(tmp_path / "wide.png", gradient()))
    centre = ((WINDOW[0] + WINDOW[2]) / 2, (WINDOW[1] + WINDOW[3]) / 2)
    seen = [ref.zoom]
    assert ref.can_zoom_in and not ref.can_zoom_out and not ref.zoom_out(SIZE, TOP)
    while ref.can_zoom_in:
        page_point = ref.view(SIZE, TOP).to_page(centre)
        assert ref.zoom_in(SIZE, TOP)
        seen.append(ref.zoom)
        assert np.allclose(ref.view(SIZE, TOP).to_page(centre), page_point, atol=1.0)
    assert tuple(seen) == ZOOMS and not ref.zoom_in(SIZE, TOP) and ref.zoom == 4.0
    while ref.zoom_out(SIZE, TOP):
        pass
    assert ref.zoom == 1.0 and ref.origin is None


def test_the_zoomed_page_is_the_page_drawn_larger_inside_the_white_margin(tmp_path):
    ref = Reference.open(write_image(tmp_path / "wide.png", gradient()))
    whole = ref.display(SIZE, TOP).copy()
    ref.set_zoom(2.0, SIZE, TOP)
    view = ref.view(SIZE, TOP)
    shown = ref.display(SIZE, TOP)
    for wall in [(300, 200), (640, 324), (1000, 500), (WINDOW[0] + 1, WINDOW[1] + 1)]:
        px, py = view.to_page(wall)
        there = whole[int(round(py)), int(round(px))].astype(int)
        assert np.abs(shown[wall[1], wall[0]].astype(int) - there).max() <= 3
    x0, y0, x1, y1 = WINDOW
    assert (shown[y0:y1, x0:x1] != 255).any(axis=2).all()               # the page fills the window
    for margin in (shown[:y0], shown[y1:], shown[:, :x0], shown[:, x1:]):
        assert (margin == 255).all()                                     # the white margin (D58), the toolbar's band


def test_the_page_is_dragged_only_as_far_as_it_still_covers_the_window(tmp_path):
    ref = Reference.open(write_pdf(tmp_path / "lesson.pdf"))
    ref.set_zoom(1.25, SIZE, TOP)                                      # a portrait page: narrower than the window
    view = ref.view(SIZE, TOP)
    assert view.size[0] < WINDOW[2] - WINDOW[0] and view.size[1] > WINDOW[3] - WINDOW[1]
    assert view.origin[0] == WINDOW[0] + (WINDOW[2] - WINDOW[0] - view.size[0]) // 2   # centred across
    assert not ref.place((view.origin[0] + 300, view.origin[1]), SIZE, TOP)           # nothing to drag across
    ref.set_zoom(3.0, SIZE, TOP)
    for far in [(5000, 5000), (-5000, -5000), (5000, -5000)]:
        ref.place(far, SIZE, TOP)
        (ox, oy), (pw, ph) = ref.view(SIZE, TOP).origin, ref.view(SIZE, TOP).size
        assert ox <= WINDOW[0] and oy <= WINDOW[1] and ox + pw >= WINDOW[2] and oy + ph >= WINDOW[3]


def test_a_page_turn_keeps_the_zoom_and_starts_at_the_top(tmp_path):
    ref = Reference.open(write_pdf(tmp_path / "lesson.pdf"))
    ref.set_zoom(2.5, SIZE, TOP)
    ref.place((0, -900), SIZE, TOP)
    assert ref.view(SIZE, TOP).origin[1] < WINDOW[1]
    assert ref.next() and ref.zoom == 2.5
    view = ref.view(SIZE, TOP)
    assert view.origin[1] == WINDOW[1] and view.origin[0] == WINDOW[0] + (WINDOW[2] - WINDOW[0] - view.size[0]) // 2
    ref.place((0, -900), SIZE, TOP)
    assert ref.previous() and ref.view(SIZE, TOP).origin[1] == WINDOW[1]


def test_ink_drawn_while_zoomed_stays_on_the_same_place_of_the_page(tmp_path):
    ctl = doc_controller(Reference.open(write_pdf(tmp_path / "lesson.pdf")))
    zoom_to(ctl, 2.0)
    view = ctl.page_view
    wall = [(400.0, 300.0), (600.0, 300.0), (600.0, 400.0)]
    stroke(ctl, wall)
    (s,) = ctl.canvas.strokes.values()
    assert s.width == WIDTHS["medium"] / 2                           # as wide on the wall as it is drawn
    for w in wall:
        assert min(np.hypot(x - view.to_page(w)[0], y - view.to_page(w)[1]) for x, y in s.points) < 1e-6
    zoomed = render(ctl)
    assert (zoomed[300, 500] < 100).all()                            # drawn where the finger was
    ctl.press("zoom:fit")
    assert ctl.page_view is None
    whole = render(ctl)
    px, py = view.to_page((500.0, 300.0))
    assert (whole[int(round(py)), int(round(px))] < 100).all()       # ... and on the same place of the page
    assert (whole[300, 500] > 200).all()
    assert ctl.board.page.canvas.strokes == {}                        # on the document's own layer


def test_the_eraser_and_move_reach_as_far_on_the_wall_at_any_zoom(tmp_path):
    ctl = doc_controller(Reference.open(write_pdf(tmp_path / "lesson.pdf")))
    zoom_to(ctl, 2.0)
    stroke(ctl, [(400.0, 300.0), (700.0, 300.0)])
    ctl.press("eraser")                                               # reach on the wall: 24 + 8 / 2 = 28 px
    stroke(ctl, [(550.0, 340.0)])
    assert len(ctl.canvas.strokes) == 1 and ctl.log["erase_strokes"] == 0
    stroke(ctl, [(550.0, 320.0)])
    assert len(ctl.canvas.strokes) == 2 and ctl.log["erase_strokes"] == 1   # cut in two
    ctl.press("undo")
    ctl.press("move")
    (sid,) = ctl.canvas.strokes
    before = list(ctl.canvas.strokes[sid].points)
    stroke(ctl, [(450.0, 306.0), (450.0, 346.0)])                     # on the ink (6 px off it), 40 px down
    after = ctl.canvas.strokes[sid].points
    assert np.allclose(np.asarray(after) - np.asarray(before), [0.0, 20.0])   # 20 px of the page at 200 %
    assert ctl.reference.origin == ctl.page_view.origin                # the page did not move
    ctl.press("undo")
    assert ctl.canvas.strokes[sid].points == before


def test_move_where_no_ink_is_drags_the_zoomed_page_and_is_not_an_undo_step(tmp_path):
    ctl = doc_controller(Reference.open(write_pdf(tmp_path / "lesson.pdf")))
    ctl.press("move")
    stroke(ctl, [(600.0, 300.0), (600.0, 200.0)])
    assert ctl.reference.origin is None and ctl.log["doc:pans"] == 0  # at 100 %: nothing to drag
    zoom_to(ctl, 2.5)
    ctl.press("pen")
    stroke(ctl, [(500.0, 300.0), (520.0, 300.0)])                      # ink elsewhere on the page
    ctl.press("move")
    top = ctl.page_view.origin
    stroke(ctl, [(900.0, 400.0), (900.0, 350.0), (900.0, 300.0)])    # drag the page up by 100 px
    assert ctl.page_view.origin == (top[0], top[1] - 100) and ctl.log["doc:pans"] == 1
    assert ("pan", (900.0, 300.0), ctl.attempt) in ctl.outcomes        # diagnostics: wall points
    assert ctl.history.undo(ctl.canvas) is not None and ctl.canvas.strokes == {}   # the undo is the pen stroke's
    assert ctl.page_view.origin == (top[0], top[1] - 100)


def test_a_select_loop_while_zoomed_chooses_the_part_of_the_page_around_the_ink(tmp_path):
    # D74: on a document SELECT chooses a part of the page (it selected the ink inside the loop before D74)
    ctl = doc_controller(Reference.open(write_pdf(tmp_path / "lesson.pdf")))
    zoom_to(ctl, 2.0)
    stroke(ctl, [(500.0, 300.0), (560.0, 300.0)])
    stroke(ctl, [(900.0, 500.0), (960.0, 500.0)])
    inside, outside = (ctl.canvas.strokes[i] for i in ctl.canvas.strokes)
    ctl.press("select")
    loop = [(530 + 80 * np.cos(a), 300 + 50 * np.sin(a)) for a in np.linspace(0, 2 * np.pi, 40)]
    stroke(ctl, loop)
    x0, y0, x1, y1 = ctl.region
    assert ctl.selection == []
    assert all(x0 <= x <= x1 and y0 <= y <= y1 for x, y in inside.points)
    assert not any(x0 <= x <= x1 and y0 <= y <= y1 for x, y in outside.points)


def test_the_zoom_bar_is_shown_with_a_document_pressed_by_holding_and_never_drawn_on(tmp_path):
    ctl = DrawingController(Canvas(SIZE), Toolbar(SIZE, ai=True))
    assert ctl.zoom_bar is None and not ctl.zoom_enabled("zoom:in")    # the whiteboard: no zoom
    board = render(ctl)
    x0, y0, x1, y1 = ZoomBar(SIZE, TOP).rect
    assert (board[y0:y1, x0:x1] == 255).all()
    ctl.set_reference(Reference.open(write_pdf(tmp_path / "lesson.pdf")))
    bar = ctl.zoom_bar
    assert bar.rect == (x0, y0, x1, y1) and y1 <= TOP - MARGIN and x1 <= SIZE[0] - MARGIN
    assert not ctl.zoom_enabled("zoom:out") and not ctl.zoom_enabled("zoom:fit") and ctl.zoom_label() == "100%"
    dwell(ctl, "zoom:out")
    assert ctl.reference.zoom == 1.0 and ctl.log["zoom_limit"] == 1  # greyed: nothing happens
    dwell(ctl, "zoom:in", 2.0)
    assert ctl.reference.zoom == 1.25 and ctl.zoom_label() == "125%" and ctl.log["press:zoom:in"] == 1
    dwell(ctl, "zoom:fit", 4.0)
    assert ctl.reference.zoom == 1.0
    stroke(ctl, [bar.button("zoom:in").centre, (600.0, 300.0)])        # starts on the bar: refused
    assert ctl.canvas.strokes == {} and ctl.log["strokes_refused_on_panel"] == 1
    stroke(ctl, [(600.0, 600.0), (900.0, 600.0), (1100.0, 600.0)])   # runs into the bar: ends there
    (s,) = ctl.canvas.strokes.values()
    assert max(x for x, _ in s.points) < x0 and ctl.log["strokes_ended_on_panel"] == 1
    ctl.press("ai")                                                    # the AI panel: the bar stands left of it
    panel = ctl.panel_layout.rect
    moved = ctl.zoom_bar.rect
    assert moved[2] == panel[0] - 12 and (moved[1], moved[3]) == (y0, y1)
    dwell(ctl, "zoom:in", 6.0)
    assert ctl.reference.zoom == 1.25
    ctl.press("pages")                                                 # the board panel does not reach it
    assert ctl.zoom_bar.rect == (x0, y0, x1, y1)
    ctl.press("board:view")                                            # SHOW BOARD: no bar
    assert ctl.zoom_bar is None and ctl.page_view is None


def test_the_zoom_bar_greys_what_cannot_act_and_shows_the_scroll_bars_while_zoomed(tmp_path):
    ctl = doc_controller(Reference.open(write_pdf(tmp_path / "lesson.pdf")))
    bar = ctl.zoom_bar

    def glyph(img, name):
        x0, y0, x1, y1 = bar.button(name).rect
        return tuple(int(v) for v in img[(y0 + y1) // 2, (x0 + x1) // 2])

    img = render(ctl)
    assert glyph(img, "zoom:out") == LABEL_OFF and glyph(img, "zoom:in") == LABEL
    right = img[WINDOW[1]:WINDOW[3], WINDOW[2] - 10]
    assert not (right == THUMB).all(axis=1).any()                      # 100 %: no scroll bar
    zoom_to(ctl, 4.0)
    ctl.reference.place((0, 10 ** 6), SIZE, TOP)                      # the top of the page
    img = render(ctl)
    assert glyph(img, "zoom:out") == LABEL and glyph(img, "zoom:in") == LABEL_OFF
    rows = np.nonzero((img[:, WINDOW[2] - 10] == THUMB).all(axis=1))[0]
    assert len(rows) > 20 and rows.min() < 200                         # at the top of the page
    ctl.reference.place((0, -10 ** 6), SIZE, TOP)                     # the bottom of the page
    img = render(ctl)
    rows = np.nonzero((img[:, WINDOW[2] - 10] == THUMB).all(axis=1))[0]
    assert rows.max() > 400 and rows.max() < bar.rect[1]
    cols = np.nonzero((img[WINDOW[3] - 10] == THUMB).all(axis=1))[0]
    assert len(cols) > 20 and cols.max() < bar.rect[0]                 # 400 % is wider than the window too


def test_the_zoom_and_place_are_saved_with_the_board_and_an_old_board_opens_at_100(tmp_path):
    path = write_pdf(tmp_path / "lesson.pdf")
    ref = Reference.open(path)
    ref.next()
    ref.set_zoom(2.0, SIZE, TOP)
    ref.place((0, -500), SIZE, TOP)
    data = ref.to_dict()
    again = Reference.from_dict(data)
    assert again.current == 1 and again.zoom == 2.0 and again.view(SIZE, TOP) == ref.view(SIZE, TOP)
    old = {k: v for k, v in data.items() if k not in ("zoom", "origin")}   # a board saved before D72
    assert Reference.from_dict(old).zoom == 1.0 and Reference.from_dict(old).origin is None
    assert Reference.from_dict({**data, "zoom": 7}).zoom == 1.0


def test_the_setup_watch_still_sees_the_canvas_over_a_dark_document_at_400_percent(tmp_path):
    ref = Reference.open(write_image(tmp_path / "night.png", np.full((800, 1200, 3), 15, np.uint8)))
    ctl = doc_controller(ref, ai=False)
    zoom_to(ctl, 4.0)
    screen = render(ctl)
    rng = np.random.default_rng(0)
    frame = np.clip(55 + 0.6 * warp(screen, H_REAL) + rng.normal(0, 2, (CAMERA[1], CAMERA[0])), 0, 255).astype(np.uint8)
    expected = truth(H_REAL, canvas_corners(SIZE))
    corners = canvas_quad(frame)
    assert corners is not None and np.abs(corners - expected).max() < 4.5 and moved_by(expected, corners) is None
