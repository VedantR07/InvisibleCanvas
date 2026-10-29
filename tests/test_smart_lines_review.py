"""Smart Lines recognition and review (brain.md D64): each completed line is read in the background as a literal and a
corrected text; nothing is accepted on its own; OK, AS WRITTEN, EDIT, KEEP INK and RETRY are undoable; a late
reading after an edit, a decision or a retry is ignored; readings and decisions are saved, unread lines are read
again on resume; the strokes are never changed. No test reaches a real Ollama (fake openers and recognizers)."""

import base64
import json
import socket
import threading
import time
import urllib.error

import cv2
import numpy as np
import pytest

from invisible_canvas.ai.recognize import (
    LINE_MAX_TOKENS, SCHEMA, SYSTEM, LineRecognizer, RecognitionWorker, build_line_request, reading_from_response,
)
from invisible_canvas.canvas import text as typeset
from invisible_canvas.canvas.board import Board
from invisible_canvas.canvas.lines import INK, OFF_FILL, READING_INK, SUGGESTION, render_controls, render_sheet
from invisible_canvas.canvas.model import Canvas
from invisible_canvas.canvas.render import PAGE_FILL, TOOL_SELECTED, CanvasRenderer
from invisible_canvas.canvas.toolbar import Toolbar
from invisible_canvas.config import AIConfig
from invisible_canvas.interaction.drawing import DrawingController
from invisible_canvas.interaction.engine import HOVER, STROKE_END, STROKE_POINT, STROKE_START, Event
from invisible_canvas.tools.draw import handle_keys

SIZE = (1280, 720)
Y = 480
CFG = AIConfig(enabled=True, backend="local", local_model="qwen3-vl:8b-instruct", local_url="http://127.0.0.1:11434",
               model="claude-opus-5-5", effort="medium", max_tokens=16000, timeout_s=120.0, fallbacks=True)


def ok(written, text=None):
    return {"ok": True, "written": written, "text": written if text is None else text, "error": "", "latency_s": 1.0}


def failed(error="No answer within 120 s."):
    return {"ok": False, "written": "", "text": "", "error": error, "latency_s": 120.0}


def stroke(ctl, points):
    ctl.handle([Event(STROKE_START, 0.0, points[0])] + [Event(STROKE_POINT, 0.0, p) for p in points[1:]]
               + [Event(STROKE_END, 0.0)])


def dwell(ctl, name, t0=0.0):
    """Hold the cursor on a button where it is now (D65: Smart Lines buttons beside an open panel)."""
    if name.startswith("lines:"):
        b = ctl.lines_controls.button(name)
    elif name.startswith("ai:"):
        b = next(x for x in ctl.panel_layout.buttons if x.name == name)
    else:
        b = ctl.toolbar.button(name)
    dwell_at(ctl, b.centre, t0)


def dwell_at(ctl, point, t0=0.0):
    ctl.update_pointer(t0, point)
    ctl.update_pointer(t0 + 1.05, point)
    ctl.update_pointer(t0 + 1.1, None)


def controller(recognition=True, ai=False):
    ctl = DrawingController(Canvas(SIZE), Toolbar(SIZE, ai=ai))
    ctl.recognition = recognition
    ctl.press("lines")
    return ctl


def write_line(ctl, x=300):
    stroke(ctl, [(x, Y - 30), (x + 5, Y), (x, Y + 30)])
    stroke(ctl, [(x + 20, Y - 30), (x + 40, Y + 30)])
    ctl.press("lines:complete")
    return ctl.sheet().lines[-1]


def snapshot(line):
    return [(s.id, list(s.points), s.color, s.width) for s in line.strokes]


def texts_drawn(monkeypatch, fn):
    texts, real = [], typeset.draw
    monkeypatch.setattr(typeset, "draw", lambda img, ops: (texts.extend(op[2] for op in ops if op[0] == "text"),
                                                          real(img, ops))[1])
    fn()
    monkeypatch.setattr(typeset, "draw", real)
    return texts


# -- the recognizer -----------------------------------------------------------------------------------------------

def test_one_request_asks_the_local_model_for_the_literal_and_the_corrected_text():
    png = b"\x89PNG fake"
    r = build_line_request(CFG, png)
    assert r["model"] == "qwen3-vl:8b-instruct" and r["stream"] is False and r["format"] == SCHEMA
    assert SCHEMA["required"] == ["written", "text"]
    assert r["options"] == {"temperature": 0, "num_predict": LINE_MAX_TOKENS}
    system, user = r["messages"]
    assert system["content"] == SYSTEM and base64.b64decode(user["images"][0]) == png
    assert "Do not correct spelling" in SYSTEM and "Correct clear spelling mistakes" in SYSTEM   # the two texts
    assert "Write [?] for each character you cannot read" in SYSTEM


def reply(content, done="stop"):
    return {"model": "qwen3-vl:8b-instruct", "done_reason": done, "eval_count": 30,
            "message": {"content": content if isinstance(content, str) else json.dumps(content)}}


def test_readings_from_the_model_and_every_kind_of_unusable_answer():
    r = reading_from_response(reply({"written": "ICE IS  COLDWATER ", "text": "ICE IS COLD WATER"}))
    assert r["ok"] and r["written"] == "ICE IS COLDWATER" and r["text"] == "ICE IS COLD WATER" and r["error"] == ""
    r = reading_from_response(reply({"written": "CAT", "text": ""}))
    assert r["ok"] and r["text"] == "CAT"                                  # no correction: the literal one
    r = reading_from_response(reply({"written": "[?][?][?]", "text": "CAT"}))
    assert not r["ok"] and "Nothing readable" in r["error"] and r["text"] == ""     # never a suggestion from nothing
    for bad, message in [(reply({"written": "", "text": ""}), "Nothing readable"),
                         (reply({"written": "A"}, done="length"), "cut off"),
                         ({"model": "m", "message": {}}, "no text"),
                         (reply("not json"), "could not be read"),
                         (reply("[1, 2]"), "could not be read")]:
        r = reading_from_response(bad)
        assert not r["ok"] and message in r["error"], bad


class Response:
    def __init__(self, data):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *e):
        pass

    def read(self):
        return json.dumps(self.data).encode()


@pytest.mark.parametrize("error, message", [
    (urllib.error.URLError(ConnectionRefusedError()), "start Ollama"),
    (urllib.error.URLError(socket.timeout()), "No answer within 120 s"),
    (urllib.error.HTTPError("u", 404, "missing", {}, None), "ollama pull qwen3-vl:8b-instruct"),
    (ValueError("x"), "Local AI request failed")])
