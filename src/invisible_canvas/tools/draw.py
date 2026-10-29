"""`draw`: drawing on the projection with one hand gesture and toolbar tools (Phase 2, brain.md §9.10, D46).

    index finger only            -> use the current tool: PEN draws, ERASER erases, MOVE drags a drawing
    anything else (open hand, fist) -> cursor only
    cursor held on a toolbar button 1 s (CLEAR 2 s) -> press it

The hand is lit plain white with a ring cursor (D50): on by default (D69, user decision 2026-10-29: essential for
writing over existing content; it was off from 2026-10-23); `--no-light` switches it off for a session. D68:
the `l` key switches it on or off during a session; the report compares the frames of the two states (`light_ab`:
hand found and lost, frame rate, pipeline, ink), the trace marks each frame (`light_on`, `lit`).
The AI button is on by default (`[ai] enabled = true`, D57; `--no-ai` switches it off for one session, `--ai`
forces it on): the AI reads the SELECT-ed writing (D51, §9.11); by default
a free local model through Ollama (D52), or Claude with `[ai] backend = "claude"`. Requests
run in a background worker; the report records each answer and the frame rate while a request was running (S3).

D61: with a document shown, the AI reads the shown page (the picture, or the PDF page rendered for it). ASK takes a
question typed on the laptop keyboard (shown live in the panel; Enter sends, Esc cancels; while it is typed the keys
below type text instead).

D62: Smart Lines: the LINES tool writes one line at a time in a fixed writing zone; COMPLETE LINE moves it, as
written, into the numbered notes area at the top (it scrolls when full). Layout from `[smart_lines]`; saved with the
board; report `smart_lines`.

D64: with the AI on, each completed line is read in the background by the local model (`[ai] local_model`, free)
as a literal and a corrected text; the teacher confirms one, edits it (typed on the laptop, as ASK), keeps the ink
or retries. Line images and readings are saved under data/ai/lines/; the report has each line's status and the
frame rate while lines were read (`line_recognition`). D67: the reader warms up once at the start, in the
background, with a small image made by the app (never the user's content); the report has the warm-up and the
first line's reading time against the later ones.

Keyboard (laptop): o open a file, z undo, y redo, s save, c twice clear, l light on the hand, ESC quit. Before
tracking, the setup check runs (a moved setup is recalibrated automatically and validated first, D39). On exit the
current page is saved to data/canvas/ (strokes JSON + PNG), every page to a board file (D59: board-*.json + a PNG per
page), and a report to data/reports/draw-*.json. `--load FILE` continues a board (or a single canvas) file,
`--resume` the newest board.
"""

from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

from ..ai.client import AIAnswer, ClaudeAssistant
from ..ai.local import LocalAssistant
from ..ai.recognize import LineRecognizer, RecognitionWorker
from ..ai.worker import AIWorker
from ..calibration.store import check_compatible, load_calibration
from ..calibration.watch import SetupWatch, expected_corners
from ..canvas import text as typeset
from ..canvas.board import Board
from ..canvas.lines import LinesLayout, render_sheet
from ..canvas.model import Canvas
from ..canvas.reference import Reference, ReferenceError, annotations_dict, annotations_from
from ..canvas.render import CanvasRenderer
from ..canvas.toolbar import Toolbar
from ..config import Config
from ..display import patterns
from ..display.file_dialog import choose_file
from ..display.handlight import HandLight
from ..interaction.drawing import DrawingController
from ..interaction.engine import IDLE, InteractionEngine
from ..vision.hands import HandTracker, HandTrackingError
from .common import add_device_args, current_seq, now_iso, open_session, save_report, stamp
from .draw_diagnostics import DrawDiagnostics
from .tracking_session import (
    TRACKER_OPTIONS, HandPoints, brightness_check, checked_mapper, draw_skeleton, projector_landmarks,
)

TITLE = "SETUP CHECK before drawing"
RECHECK_TITLE = "SETUP CHECK: the projection moved"
HELP = "index finger = use the tool | open hand or fist = cursor only | hold the cursor on a button 1 s to press it"
# D58: the projector or camera moved during the session
MOVED_TEXT = ("The projector or camera moved: recalibrating.", "Keep hands and objects out of the projection.")
MOVED_WARNING = ("The projector or camera moved: the cursor may be off.", "Restart to recalibrate.")
FAILED_WARNING = ("The projector or camera moved and recalibration failed.", "Keep the projection clear: retrying.")
COUNTDOWN_S = 3.0      # the message is shown this long before the setup check starts
RETRY_S = 15.0         # after a failed recalibration, the watch waits this long before it may trigger again
MAX_SETUP_EVENTS = 5   # after this many events that did not end in a recalibration, the watch stops


