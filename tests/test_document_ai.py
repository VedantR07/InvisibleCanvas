"""The AI on documents and ASK (brain.md D61): the request carries the shown page itself and speaks of a page; the
handwriting requests are unchanged; ASK's question is typed on the laptop keyboard without stopping the gestures.
No network: the assistants are fakes or never reach a server."""

import base64
import json
import time

import cv2
import numpy as np
import pytest
from PIL import Image

from invisible_canvas.ai.client import ACTIONS, DOCUMENT_ACTIONS, SYSTEM, SYSTEM_DOCUMENT, AIAnswer, build_request, \
    task_for
from invisible_canvas.ai.local import LocalAssistant, build_local_request
from invisible_canvas.ai.worker import AIWorker
from invisible_canvas.canvas.model import Canvas
from invisible_canvas.canvas.panel import PANEL_ACTIONS, QUESTION_MAX, AIPanel, clip_lines, wrap
from invisible_canvas.canvas.reference import Reference, ReferenceError
from invisible_canvas.canvas.render import ASK_PROMPT, CanvasRenderer
from invisible_canvas.canvas.selection import png_bytes
from invisible_canvas.canvas.toolbar import Toolbar
from invisible_canvas.config import AIConfig
from invisible_canvas.interaction.drawing import DrawingController
from invisible_canvas.interaction.engine import HOVER, STROKE_END, STROKE_POINT, STROKE_START, Event
from invisible_canvas.tools.draw import handle_keys

SIZE = (1280, 720)
CFG = AIConfig(enabled=True, backend="local", local_model="qwen3-vl:8b-instruct", local_url="http://127.0.0.1:9",
               model="claude-opus-5-5", effort="medium", max_tokens=16000, timeout_s=2.0, fallbacks=False)
PNG = png_bytes(np.full((40, 60, 3), 255, np.uint8))


def write_pdf(path, colours=((255, 0, 0), (0, 255, 0), (0, 0, 255))):
    pages = [Image.new("RGB", (600, 800), c) for c in colours]
    pages[0].save(str(path), save_all=True, append_images=pages[1:], resolution=100)
    return path


def stroke(ctl, points):
    ctl.handle([Event(STROKE_START, 0.0, points[0])] + [Event(STROKE_POINT, 0.0, p) for p in points[1:]]
               + [Event(STROKE_END, 0.0)])


def type_text(ctl, text):
    for ch in text:
        ctl.type_key(ord(ch))


def shown_texts(ctl, monkeypatch):
    texts, real = [], cv2.putText
    monkeypatch.setattr(cv2, "putText", lambda img, text, *a, **k: (texts.append(text), real(img, text, *a, **k))[1])
    CanvasRenderer(SIZE).render(ctl.canvas, ctl, ctl.toolbar, mode=HOVER, cursor=None)
    monkeypatch.setattr(cv2, "putText", real)
    return texts


def decoded(png):
    return cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)


# -- the request --------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("context", [None, {"source": "selection"}, {"source": "canvas"}])
def test_the_handwriting_requests_are_unchanged(context):
    local = build_local_request(CFG, "summarize", PNG, context)
    assert local["messages"][0]["content"] == SYSTEM and local["messages"][1]["content"] == f"Task: {ACTIONS['summarize']}"
    claude = build_request(CFG, "explore", PNG, context)
    assert claude["system"] == SYSTEM and claude["messages"][0]["content"][1]["text"] == f"Task: {ACTIONS['explore']}"


def test_a_document_request_carries_the_page_image_and_speaks_of_a_page():
    page = png_bytes(np.full((1600, 1131, 3), 200, np.uint8))
    context = {"source": "document", "page": "PDF page 2 of 3 - lesson.pdf"}
    for action in PANEL_ACTIONS:
        if action == "ask":
            continue
        local = build_local_request(CFG, action, page, context)
        system, user = local["messages"]
        assert system["content"] == SYSTEM_DOCUMENT and user["content"] == f"Task: {DOCUMENT_ACTIONS[action]}"
        assert base64.b64decode(user["images"][0]) == page                       # the page itself, not a file name
        claude = build_request(CFG, action, page, context)
        image, text = claude["messages"][0]["content"]
        assert claude["system"] == SYSTEM_DOCUMENT and base64.b64decode(image["source"]["data"]) == page
    assert "finger" in SYSTEM and "finger" not in SYSTEM_DOCUMENT and "page" in SYSTEM_DOCUMENT
    assert set(DOCUMENT_ACTIONS) == set(ACTIONS) == set(PANEL_ACTIONS)