def test_the_recognizer_turns_every_failure_into_a_reading(error, message):
    def opener(request, timeout):
        raise error
    r = LineRecognizer(CFG, opener).read(b"png")
    assert not r["ok"] and message in r["error"] and r["latency_s"] >= 0


def test_the_recognizer_reads_through_ollamas_chat_api():
    seen = []

    def opener(request, timeout):
        seen.append((request.full_url, json.loads(request.data), timeout))
        return Response(reply({"written": "THE SUN IS A STAR", "text": "THE SUN IS A STAR"}))
    r = LineRecognizer(CFG, opener).read(b"png")
    assert r["ok"] and r["text"] == "THE SUN IS A STAR" and r["model"] == "qwen3-vl:8b-instruct"
    url, body, timeout = seen[0]
    assert url == "http://127.0.0.1:11434/api/chat" and body["format"] == SCHEMA and timeout == 120.0


def test_the_worker_reads_one_line_after_another_skips_cancelled_ones_and_saves_them(tmp_path):
    gate, order = threading.Event(), []

    class Slow:
        def read(self, png):
            gate.wait(5)
            order.append(png)
            return ok(png.decode())

    worker = RecognitionWorker(Slow(), save_dir=tmp_path)
    for n in (1, 2, 3):
        worker.submit(n, f"L{n}".encode(), {"page": 1, "line": n})
    assert worker.busy
    worker.cancel(2)                                                       # not started yet: skipped
    gate.set()
    results, end = [], time.time() + 5
    while len(results) < 3 and time.time() < end:
        results += worker.poll()
        time.sleep(0.01)
    assert [(n, r and r["text"]) for n, r in results] == [(1, "L1"), (2, None), (3, "L3")]
    assert order == [b"L1", b"L3"] and not worker.busy and [r["request"] for r in worker.readings] == [1, 3]
    saved = sorted(p.name for p in tmp_path.iterdir())
    assert len(saved) == 4 and saved[0].endswith("-001-p1-l1.json") and saved[2].endswith("-003-p1-l3.json")
    assert json.loads((tmp_path / saved[0]).read_text())["text"] == "L1"
    worker.close()


# -- reading and review in the controller ------------------------------------------------------------------------

def test_done_shows_the_line_at_once_and_reads_it_once_in_the_background(monkeypatch):
    ctl = controller()
    line = write_line(ctl)
    written = snapshot(line)
    assert line.status == "recognizing" and line.decision is None and ctl.review_line() is line
    (n, png, context), = ctl.take_line_jobs()
    assert png[:4] == b"\x89PNG" and context == {"page": 1, "line": 1} and line.request == n
    assert ctl.take_line_jobs() == [] and ctl.take_line_cancels() == []       # one request awaited
    texts = texts_drawn(monkeypatch, lambda: ctl.background)
    assert "reading..." in texts
    assert ctl.lines_view()[3][:3] == (1, "recognizing", "reading the handwriting...")
    ctl.line_result(n, ok("ICE IS COLDWATER", "ICE IS COLD WATER"))
    assert line.status == "check" and line.decision is None and line.text == "ICE IS COLD WATER"   # not accepted
    assert snapshot(line) == written                                          # the strokes are untouched
    texts = texts_drawn(monkeypatch, lambda: ctl.background)
    assert "ICE IS COLD WATER" in texts
    enabled, _, _, bar = ctl.lines_view()
    assert bar == (1, "check", "ICE IS COLD WATER", "(written: ICE IS COLDWATER)", None)
    assert {"lines:ok", "lines:written", "lines:edit", "lines:ink", "lines:retry"} <= enabled


def test_ok_and_as_written_and_keep_ink_are_undoable_steps():
    ctl = controller()
    line = write_line(ctl)
    (n, _, _), = ctl.take_line_jobs()
    ctl.line_result(n, ok("ICE IS COLDWATER", "ICE IS COLD WATER"))
    written = snapshot(line)
    dwell(ctl, "lines:ok")
    assert line.status == "confirmed" and line.text == "ICE IS COLD WATER" and line.decision["kind"] == "ok"
    assert ctl.review_line() is None and not ctl.lines_enabled("lines:ok")    # nothing left to review
    ctl.undo()
    assert line.status == "check" and ctl.review_line() is line
    ctl.redo()
    assert line.text == "ICE IS COLD WATER"
    ctl.undo()
    dwell(ctl, "lines:written", 5.0)
    assert line.status == "confirmed" and line.text == "ICE IS COLDWATER" and line.decision["kind"] == "as_written"
    ctl.undo()
    dwell(ctl, "lines:ink", 10.0)
    assert line.status == "ink" and line.text is None
    ctl.review_pick = {"sheet": ctl.sheet(), "line": line}
    assert ctl.lines_view()[3][2:4] == ("kept as handwriting", "(suggestion: ICE IS COLD WATER)")
    dwell(ctl, "lines:ok", 15.0)                                              # the suggestion after all
    assert line.status == "confirmed" and line.text == "ICE IS COLD WATER"
    for _ in range(2):
        ctl.undo()
    assert line.status == "check" and len(ctl.sheet().lines) == 1
    ctl.undo()                                                                # DONE itself: back to unfinished
    assert ctl.sheet().lines == [] and len(ctl.sheet().canvas.strokes) == 2
    ctl.redo()
    assert ctl.sheet().lines == [line] and line.status == "check" and snapshot(line) == written
    assert ctl.take_line_jobs() == []                                         # its reading came back with it
    ctl.press("pen")
    stroke(ctl, [(300, 150), (400, 150)])
    ctl.undo()                                                                # PEN: the page's ink only
    assert ctl.canvas.strokes == {} and line.status == "check"


def test_as_written_is_greyed_when_the_literal_text_is_the_suggestion():
    ctl = controller()
    line = write_line(ctl)
    (n, _, _), = ctl.take_line_jobs()
    ctl.line_result(n, ok("THE SUN IS A STAR"))
    assert ctl.lines_enabled("lines:ok") and not ctl.lines_enabled("lines:written")
    assert ctl.lines_view()[3][3] == ""                                       # no "(written: ...)": the same text
    dwell(ctl, "lines:written")
    assert line.status == "check" and ctl.log["lines:review_disabled"] == 1


