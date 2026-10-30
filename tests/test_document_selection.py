"""SELECT on a document (brain.md D74): a loop chooses a part of the page, the AI reads only that part (sharply,
from the page itself), the panel says so, the part is framed on the wall at any zoom; a slip or a loop off the page
chooses nothing; a page turn, SHOW BOARD and CLEAR drop it, a zoom keeps it; whole-page requests are unchanged."""

import cv2
import numpy as np
from PIL import Image, ImageDraw

from invisible_canvas.ai.client import SYSTEM, SYSTEM_DOCUMENT, SYSTEM_REGION, system_for
from invisible_canvas.canvas.model import Canvas
from invisible_canvas.canvas.reference import AI_MAX_SIDE, Reference
from invisible_canvas.canvas.render import HIGHLIGHT, CanvasRenderer
from invisible_canvas.canvas.toolbar import Toolbar
from invisible_canvas.interaction.drawing import DrawingController
from invisible_canvas.interaction.engine import HOVER, STROKE_END, STROKE_POINT, STROKE_START, Event

SIZE = (1280, 720)
TOP = Toolbar(SIZE).top
QUADRANTS = {"tl": (255, 0, 0), "tr": (0, 160, 0), "bl": (0, 0, 255), "br": (250, 200, 0)}   # RGB


def write_pdf(path, pages=3):
    """Portrait pages in four coloured quarters (fitted on the wall: x 406-874, y 12-636)."""
    images = []
    for _ in range(pages):
        image = Image.new("RGB", (600, 800), (255, 255, 255))
        d = ImageDraw.Draw(image)
        d.rectangle((0, 0, 299, 399), fill=QUADRANTS["tl"])
        d.rectangle((300, 0, 599, 399), fill=QUADRANTS["tr"])
        d.rectangle((0, 400, 299, 799), fill=QUADRANTS["bl"])
        d.rectangle((300, 400, 599, 799), fill=QUADRANTS["br"])
        images.append(image)
    images[0].save(str(path), save_all=True, append_images=images[1:], resolution=100)
    return path


def write_image(path, image):
    cv2.imencode(path.suffix, image)[1].tofile(str(path))
    return path


def stroke(ctl, points):
    ctl.handle([Event(STROKE_START, 0.0, points[0])] + [Event(STROKE_POINT, 0.0, p) for p in points[1:]]
               + [Event(STROKE_END, 0.0)])


def loop(cx, cy, rx, ry, n=48):
    return [(cx + rx * np.cos(a), cy + ry * np.sin(a)) for a in np.linspace(0, 2 * np.pi, n)]


def doc_controller(ref):
    ctl = DrawingController(Canvas(SIZE), Toolbar(SIZE, ai=True))
    ctl.set_reference(ref)
    return ctl


def select(ctl, points):
    ctl.press("select")
    stroke(ctl, points)


def ask(ctl, action="summarize"):
    ctl.press("ai")
    ctl.press(f"ai:{action}")
    _, png, context = ctl.take_ai_jobs()[-1]
    ctl.panel = None
    return cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR), context


def test_a_select_loop_on_a_document_chooses_a_part_of_the_page_not_the_ink(tmp_path):
    ctl = doc_controller(Reference.open(write_pdf(tmp_path / "lesson.pdf")))
    stroke(ctl, [(500.0, 150.0), (560.0, 150.0)])                    # a note on the page, inside the loop
    assert ctl.ai_title() == "AI on PDF page 1 of 3"
    select(ctl, loop(520, 170, 60, 60))
    assert ctl.selection == []                                       # not the ink
    x0, y0, x1, y1 = ctl.region
    assert abs(x0 - 460) < 3 and abs(y0 - 110) < 3 and abs(x1 - 580) < 3 and abs(y1 - 230) < 3
    assert ctl.ai_title() == "AI on part of PDF page 1 of 3" and ctl.log["doc:selections"] == 1
    assert ctl.selection_log[-1]["region"] == [round(v) for v in ctl.region]


def test_the_ai_reads_only_the_selected_part_sharply_and_the_whole_page_as_before(tmp_path):
    ctl = doc_controller(Reference.open(write_pdf(tmp_path / "lesson.pdf")))
    page, context = ask(ctl)
    assert "region" not in context and max(page.shape[:2]) == AI_MAX_SIDE   # the whole page (D61)
    select(ctl, loop(520, 170, 60, 60))                              # inside the top-left quarter (red)
    part, context = ask(ctl)
    assert max(part.shape[:2]) == AI_MAX_SIDE                        # rendered at that size, not cut from the page
    assert np.allclose(part.reshape(-1, 3).mean(axis=0), [0, 0, 255], atol=3)   # BGR red: the right quarter
    fx0, fy0, fx1, fy1 = context["region"]
    assert 0.1 < fx0 < fx1 < 0.4 and 0.15 < fy0 < fy1 < 0.4 and context["source"] == "document"
    select(ctl, loop(760, 520, 60, 60))                              # the bottom-right quarter (yellow)
    part, _ = ask(ctl)
    assert np.allclose(part.reshape(-1, 3).mean(axis=0), [0, 200, 250], atol=3)


def test_a_selected_part_of_a_picture_is_cut_from_the_picture_itself(tmp_path):
    xs, ys = np.meshgrid(np.arange(1000) % 256, np.arange(700) % 256)
    picture = np.dstack([xs, ys, (xs + ys) % 256]).astype(np.uint8)
    ref = Reference.open(write_image(tmp_path / "photo.png", picture))
    fraction = (0.25, 0.5, 0.5, 0.75)
    part = cv2.imdecode(np.frombuffer(ref.ai_png(fraction), np.uint8), cv2.IMREAD_COLOR)
    assert np.array_equal(part, picture[350:525, 250:500])             # the picture's own pixels
    ctl = doc_controller(ref)
    select(ctl, loop(640, 324, 100, 80))
    assert ctl.ai_title() == "AI on part of the image"


