"""Phase 3A (D51, §9.11): the Claude request and answer, the background worker, selection, the AI panel and the
controller flow. No network: Claude is a fake client."""

import base64
import json
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from invisible_canvas.ai.client import ACTIONS, FALLBACK_BETA, SCHEMA, AIAnswer, ClaudeAssistant, build_request, \
    error_message, parse_response
from invisible_canvas.ai.worker import AIWorker
from invisible_canvas.canvas.model import Canvas, Stroke
from invisible_canvas.canvas.panel import PANEL_ACTIONS, AIPanel, ascii_text, wrap
from invisible_canvas.canvas.render import CanvasRenderer
from invisible_canvas.canvas.selection import loop_area, png_bytes, select_in_loop, selection_image
from invisible_canvas.canvas.toolbar import Toolbar
from invisible_canvas.config import AIConfig
from invisible_canvas.interaction.drawing import DrawingController
from invisible_canvas.interaction.engine import HOVER, STROKE_END, STROKE_POINT, STROKE_START, Event

SIZE = (1280, 720)
CFG = AIConfig(enabled=True, model="claude-opus-5-5", effort="medium", max_tokens=16000, timeout_s=60.0,
               fallbacks=True)
PNG = png_bytes(np.full((40, 60, 3), 255, np.uint8))


def response(text=None, stop="end_turn", model="claude-opus-5-5", blocks=None):
    content = blocks if blocks is not None else [SimpleNamespace(type="thinking", thinking=""),
                                                 SimpleNamespace(type="text", text=text)]
    return SimpleNamespace(stop_reason=stop, model=model, content=content,
                           usage=SimpleNamespace(input_tokens=1200, output_tokens=90), _request_id="req_1")


class FakeClient:
    def __init__(self, reply=None, error=None, delay=0.0):
        self.calls, self.reply, self.error, self.delay = [], reply, error, delay
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.calls.append(kw)
        time.sleep(self.delay)
        if self.error is not None:
            raise self.error
        return self.reply


# -- request and answer ------------------------------------------------------------------------------------