def test_edit_types_the_line_on_the_laptop_keyboard():
    ctl = controller()
    line = write_line(ctl)
    (n, _, _), = ctl.take_line_jobs()
    ctl.line_result(n, ok("ICE IS COLDWATER", "ICE IS COLD WATER"))
    dwell(ctl, "lines:edit")
    assert ctl.typing and not ctl.asking and ctl.line_edit["text"] == "ICE IS COLD WATER"
    assert ctl.lines_view()[3][4] == "ICE IS COLD WATER"
    ok_button = ctl.lines_layout.button("lines:ok").centre
    ctl.update_pointer(5.0, ok_button)
    ctl.update_pointer(6.1, ok_button)                                        # no review buttons while typing
    assert ctl.log["press:lines:ok"] == 0
    saved = []
    keys = [8] * 5 + [ord(c) for c in "WATER. zys"] + [8, 8, 8, 8]            # z, y and s are text here
    assert not handle_keys(keys, ctl, 0.0, {"until": 0.0}, saved, lambda: saved.append(1))
    assert ctl.line_edit["text"] == "ICE IS COLD WATER." and saved == [] and ctl.log["undo"] == 0
    handle_keys([13], ctl, 0.0, {"until": 0.0}, saved, lambda: None)          # Enter saves
    assert not ctl.typing and line.status == "confirmed" and line.decision == {"kind": "edit",
                                                                                "text": "ICE IS COLD WATER."}
    ctl.undo()
    assert line.status == "check"
    dwell(ctl, "lines:edit", 10.0)
    ctl.type_key(ord("X"))
    ctl.type_key(27)                                                          # Esc cancels
    assert not ctl.typing and line.status == "check" and ctl.log["lines:edit_cancelled"] == 1
    dwell(ctl, "lines:edit", 15.0)
    for _ in range(40):
        ctl.type_key(8)
    ctl.type_key(13)                                                          # empty: nothing saved, still typing
    assert ctl.typing and line.status == "check"
    ctl.press("pen")                                                          # leaving LINES ends the typing
    assert not ctl.typing and ctl.log["lines:edit_left"] == 1


def test_edit_and_ask_take_turns_at_the_keyboard():
    ctl = controller(ai=True)
    ctl.press("pen")
    stroke(ctl, [(300, 150), (400, 150)])                                     # freehand ink for the AI
    ctl.press("lines")
    line = write_line(ctl)
    ctl.press("ai")
    ctl.press("ai:ask")
    assert ctl.asking
    ctl.press("lines:edit")                                                   # the question is being typed
    assert ctl.line_edit is None and ctl.log["lines:edit_refused_ask"] == 1 and "AI question" in ctl.notice["text"]
    ctl.type_key(27)
    ctl.press("lines:edit")
    assert ctl.line_edit["line"] is line
    ctl.press("ai:ask")
    assert ctl.panel["state"] == "error" and "line being edited" in ctl.panel["message"]
    ctl.type_key(ord("A"))
    assert ctl.line_edit["text"] == "A"


def test_a_late_reading_after_an_edit_or_keep_ink_is_ignored():
    ctl = controller()
    line = write_line(ctl)
    (n, _, _), = ctl.take_line_jobs()
    dwell(ctl, "lines:edit")                                                  # before the reading comes
    for c in "OXYGEN":
        ctl.type_key(ord(c))
    ctl.type_key(13)
    assert line.decision == {"kind": "edit", "text": "OXYGEN"} and line.request is None
    assert ctl.take_line_cancels() == [n] and ctl.take_line_cancels() == []
    ctl.line_result(n, ok("OXYGFN"))                                          # late: ignored
    assert line.text == "OXYGEN" and line.reading is None and ctl.log["lines:stale_results"] == 1
    line2 = write_line(ctl, 500)
    (n2, _, _), = ctl.take_line_jobs()
    ctl.review_pick = {"sheet": ctl.sheet(), "line": line2}
    dwell(ctl, "lines:ink", 5.0)
    ctl.line_result(n2, None)                                                 # skipped by the reader
    assert line2.status == "ink" and ctl.log["lines:skipped"] == 1
    ctl.undo()                                                                # KEEP INK undone: read again
    assert line2.status == "recognizing"
    (n3, _, _), = ctl.take_line_jobs()
    ctl.line_result(n3, ok("NITROGEN"))
    assert line2.status == "check" and line2.text == "NITROGEN"


def test_retry_reads_again_and_a_reading_of_an_undone_retry_is_ignored():
    ctl = controller()
    line = write_line(ctl)
    (n1, _, _), = ctl.take_line_jobs()
    ctl.line_result(n1, failed())
    assert line.status == "failed" and ctl.review_line() is line
    assert ctl.lines_view()[3][2] == "not recognised - No answer within 120 s."
    assert not ctl.lines_enabled("lines:ok") and not ctl.lines_enabled("lines:written")
    assert ctl.lines_enabled("lines:retry") and ctl.lines_enabled("lines:edit") and ctl.lines_enabled("lines:ink")
    dwell(ctl, "lines:retry")
    assert line.status == "recognizing" and ctl.review_line() is line
    (n2, _, _), = ctl.take_line_jobs()
    ctl.undo()                                                                # RETRY undone: the failure is back
    assert line.status == "failed" and ctl.take_line_cancels() == [n2]
    ctl.line_result(n2, ok("CAT"))
    assert line.status == "failed" and ctl.log["lines:stale_results"] == 1
    ctl.redo()                                                                # RETRY again: a new request
    (n3, _, _), = ctl.take_line_jobs()
    ctl.line_result(n3, ok("CAT"))
    assert n3 not in (n1, n2) and line.status == "check" and line.text == "CAT"
    dwell(ctl, "lines:ok", 5.0)
    ctl.review_pick = {"sheet": ctl.sheet(), "line": line}
    dwell(ctl, "lines:retry", 10.0)                                           # a confirmed line can be read again
    assert line.status == "recognizing" and line.decision is None
    ctl.undo()
    assert line.status == "confirmed" and line.text == "CAT"


def test_a_reading_for_a_line_undone_meanwhile_is_kept_for_the_redo():
    ctl = controller()
    line = write_line(ctl)
    (n, _, _), = ctl.take_line_jobs()
    ctl.undo()                                                                # DONE undone while it is read
    assert ctl.sheet().lines == [] and ctl.take_line_cancels() == []
    ctl.line_result(n, ok("SUN"))
    assert line.reading["text"] == "SUN" and ctl.review_line() is None
    ctl.redo()
    assert ctl.sheet().lines == [line] and line.status == "check" and ctl.take_line_jobs() == []