def test_a_slip_or_a_loop_off_the_page_chooses_nothing(tmp_path):
    ctl = doc_controller(Reference.open(write_pdf(tmp_path / "lesson.pdf")))
    select(ctl, loop(520, 170, 60, 60))
    select(ctl, loop(520, 170, 6, 6))                                # a slip: the whole page again
    assert ctl.region is None and ctl.log["doc:selection_none"] == 1
    select(ctl, loop(200, 300, 80, 80))                              # in the white beside the page
    assert ctl.region is None and ctl.ai_title() == "AI on PDF page 1 of 3"
    select(ctl, loop(400, 300, 80, 80))                              # mostly beside it: cut to the page
    assert ctl.region is not None and ctl.region[0] >= 406
    _, context = ask(ctl)
    assert context["region"][0] == 0.0


def test_an_open_loop_that_runs_into_the_ai_panel_chooses_all_it_went_around(tmp_path):
    # wall test 2026-10-31 01:06: loops beside the open AI panel ended on it, open; closed at their tightest point
    # (D53) a 317-px-wide loop became a 26-px-wide part
    ctl = doc_controller(Reference.open(write_pdf(tmp_path / "lesson.pdf")))
    ctl.press("ai")                                                  # the panel: x >= 824
    arc = [(650 + 150 * np.cos(a), 300 - 50 * np.sin(a)) for a in np.linspace(0.3, 2 * np.pi - 0.6, 40)]
    run_on = [(arc[-1][0] + 30 * k, arc[-1][1]) for k in range(1, 8)]    # then right, into the panel
    ctl.press("select")
    stroke(ctl, arc + run_on)
    assert ctl.blocked is None and ctl.log["strokes_ended_on_panel"] == 1
    x0, y0, x1, y1 = ctl.region
    assert x0 < 510 and y0 < 255 and y1 > 345 and x1 >= 790              # the whole box it went around
    assert ctl.ai_title() == "AI on part of PDF page 1 of 3"


def test_a_page_turn_show_board_and_clear_drop_the_part_and_a_zoom_keeps_it(tmp_path):
    ctl = doc_controller(Reference.open(write_pdf(tmp_path / "lesson.pdf")))
    select(ctl, loop(520, 170, 60, 60))
    rect = ctl.region
    ctl.press("zoom:in")
    ctl.press("zoom:in")
    assert ctl.region == rect                                         # kept, in the page's own coordinates
    ctl.press("board:next")
    assert ctl.region is None
    ctl.press("board:prev")
    assert ctl.region is None                                        # dropped, not given back
    select(ctl, loop(640, 324, 60, 60))
    ctl.press("board:view")                                          # SHOW BOARD
    assert ctl.region is None and ctl.ai_source() == "canvas"
    ctl.press("board:view")
    select(ctl, loop(640, 324, 60, 60))
    ctl.press("clear")
    assert ctl.region is None


def test_a_loop_drawn_while_zoomed_chooses_the_part_under_it(tmp_path):
    ctl = doc_controller(Reference.open(write_pdf(tmp_path / "lesson.pdf")))
    while ctl.reference.zoom < 2.0:
        ctl.press("zoom:in")
    view = ctl.page_view
    select(ctl, loop(640, 300, 120, 80))
    (ex0, ey0), (ex1, ey1) = view.to_page((520, 220)), view.to_page((760, 380))
    x0, y0, x1, y1 = ctl.region
    assert max(abs(x0 - ex0), abs(y0 - ey0), abs(x1 - ex1), abs(y1 - ey1)) < 2
    ctl.press("zoom:fit")
    assert ctl.region == (x0, y0, x1, y1)


def test_the_part_is_framed_on_the_wall_at_its_zoom(tmp_path):
    ctl = doc_controller(Reference.open(write_pdf(tmp_path / "lesson.pdf")))
    select(ctl, loop(520, 170, 60, 60))

    def framed(img, x, y):
        return tuple(int(v) for v in img[y, x]) == HIGHLIGHT

    img = CanvasRenderer(SIZE).render(ctl.canvas, ctl, ctl.toolbar, mode=HOVER, cursor=None)
    x0, y0, x1, y1 = (int(round(v)) for v in ctl.region)
    assert framed(img, (x0 + x1) // 2, y0 - 4) and framed(img, x1 + 4, (y0 + y1) // 2)
    ctl.press("zoom:in")
    ctl.press("zoom:in")                                             # 150 %
    view = ctl.page_view
    img = CanvasRenderer(SIZE).render(ctl.canvas, ctl, ctl.toolbar, mode=HOVER, cursor=None)
    (wx0, wy0), (wx1, wy1) = np.round(view.to_wall([ctl.region[:2], ctl.region[2:]])).astype(int)
    assert framed(img, (wx0 + wx1) // 2, wy1 + 4) and framed(img, wx1 + 4, (max(wy0, 12) + wy1) // 2)
    assert not framed(img, (wx0 + wx1) // 2, 6)                       # nothing in the white margin (D58)


def test_only_a_selected_part_adds_to_the_prompt():
    assert system_for({"source": "document", "page": "PDF page 1 of 3"}) == SYSTEM_DOCUMENT
    assert system_for({"source": "document", "region": [0.1, 0.1, 0.5, 0.4]}) == SYSTEM_DOCUMENT + SYSTEM_REGION
    assert system_for({"source": "selection"}) == SYSTEM and system_for(None) == SYSTEM