def test_the_request_carries_the_image_the_task_and_the_structured_output():
    r = build_request(CFG, "summarize", PNG)
    assert r["model"] == "claude-opus-5-5" and r["max_tokens"] == 16000
    assert r["output_config"] == {"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}}
    assert r["betas"] == [FALLBACK_BETA] and r["fallbacks"] == "default"
    image, text = r["messages"][0]["content"]
    assert image["source"]["media_type"] == "image/png" and base64.b64decode(image["source"]["data"]) == PNG
    assert ACTIONS["summarize"] in text["text"] and "thinking" not in r          # adaptive by default on Opus 5.5
    plain = build_request(AIConfig(**{**CFG.__dict__, "fallbacks": False}), "questions", PNG)
    assert "betas" not in plain and "fallbacks" not in plain
    with pytest.raises(ValueError):
        build_request(CFG, "translate", PNG)


def test_the_answer_is_parsed_and_failures_become_panel_messages():
    ok = parse_response("explain", response(json.dumps({"transcription": " 2 + 2 = 4 ", "result": "Four."})))
    assert ok.ok and ok.transcription == "2 + 2 = 4" and ok.result == "Four." and ok.usage["input_tokens"] == 1200
    fallback = [SimpleNamespace(type="fallback"), SimpleNamespace(type="text", text='{"transcription":"a","result":"b"}')]
    assert parse_response("explain", response(blocks=fallback, model="claude-opus-5")).model == "claude-opus-5"
    refusal = parse_response("explain", response(stop="refusal", blocks=[]))
    assert not refusal.ok and "declined" in refusal.error
    assert "cut off" in parse_response("explain", response('{"transcr', stop="max_tokens")).error
    assert not parse_response("explain", response("not json")).ok
    assert not parse_response("explain", response(blocks=[])).ok


def test_the_assistant_never_raises_and_names_the_problem():
    good = ClaudeAssistant(CFG, FakeClient(response('{"transcription": "hi", "result": "A greeting."}')))
    a = good.ask("summarize", PNG)
    assert a.ok and a.result == "A greeting." and a.latency_s >= 0 and good.client.calls[0]["fallbacks"] == "default"
    no_key = TypeError("Could not resolve authentication method. Expected one of api_key ...")
    assert "ANTHROPIC_API_KEY" in ClaudeAssistant(CFG, FakeClient(error=no_key)).ask("summarize", PNG).error
    for name, words in (("APIConnectionError", "internet"), ("APITimeoutError", "60 s"), ("RateLimitError", "moment"),
                        ("AuthenticationError", "not accepted")):
        err = type(name, (Exception,), {})("x")
        assert words in ClaudeAssistant(CFG, FakeClient(error=err)).ask("explain", PNG).error
    server = type("InternalServerError", (Exception,), {"status_code": 529})("overloaded")
    assert "529" in error_message(server, CFG)


def test_a_real_sdk_connection_error_is_recognised():
    anthropic = pytest.importorskip("anthropic")
    import httpx2
    err = anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"))
    assert "internet" in ClaudeAssistant(CFG, FakeClient(error=err)).ask("summarize", PNG).error


# -- worker -----------------------------------------------------------------------------------------------

def test_the_worker_runs_one_request_at_a_time_in_the_background(tmp_path):
    release = threading.Event()

    class SlowAssistant:
        def ask(self, action, png):
            release.wait(5)
            return AIAnswer(action, ok=True, transcription="x", result="y", latency_s=0.1)

    w = AIWorker(SlowAssistant(), save_dir=tmp_path)
    t0 = time.perf_counter()
    assert w.submit("summarize", PNG) and time.perf_counter() - t0 < 0.05        # never waits
    assert w.busy and not w.submit("explain", PNG) and w.poll() == []
    release.set()
    deadline = time.time() + 5
    got = []
    while not got and time.time() < deadline:
        got = w.poll()
        time.sleep(0.01)
    assert [a.action for a in got] == ["summarize"] and not w.busy
    assert len(list(tmp_path.glob("*.png"))) == 1 and json.loads(next(tmp_path.glob("*.json")).read_text())["ok"]
    w.close()


# -- selection --------------------------------------------------------------------------------------------

def canvas_with_words():
    c = Canvas(SIZE)
    for k, x in enumerate((200, 500, 800)):                       # three "words", two strokes each
        for dy in (0, 30):
            s = Stroke(c.new_id(), (25, 25, 25), 8.0)
            for i in range(30):
                s.append((x + 4 * i, 300 + dy + 10 * np.sin(i / 3)))
            c.add(s)
    return c


def square(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0 + 5, y0 + 5)]


def test_a_loop_selects_the_strokes_inside_it():
    c = canvas_with_words()
    assert select_in_loop(c, square(470, 260, 650, 370)) == [3, 4]          # the middle word only
    assert select_in_loop(c, square(150, 260, 1000, 370)) == [1, 2, 3, 4, 5, 6]
    assert select_in_loop(c, square(560, 260, 650, 370)) == []              # < 60 % of each stroke inside
    assert select_in_loop(c, square(500, 300, 510, 310)) == [] and loop_area(square(500, 300, 510, 310)) < 400


def test_the_selection_image_is_cropped_scaled_and_png():
    c = canvas_with_words()
    img = selection_image(c, [3, 4])
    assert img is not None and max(img.shape[:2]) <= 1024 and min(img.shape[:2]) >= 100
    assert (img < 128).any() and img[0, 0].tolist() == [255, 255, 255]    # ink inside, white margin
    whole = selection_image(c, [])                                         # nothing selected: everything
    assert whole.shape[1] > img.shape[1]
    assert selection_image(Canvas(SIZE)) is None
    assert cv2.imdecode(np.frombuffer(png_bytes(img), np.uint8), cv2.IMREAD_COLOR).shape == img.shape


# -- panel and controller ---------------------------------------------------------------------------------

def test_panel_layout_and_ascii_text():
    tb = Toolbar(SIZE, ai=True)
    panel = AIPanel(SIZE, tb.top)
    assert [b.name for b in panel.buttons] == [f"ai:{a}" for a in PANEL_ACTIONS] + ["ai:close"]
    assert all(panel.contains(b.centre) and panel.hit(b.centre) is b for b in panel.buttons)
    assert panel.rect[3] <= tb.top and not panel.contains((100, 100))
    assert ascii_text("“E = mc²” — it’s") == '"E = mc2" - it\'s'
    lines = wrap("a " * 200 + "supercalifragilisticexpialidocious" * 3, 300, 0.6)
    assert all(cv2.getTextSize(l, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)[0][0] <= 300 for l in lines)


