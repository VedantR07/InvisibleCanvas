"""Phase 3A (D51, §9.11): the Claude request and answer, the background worker, selection, the AI panel and the
controller flow. No network: Claude is a fake client."""

import base64
import itertools
import json
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from invisible_canvas.ai.client import ACTIONS, EXPLORE_SCHEMA, FALLBACK_BETA, SCHEMA, UNREADABLE, AIAnswer, \
    ClaudeAssistant, build_request, error_message, parse_response
from invisible_canvas.ai.worker import AIWorker
from invisible_canvas.canvas.model import Canvas, Stroke
from invisible_canvas.canvas.panel import PANEL_ACTIONS, AIPanel, ascii_text, wrap
from invisible_canvas.canvas.render import CanvasRenderer
from invisible_canvas.canvas.selection import close_loop, loop_area, png_bytes, select_in_loop, selection_image
from invisible_canvas.canvas.toolbar import Toolbar
from invisible_canvas.config import AIConfig
from invisible_canvas.interaction.drawing import DrawingController
from invisible_canvas.interaction.engine import HOVER, STROKE_END, STROKE_POINT, STROKE_START, Event

SIZE = (1280, 720)
CFG = AIConfig(enabled=True, backend="claude", local_model="qwen3-vl:8b", local_url="http://127.0.0.1:11434",
               model="claude-opus-5-5", effort="medium", max_tokens=16000, timeout_s=60.0, fallbacks=True)
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
        def ask(self, action, png, context=None):
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


# D53: the stroke starts where pointing starts, so a drawn loop carries the finger's way to its start (lead-in) and
# may run on past it. Joined end-to-start, those pieces changed the polygon (S1 run 1, loops 8 and 9).

def arc(cx, cy, rx, ry, a0, a1, n):
    return [(cx + rx * np.cos(a), cy + ry * np.sin(a)) for a in np.linspace(a0, a1, n)]


def line(p, q, step=10.0):
    n = max(int(np.hypot(q[0] - p[0], q[1] - p[1]) / step), 1)
    return [(p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t) for t in np.arange(n) / n]


def selected_as_drawn(c, loop):
    """The selection with the loop joined end-to-start as drawn (the behaviour before D53)."""
    contour = np.asarray(loop, np.float32).reshape(-1, 1, 2)
    return [sid for sid, s in c.strokes.items()
            if np.mean([cv2.pointPolygonTest(contour, (float(x), float(y)), False) >= 0 for x, y in s.array()]) >= 0.6]


def on_ellipse(points, cx, cy, rx, ry):
    p = np.asarray(points)
    return np.allclose(((p[:, 0] - cx) / rx) ** 2 + ((p[:, 1] - cy) / ry) ** 2, 1.0, atol=1e-6)


def test_close_loop_keeps_closed_and_short_loops():
    circle = arc(558, 315, 100, 60, 0, 2 * np.pi, 60)
    assert np.array_equal(close_loop(circle), np.asarray(circle))
    assert np.array_equal(close_loop(square(470, 260, 650, 370)), np.asarray(square(470, 260, 650, 370)))


def test_a_lead_in_over_a_neighbouring_word_is_not_selected():
    c = canvas_with_words()
    lead_in = line((190, 350), (190, 280)) + line((190, 280), (458, 315))   # from below the first word, over it
    loop = lead_in + arc(558, 315, 100, 60, np.pi, 3 * np.pi - 0.08, 100)    # then around the middle word
    assert selected_as_drawn(c, loop) == [1, 2, 3, 4]                         # the bug: the first word came too
    closed = close_loop(loop)
    assert len(closed) == 100 and on_ellipse(closed, 558, 315, 100, 60)      # exactly the loop, lead-in dropped
    assert select_in_loop(c, loop) == [3, 4]


def test_a_lead_in_through_the_word_does_not_cut_its_strokes_out():
    c = canvas_with_words()
    lead_in = line((560, 360), (558, 255))                                  # from inside, up through the word
    loop = lead_in + arc(558, 315, 100, 60, -np.pi / 2, 1.5 * np.pi + 1.2, 120)   # around, running on past the top
    assert selected_as_drawn(c, loop) == [4]                                 # the bug: stroke 3 cut out
    closed = close_loop(loop)
    assert on_ellipse(closed, 558, 315, 100, 60) and np.linalg.norm(closed[0] - closed[-1]) < 2.0
    assert select_in_loop(c, loop) == [3, 4]