def test_ask_carries_the_typed_question_and_never_goes_without_one():
    task = task_for("ask", {"question": "  what is\n  this?  "})
    assert task.endswith("Question: what is this?") and "what is written" in task
    doc = task_for("ask", {"source": "document", "question": "Which gas {is} released?"})
    assert doc.endswith("Question: Which gas {is} released?") and "page" in doc        # braces kept as typed
    with pytest.raises(ValueError):
        task_for("ask", {"question": "   "})
    opened = []
    a = LocalAssistant(CFG, opener=lambda *a, **k: opened.append(1)).ask("ask", PNG, {"source": "canvas"})
    assert not a.ok and a.error and opened == []                                   # a panel message, no request


def test_the_worker_hands_the_context_over_and_keeps_it_with_the_answer(tmp_path):
    seen = []

    class Assistant:
        def ask(self, action, png, context=None):
            seen.append(context)
            return AIAnswer(action, ok=True, transcription="Photosynthesis", result="Oxygen.")

    w = AIWorker(Assistant(), save_dir=tmp_path)
    context = {"source": "document", "page": "PDF page 1 of 2 - lesson.pdf", "question": "What gas?"}
    assert w.submit("ask", PNG, context)
    deadline = time.time() + 5
    while not w.answers and time.time() < deadline:
        time.sleep(0.01)
    assert seen == [context] and w.answers[0].context == context
    assert json.loads(next(tmp_path.glob("*-ask.json")).read_text())["context"] == context
    w.close()


# -- the controller on a document -----------------------------------------------------------------------------------

def doc_controller(tmp_path):
    ref = Reference.open(write_pdf(tmp_path / "lesson.pdf"))
    ctl = DrawingController(Canvas(SIZE), Toolbar(SIZE, ai=True))
    stroke(ctl, [(100, 600), (300, 600)])                  # writing on the whiteboard
    ctl.set_reference(ref)
    return ctl, ref


def test_the_ai_reads_the_shown_page_without_the_annotations(tmp_path, monkeypatch):
    ctl, ref = doc_controller(tmp_path)
    ctl.press("pages")
    ctl.press("board:next")                                # PDF page 2 (green)
    stroke(ctl, [(500, 300), (700, 300)])                  # an annotation on it
    ctl.press("ai")
    assert ctl.ai_source() == "document" and ctl.ai_title() == "AI on PDF page 2 of 3"
    assert "Choose what the AI should do with this page." in " ".join(shown_texts(ctl, monkeypatch))
    ctl.press("ai:summarize")
    (action, png, context), = ctl.take_ai_jobs()
    assert action == "summarize" and context == {"source": "document", "page": "PDF page 2 of 3 - lesson.pdf"}
    sent = decoded(png)
    assert np.array_equal(sent, ref.page_image(1600))      # the rendered page itself, at the AI's size
    assert np.allclose(sent.reshape(-1, 3).mean(axis=0), [0, 255, 0], atol=2)       # no ink on it
    assert ctl.log["ai_on_document"] == 1


def test_the_panel_shows_a_page_answer_readably(tmp_path, monkeypatch):
    ctl, ref = doc_controller(tmp_path)
    ctl.press("ai")
    ctl.press("ai:summarize")
    ctl.take_ai_jobs()
    page = "Photosynthesis " + "Plants make their own food using light energy. " * 6        # a page copied out
    ctl.ai_answer(AIAnswer("summarize", ok=True, transcription=page, result="Plants make food from light."))
    texts = shown_texts(ctl, monkeypatch)
    assert "AI on PDF page 1 of 3" in texts and "PAGE:" in texts and "READ:" not in texts and "SUMMARIZE:" in texts
    assert "Plants make food from light." in " ".join(texts)
    page_lines = [t for t in texts[texts.index("PAGE:") + 1:texts.index("SUMMARIZE:")] if t]   # not the spacer
    assert len(page_lines) == 2 and page_lines[-1].endswith(" ...")                    # at most two lines