def ev(kind, point=None):
    return Event(kind, 0.0, point)


def ai_controller():
    c = canvas_with_words()
    return c, DrawingController(c, Toolbar(SIZE, ai=True))


def test_select_then_ask_then_answer():
    c, ctl = ai_controller()
    ctl.press("select")
    loop = square(470, 260, 650, 370)
    ctl.handle([ev(STROKE_START, loop[0])] + [ev(STROKE_POINT, p) for p in loop[1:]] + [ev(STROKE_END)])
    assert ctl.selection == [3, 4] and len(c.strokes) == 6                 # selecting draws nothing
    ctl.press("ai")
    assert ctl.panel["state"] == "menu"
    ctl.press("ai:summarize")
    (action, png), = ctl.take_ai_jobs()
    assert action == "summarize" and png[:4] == b"\x89PNG" and ctl.panel["state"] == "thinking"
    ctl.press("ai:explain")                                                  # one request at a time
    assert ctl.take_ai_jobs() == [] and ctl.log["ai_refused_busy"] == 1
    ctl.ai_answer(AIAnswer("summarize", ok=True, transcription="hello", result="A greeting."))
    assert ctl.panel["state"] == "answer" and ctl.panel["answer"].result == "A greeting."
    ctl.ai_answer(AIAnswer("explain", ok=False, error="No connection to the Claude API: check the internet."))
    assert ctl.panel["state"] == "error" and "internet" in ctl.panel["message"]
    ctl.press("ai:close")
    assert ctl.panel is None
    ctl.ai_answer(AIAnswer("summarize", ok=True, result="late"))             # after closing: not shown
    assert ctl.panel is None and ctl.log["ai_answers"] == 2


def test_the_panel_blocks_drawing_under_it_and_empty_canvas_says_so():
    c, ctl = ai_controller()
    ctl.press("ai")
    inside = ctl.panel_layout.buttons[-1].centre
    ctl.handle([ev(STROKE_START, (inside[0], inside[1] + 120)), ev(STROKE_END)])
    assert ctl.log["strokes_refused_on_panel"] == 1 and len(c.strokes) == 6
    ctl.clear()
    ctl.press("ai:questions")
    assert ctl.panel["state"] == "error" and "Nothing written" in ctl.panel["message"] and ctl.take_ai_jobs() == []


def test_the_panel_is_pressed_by_dwell():
    c, ctl = ai_controller()
    ctl.press("ai")
    target = next(x for x in ctl.panel_layout.buttons if x.name == "ai:examples").centre
    ctl.update_pointer(0.0, target)
    ctl.update_pointer(0.5, target)
    assert ctl.dwell_progress == ("ai:examples", pytest.approx(0.5))
    ctl.update_pointer(1.05, target)
    assert ctl.take_ai_jobs()[0][0] == "examples"


@pytest.mark.parametrize("state", ["menu", "thinking", "answer", "error"])
def test_every_panel_state_renders(state):
    c, ctl = ai_controller()
    ctl.selection = [3, 4]
    ctl.press("ai")
    if state != "menu":
        ctl.press("ai:summarize")
    if state == "answer":
        ctl.ai_answer(AIAnswer("summarize", ok=True, transcription="the quick brown fox " * 5, result="word " * 200))
    if state == "error":
        ctl.ai_answer(AIAnswer("summarize", ok=False, error="The API key was not accepted."))
    blank = CanvasRenderer(SIZE).render(c, DrawingController(c, Toolbar(SIZE, ai=True)), Toolbar(SIZE, ai=True),
                                        mode=HOVER, cursor=None)
    img = CanvasRenderer(SIZE).render(c, ctl, ctl.toolbar, mode=HOVER, cursor=None)
    x0, y0, x1, y1 = ctl.panel_layout.rect
    assert (img[y0:y1, x0:x1] != blank[y0:y1, x0:x1]).any()
    assert (img[290:300, 500:600] != blank[290:300, 500:600]).any()           # the selection halo


def test_ai_off_never_loads_the_sdk():
    code = ("import sys; import invisible_canvas.tools.draw, invisible_canvas.interaction.drawing; "
            "print('anthropic' in sys.modules)")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert out.stdout.strip() == "False", out.stderr