def test_s1_run1_recorded_loops():
    """The 17 loops of S1 run 1 (2026-10-24), rebuilt from the trace: every completed loop selects exactly its word
    (before D53, loops 8 and 9 did not); the 5 loops that broke off (tracking lost) still select nothing."""
    data = json.loads((Path(__file__).parent / "fixtures" / "s1_run1_loops.json").read_text())
    canvas = Canvas.from_dict(data["canvas"])
    words = data["words"]
    for loop in data["loops"]:
        expected = words[loop["word"]] if loop["word"] else []
        assert (selected_as_drawn(canvas, loop["points"]) == expected) == (loop["n"] not in (8, 9)), loop["n"]
        assert select_in_loop(canvas, loop["points"]) == expected, loop["n"]
    assert sum(1 for loop in data["loops"] if loop["word"]) == 12


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
    assert ascii_text("100°C") == "100 degC"
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
    assert ctl.selection_log[-1]["ids"] == [3, 4] and ctl.selection_log[-1]["loop_bounds"] == [470, 260, 650, 370]
    assert ctl.selection_log[-1]["points"] == ctl.selection_log[-1]["closed_points"] == 5
    ctl.press("ai")
    assert ctl.panel["state"] == "menu"
    ctl.press("ai:summarize")
    (action, png, context), = ctl.take_ai_jobs()
    assert action == "summarize" and png[:4] == b"\x89PNG" and ctl.panel["state"] == "thinking"
    assert context == {"source": "selection"}                               # D61: what the AI reads
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


# -- local backend (D52): Ollama on this laptop --------------------------------------------------------------

import http.server
import socketserver

from invisible_canvas.ai.local import LocalAssistant, build_local_request, local_error_message, parse_local_response

LOCAL = AIConfig(**{**CFG.__dict__, "backend": "local", "timeout_s": 2.0})


def test_the_local_request_matches_the_claude_one():
    r = build_local_request(LOCAL, "explain", PNG)
    assert r["model"] == "qwen3-vl:8b" and r["stream"] is False and r["format"] == SCHEMA
    assert r["options"]["num_predict"] == 1024                        # never runs away (2026-10-23 smoke test)
    system, user = r["messages"]
    assert system["role"] == "system" and ACTIONS["explain"] in user["content"]
    assert base64.b64decode(user["images"][0]) == PNG
    with pytest.raises(ValueError):
        build_local_request(LOCAL, "translate", PNG)


def test_the_local_answer_is_parsed():
    reply = {"model": "qwen3-vl:8b", "done_reason": "stop", "prompt_eval_count": 900, "eval_count": 60,
             "message": {"role": "assistant", "content": json.dumps({"transcription": "x = 2", "result": "Two."})}}
    a = parse_local_response("explain", reply)
    assert a.ok and a.transcription == "x = 2" and a.usage == {"prompt_eval_count": 900, "eval_count": 60}
    assert "cut off" in parse_local_response("explain", {**reply, "done_reason": "length"}).error
    assert not parse_local_response("explain", {**reply, "message": {"content": "not json"}}).ok
    assert not parse_local_response("explain", {"model": "m"}).ok


class OllamaStub(http.server.BaseHTTPRequestHandler):
    mode = "ok"
    seen = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        OllamaStub.seen.append((self.path, body))
        if OllamaStub.mode == "missing":
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'{"error": "model not found"}')
            return
        if OllamaStub.mode == "slow":
            time.sleep(3)
        answer = {"transcription": "hello", "result": "A greeting."}
        if "topic" in body.get("format", {}).get("properties", {}):          # an EXPLORE request (D54)
            answer = {"transcription": "VOLCANO", "readable": True, "topic": "Volcanoes", "result": "- Molten rock"}
        out = {"model": body["model"], "done_reason": "stop", "message": {"content": json.dumps(answer)}}
        data = json.dumps(out).encode()
        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except ConnectionError:                    # the client gave up first (the timeout test)
            pass

    def log_message(self, *a):
        pass


@pytest.fixture
def ollama():
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), OllamaStub)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    OllamaStub.mode, OllamaStub.seen = "ok", []
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def test_the_local_assistant_talks_to_ollama_over_http(ollama):
    cfg = AIConfig(**{**LOCAL.__dict__, "local_url": ollama})
    assistant = LocalAssistant(cfg)
    assert assistant.warm_up() and OllamaStub.seen[-1][0] == "/api/generate"
    a = assistant.ask("summarize", PNG)
    assert a.ok and a.result == "A greeting." and OllamaStub.seen[-1][0] == "/api/chat"
    OllamaStub.mode = "missing"
    assert "ollama pull qwen3-vl:8b" in assistant.ask("summarize", PNG).error
    OllamaStub.mode = "slow"
    assert "No answer within 2 s" in assistant.ask("summarize", PNG).error