def test_without_a_reader_lines_are_marked_not_recognised_and_cannot_be_retried():
    ctl = controller(recognition=False)
    line = write_line(ctl)
    assert ctl.take_line_jobs() == []
    assert line.status == "failed" and "AI is off" in line.reading["error"] and not ctl.lines_enabled("lines:retry")
    dwell(ctl, "lines:ink")
    assert line.status == "ink"


def test_the_review_bar_goes_through_the_lines_waiting_and_a_note_line_can_be_picked():
    ctl = controller()
    lines = [write_line(ctl, 200 + 100 * k) for k in range(3)]
    jobs = ctl.take_line_jobs()
    assert [c["line"] for _, _, c in jobs] == [1, 2, 3]
    assert ctl.review_line() is lines[2]                                      # the newest one being read
    ctl.line_result(jobs[2][0], ok("THREE"))
    ctl.line_result(jobs[1][0], failed())
    assert ctl.review_line() is lines[1]                                      # the first one waiting
    dwell(ctl, "lines:ink")
    assert ctl.review_line() is lines[2]
    dwell(ctl, "lines:ok", 5.0)
    assert ctl.review_line() is lines[0] and lines[0].status == "recognizing"
    dwell(ctl, "lines:row:2", 10.0)                                           # hold on note line 3
    assert ctl.review_line() is lines[2] and ctl.log["lines:pick"] == 1
    assert ctl.lines_view()[3][:3] == (3, "confirmed", "THREE")
    assert not ctl.lines_enabled("lines:row:3")                               # no line there
    ctl.press("pen")
    assert ctl.review_line() is None                                          # LINES only


def test_a_line_stroke_ends_on_the_review_bar_and_nothing_is_drawn_there():
    ctl = controller()
    write_line(ctl)
    ctl.take_line_jobs()
    bx0, by0, bx1, by1 = ctl.lines_layout.bar
    ctl.handle([Event(STROKE_START, 0.0, (300, 420)), Event(STROKE_POINT, 0.0, (300, 410)),
                Event(STROKE_POINT, 0.0, (300, (by0 + by1) / 2)), Event(STROKE_POINT, 0.0, (300, 300))])
    assert ctl.blocked == "zone" and ctl.log["line_strokes_left_zone"] == 1  # D66: ended where it left the zone
    s = list(ctl.sheet().canvas.strokes.values())[-1]
    assert min(y for _, y in s.points) >= by1


def test_readings_and_decisions_are_saved_and_unread_lines_are_read_again_on_resume():
    ctl = controller()
    lines = [write_line(ctl, 200 + 60 * k) for k in range(5)]
    jobs = {c["line"]: n for n, _, c in ctl.take_line_jobs()}
    ctl.line_result(jobs[1], ok("OXYGFN", "OXYGEN"))
    ctl.line_result(jobs[2], ok("CAT"))
    ctl.line_result(jobs[3], ok("DOG"))
    ctl.line_result(jobs[5], failed())                                        # line 4: still being read at the save
    dwell(ctl, "lines:edit")                                                  # line 1 (waiting first)
    for c in " gas":
        ctl.type_key(ord(c))
    ctl.type_key(13)
    ctl.review_pick = {"sheet": ctl.sheet(), "line": lines[2]}
    dwell(ctl, "lines:ink", 5.0)
    before = [(line.id, line.status, line.text, line.reading) for line in lines]
    data = json.loads(json.dumps(ctl.board.to_dict()))
    assert data["smart_lines"][0]["version"] == 2 and "request" not in data["smart_lines"][0]["lines"][3]
    again = Board.from_dict(data)
    after = again.pages[0].lines.lines
    assert [(line.id, line.status, line.text, line.reading) for line in after] == before
    assert [line.text for line in after] == ["OXYGEN gas", "CAT", None, None, None]
    for a, b in zip(lines, after):                                            # the strokes as written (2 decimals)
        assert [(s.id, s.color, s.width) for s in a.strokes] == [(s.id, s.color, s.width) for s in b.strokes]
        assert all(np.allclose(sa.array(), sb.array(), atol=0.006) for sa, sb in zip(a.strokes, b.strokes))
    assert [line.status for line in after] == ["confirmed", "check", "ink", "recognizing", "failed"]
    resumed = DrawingController(Canvas(SIZE), Toolbar(SIZE), board=again)
    resumed.recognition = True
    (n, png, context), = resumed.take_line_jobs()                             # only the line without a reading
    assert context == {"page": 1, "line": 4}
    old = json.loads(json.dumps(data))                                        # a Phase 1 record (version 1)
    old["smart_lines"][0]["version"] = 1
    for record in old["smart_lines"][0]["lines"]:
        del record["reading"], record["decision"]
    phase1 = DrawingController(Canvas(SIZE), Toolbar(SIZE), board=Board.from_dict(old))
    phase1.recognition = True
    assert [c["line"] for _, _, c in phase1.take_line_jobs()] == [1, 2, 3, 4, 5]   # all read now
    with pytest.raises(ValueError):
        bad = json.loads(json.dumps(data))
        bad["smart_lines"][0]["lines"][0]["decision"] = {"kind": "guess", "text": "x"}
        Board.from_dict(bad)


def test_the_controls_and_review_bar_are_drawn_only_with_lines_and_cached():
    ctl = controller()
    line = write_line(ctl)
    (n, _, _), = ctl.take_line_jobs()
    ctl.line_result(n, ok("ICE IS COLDWATER", "ICE IS COLD WATER"))
    r = CanvasRenderer(SIZE)
    bx0, by0, bx1, by1 = ctl.lines_layout.bar
    img = r.render(ctl.canvas, ctl, ctl.toolbar, mode=HOVER, cursor=None)
    bar = img[by0:by1, bx0:bx1]
    assert (bar != 255).any() and (np.abs(bar.astype(int) - SUGGESTION).sum(axis=2) < 60).any()   # blue text
    _, top, _, bottom = ctl.lines_layout.rows[0].rect
    row = img[top:bottom, 40:900]
    assert (np.abs(row.astype(int) - SUGGESTION).sum(axis=2) < 60).any()   # the suggestion in the notes, blue
    view = ctl.lines_view()
    assert render_controls(ctl.lines_layout, view) is render_controls(ctl.lines_layout, ctl.lines_view())
    ok_button = ctl.lines_layout.button("lines:ok")
    ctl.update_pointer(0.0, ok_button.centre)
    ctl.update_pointer(0.5, ok_button.centre)
    img = r.render(ctl.canvas, ctl, ctl.toolbar, mode=HOVER, cursor=None)
    x0, y0, x1, y1 = ok_button.rect
    assert (img[y1 - 6, x0 + 5:x0 + 25] == (200, 60, 200)).all()              # hold-to-press progress
    ctl.update_pointer(0.6, None)
    ctl.press("pen")
    img = r.render(ctl.canvas, ctl, ctl.toolbar, mode=HOVER, cursor=None)
    assert (img[by0:by1, bx0:bx1] == 255).all()                               # no review bar with PEN
    assert (np.abs(img[top:bottom, 40:900].astype(int) - SUGGESTION).sum(axis=2) < 60).any()   # notes still