def add_parser(subparsers) -> None:
    p = subparsers.add_parser("draw", help="draw with the index finger and toolbar tools (Phase 2)")
    add_device_args(p)
    p.add_argument("--seconds", type=float, default=0.0, help="stop after N seconds (default: until ESC)")
    p.add_argument("--load", type=Path, help="continue a saved board or canvas (data/canvas/board-*.json, canvas-*.json)")
    p.add_argument("--resume", action="store_true", help="continue the newest saved board (D59)")
    p.add_argument("--no-recalibrate", action="store_true", help="stop instead of recalibrating a moved setup")
    p.add_argument("--save-every", type=float, default=0.0, help="save a camera frame every S seconds (diagnostic)")
    p.add_argument("--trace", action="store_true", help="per-frame JSONL trace: shape measures, mode, events")
    p.add_argument("--light", action="store_true", help="light the hand plain white, ring cursor (D50; on by default since D69: kept for scripts)")
    p.add_argument("--no-light", action="store_true", help="switch the light on the hand off for this session (D69)")
    p.add_argument("--ai", action="store_true", help="switch the AI on for this session (the AI reads the selection, D51/D52)")
    p.add_argument("--no-ai", action="store_true", help="switch the AI off for this session (on by default, D57)")
    p.set_defaults(func=run)


def _round_point(p) -> list | None:
    return None if p is None else [round(float(p[0]), 2), round(float(p[1]), 2)]


def _percentiles(values) -> dict | None:
    if not values:
        return None
    a = np.asarray(values, dtype=np.float64)
    return {"median": float(np.median(a)), "p95": float(np.percentile(a, 95)), "max": float(a.max())}


def light_state(rows: list[dict]) -> dict | None:
    """D68: the frames of one light state (on or off) for the A/B: how often a hand was found and lost, how fast,
    how much ink. Losses: a frame with a hand followed by one without (frames < 0.5 s apart); while drawing: the
    frame before was in DRAW."""
    if not rows:
        return None
    hand = [r for r in rows if r["hand"]]
    pairs = [(a, b) for a, b in zip(rows, rows[1:]) if 0 < b["t"] - a["t"] < 0.5]
    losses = [(a, b) for a, b in pairs if a["hand"] and not b["hand"]]
    return {"frames": len(rows), "seconds": round(sum(b["t"] - a["t"] for a, b in pairs), 1),
            "processing_fps": segment_fps([r["t"] for r in rows]),
            "hand_frames": len(hand), "hand_found": round(len(hand) / len(rows), 4),
            "hand_losses": len(losses), "losses_per_1000_hand_frames": round(1000 * len(losses) / max(len(hand), 1), 1),
            "losses_while_drawing": sum(1 for a, _ in losses if a["mode"] == "draw"),
            "draw_frames": sum(r["mode"] == "draw" for r in rows), "lit_frames": sum(r["lit"] for r in rows),
            "ink_points": sum(r["ink_points"] for r in rows),
            "inference_ms": _percentiles([r["inference_ms"] for r in rows]),
            "inference_ms_with_hand": _percentiles([r["inference_ms"] for r in hand]),
            "pipeline_ms": _percentiles([r["pipeline_ms"] for r in rows]),
            "pipeline_ms_with_hand": _percentiles([r["pipeline_ms"] for r in hand])}


def segment_fps(times: list[float], gap: float = 0.5) -> float:
    """Frames per second over a subset of frames, counting only intervals shorter than `gap` (separate blocks)."""
    dts = [b - a for a, b in zip(times, times[1:]) if 0 < b - a < gap]
    return len(dts) / sum(dts) if dts else 0.0


def with_message(img: np.ndarray, lines) -> np.ndarray:
    """The image with `lines` in a framed white box at its centre (D58 messages on the wall)."""
    out = img.copy()
    scale, thick = 0.8, 2
    sizes = [cv2.getTextSize(line, cv2.FONT_HERSHEY_SIMPLEX, scale, thick)[0] for line in lines]
    w = max(s[0] for s in sizes) + 48
    step = max(s[1] for s in sizes) + 18
    h = step * len(lines) + 30
    x0, y0 = (out.shape[1] - w) // 2, (out.shape[0] - h) // 2
    cv2.rectangle(out, (x0, y0), (x0 + w, y0 + h), (255, 255, 255), -1)
    cv2.rectangle(out, (x0, y0), (x0 + w, y0 + h), (40, 40, 215), 3)
    for k, line in enumerate(lines):
        cv2.putText(out, line, (x0 + 24, y0 + 15 + step * (k + 1) - 9), cv2.FONT_HERSHEY_SIMPLEX, scale, (30, 30, 30),
                    thick, cv2.LINE_AA)
    return out


def recheck(config: Config, s, calibration, canvas_image: np.ndarray):
    """D58: say on the wall why drawing pauses, then run the setup check again (and the validated recovery when
    the setup moved, D39): (mapper, calibration, info), or None when it failed."""
    s.projector.show(with_message(canvas_image, MOVED_TEXT))
    end = time.perf_counter() + COUNTDOWN_S
    while time.perf_counter() < end:
        cv2.waitKey(50)
    return checked_mapper(config, s, calibration, no_recalibrate=False, title=RECHECK_TITLE)