def test_the_local_assistant_says_when_ollama_is_not_running():
    with socketserver.TCPServer(("127.0.0.1", 0), OllamaStub) as s:
        port = s.server_address[1]                                 # a port with nothing listening after close
    # Windows refuses a closed local port only after ~2 s of retries: a realistic timeout lets the refusal win
    cfg = AIConfig(**{**LOCAL.__dict__, "local_url": f"http://127.0.0.1:{port}", "timeout_s": 15.0})
    a = LocalAssistant(cfg).ask("summarize", PNG)
    assert not a.ok and "start Ollama" in a.error
    assert LocalAssistant(cfg).warm_up() is False
    assert "Local AI request failed" in local_error_message(ValueError("x"), cfg)


def test_the_worker_warms_the_local_model_up_first():
    class Warm:
        def __init__(self):
            self.order = []

        def warm_up(self):
            self.order.append("warm")
            return True

        def ask(self, action, png, context=None):
            self.order.append(action)
            return AIAnswer(action, ok=True)

    assistant = Warm()
    w = AIWorker(assistant, warm_up=True)
    w.submit("summarize", PNG)
    deadline = time.time() + 5
    while not w.answers and time.time() < deadline:
        time.sleep(0.01)
    assert assistant.order == ["warm", "summarize"] and w.warmed_up is True
    w.close()


# -- EXPLORE (D54): the topic and what lies beyond the writing, in the same single request ----------------------

EXPLORE_OK = {"transcription": "VOLCANO", "readable": True, "topic": "Volcanoes",
              "result": "- Openings where molten rock reaches the surface\n- Related: plate tectonics"}


def claude_reply(data):
    return response(json.dumps(data))


def ollama_reply(data):
    return {"model": "qwen3-vl:8b", "done_reason": "stop", "message": {"content": json.dumps(data)}}


def test_explore_has_its_own_answer_format_and_the_other_actions_keep_theirs():
    assert "explore" in ACTIONS and "explore" in PANEL_ACTIONS
    assert EXPLORE_SCHEMA["required"] == ["transcription", "readable", "topic", "result"]
    assert EXPLORE_SCHEMA["properties"]["readable"]["type"] == "boolean"
    claude, local = build_request(CFG, "explore", PNG), build_local_request(LOCAL, "explore", PNG)
    assert claude["output_config"]["format"]["schema"] == EXPLORE_SCHEMA and local["format"] == EXPLORE_SCHEMA
    assert ACTIONS["explore"] in claude["messages"][0]["content"][1]["text"]
    assert ACTIONS["explore"] in local["messages"][1]["content"]
    for action in ("summarize", "explain", "simplify", "examples", "questions"):     # unchanged requests
        assert build_request(CFG, action, PNG)["output_config"]["format"]["schema"] == SCHEMA
        assert build_local_request(LOCAL, action, PNG)["format"] == SCHEMA


@pytest.mark.parametrize("parse, reply", [(parse_response, claude_reply), (parse_local_response, ollama_reply)])
def test_explore_names_a_topic_or_says_it_could_not_read_one(parse, reply):
    a = parse("explore", reply(EXPLORE_OK))
    assert a.ok and a.readable is True and a.topic == "Volcanoes" and a.result.startswith("- Openings")
    for unread in ({**EXPLORE_OK, "readable": False},                 # the model could not read it
                   {**EXPLORE_OK, "topic": "  "},                     # no topic named
                   {**EXPLORE_OK, "transcription": "[?] [?]"},        # nothing read but unreadable marks
                   {**EXPLORE_OK, "readable": "true"}):               # not a JSON true
        u = parse("explore", reply(unread))
        assert u.ok and u.readable is False and u.topic == ""
        assert u.result == UNREADABLE                                 # the model's facts are never shown
    assert not parse("explore", reply({"transcription": "x", "result": "y"})).ok     # format not kept: an error
    s = parse("summarize", reply({"transcription": "x", "result": "y"}))
    assert s.ok and s.result == "y" and s.readable is None and s.topic == ""        # other actions unchanged


def test_the_panel_has_explore_and_keeps_its_answer_area():
    tb = Toolbar(SIZE, ai=True)
    panel = AIPanel(SIZE, tb.top)
    assert [b.name for b in panel.buttons] == [f"ai:{a}" for a in PANEL_ACTIONS] + ["ai:close"]
    x0, y0, x1, y1 = panel.rect
    rects = [b.rect for b in panel.buttons]
    assert all(x0 < bx0 and bx1 < x1 and y0 < by0 and by1 < panel.text_top for bx0, by0, bx1, by1 in rects)
    assert not any(a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]          # no two buttons overlap
                   for a, b in itertools.combinations(rects, 2))
    for b in panel.buttons:                    # every label fits; every button at least toolbar-sized
        bw, bh = b.rect[2] - b.rect[0], b.rect[3] - b.rect[1]
        assert cv2.getTextSize(b.name[3:].upper(), cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)[0][0] <= bw - 16
        assert bw >= tb.button_w and bh >= 52
    close = panel.buttons[-1].rect
    assert close[2] == max(r[2] for r in rects) and close[3] == max(r[3] for r in rects)   # bottom right, as before
    assert y1 - panel.text_top == 374                                 # the answer area did not shrink (D51: 374 px)