def test_the_notes_are_typeset_and_drawn_again_only_when_a_line_changes():
    ctl = controller()
    layout = ctl.lines_layout
    line = write_line(ctl)
    sheet = ctl.sheet()
    first = render_sheet(sheet, layout, True)
    assert render_sheet(sheet, layout, True) is first
    (n, _, _), = ctl.take_line_jobs()
    ctl.line_result(n, ok("Café: 3 × 4 = 12, 25 °C"))                        # any Unicode text (Segoe UI)
    second = render_sheet(sheet, layout, True)
    assert second is not first and line.text == "Café: 3 × 4 = 12, 25 °C"
    stroke(ctl, [(500, Y - 30), (500, Y + 30)])                               # a new stroke: the zone only
    notes = sheet._notes
    third = render_sheet(sheet, layout, True)
    assert sheet._notes is notes and third is not second
    x0, y0, x1, y1 = layout.zone
    assert (third[y0:y1, 495:506] < 100).any() and (second[y0:y1, 495:506] > 110).all()   # (the baseline: 120)
    ctl.undo()                                                                # the stroke goes: drawn again
    assert (render_sheet(sheet, layout, True)[y0:y1, 495:506] > 110).all()


# -- D65: the AI panel and the Smart Lines buttons -----------------------------------------------------------------