def board_data(controller: DrawingController) -> dict:
    """The board file's content. D59: every page; D60: the open document (its path, page and annotations; the
    document itself is never copied or changed), what was shown, and the annotations of documents closed meanwhile."""
    data = controller.board.to_dict()
    if controller.reference is not None:
        data["reference"], data["view"] = controller.reference.to_dict(), controller.view
    if controller.kept_annotations:
        data["closed_documents"] = [{"path": kept["path"], "annotations": annotations_dict(kept["annotations"])}
                                    for kept in controller.kept_annotations.values()]
    return data


def line_report(line) -> dict:
    """D64: one Smart Line for the report: its status, the teacher's decision and text, and the reading."""
    reading, decision = line.reading or {}, line.decision or {}
    return {"id": line.id, "status": line.status, "decision": decision.get("kind"), "text": line.text,
            "written": reading.get("written"), "suggestion": reading.get("text") if reading.get("ok") else None,
            "error": reading.get("error") or None, "latency_s": reading.get("latency_s")}


def save_board(config: Config, controller: DrawingController) -> Path:
    """D59: the board file (`board_data`), and a PNG of each page next to it."""
    folder = config.root / "data" / "canvas"
    folder.mkdir(parents=True, exist_ok=True)
    base = folder / f"board-{stamp()}"
    path = base.with_suffix(".json")
    path.write_text(json.dumps(board_data(controller)), encoding="utf-8")
    board = controller.board
    for k, page in enumerate(board.pages):
        notes = None                                   # D62: the page's completed Smart Lines under its ink
        if page.lines is not None and page.lines.lines:
            notes = render_sheet(page.lines, controller.lines_layout, show_zone=False)
        cv2.imwrite(str(folder / f"{base.name}-p{k + 1}.png"), CanvasRenderer(board.size)._strokes(page.canvas, notes))
    return path