def test_explore_is_pressed_by_dwell_and_its_answer_shows_the_topic_or_the_note(monkeypatch):
    c, ctl = ai_controller()
    ctl.press("ai")
    target = next(b for b in ctl.panel_layout.buttons if b.name == "ai:explore").centre
    ctl.update_pointer(0.0, target)
    ctl.update_pointer(1.05, target)
    (action, png, context), = ctl.take_ai_jobs()
    assert action == "explore" and png[:4] == b"\x89PNG" and ctl.panel["state"] == "thinking"
    texts, real = [], cv2.putText
    monkeypatch.setattr(cv2, "putText", lambda img, text, *a, **k: (texts.append(text), real(img, text, *a, **k))[1])
    ctl.ai_answer(parse_local_response("explore", ollama_reply(EXPLORE_OK)))
    CanvasRenderer(SIZE).render(c, ctl, ctl.toolbar, mode=HOVER, cursor=None)
    assert "READ:" in texts and "VOLCANO" in texts and "EXPLORE: VOLCANOES" in texts
    assert "- Openings where molten rock reaches the surface" in " ".join(texts)
    texts.clear()
    ctl.ai_answer(parse_local_response("explore", ollama_reply(
        {"transcription": "[?] [?]", "readable": False, "topic": "Dragons", "result": "- Dragons breathe fire"})))
    CanvasRenderer(SIZE).render(c, ctl, ctl.toolbar, mode=HOVER, cursor=None)
    shown = " ".join(texts)
    assert "EXPLORE:" in texts and UNREADABLE in shown                    # the fixed note, as written
    assert "Dragons" not in shown and "DRAGONS" not in shown and "fire" not in shown   # nothing guessed


def test_explore_goes_through_the_same_local_request(ollama):
    a = LocalAssistant(AIConfig(**{**LOCAL.__dict__, "local_url": ollama})).ask("explore", PNG)
    assert a.ok and a.topic == "Volcanoes" and a.readable is True and a.result == "- Molten rock"
    path, body = OllamaStub.seen[-1]
    assert path == "/api/chat" and body["format"] == EXPLORE_SCHEMA


def test_a_cut_off_explore_answer_shows_the_note_and_the_other_actions_still_report_it():
    # dry run 2026-10-25: on a scribble the model repeated "[?]" until the token limit
    cut = [parse_response("explore", response('{"transcription": "[?] [?] [?', stop="max_tokens")),
           parse_local_response("explore", {**ollama_reply({}), "done_reason": "length"})]
    assert all(a.ok and a.readable is False and a.result == UNREADABLE and a.topic == "" for a in cut)
    assert "cut off" in parse_response("summarize", response('{"tr', stop="max_tokens")).error      # unchanged
    assert "cut off" in parse_local_response("summarize", {**ollama_reply({}), "done_reason": "length"}).error
    assert build_local_request(LOCAL, "explore", PNG)["options"]["num_predict"] == 400
    assert all(build_local_request(LOCAL, a, PNG)["options"]["num_predict"] == 1024
               for a in ("summarize", "explain", "simplify", "examples", "questions"))


def test_explore_points_run_together_are_put_on_their_own_lines():
    # EXPLORE physical run 1 (2026-10-25): the SQL answer came as one line and the panel wrapped it as a paragraph
    sql = ("- Structured Query Language manages relational databases. - Standardized by ANSI and ISO for data "
           "manipulation. - Used for querying, updating, and managing database structures. - Explore ACID properties "
           "for transactional integrity.")
    a = parse_local_response("explore", ollama_reply({**EXPLORE_OK, "transcription": "WHAT IS SQL", "topic": "SQL",
                                                      "result": sql}))
    assert a.result.split("\n") == [
        "- Structured Query Language manages relational databases.",
        "- Standardized by ANSI and ISO for data manipulation.",
        "- Used for querying, updating, and managing database structures.",
        "- Explore ACID properties for transactional integrity."]
    assert parse_local_response("explore", ollama_reply(EXPLORE_OK)).result == EXPLORE_OK["result"]   # already lines
    kept = parse_local_response("explore", ollama_reply({**EXPLORE_OK, "result": "- A well - known x-ray fact"}))
    assert kept.result == "- A well - known x-ray fact"                       # a dash inside a point stays
    s = parse_local_response("summarize", ollama_reply({"transcription": "x", "result": "One. - Two"}))
    assert s.result == "One. - Two"                                            # other actions untouched