def test_an_answer_says_what_was_read_even_if_a_document_opened_meanwhile(tmp_path, monkeypatch):
    ctl = DrawingController(Canvas(SIZE), Toolbar(SIZE, ai=True))
    stroke(ctl, [(100, 300), (300, 300)])
    ctl.press("ai")
    ctl.press("ai:explain")
    ctl.take_ai_jobs()
    ctl.set_reference(Reference.open(write_pdf(tmp_path / "lesson.pdf")))         # the o key, while the AI reads
    assert ctl.ai_title() == "AI on the whole canvas"
    ctl.ai_answer(AIAnswer("explain", ok=True, transcription="hello", result="A greeting."))
    texts = shown_texts(ctl, monkeypatch)
    assert "AI on the whole canvas" in texts and "READ:" in texts and "PAGE:" not in texts
    ctl.press("ai:close")
    ctl.press("ai")                                                                # a new request: the page
    assert ctl.ai_title() == "AI on PDF page 1 of 3"


def test_an_image_document_and_the_whiteboard_say_what_the_ai_reads(tmp_path):
    path = tmp_path / "photo.png"
    cv2.imencode(".png", np.full((300, 400, 3), 90, np.uint8))[1].tofile(str(path))
    ctl = DrawingController(Canvas(SIZE), Toolbar(SIZE, ai=True))
    stroke(ctl, [(100, 300), (300, 300)])
    ctl.set_reference(Reference.open(path))
    ctl.press("ai")
    assert ctl.ai_title() == "AI on the image"
    ctl.press("pages")
    ctl.press("board:view")                                # back to the whiteboard: its writing again
    ctl.press("ai")
    assert ctl.ai_source() == "canvas" and ctl.ai_title() == "AI on the whole canvas"
    ctl.press("ai:examples")
    (action, png, context), = ctl.take_ai_jobs()
    assert context == {"source": "canvas"} and (decoded(png) == 255).all(axis=2).any()   # the ink on white


def test_a_page_that_cannot_be_prepared_gives_a_message(tmp_path, monkeypatch):
    ctl, ref = doc_controller(tmp_path)

    def broken():
        raise ReferenceError("lesson.pdf: page 1 could not be rendered.")
    monkeypatch.setattr(ref, "ai_png", broken)
    ctl.press("ai")
    ctl.press("ai:summarize")
    assert ctl.panel["state"] == "error" and "could not be rendered" in ctl.panel["message"]
    assert ctl.take_ai_jobs() == []


# -- ASK: the question typed on the laptop ------------------------------------------------------------------------

def test_ask_takes_a_typed_question_shown_live_and_sends_it_with_enter(tmp_path, monkeypatch):
    ctl, ref = doc_controller(tmp_path)
    ctl.press("ai")
    ctl.press("ai:ask")
    assert ctl.typing and ctl.take_ai_jobs() == []
    type_text(ctl, "Whta")
    ctl.type_key(8)
    ctl.type_key(8)
    type_text(ctl, "at gas?")
    for code in (0, 9, 200, 0x260000):                     # not typed text: ignored
        ctl.type_key(code)
    assert ctl.panel["question"] == "What gas?"
    texts = shown_texts(ctl, monkeypatch)
    assert "What gas?_" in texts and " ".join(wrap(ASK_PROMPT, 412, 0.55)) in " ".join(texts)
    ctl.type_key(13)
    (action, png, context), = ctl.take_ai_jobs()
    assert action == "ask" and context == {"source": "document", "page": "PDF page 1 of 3 - lesson.pdf",
                                           "question": "What gas?"}
    assert not ctl.typing and ctl.panel["state"] == "thinking"
    ctl.ai_answer(AIAnswer("ask", ok=True, transcription="Red page", result="Oxygen."))
    texts = shown_texts(ctl, monkeypatch)
    assert "ASK: What gas?" in texts and "Oxygen." in texts


def test_escape_cancels_the_question_and_empty_or_long_questions_are_handled(tmp_path):
    ctl, ref = doc_controller(tmp_path)
    ctl.press("ai")
    ctl.press("ai:ask")
    ctl.type_key(13)                                       # nothing typed: Enter does nothing
    assert ctl.typing and ctl.take_ai_jobs() == []
    type_text(ctl, "x" * (QUESTION_MAX + 20))
    assert len(ctl.panel["question"]) == QUESTION_MAX
    ctl.type_key(27)                                       # Esc: back to the menu, nothing sent
    assert not ctl.typing and ctl.panel["state"] == "menu" and ctl.take_ai_jobs() == []
    assert ctl.log["ask_cancelled"] == 1
    ctl.press("ai:ask")
    assert ctl.panel["question"] == ""                     # a new question starts empty