def load_board(config: Config, args, size: tuple[int, int]) -> tuple[Board, dict]:
    """`--load FILE` (a board or a single canvas file), `--resume` (the newest board file), else one blank page.
    Returns the board and the file's data (for the document it had open, D60)."""
    path = args.load
    if path is None and getattr(args, "resume", False):
        boards = sorted((config.root / "data" / "canvas").glob("board-*.json"))
        path = boards[-1] if boards else None
        print(f"resuming {path}" if path else "no saved board to resume: starting with a blank page")
    if path is None:
        return Board(size), {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return Board.from_dict(data), data


def restore_reference(controller: DrawingController, data: dict) -> None:
    """D60: reopen the document a saved board had open (if the file is still there), with its annotations; the
    annotations of documents closed before the save come back when those files are opened."""
    for closed in data.get("closed_documents", []):
        controller.keep_annotations(closed["path"], annotations_from(closed["annotations"]))
    if not data.get("reference"):
        return
    try:
        controller.set_reference(Reference.from_dict(data["reference"]))
        controller.view = data.get("view", "doc")
    except ReferenceError as e:
        controller.show_notice(f"The saved document was not reopened: {e}")


def open_document(controller: DrawingController, engine: InteractionEngine, t: float) -> None:
    """D60: OPEN FILE (or the o key): the pen lifts, the Open dialog on the laptop, then the document is shown, or a
    message says why it could not be."""
    controller.handle(engine.release(t))
    path = choose_file()
    if path is None:
        controller.log["open_cancelled"] += 1
        return
    try:
        controller.set_reference(Reference.open(path))
        print(f"opened {path} ({controller.reference.label()})")
    except ReferenceError as e:
        controller.log["open_failed"] += 1
        controller.show_notice(str(e))
        print(f"could not open {path}: {e}")


def handle_keys(keys, controller: DrawingController, now: float, clear_armed: dict, saved_paths: list, save,
                toggle_light=None) -> bool:
    """The laptop keys of one frame (pollKey and waitKey: -1 when none); True means quit (ESC). While an ASK
    question is typed (D61) every key is text for it, Esc included (it cancels the question, not the session).
    D68: `l` switches the light on the hand on or off (`toggle_light`)."""
    for key in keys:
        if not 0 < key < 256:                          # no key, or an arrow / F-key (only typed text is used)
            continue
        if controller.typing:
            controller.type_key(key)
        elif key == 27:
            return True
        elif key in (ord("l"), ord("L")) and toggle_light is not None:
            toggle_light()
        elif key in (ord("o"), ord("O")):              # D60: open a document, as the OPEN FILE button
            controller.open_requested = True
        elif key in (ord("z"), ord("Z")):
            controller.undo()
        elif key in (ord("y"), ord("Y")):
            controller.redo()
        elif key in (ord("s"), ord("S")):
            saved_paths.append(save())
            print(f"saved: {saved_paths[-1][0]}")
        elif key in (ord("c"), ord("C")):
            if now < clear_armed["until"]:
                controller.clear()
                clear_armed["until"] = 0.0
            else:
                clear_armed["until"] = now + 2.0
                print("press c again within 2 s to clear the canvas")
    return False


def save_canvas(config: Config, canvas: Canvas, renderer: CanvasRenderer) -> tuple[Path, Path]:
    folder = config.root / "data" / "canvas"
    folder.mkdir(parents=True, exist_ok=True)
    base = folder / f"canvas-{stamp()}"
    base.with_suffix(".json").write_text(json.dumps(canvas.to_dict()), encoding="utf-8")
    cv2.imwrite(str(base.with_suffix(".png")), renderer._strokes(canvas))
    return base.with_suffix(".json"), base.with_suffix(".png")


def run(config: Config, args) -> int:
    calibration = load_calibration(config.calibration_dir)
    ai_on = bool(getattr(args, "ai", False) or config.ai.enabled) and not getattr(args, "no_ai", False)
    worker = line_worker = None
    if ai_on:
        try:
            assistant = LocalAssistant(config.ai) if config.ai.backend == "local" else ClaudeAssistant(config.ai)
            worker = AIWorker(assistant, save_dir=config.root / "data" / "ai", warm_up=True)
        except ImportError as e:
            print(f"the AI needs the anthropic package ({e}): pip install -e .[ai]")
            return 2
        # D64: Smart Lines are read by the local model (free), whatever the AI panel's backend
        # D67 (R43): the reader warms up once, in its own thread, before the first line
        line_worker = RecognitionWorker(LineRecognizer(config.ai), save_dir=config.root / "data" / "ai" / "lines",
                                        warm_up=True)
    try:
        tracker = HandTracker(**TRACKER_OPTIONS)
    except HandTrackingError as e:
        print(f"cannot start hand tracking: {e}")
        return 2
    save_dir = config.reports_dir.parent / "diagnostics" / f"draw-{stamp()}"
    trace = None
    records, shapes = [], Counter()
    with tracker, open_session(config, args) as s:
        check_compatible(calibration, s.camera_info.size, s.canvas_size)
        checked = checked_mapper(config, s, calibration, no_recalibrate=args.no_recalibrate, title=TITLE)
        if checked is None:
            return 1
        mapper, calibration, setup_info = checked
        size = s.canvas_size
        board, board_data = load_board(config, args, size)
        toolbar, renderer = Toolbar(size, ai=ai_on), CanvasRenderer(size)
        sl = config.smart_lines
        try:                                           # D62: checked against this canvas, its toolbar (D65: panels)
            lines_layout = LinesLayout(size, toolbar.top, sl.zone, sl.notes, sl.line_height, sl.line_spacing,
                                       sl.numbering, sl.font, sl.text_size)
            controller = DrawingController(board.page.canvas, toolbar, board=board, lines_layout=lines_layout)
        except ValueError as e:
            print(f"[smart_lines] in the config: {e}")
            return 2
        if not typeset.available(sl.font):
            print(f"[smart_lines] font {sl.font} not found in {typeset.FONT_DIR}: the notes use Pillow's own font")
        controller.recognition = line_worker is not None
        restore_reference(controller, board_data)
        engine, points = InteractionEngine(), HandPoints(mapper)
        light = None if getattr(args, "no_light", False) else HandLight()   # D69: on by default (user, 2026-10-29)
        brightness = brightness_check(s, mapper, renderer.render(controller.canvas, controller, toolbar, mode=IDLE, cursor=None))
        diag = DrawDiagnostics(size, toolbar.top)       # §9.12 item 1: observation only
        watch = SetupWatch(expected_corners(mapper, size))   # D58: did the projector or camera move meanwhile?
        setup_events, warning, watch_from = [], None, 0.0
        if args.trace:
            save_dir.mkdir(parents=True, exist_ok=True)
            trace = open(save_dir / "trace.jsonl", "w", encoding="utf-8", buffering=1 << 20)   # ~1 write per s
        print(f"drawing: {HELP}. Keys: o open a file, z undo, y redo, s save, c twice clear, l light on the hand "
              f"(now {'on' if light is not None else 'off'}), ESC quit "
              "(while an ASK question is typed, keys type it: Enter sends, Esc cancels).")
        s.camera.reset_stats()
        start = time.perf_counter()
        seq, last_saved, clear_armed, last_t = current_seq(s), -1e9, {"until": 0.0}, None
        saved_paths = []
        last_t0 = None
        light_toggles = []

        def toggle_light() -> None:                    # D68: the `l` key; a fresh light holds nothing from before
            nonlocal light
            light = None if light is not None else HandLight()
            light_toggles.append({"t": round(time.perf_counter() - start, 2), "on": light is not None})
            print(f"light on the hand: {'on' if light is not None else 'off'} at {light_toggles[-1]['t']} s")

        def save_all() -> list[str]:                   # the s key: this page's canvas and the whole board
            return ([str(p) for p in save_canvas(config, controller.canvas, renderer)]
                    + [str(save_board(config, controller))])

        while True:
            frame = s.camera.wait_frame(seq, 2.0)
            if frame is None:
                print("camera stopped delivering frames")
                break
            seq, last_t = frame.seq, frame.timestamp
            t0 = time.perf_counter()
            obs = tracker.process(frame.image, frame.timestamp)
            t1 = time.perf_counter()
            prev_candidate = engine._candidate              # diagnostics: the engine's own state, read only
            shape, hand = points(frame.timestamp, obs)
            th = time.perf_counter()
            step = engine.update(frame.timestamp, hand)
            te = time.perf_counter()
            controller.handle(step.events)
            controller.update_pointer(frame.timestamp, step.cursor)
            if controller.take_open_request():          # D60: the Open dialog on the laptop (the loop waits)
                open_document(controller, engine, frame.timestamp)
                seq, last_t0 = current_seq(s), None
            tc = time.perf_counter()
            if worker is not None:                         # D51: jobs to the background worker, answers back
                for action, png, context in controller.take_ai_jobs():
                    if not worker.submit(action, png, context):
                        controller.ai_answer(AIAnswer(action, ok=False, error="Still busy with the previous request."))
                for answer in worker.poll():
                    controller.ai_answer(answer)
            if line_worker is not None:                    # D64: Smart Lines to the reader, readings back
                for request in controller.take_line_cancels():
                    line_worker.cancel(request)
                for request, png, context in controller.take_line_jobs():
                    line_worker.submit(request, png, context)
                for request, reading in line_worker.poll():
                    controller.line_result(request, reading)
            else:
                controller.take_line_jobs()                # the AI is off: new lines are marked not recognised
            ta = time.perf_counter()
            lit = None if light is None else light.update(frame.timestamp, projector_landmarks(mapper, obs))
            img = renderer.render(controller.canvas, controller, toolbar, mode=step.mode, cursor=step.cursor, light=lit)
            if warning is not None:                        # D58: the setup moved and is not recalibrated (yet)
                img = with_message(img, warning)
            tr = time.perf_counter()
            s.projector.show(img)
            keys = [cv2.pollKey()]                         # D61: kept (a question is typed key by key)
            t2 = time.perf_counter()
            shapes[shape.shape if shape else None] += 1
            records.append({"t": frame.timestamp - start, "mode": step.mode, "hand": obs is not None,
                            "inference_ms": (t1 - t0) * 1000, "pipeline_ms": (t2 - frame.timestamp) * 1000,
                            "ai_busy": bool(worker is not None and worker.busy),
                            "lines_busy": bool(line_worker is not None and line_worker.busy),
                            "lines_warming": bool(line_worker is not None and line_worker.warming_up),
                            # D68: the light switched on, a light painted this frame, ink points added this frame
                            "light_on": light is not None, "lit": lit is not None,
                            "ink_points": sum(1 for o in controller.outcomes if o[0] == "added")})
            td = time.perf_counter()
            stage_ms = {"queue": (t0 - frame.timestamp) * 1000, "inference": (t1 - t0) * 1000,
                        "hand": (th - t1) * 1000, "engine": (te - th) * 1000, "controller": (tc - te) * 1000,
                        "ai": (ta - tc) * 1000, "render": (tr - ta) * 1000, "show": (t2 - tr) * 1000}
            fields = diag.frame(t=frame.timestamp, action=tracker.action, status=points.status, cursor=step.cursor,
                                step=step, prev_candidate=prev_candidate, candidate=engine._candidate,
                                outcomes=controller.outcomes, stage_ms=stage_ms,
                                loop_ms=None if last_t0 is None else (t0 - last_t0) * 1000,
                                blocked=controller.blocked is not None)
            last_t0 = t0
            if trace is not None:
                kinds = [e.kind for e in step.events]
                extra = {"action": tracker.action, "status": points.status,
                         "tip_in_view": None if obs is None else obs.tip_in_view, "raw_proj": _round_point(points.raw),
                         **fields, "stroke": controller.attempt if controller.stroke_open or controller.outcomes
                         or "stroke_end" in kinds else None,
                         "stroke_id": None if controller.active is None else controller.active.id,
                         "blocked": controller.blocked,                  # D56: why the pointing draws nothing
                         "ai_busy": records[-1]["ai_busy"],              # an AI request was running (S3, §9.13)
                         "lines_busy": records[-1]["lines_busy"],        # D64: a Smart Line was being read
                         "lines_warming": records[-1]["lines_warming"],  # D67: the reader's warm-up was running
                         "light_on": records[-1]["light_on"],            # D68: the light on the hand switched on
                         "page": controller.board.current + 1,           # D59
                         "view": controller.view,                        # D60: board or doc
                         "tool": controller.tool,                        # D62: lines (Smart Lines) or another
                         "candidate": engine._candidate, "buffered": len(engine._buffer),
                         "queue_ms": round(stage_ms["queue"], 2), "inference_ms": round(stage_ms["inference"], 2),
                         "pipeline_ms": round((t2 - frame.timestamp) * 1000, 2),
                         "stage_ms": {k: round(v, 3) for k, v in stage_ms.items() if k not in ("queue", "inference")}}
            diag.stages["diag"].add((time.perf_counter() - td) * 1000)
            if trace is not None:
                tw = time.perf_counter()
                trace.write(json.dumps({"t": round(frame.timestamp - start, 4), "seq": frame.seq, "mode": step.mode,
                                        "pending": step.pending, "shape": shape.as_dict() if shape else None,
                                        "cursor": step.cursor, "events": kinds,
                                        "source": obs.source if obs else None, "lit": lit is not None, **extra}) + "\n")
                diag.stages["trace"].add((time.perf_counter() - tw) * 1000)
            if args.save_every and frame.timestamp - last_saved >= args.save_every:
                last_saved = frame.timestamp
                save_dir.mkdir(parents=True, exist_ok=True)
                cv2.imwrite(str(save_dir / f"t{frame.timestamp - start:06.1f}_{step.mode}.jpg"), frame.image,
                            [cv2.IMWRITE_JPEG_QUALITY, 90])
            if len(records) % 2 == 0:
                view = frame.image.copy()
                if obs is not None:
                    draw_skeleton(view, obs.landmarks)
                recent = records[-60:]
                fps = (len(recent) - 1) / max(recent[-1]["t"] - recent[0]["t"], 1e-6) if len(recent) > 1 else 0.0
                s.operator.show(view, lines=[
                    "DRAW (Phase 2)", f"mode: {step.mode.upper()}   shape: {shape.shape if shape else '-'}",
                    f"processing {fps:.1f} fps, capture -> projector "
                    f"{np.median([r['pipeline_ms'] for r in recent]):.0f} ms (+ display path)",
                    f"tool {controller.tool.upper()} | colour {controller.colour} | width {controller.width} | "
                    f"{controller.board.label()} | strokes {len(controller.canvas.strokes)} | selected {len(controller.selection)}",
                    "AI: off" if worker is None else
                    f"AI: {'working' if worker.busy else 'ready'} ({len(worker.answers)} answers)",
                    f"ASK - type the question, Enter sends, Esc cancels: {controller.panel['question']}_"
                    if controller.asking else
                    f"EDIT the line - type it, Enter saves, Esc cancels: {controller.line_edit['text']}_"
                    if controller.line_edit is not None else "",
                    HELP, "keys: o open a file  z undo  y redo  s save  c c clear  "
                    f"l light {'on' if light is not None else 'off'}  ESC quit"])
            moved = watch.update(frame.timestamp, frame.image) if time.perf_counter() >= watch_from else None
            if moved is not None:                          # D58: the projector or the camera moved
                controller.handle(engine.release(frame.timestamp))     # a pen lift: nothing bridged across the pause
                event = {"t": round(frame.timestamp - start, 2), "displacement_px": [round(float(v), 1) for v in moved]}
                print(f"the projection moved by {event['displacement_px']} camera px at {event['t']} s")
                if args.no_recalibrate:
                    event["status"], warning, watch_from = "warned", MOVED_WARNING, float("inf")
                else:
                    paused = time.perf_counter()
                    rechecked = recheck(config, s, calibration,
                                        renderer.render(controller.canvas, controller, toolbar, mode=IDLE, cursor=None))
                    event["pause_s"] = round(time.perf_counter() - paused, 1)
                    if rechecked is None:
                        event["status"], warning, watch_from = "failed", FAILED_WARNING, time.perf_counter() + RETRY_S
                    else:
                        mapper, calibration, info = rechecked
                        points.mapper = mapper
                        points.reset()
                        warning = None
                        if info["recovery"]:                   # recalibrated: watch against the new calibration
                            event["status"] = "recalibrated"
                            watch.reset(expected_corners(mapper, size))
                        else:                                  # the setup check found no move: watch from what is seen
                            event["status"] = "unchanged"
                            watch.reset(watch.expected + moved)
                        event.update(setup_variation_px=round(info["setup_variation_px"], 2),
                                     calibration_created_at=calibration.created_at, recovery=info["recovery"])
                    if len(setup_events) + 1 >= MAX_SETUP_EVENTS and event["status"] != "recalibrated":
                        watch_from = float("inf")              # something keeps triggering it: stop watching
                    seq, last_t0 = current_seq(s), None
                setup_events.append(event)
            keys.append(cv2.waitKey(1))
            now = time.perf_counter()
            diag.stages["post"].add((now - t2) * 1000)
            if args.seconds and now - start >= args.seconds:
                break
            if handle_keys(keys, controller, now, clear_armed, saved_paths, save_all, toggle_light):
                break
        if trace is not None:
            trace.close()
        if last_t is not None:          # end an open stroke / erase / pinch cleanly (no hand, after the hold)
            controller.handle(engine.update(last_t + 1.0, None).events)
        camera_stats = s.camera.stats()
        s.projector.show(patterns.blank(size))
    if worker is not None:
        worker.close(timeout=0.2)                      # a request still running is abandoned (daemon thread)
    if line_worker is not None:
        line_worker.close(timeout=0.2)                 # lines still unread are read again on --resume (D64)

    json_path, png_path = save_canvas(config, controller.canvas, renderer)
    board_path = save_board(config, controller)
    duration = records[-1]["t"] - records[0]["t"] if len(records) > 1 else 0.0
    hand_frames = [r for r in records if r["hand"]]
    report = {
        "created_at": now_iso(),
        "calibration_created_at": calibration.created_at,
        "setup_check": setup_info,
        "brightness": brightness,
        "duration_s": duration,
        "frames": len(records),
        "processing_fps": (len(records) - 1) / duration if duration > 0 else 0.0,
        "camera_fps": camera_stats.mean_fps,
        "inference_ms": _percentiles([r["inference_ms"] for r in records]),
        "pipeline_ms": _percentiles([r["pipeline_ms"] for r in records]),
        "pipeline_ms_with_hand": _percentiles([r["pipeline_ms"] for r in hand_frames]),
        "mode_frames": dict(engine.mode_frames),
        "mode_entries": dict(engine.entries),
        "shape_frames": {str(k): v for k, v in shapes.items()},
        "actions": dict(controller.log),
        "tool_at_end": controller.tool,
        "strokes_on_canvas": len(controller.canvas.strokes),               # the current page
        "board": {"json": str(board_path), "pages": controller.board.count, "current": controller.board.current + 1,
                  "strokes_per_page": [len(p.canvas.strokes) for p in controller.board.pages]},   # D59
        "reference": None if controller.reference is None else {                                    # D60
            "path": str(controller.reference.path), "kind": controller.reference.kind,
            "pages": controller.reference.count, "page": controller.reference.current + 1, "view": controller.view,
            "annotated_pages": sorted(k + 1 for k, p in controller.reference.annotations.items() if p.canvas.strokes)},
        "closed_documents_with_annotations": [kept["path"] for kept in controller.kept_annotations.values()],
        "smart_lines": [{"page": k + 1, "lines": len(p.lines.lines), "line_ids": [line.id for line in p.lines.lines],
                         "line_strokes": [len(line.strokes) for line in p.lines.lines],
                         "unfinished_strokes": len(p.lines.canvas.strokes),                   # D62
                         "status": dict(Counter(line.status for line in p.lines.lines)),     # D64
                         "line_details": [line_report(line) for line in p.lines.lines]}
                        for k, p in enumerate(controller.board.pages) if p.lines is not None and p.lines.has_content],
        "line_recognition": None if line_worker is None else {                                       # D64
            "model": config.ai.local_model, "requests": controller.log["lines:requests"],
            "readings": len(line_worker.readings), "read": controller.log["lines:read"],
            "not_read": controller.log["lines:not_read"], "stale_ignored": controller.log["lines:stale_results"],
            "skipped": controller.log["lines:skipped"],
            "latency_s": _percentiles([r["latency_s"] for r in line_worker.readings]),
            # D67 (R43): the warm-up, and the first line's time against the later ones, to judge whether it helps
            "warm_up": line_worker.warm_up_result,
            "warm_up_frames": sum(r["lines_warming"] for r in records),
            "warm_up_processing_fps": segment_fps([r["t"] for r in records if r["lines_warming"]]),
            "first_reading_latency_s": line_worker.readings[0]["latency_s"] if line_worker.readings else None,
            "first_reading_waited_s": line_worker.readings[0]["waited_s"] if line_worker.readings else None,
            "later_reading_latency_s": _percentiles([r["latency_s"] for r in line_worker.readings[1:]]),
            "busy_frames": sum(r["lines_busy"] for r in records),
            "busy_processing_fps": segment_fps([r["t"] for r in records if r["lines_busy"]]),
            "idle_processing_fps": segment_fps([r["t"] for r in records if not r["lines_busy"]]),
            "busy_pipeline_ms": _percentiles([r["pipeline_ms"] for r in records if r["lines_busy"]]),
            "busy_inference_ms": _percentiles([r["inference_ms"] for r in records if r["lines_busy"]]),
            "idle_inference_ms": _percentiles([r["inference_ms"] for r in records if not r["lines_busy"]]),
        },
        "canvas": {"json": str(json_path), "png": str(png_path), "saved_during_run": saved_paths},
        "trace": str(save_dir / "trace.jsonl") if args.trace else None,
        "light": not getattr(args, "no_light", False),                        # at the start (D69: on by default)
        # D68: the light switched with the `l` key, and the frames of each state (an A/B in one session)
        "light_ab": {"toggles": light_toggles, "off": light_state([r for r in records if not r["light_on"]]),
                     "on": light_state([r for r in records if r["light_on"]])},
        "selections": controller.selection_log,
        # §9.12 item 1: why fingertips did or did not become ink, per band, and per-stage timing (observation only)
        "diagnostics": diag.report(strokes_committed=controller.log["strokes"], attempts=controller.attempts),
        # D58: the projector or camera moving during the session: checks, and each move with what was done
        "setup_watch": {**watch.summary(), "events": setup_events},
        "ai": None if worker is None else {
            "backend": config.ai.backend, "warmed_up": worker.warmed_up,
            "model": config.ai.local_model if config.ai.backend == "local" else config.ai.model,
            "effort": config.ai.effort, "fallbacks": config.ai.fallbacks,
            "requests": controller.log["ai_requests"], "answers": [a.to_dict() for a in worker.answers],
            "busy_frames": sum(r["ai_busy"] for r in records),
            "busy_processing_fps": segment_fps([r["t"] for r in records if r["ai_busy"]]),
            "busy_pipeline_ms": _percentiles([r["pipeline_ms"] for r in records if r["ai_busy"]]),
        },
    }
    print(f"{len(records)} frames over {duration:.1f} s: processing {report['processing_fps']:.1f} fps "
          f"(camera {camera_stats.mean_fps:.1f}); pipeline median {report['pipeline_ms']['median']:.1f} ms, "
          f"p95 {report['pipeline_ms']['p95']:.1f} ms" if records else "no frames")
    print(f"modes (frames): {dict(engine.mode_frames)}; entered: {dict(engine.entries)}")
    print(f"actions: {dict(controller.log)}; strokes on the current page {len(controller.canvas.strokes)}")
    print(f"board: {controller.board.count} pages (strokes per page {report['board']['strokes_per_page']}), current {controller.board.current + 1}: {board_path}")
    w = report["setup_watch"]
    print(f"setup watch: {w['checks']} checks (mean {w['check_ms_mean']} ms), {len(w['events'])} moves"
          + "".join(f"\n  at {e['t']} s moved {e['displacement_px']} camera px: {e['status']}"
                    + (f" (paused {e['pause_s']} s)" if "pause_s" in e else "") for e in w["events"]))
    d = report["diagnostics"]
    print(f"diagnostics: states {d['states']}")
    print(f"  ink {d['ink']}")
    print("  hand losses per 1000 hand frames: "
          + ", ".join(f"{b} {v['losses_per_1000']}" for b, v in d["bands"].items() if v["losses_per_1000"] is not None))
    print(f"  strokes {d['strokes']}")
    if d["overhead"]["diag_ms"] is not None:
        print(f"  diagnostics cost per frame: median {d['overhead']['diag_ms']['median']:.3f} ms, "
              f"p95 {d['overhead']['diag_ms']['p95']:.3f} ms (target < {d['overhead']['target_ms']} ms)")
    if worker is not None:
        for a in worker.answers:
            print(f"AI {a.action}: {'ok' if a.ok else 'ERROR ' + a.error} in {a.latency_s:.1f} s"
                  + (f" | read: {a.transcription[:60]!r}" if a.ok else "")
                  + (f" | topic: {a.topic!r}" if a.readable else " | no clear topic" if a.readable is False else ""))
        ai = report["ai"]
        if ai["busy_frames"]:
            print(f"while AI requests ran: {ai['busy_frames']} frames, {ai['busy_processing_fps']:.1f} fps, "
                  f"pipeline p95 {ai['busy_pipeline_ms']['p95']:.1f} ms")
    rec = report["line_recognition"]
    if rec is not None:                                # D67: the warm-up, whether or not a line was read
        w = rec["warm_up"]
        print("Smart Lines reader warm-up: " + ("not finished" if w is None else
                                                f"answered in {w['latency_s']:.1f} s" if w["answered"] else
                                                f"no answer ({w['error']})"))
    if rec is not None and rec["requests"]:
        print(f"Smart Lines read: {rec['requests']} requests, {rec['read']} read, {rec['not_read']} not read, "
              f"{rec['stale_ignored']} late readings ignored"
              + (f"; while reading {rec['busy_frames']} frames at {rec['busy_processing_fps']:.1f} fps "
                 f"(otherwise {rec['idle_processing_fps']:.1f})" if rec["busy_frames"] else ""))
        if rec["first_reading_latency_s"] is not None:
            later = rec["later_reading_latency_s"]
            print(f"  first line read in {rec['first_reading_latency_s']:.1f} s (after {rec['first_reading_waited_s']:.1f} s "
                  f"in the queue)" + (f"; later lines median {later['median']:.1f} s, max {later['max']:.1f} s"
                                      if later else ""))
    ab = report["light_ab"]
    if ab["toggles"]:                                  # D68: the A/B of the light on the hand
        for state in ("off", "on"):
            st = ab[state]
            if st is not None:
                print(f"light {state}: {st['frames']} frames ({st['seconds']} s), {st['processing_fps']:.1f} fps, "
                      f"hand found {st['hand_found']:.0%}, {st['losses_per_1000_hand_frames']} losses per 1000 hand "
                      f"frames ({st['losses_while_drawing']} while drawing), pipeline median "
                      f"{st['pipeline_ms']['median']:.1f} ms, p95 {st['pipeline_ms']['p95']:.1f} ms")
    print(f"canvas: {json_path} (+ .png)")
    print(f"report: {save_report(config, 'draw', report)}")
    if controller.reference is not None:               # D60: let go of the document file
        controller.reference.close()
    return 0
