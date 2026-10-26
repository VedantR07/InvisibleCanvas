"""Reference documents (brain.md D60): images and PDFs opened, fitted, paged, annotated on their own layer, never
changed; switching between them and the whiteboard; saving; the setup watch over a dark document."""

import hashlib
import json

import cv2
import numpy as np
import pytest
from PIL import Image
from synthetic_camera import CAMERA, H_REAL, truth, warp

from invisible_canvas.calibration.watch import canvas_corners, canvas_quad, moved_by
from invisible_canvas.canvas.board import Board
from invisible_canvas.canvas.model import Canvas
from invisible_canvas.canvas.reference import AI_MAX_SIDE, MARGIN, Reference, ReferenceError
from invisible_canvas.canvas.render import CanvasRenderer
from invisible_canvas.canvas.toolbar import Toolbar
from invisible_canvas.interaction.drawing import DrawingController
from invisible_canvas.interaction.engine import HOVER, STROKE_END, STROKE_POINT, STROKE_START, Event

SIZE = (1280, 720)
TOP = Toolbar(SIZE).top


def write_image(path, image):
    ok, buf = cv2.imencode(path.suffix, image)
    buf.tofile(str(path))                                  # also for non-ASCII paths
    return path


def write_pdf(path, colours=((255, 0, 0), (0, 255, 0), (0, 0, 255))):
    pages = [Image.new("RGB", (600, 800), c) for c in colours]   # portrait pages, RGB
    pages[0].save(str(path), save_all=True, append_images=pages[1:], resolution=100)
    return path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stroke(ctl, points):
    ctl.handle([Event(STROKE_START, 0.0, points[0])] + [Event(STROKE_POINT, 0.0, p) for p in points[1:]]
               + [Event(STROKE_END, 0.0)])


def content_box(display):
    ys, xs = np.nonzero((display != 255).any(axis=2))
    return xs.min(), ys.min(), xs.max(), ys.max()


def test_an_image_is_fitted_with_its_aspect_ratio_and_a_white_margin(tmp_path):
    img = np.zeros((300, 900, 3), np.uint8)                # a wide image, 3:1
    img[:, :, 1] = 200
    ref = Reference.open(write_image(tmp_path / "notes äö.png", img))   # non-ASCII path
    assert ref.kind == "image" and ref.count == 1 and ref.label() == "Image" and not ref.can_next
    shown = ref.display(SIZE, TOP)
    assert shown.shape == (720, 1280, 3)
    x0, y0, x1, y1 = content_box(shown)
    assert x0 >= MARGIN and y0 >= MARGIN and x1 <= SIZE[0] - 1 - MARGIN and y1 < TOP - MARGIN
    assert abs((x1 - x0 + 1) / (y1 - y0 + 1) - 3.0) < 0.05          # not stretched
    assert (shown[TOP:] == 255).all()                                # nothing under the toolbar
    jpg = Reference.open(write_image(tmp_path / "photo.jpeg", img))
    assert jpg.kind == "image"