def overlaps(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def size_of(rect):
    return rect[2] - rect[0], rect[3] - rect[1]


def reviewed_line_with_panel():
    """LINES with a line waiting for review (the review bar shown) and the AI panel open."""
    ctl = controller(ai=True)
    line = write_line(ctl)
    (n, _, _), = ctl.take_line_jobs()
    ctl.line_result(n, ok("ICE IS COLDWATER", "ICE IS COLD WATER"))
    ctl.press("ai")
    assert ctl.panel["state"] == "menu" and ctl.tool == "lines"
    return ctl, line


def test_the_open_ai_panel_lies_over_none_of_the_smart_lines_buttons():
    ctl = controller(ai=True)
    own, panel = ctl.lines_layout.controls, ctl.panel_layout.rect
    assert ctl.lines_controls is own
    covered = [b.name for b in own.buttons + own.review_buttons if overlaps(b.rect, panel)]
    assert covered == ["lines:complete", "lines:up", "lines:down", "lines:written", "lines:edit", "lines:ink",
                       "lines:retry"]                                       # the conflict in the layout's own places
    ctl.press("ai")
    beside = ctl.lines_controls
    assert beside is not own and ctl.lines_controls is beside               # the same buttons while it is open
    for b in beside.buttons + beside.review_buttons:
        x0, y0, x1, y1 = b.rect
        assert not overlaps(b.rect, panel) and 0 <= x0 and x1 <= panel[0] - 16 and y1 <= ctl.toolbar.top, b.name
        assert size_of(b.rect) == size_of(own.button(b.name).rect), b.name  # the same size as in their own places
        assert b.rect[1::2] == own.button(b.name).rect[1::2], b.name        # and at the same height
    for r in (beside.track, beside.bar):
        assert not overlaps(r, panel)
    assert all(overlaps(b.rect, beside.bar) for b in beside.review_buttons)
    assert ctl.lines_layout.zone[0] + 200 <= beside.button("lines:complete").rect[0]
    ctl.press("ai:close")
    assert ctl.lines_controls is own                                        # back in their own places
    ctl.press("pages")                                                      # D71: the PAGES panel covers the scroll
    pages, column = ctl.board_layout.rect, ctl.lines_controls.column          # column only: it stands beside it
    assert ctl.board_open and ctl.lines_controls is not own and not overlaps(column, pages)
    assert column[2] == pages[0] - 16 and ctl.lines_controls.bar == own.bar
    assert ctl.lines_controls.button("lines:complete").rect == own.button("lines:complete").rect
    with pytest.raises(ValueError, match="writing zone"):                   # no room beside a too-wide panel
        ctl.lines_layout.beside((200, 16, 1264, 632))


def test_done_review_and_scroll_work_beside_the_open_ai_panel():
    ctl = controller(ai=True)
    ctl.press("pen")
    stroke(ctl, [(300, 150), (400, 150)])                                   # freehand ink for the AI to read
    ctl.press("lines")
    ctl.press("ai")
    stroke(ctl, [(300, Y - 30), (305, Y), (300, Y + 30)])
    dwell(ctl, "lines:complete")                                            # DONE beside the panel
    line = ctl.sheet().lines[0]
    assert ctl.log["lines:complete"] == 1 and ctl.panel is not None
    (n, _, _), = ctl.take_line_jobs()
    ctl.line_result(n, ok("ICE IS COLDWATER", "ICE IS COLD WATER"))
    dwell(ctl, "lines:ok", 5.0)
    assert line.status == "confirmed" and line.text == "ICE IS COLD WATER"
    ctl.undo()
    dwell(ctl, "lines:written", 10.0)
    assert line.text == "ICE IS COLDWATER"
    ctl.undo()
    dwell(ctl, "lines:edit", 15.0)
    ctl.type_key(ord("!"))
    ctl.type_key(13)
    assert line.text == "ICE IS COLD WATER!"
    ctl.undo()
    dwell(ctl, "lines:ink", 20.0)
    assert line.status == "ink"
    ctl.undo()
    dwell(ctl, "lines:retry", 25.0)
    assert line.status == "recognizing"
    for k in range(7):                                                      # scrolling beside the panel
        stroke(ctl, [(200 + 30 * k, Y - 30), (200 + 30 * k, Y + 30)])
        dwell(ctl, "lines:complete", 30.0 + 5 * k)
    sheet = ctl.sheet()
    assert len(sheet.lines) == 8 and sheet.first_shown(5) == 3
    dwell(ctl, "lines:up", 80.0)
    assert sheet.first_shown(5) == 2
    dwell(ctl, "lines:down", 85.0)
    assert sheet.first_shown(5) == 3
    dwell(ctl, "ai:summarize", 90.0)                                        # the AI panel itself still works
    (action, _, context), = ctl.take_ai_jobs()
    assert action == "summarize" and ctl.panel["state"] == "thinking" and ctl.tool == "lines"


def test_nothing_is_pressed_or_drawn_through_the_open_ai_panel():
    ctl, line = reviewed_line_with_panel()
    own = ctl.lines_layout.controls
    stroke(ctl, [(300, Y - 30), (305, Y), (300, Y + 30)])                  # an unfinished line to complete
    before = dict(ctl.log)
    names = [n for n in ("lines:complete", "lines:written", "lines:edit", "lines:ink", "lines:retry", "lines:up",
                         "lines:down") if not any(b.contains(own.button(n).centre) for b in ctl.panel_layout.buttons)]
    assert len(names) == 6                                                  # (D71: SCROLL UP's place is on a panel
    for k, name in enumerate(names):                                        # button, which acts there)
        point = own.button(name).centre                                     # the layout's own place: on the panel
        assert ctl.panel_layout.contains(point)
        dwell_at(ctl, point, 10.0 * k)
        assert ctl.dwell is None and ctl.log[f"press:{name}"] == before.get(f"press:{name}", 0), name
    assert dict(ctl.log) == before                                          # nothing pressed at all
    assert line.status == "check" and len(ctl.sheet().lines) == 1 and len(ctl.sheet().canvas.strokes) == 1
    assert ctl.panel is not None and ctl.panel["state"] == "menu"           # nor did the panel act
    ctl.handle([Event(STROKE_START, 0.0, (400, Y)), Event(STROKE_POINT, 0.0, (600, Y)),
                Event(STROKE_POINT, 0.0, (900, Y)), Event(STROKE_POINT, 0.0, (1000, Y))])   # on into the panel
    assert ctl.blocked == "zone" and ctl.log["line_strokes_left_zone"] == 1     # D66: ended at the panel's edge
    assert max(x for s in ctl.sheet().canvas.strokes.values() for x, _ in s.points) < ctl.panel_layout.rect[0]
    ctl.handle([Event(STROKE_END, 0.0)])
    x0, y0, x1, y1 = ctl.lines_controls.button("lines:complete").rect
    ctl.handle([Event(STROKE_START, 0.0, ((x0 + x1) / 2, (y0 + y1) / 2))])  # a start on DONE beside the panel
    assert ctl.blocked == "zone" and ctl.log["line_starts_outside_zone"] == 1   # no ink on it
    ctl.handle([Event(STROKE_END, 0.0)])
    ctl.handle([Event(STROKE_START, 0.0, (500, (y0 + y1) / 2)),
                Event(STROKE_POINT, 0.0, ((x0 + x1) / 2, (y0 + y1) / 2))])   # a line stroke reaching DONE
    assert ctl.blocked == "zone" and ctl.log["line_strokes_left_zone"] == 2
    ctl.handle([Event(STROKE_END, 0.0)])
    assert all(not ctl.panel_layout.contains(p) and not ctl.lines_controls.button("lines:complete").contains(p)
               for s in ctl.sheet().canvas.strokes.values() for p in s.points)
    dwell(ctl, "ai:close", 100.0)
    assert ctl.panel is None
    dwell_at(ctl, own.button("lines:complete").centre, 110.0)              # closed: DONE in its own place again
    assert ctl.log["lines:complete"] == before["lines:complete"] + 1 and len(ctl.sheet().lines) == 2


def test_the_controls_are_drawn_beside_the_open_ai_panel_and_the_panel_over_their_own_places():
    ctl, line = reviewed_line_with_panel()
    r = CanvasRenderer(SIZE)
    beside, own = ctl.lines_controls, ctl.lines_layout.controls
    ok_button = beside.button("lines:ok")
    ctl.update_pointer(0.0, ok_button.centre)
    ctl.update_pointer(0.5, ok_button.centre)                               # half-way through a dwell on OK
    img = r.render(ctl.canvas, ctl, ctl.toolbar, mode=HOVER, cursor=None)
    for name in ("lines:complete", "lines:up", "lines:ok", "lines:retry"):
        x0, y0, x1, y1 = beside.button(name).rect
        assert (img[y0:y1, x0:x1] < 200).any(), name                       # drawn, left of the panel
    for name in ("lines:complete", "lines:retry"):                           # their own places: the panel's empty
        x0, y0, x1, y1 = own.button(name).rect                              # answer area, no button drawn there
        assert (img[y0 + 2:y1 - 2, x0 + 2:x1 - 2] == 250).all(), name
    x0, y0, x1, y1 = ok_button.rect
    assert (img[y1 - 6, x0 + 5:x0 + 20] == (200, 60, 200)).all()           # the hold-to-press progress on OK
    px0, py0, px1, py1 = ctl.panel_layout.rect
    assert tuple(img[py0 + 300, px0 + 200]) == (250, 250, 250)              # the panel, whole
    ctl.update_pointer(0.6, None)
    ctl.press("ai")                                                          # closed: the bar ends at its own end
    img = r.render(ctl.canvas, ctl, ctl.toolbar, mode=HOVER, cursor=None)
    x0, y0, x1, y1 = own.button("lines:retry").rect
    assert (img[y0:y1, x0:x1] < 200).any() and ctl.lines_controls is own


# -- D67: the reader's warm-up (R43), and the notes' colours on the wall -------------------------------------------

class WarmingRecognizer:
    """A fake reader whose warm-up waits for `gate` (or raises); records the calls in order."""

    def __init__(self, gate=None, fail=False):
        self.gate, self.fail, self.calls = gate, fail, []

    def warm_up(self):
        self.calls.append("warm_up")
        if self.gate is not None:
            self.gate.wait(5)
        if self.fail:
            raise RuntimeError("boom")
        self.calls.append("warm_up_done")
        return {"answered": True, "error": "", "latency_s": 0.01}

    def read(self, png):
        self.calls.append("read")
        return ok(png.decode())


def wait_for(condition, timeout=5.0):
    end = time.time() + timeout
    while not condition() and time.time() < end:
        time.sleep(0.005)
    return condition()


def test_the_warm_up_runs_once_in_the_background_before_any_line(tmp_path):
    gate = threading.Event()
    fake = WarmingRecognizer(gate)
    t0 = time.perf_counter()
    worker = RecognitionWorker(fake, save_dir=tmp_path, warm_up=True)
    assert time.perf_counter() - t0 < 0.5 and worker.warming_up               # the caller does not wait for it
    worker.submit(1, b"L1", {"page": 1, "line": 1})                           # a line done during the warm-up ...
    assert wait_for(lambda: fake.calls) and fake.calls == ["warm_up"]
    time.sleep(0.1)
    assert fake.calls == ["warm_up"] and worker.poll() == [] and worker.busy  # ... waits: never two requests at once
    gate.set()
    assert wait_for(lambda: not worker.busy)
    assert [(n, r["text"]) for n, r in worker.poll()] == [(1, "L1")]          # only the line comes back: no note
    assert fake.calls == ["warm_up", "warm_up_done", "read"] and not worker.warming_up
    assert worker.warm_up_result == {"answered": True, "error": "", "latency_s": 0.01}
    assert [r["request"] for r in worker.readings] == [1]                     # the warm-up is not a reading ...
    assert worker.readings[0]["waited_s"] >= 0.1                              # (the line's wait behind it, recorded)
    assert len(list(tmp_path.glob("*.json"))) == 1                            # ... nor saved as a line
    worker.close()
    plain = RecognitionWorker(fake)                                           # without warm_up: none
    plain.submit(2, b"L2")
    assert wait_for(lambda: not plain.busy) and not plain.warming_up and plain.warm_up_result is None
    plain.close()
    assert fake.calls.count("warm_up") == 1 and fake.calls[-1] == "read"


def test_a_failed_warm_up_is_recorded_and_lines_are_still_read():
    worker = RecognitionWorker(WarmingRecognizer(fail=True), warm_up=True)
    worker.submit(1, b"L1", {"page": 1, "line": 1})
    assert wait_for(lambda: not worker.busy)
    assert worker.warm_up_result == {"answered": False, "error": "warm-up failed: RuntimeError", "latency_s": None}
    assert [(n, r["text"]) for n, r in worker.poll()] == [(1, "L1")] and not worker.warming_up
    worker.close()


def test_closing_during_the_warm_up_returns_promptly_and_reads_nothing_more():
    gate = threading.Event()
    fake = WarmingRecognizer(gate)
    worker = RecognitionWorker(fake, warm_up=True)
    worker.submit(1, b"L1")
    assert wait_for(lambda: fake.calls)
    t0 = time.perf_counter()
    worker.close(timeout=0.2)
    assert time.perf_counter() - t0 < 1.0                                     # the app's exit is not held up
    gate.set()
    worker._thread.join(2.0)
    assert not worker._thread.is_alive() and fake.calls == ["warm_up", "warm_up_done"]   # no line read after close


def test_the_warm_up_request_is_a_line_request_with_a_small_image_made_by_the_app():
    seen = []

    def opener(request, timeout):
        seen.append((request.full_url, json.loads(request.data), timeout))
        return Response(reply({"written": "", "text": ""}))
    result = LineRecognizer(CFG, opener).warm_up()
    assert result["answered"] and result["error"] == "" and result["latency_s"] >= 0
    (url, body, timeout), = seen
    line = build_line_request(CFG, b"png")                                    # the line's own request, prompt unchanged
    assert url == "http://127.0.0.1:11434/api/chat" and timeout == 120.0
    assert {k: v for k, v in body.items() if k != "messages"} == {k: v for k, v in line.items() if k != "messages"}
    assert body["messages"][0] == line["messages"][0]
    assert body["messages"][1]["content"] == line["messages"][1]["content"]
    image = cv2.imdecode(np.frombuffer(base64.b64decode(body["messages"][1]["images"][0]), np.uint8), cv2.IMREAD_COLOR)
    assert image.shape[:2] == (160, 640) and image.min() < 60 and (image == 255).mean() > 0.8   # one stroke on white
    for error, message in [(urllib.error.URLError(ConnectionRefusedError()), "start Ollama"),
                           (urllib.error.URLError(socket.timeout()), "No answer within 120 s"),
                           (urllib.error.HTTPError("u", 404, "missing", {}, None), "ollama pull")]:
        def failing(request, timeout, error=error):
            raise error
        result = LineRecognizer(CFG, failing).warm_up()                      # never raises
        assert result["answered"] is False and message in result["error"] and result["latency_s"] >= 0


def test_the_suggestion_and_the_reading_ink_are_dark_and_distinct_on_the_wall():
    # Wall test run 2: the blue suggestion and the grey ink of a line being read were hard to see on the wall
    def luminance(bgr):
        return 0.0722 * bgr[0] + 0.7152 * bgr[1] + 0.2126 * bgr[2]
    assert luminance(SUGGESTION) <= 60 and SUGGESTION[0] >= SUGGESTION[1] + 60 >= SUGGESTION[2] + 60   # dark blue
    assert 95 <= luminance(READING_INK) <= 115 and luminance(READING_INK) - luminance(INK) >= 60       # grey, not black
    assert len(set(READING_INK)) == 1                                         # a grey, unlike the blue
    ctl = controller()
    write_line(ctl, 200)                                                      # line 1: still being read
    write_line(ctl, 400)                                                      # line 2: a suggestion
    jobs = ctl.take_line_jobs()
    ctl.line_result(jobs[1][0], ok("CAT"))
    img = render_sheet(ctl.sheet(), ctl.lines_layout, True)
    rows = ctl.lines_layout.rows
    reading = img[rows[0].rect[1]:rows[0].rect[3], 80:900].astype(int)       # right of the number
    suggested = img[rows[1].rect[1]:rows[1].rect[3], 80:900].astype(int)
    assert (np.abs(reading - READING_INK).sum(axis=2) < 10).sum() > 50 and reading.min() >= min(READING_INK) - 10
    assert (np.abs(suggested - SUGGESTION).sum(axis=2) < 30).sum() > 50


# -- D71: the look of the user's mockup ----------------------------------------------------------------------------

def near(img, colour, tolerance=30):
    return (np.abs(img.astype(int) - colour).sum(axis=2) < tolerance).sum()


def test_write_here_stands_in_the_zone_until_something_is_written():
    ctl = controller()
    zx0, zy0, _, _ = ctl.lines_layout.zone
    caption = (slice(zy0 + 16, zy0 + 48), slice(zx0 + 44, zx0 + 160))
    assert ctl.background[caption].min() <= 130                               # "Write here" inside the zone
    stroke(ctl, [(600, Y - 30), (605, Y), (600, Y + 30)])                     # the first stroke, away from it
    assert ctl.background[caption].min() == 255                               # gone
    ctl.undo()
    assert ctl.background[caption].min() <= 130                               # nothing written: back
    write_line(ctl)                                                           # DONE: the zone is empty again
    assert ctl.background[caption].min() <= 130


def test_ok_and_done_are_filled_blue_when_they_can_act_and_grey_when_not():
    ctl = controller()
    line = write_line(ctl)
    (n, _, _), = ctl.take_line_jobs()
    ctl.line_result(n, ok("ICE IS COLDWATER", "ICE IS COLD WATER"))
    r = CanvasRenderer(SIZE)
    img = r.render(ctl.canvas, ctl, ctl.toolbar, mode=HOVER, cursor=None)
    layout = ctl.lines_layout

    def inside(name):
        x0, y0, x1, y1 = layout.button(name).rect
        return img[y0 + 4:y1 - 4, x0 + 4:x1 - 4]
    assert ctl.lines_enabled("lines:ok") and near(inside("lines:ok"), SUGGESTION) > 0.6 * inside("lines:ok")[..., 0].size
    assert near(inside("lines:edit"), SUGGESTION) == 0 and (inside("lines:edit") == 255).mean() > 0.6   # white
    assert not ctl.lines_enabled("lines:complete") and near(inside("lines:complete"), OFF_FILL, 6) > 1000
    stroke(ctl, [(600, Y - 30), (605, Y), (600, Y + 30)])
    dwell(ctl, "lines:ok", 5.0)
    dwell(ctl, "lines:row:0", 10.0)                                           # the line in the review bar again
    img = r.render(ctl.canvas, ctl, ctl.toolbar, mode=HOVER, cursor=None)
    assert line.status == "confirmed" and ctl.review_line() is line and not ctl.lines_enabled("lines:ok")
    assert near(inside("lines:ok"), SUGGESTION) == 0 and near(inside("lines:ok"), OFF_FILL, 6) > 500   # grey
    assert ctl.lines_enabled("lines:complete") and near(inside("lines:complete"), SUGGESTION) > 3000   # DONE blue
    assert (inside("lines:complete") > 245).all(axis=2).sum() > 50            # its white label


def test_the_toolbar_is_typeset_once_per_state_and_shows_the_tool_in_use():
    ctl = controller()
    r = CanvasRenderer(SIZE)
    calls = []
    real = typeset.draw
    typeset.draw = lambda img, ops: (calls.append(len(ops)), real(img, ops))[1]
    try:
        img = r.render(ctl.canvas, ctl, ctl.toolbar, mode=HOVER, cursor=None)
        first = len(calls)
        again = r.render(ctl.canvas, ctl, ctl.toolbar, mode=HOVER, cursor=None)
        assert len(calls) == first and (again == img).all()                   # nothing typeset again
        ctl.press("pen")
        r.render(ctl.canvas, ctl, ctl.toolbar, mode=HOVER, cursor=None)
        assert len(calls) > first                                             # a new state: typeset once
    finally:
        typeset.draw = real
    img = r.render(ctl.canvas, ctl, ctl.toolbar, mode=HOVER, cursor=None)
    for name in ("pen", "black", "medium"):                                   # in use: outlined purple
        x0, y0, x1, y1 = ctl.toolbar.button(name).rect
        assert near(img[y0:y1, x0:x1], TOOL_SELECTED) > 100, name
    for name in ("lines", "red", "thin", "undo"):
        x0, y0, x1, y1 = ctl.toolbar.button(name).rect
        assert near(img[y0:y1, x0:x1], TOOL_SELECTED) == 0, name
    x0, y0, x1, y1 = ctl.toolbar.button("eraser").rect
    assert (img[y0 + 10:y1 - 10, x0 + 6:x1 - 6].min(axis=2) < 120).sum() > 40   # its label, dark
    ctl.update_pointer(0.0, ctl.toolbar.button("undo").centre)
    ctl.update_pointer(0.5, ctl.toolbar.button("undo").centre)
    img = r.render(ctl.canvas, ctl, ctl.toolbar, mode=HOVER, cursor=None)
    x0, y0, x1, y1 = ctl.toolbar.button("undo").rect
    assert (img[y1 - 6, x0 + 5:x0 + 20] == (200, 60, 200)).all()              # hold-to-press progress, each frame


def test_the_notes_end_at_an_open_panel_and_the_page_label_is_a_pill():
    ctl = controller(ai=True)
    for k in range(2):
        write_line(ctl, 200 + 80 * k)
    for n, _, _ in ctl.take_line_jobs():
        ctl.line_result(n, ok("A VERY LONG LINE OF WRITING THAT GOES ON AND ON ACROSS THE WHOLE WALL " * 2))
    nx0, ny0, nx1, ny1 = ctl.lines_layout.notes
    wide = ctl.background
    assert ctl._notes_right() is None and (wide[ny0 + 20:ny1 - 20, 900:nx1 - 40] < 120).any()   # text out to 1100+
    ctl.press("ai")
    right = ctl._notes_right()
    assert right == min(ctl.panel_layout.rect[0], ctl.lines_controls.column[0]) - 12
    clipped = ctl.background
    assert (clipped[ny0 + 4:ny1 - 4, right + 2:nx1] == 255).all()             # nothing right of it, frame neither
    assert (clipped[ny0 + 20:ny1 - 20, right - 200:right - 20] < 120).any()   # the text up to it ("...")
    ctl.press("ai:close")
    assert ctl.background is not clipped and ctl._notes_right() is None
    img = CanvasRenderer(SIZE).render(ctl.canvas, ctl, ctl.toolbar, mode=HOVER, cursor=None)
    assert tuple(img[10, 40]) == PAGE_FILL and tuple(img[9, 13]) == (255, 255, 255)   # the pill, its round corner
    assert (img[15:35, 20:120].min(axis=2) < 120).any()                       # "Page 1 of 1"