def test_gestures_and_buttons_keep_working_while_a_question_is_typed(tmp_path):
    ctl = DrawingController(Canvas(SIZE), Toolbar(SIZE, ai=True))
    stroke(ctl, [(100, 300), (300, 300)])
    ctl.press("ai")
    ctl.press("ai:ask")
    type_text(ctl, "why")
    stroke(ctl, [(100, 400), (300, 400)])                  # drawing goes on meanwhile
    assert len(ctl.canvas.strokes) == 2 and ctl.typing and ctl.panel["question"] == "why"
    ctl.ai_answer(AIAnswer("summarize", ok=True, result="late"))                  # a late answer: not over the question
    assert ctl.typing and ctl.panel["question"] == "why"
    explain = next(b for b in ctl.panel_layout.buttons if b.name == "ai:explain").centre
    ctl.update_pointer(10.0, explain)
    ctl.update_pointer(11.05, explain)                     # another action by dwell: it runs, the question is dropped
    (action, png, context), = ctl.take_ai_jobs()
    assert action == "explain" and "question" not in context and not ctl.typing
    ctl.press("ai:close")
    ctl.press("ai")
    ctl.press("ai:ask")
    close = ctl.panel_layout.buttons[-1].centre
    ctl.update_pointer(20.0, close)
    ctl.update_pointer(21.05, close)                       # CLOSE by dwell ends the typing too
    assert ctl.panel is None and not ctl.typing


def test_ask_on_an_empty_whiteboard_says_so_at_once():
    ctl = DrawingController(Canvas(SIZE), Toolbar(SIZE, ai=True))
    ctl.press("ai")
    ctl.press("ai:ask")
    assert not ctl.typing and ctl.panel["state"] == "error" and "Nothing written" in ctl.panel["message"]


def test_ask_has_its_button_and_the_answer_area_did_not_shrink():
    tb = Toolbar(SIZE, ai=True)
    panel = AIPanel(SIZE, tb.top)
    names = [b.name for b in panel.buttons]
    assert names[-2:] == ["ai:ask", "ai:close"]
    ask, close = panel.buttons[-2].rect, panel.buttons[-1].rect
    assert ask[1] == close[1] and ask[0] < close[0]        # ASK and CLOSE share the last row
    assert panel.rect[3] - panel.text_top == 374


def test_clip_lines_keeps_at_most_n_lines_and_marks_the_cut():
    lines = wrap("word " * 80, 300, 0.62)
    clipped = clip_lines(lines, 2, 300, 0.62)
    assert len(clipped) == 2 and clipped[-1].endswith(" ...")
    assert cv2.getTextSize(clipped[-1], cv2.FONT_HERSHEY_SIMPLEX, 0.62, 1)[0][0] <= 300
    assert clip_lines(lines[:2], 2, 300, 0.62) == lines[:2]


# -- the laptop keys in `draw` --------------------------------------------------------------------------------------

def test_while_a_question_is_typed_every_key_is_text_and_esc_does_not_quit():
    ctl = DrawingController(Canvas(SIZE), Toolbar(SIZE, ai=True))
    stroke(ctl, [(100, 300), (300, 300)])
    ctl.press("ai")
    ctl.press("ai:ask")
    saves, armed = [], {"until": 0.0}
    keys = [ord(c) for c in "z s"] + [-1, 0x250000 & 0xFF, ord("c"), ord("o")]   # also: no key, an arrow
    assert not handle_keys(keys, ctl, 1.0, armed, saves, save=lambda: saves.append(1) or ["x"])
    assert ctl.panel["question"] == "z sco" and len(ctl.canvas.strokes) == 1 and saves == []
    assert not ctl.open_requested and armed["until"] == 0.0
    assert not handle_keys([27], ctl, 1.0, armed, saves, save=list)                # Esc cancels the question only
    assert not ctl.typing and ctl.panel["state"] == "menu"
    assert handle_keys([ord("z"), 27], ctl, 1.0, armed, saves, save=list)          # now z undoes, Esc quits
    assert ctl.canvas.strokes == {}