def test_a_pdf_is_paged_and_each_page_rendered(tmp_path):
    ref = Reference.open(write_pdf(tmp_path / "lesson.pdf"))
    assert ref.kind == "pdf" and ref.count == 3 and ref.label() == "PDF page 1 of 3" and not ref.can_previous
    centre = lambda r: r.display(SIZE, TOP)[TOP // 2, SIZE[0] // 2].tolist()   # noqa: E731
    assert centre(ref) == [0, 0, 255] or np.allclose(centre(ref), [0, 0, 254], atol=2)   # page 1 red (BGR)
    assert ref.next() and ref.label() == "PDF page 2 of 3" and np.allclose(centre(ref), [0, 255, 0], atol=2)
    assert ref.next() and not ref.next() and np.allclose(centre(ref), [255, 0, 0], atol=2)
    x0, y0, x1, y1 = content_box(ref.display(SIZE, TOP))
    assert abs((x1 - x0 + 1) / (y1 - y0 + 1) - 600 / 800) < 0.02      # portrait page, not stretched
    png = ref.ai_png()
    page = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
    assert max(page.shape[:2]) == AI_MAX_SIDE and np.allclose(page[100, 100], [255, 0, 0], atol=2)   # page 3 blue
    assert ref.previous() and ref.previous() and not ref.previous()
    ref.close()


@pytest.mark.parametrize("name, data, words", [
    ("notes.txt", b"hello", "only PNG, JPG and PDF"),
    ("broken.png", b"\x89PNG not really", "could not be read"),
    ("broken.pdf", b"%PDF-1.4 garbage", "could not be opened"),
])
def test_unsupported_and_damaged_files_give_a_clear_message(tmp_path, name, data, words):
    path = tmp_path / name
    path.write_bytes(data)
    with pytest.raises(ReferenceError, match=words):
        Reference.open(path)
    with pytest.raises(ReferenceError, match="not found"):
        Reference.open(tmp_path / "missing.pdf")


def controller_with(ref):
    ctl = DrawingController(Canvas(SIZE), Toolbar(SIZE, ai=True))
    stroke(ctl, [(100, 600), (300, 600)])                 # on the whiteboard, page 1
    ctl.set_reference(ref)
    return ctl


def test_annotations_are_a_separate_layer_per_document_page_and_the_file_never_changes(tmp_path):
    path = write_pdf(tmp_path / "lesson.pdf")
    before = digest(path)
    ref = Reference.open(path)
    ctl = controller_with(ref)
    board_page = ctl.board.page.canvas
    assert ctl.view == "doc" and ctl.canvas is not board_page and ctl.canvas.strokes == {}
    stroke(ctl, [(500, 300), (700, 300)])                 # an annotation on PDF page 1
    assert len(ref.annotations[0].canvas.strokes) == 1 and len(board_page.strokes) == 1
    ctl.press("board:next")                               # the arrows turn the document's pages
    assert ref.current == 1 and ctl.canvas.strokes == {} and ctl.log["doc:next"] == 1
    stroke(ctl, [(500, 400), (700, 400)])
    ctl.undo()
    assert ctl.canvas.strokes == {} and len(ref.annotations[0].canvas.strokes) == 1   # undo on this page only
    ctl.press("board:prev")
    assert len(ctl.canvas.strokes) == 1 and ctl.board.count == 1                      # no whiteboard page made
    CanvasRenderer(SIZE).render(ctl.canvas, ctl, ctl.toolbar, mode=HOVER, cursor=None)
    ref.close()
    assert digest(path) == before


def test_switching_between_the_document_and_the_whiteboard_keeps_both(tmp_path):
    ref = Reference.open(write_pdf(tmp_path / "lesson.pdf"))
    ctl = DrawingController(Canvas(SIZE), Toolbar(SIZE, ai=True))
    ctl.press("board:add")                                # whiteboard page 2 is current
    stroke(ctl, [(100, 300), (300, 300)])
    ctl.set_reference(ref)
    ctl.press("board:next")                               # PDF page 2
    assert ctl.board_label("board:prev") == "< DOC" and ctl.board_label("board:view") == "SHOW BOARD"
    assert not ctl.board_enabled("board:add")             # no new whiteboard page from the document view
    ctl.press("board:view")                               # back to the whiteboard
    assert ctl.view == "board" and ctl.board.current == 1 and len(ctl.canvas.strokes) == 1
    assert ctl.board_label("board:view") == "SHOW DOC" and ctl.background is None
    ctl.press("board:view")                               # and to the document, where it was
    assert ctl.view == "doc" and ref.current == 1 and ctl.background is not None
    ctl.press("board:closedoc")
    assert ctl.reference is None and ctl.view == "board" and ctl.board.current == 1 and len(ctl.canvas.strokes) == 1
    assert not ctl.board_enabled("board:view") and not ctl.board_enabled("board:closedoc")


def test_open_file_is_a_request_for_the_tool_and_a_failure_is_shown_on_the_wall(tmp_path):
    ctl = DrawingController(Canvas(SIZE), Toolbar(SIZE))
    ctl.press("pages")
    ctl.press("board:open")
    assert ctl.take_open_request() and not ctl.take_open_request()
    ctl.now = 10.0
    ctl.show_notice("broken.pdf: the PDF could not be opened (damaged or password protected).")
    r = CanvasRenderer(SIZE)
    shown = r.render(ctl.canvas, ctl, ctl.toolbar, mode=HOVER, cursor=None)
    assert (shown[60:120, 300:980] < 100).any()          # the message box at the top centre
    ctl.now = 20.0                                        # gone after a few seconds
    later = r.render(ctl.canvas, ctl, ctl.toolbar, mode=HOVER, cursor=None)
    assert (later[60:120, 300:900] == 255).all()


def test_closing_or_replacing_a_document_keeps_its_annotations(tmp_path):
    path = write_pdf(tmp_path / "lesson.pdf")
    ctl = controller_with(Reference.open(path))
    ctl.press("board:next")
    stroke(ctl, [(500, 300), (700, 300)])                 # a note on PDF page 2
    ctl.press("board:closedoc")
    assert ctl.reference is None and ctl.view == "board" and len(ctl.canvas.strokes) == 1   # the whiteboard as left
    again = Reference.open(tmp_path / ".." / tmp_path.name / "LESSON.PDF")                  # the same file
    ctl.set_reference(again)
    assert again.current == 0 and ctl.canvas.strokes == {} and ctl.log["doc:annotations_back"] == 1
    ctl.press("board:next")
    assert len(ctl.canvas.strokes) == 1                   # the note is back on page 2
    photo = tmp_path / "photo.png"
    write_image(photo, np.full((100, 100, 3), 90, np.uint8))
    ctl.set_reference(Reference.open(photo))              # another file replaces it: the note is kept again
    assert ctl.kept_annotations and ctl.canvas.strokes == {}
    ctl.set_reference(Reference.open(path))
    ctl.press("board:next")
    assert len(ctl.canvas.strokes) == 1 and ctl.log["doc:annotations_back"] == 2
    ctl.reference.close()


def test_the_board_file_keeps_the_document_and_its_annotations(tmp_path):
    from invisible_canvas.tools.draw import board_data, restore_reference
    path = write_pdf(tmp_path / "lesson.pdf")
    ref = Reference.open(path)
    ctl = controller_with(ref)
    ctl.press("board:next")
    stroke(ctl, [(500, 300), (700, 300)])
    closed = write_image(tmp_path / "closed.png", np.full((100, 100, 3), 90, np.uint8))
    ctl.set_reference(Reference.open(closed))
    stroke(ctl, [(500, 400), (700, 400)])                 # a note on a picture that is then closed
    ctl.set_reference(Reference.open(path))
    ctl.press("board:next")
    data = json.loads(json.dumps(board_data(ctl)))
    assert [d["path"] for d in data["closed_documents"]] == [str(closed)]
    fourth = DrawingController(Canvas(SIZE), Toolbar(SIZE), board=Board.from_dict(data))
    restore_reference(fourth, data)
    fourth.set_reference(Reference.open(closed))
    assert len(fourth.canvas.strokes) == 1                # the closed picture's note, from the board file
    again = DrawingController(Canvas(SIZE), Toolbar(SIZE), board=Board.from_dict(data))
    restore_reference(again, data)
    assert again.view == "doc" and again.reference.current == 1 and len(again.canvas.strokes) == 1
    assert len(again.board.page.canvas.strokes) == 1      # the whiteboard page too
    path.unlink()                                         # the document is gone: the board still loads
    third = DrawingController(Canvas(SIZE), Toolbar(SIZE), board=Board.from_dict(data))
    restore_reference(third, data)
    assert third.reference is None and third.view == "board" and "not reopened" in third.notice["text"]


def test_the_setup_watch_still_sees_the_canvas_over_a_dark_document(tmp_path):
    dark = np.full((800, 1200, 3), 15, np.uint8)          # an almost black photo filling the page area
    ref = Reference.open(write_image(tmp_path / "night.png", dark))
    ctl = DrawingController(Canvas(SIZE), Toolbar(SIZE))
    ctl.set_reference(ref)
    screen = CanvasRenderer(SIZE).render(ctl.canvas, ctl, ctl.toolbar, mode=HOVER, cursor=None)
    rng = np.random.default_rng(0)
    frame = np.clip(55 + 0.6 * warp(screen, H_REAL) + rng.normal(0, 2, (CAMERA[1], CAMERA[0])), 0, 255).astype(np.uint8)
    expected = truth(H_REAL, canvas_corners(SIZE))
    corners = canvas_quad(frame)
    assert corners is not None and np.abs(corners - expected).max() < 4.5 and moved_by(expected, corners) is None
