"""`draw`: drawing on the projection with one hand gesture and toolbar tools (Phase 2, brain.md §9.10, D46).

    index finger only            -> use the current tool: PEN draws, ERASER erases, MOVE drags a drawing
    anything else (open hand, fist) -> cursor only
    cursor held on a toolbar button 1 s (CLEAR 2 s) -> press it

`--light` lights the hand plain white with a ring cursor (D50; off by default since 2026-10-23, user decision).

Keyboard (laptop): z undo, y redo, s save, c twice clear, ESC quit. Before tracking, the setup check runs
(a moved setup is recalibrated automatically and validated first, D39). On exit the canvas is saved to
data/canvas/ (strokes JSON + PNG) and a report to data/reports/draw-*.json.
"""

from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

from ..calibration.store import check_compatible, load_calibration
from ..canvas.model import Canvas
from ..canvas.render import CanvasRenderer
from ..canvas.toolbar import Toolbar
from ..config import Config
from ..display import patterns
from ..display.handlight import HandLight
from ..interaction.drawing import DrawingController
from ..interaction.engine import IDLE, InteractionEngine
from ..vision.hands import HandTracker, HandTrackingError
from .common import add_device_args, current_seq, now_iso, open_session, save_report, stamp
from .tracking_session import (
    TRACKER_OPTIONS, HandPoints, brightness_check, checked_mapper, draw_skeleton, projector_landmarks,
)

TITLE = "SETUP CHECK before drawing"
HELP = "index finger = use the tool | open hand or fist = cursor only | hold the cursor on a button 1 s to press it"


def add_parser(subparsers) -> None:
    p = subparsers.add_parser("draw", help="draw with the index finger and toolbar tools (Phase 2)")
    add_device_args(p)
    p.add_argument("--seconds", type=float, default=0.0, help="stop after N seconds (default: until ESC)")
    p.add_argument("--load", type=Path, help="continue a saved canvas (data/canvas/*.json)")
    p.add_argument("--no-recalibrate", action="store_true", help="stop instead of recalibrating a moved setup")
    p.add_argument("--save-every", type=float, default=0.0, help="save a camera frame every S seconds (diagnostic)")
    p.add_argument("--trace", action="store_true", help="per-frame JSONL trace: shape measures, mode, events")
    p.add_argument("--light", action="store_true", help="light the hand plain white, ring cursor (D50; off by default)")
    p.set_defaults(func=run)


def _percentiles(values) -> dict | None:
    if not values:
        return None
    a = np.asarray(values, dtype=np.float64)
    return {"median": float(np.median(a)), "p95": float(np.percentile(a, 95)), "max": float(a.max())}


def save_canvas(config: Config, canvas: Canvas, renderer: CanvasRenderer) -> tuple[Path, Path]:
    folder = config.root / "data" / "canvas"
    folder.mkdir(parents=True, exist_ok=True)
    base = folder / f"canvas-{stamp()}"
    base.with_suffix(".json").write_text(json.dumps(canvas.to_dict()), encoding="utf-8")
    cv2.imwrite(str(base.with_suffix(".png")), renderer._strokes(canvas))
    return base.with_suffix(".json"), base.with_suffix(".png")


def run(config: Config, args) -> int:
    calibration = load_calibration(config.calibration_dir)
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
        canvas = Canvas.from_dict(json.loads(args.load.read_text(encoding="utf-8"))) if args.load else Canvas(size)
        toolbar, renderer = Toolbar(size), CanvasRenderer(size)
        controller, engine, points = DrawingController(canvas, toolbar), InteractionEngine(), HandPoints(mapper)
        light = HandLight() if args.light else None
        brightness = brightness_check(s, mapper, renderer.render(canvas, controller, toolbar, mode=IDLE, cursor=None))
        if args.trace:
            save_dir.mkdir(parents=True, exist_ok=True)
            trace = open(save_dir / "trace.jsonl", "w", encoding="utf-8")
        print(f"drawing: {HELP}. Keys: z undo, y redo, s save, c twice clear, ESC quit.")
        s.camera.reset_stats()
        start = time.perf_counter()
        seq, last_saved, clear_armed_until, last_t = current_seq(s), -1e9, 0.0, None
        saved_paths = []
        while True:
            frame = s.camera.wait_frame(seq, 2.0)
            if frame is None:
                print("camera stopped delivering frames")
                break
            seq, last_t = frame.seq, frame.timestamp
            t0 = time.perf_counter()
            obs = tracker.process(frame.image, frame.timestamp)
            t1 = time.perf_counter()
            shape, hand = points(frame.timestamp, obs)
            step = engine.update(frame.timestamp, hand)
            controller.handle(step.events)
            controller.update_pointer(frame.timestamp, step.cursor)
            lit = None if light is None else light.update(frame.timestamp, projector_landmarks(mapper, obs))
            img = renderer.render(canvas, controller, toolbar, mode=step.mode, cursor=step.cursor, light=lit)
            s.projector.show(img)
            cv2.pollKey()
            t2 = time.perf_counter()
            shapes[shape.shape if shape else None] += 1
            records.append({"t": frame.timestamp - start, "mode": step.mode, "hand": obs is not None,
                            "inference_ms": (t1 - t0) * 1000, "pipeline_ms": (t2 - frame.timestamp) * 1000})
            if trace is not None:
                trace.write(json.dumps({"t": round(frame.timestamp - start, 4), "seq": frame.seq, "mode": step.mode,
                                        "pending": step.pending, "shape": shape.as_dict() if shape else None,
                                        "cursor": step.cursor, "events": [e.kind for e in step.events],
                                        "source": obs.source if obs else None, "lit": lit is not None}) + "\n")
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
                    f"strokes {len(canvas.strokes)}",
                    "", HELP, "keys: z undo  y redo  s save  c c clear  ESC quit"])
            key = cv2.waitKey(1)
            now = time.perf_counter()
            if key == 27 or (args.seconds and now - start >= args.seconds):
                break
            if key in (ord("z"), ord("Z")):
                controller.undo()
            elif key in (ord("y"), ord("Y")):
                controller.redo()
            elif key in (ord("s"), ord("S")):
                saved_paths.append([str(p) for p in save_canvas(config, canvas, renderer)])
                print(f"saved: {saved_paths[-1][0]}")
            elif key in (ord("c"), ord("C")):
                if now < clear_armed_until:
                    controller.clear()
                    clear_armed_until = 0.0
                else:
                    clear_armed_until = now + 2.0
                    print("press c again within 2 s to clear the canvas")
        if trace is not None:
            trace.close()
        if last_t is not None:          # end an open stroke / erase / pinch cleanly (no hand, after the hold)
            controller.handle(engine.update(last_t + 1.0, None).events)
        camera_stats = s.camera.stats()
        s.projector.show(patterns.blank(size))

    json_path, png_path = save_canvas(config, canvas, renderer)
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
        "strokes_on_canvas": len(canvas.strokes),
        "canvas": {"json": str(json_path), "png": str(png_path), "saved_during_run": saved_paths},
        "trace": str(save_dir / "trace.jsonl") if args.trace else None,
        "light": bool(args.light),
    }
    print(f"{len(records)} frames over {duration:.1f} s: processing {report['processing_fps']:.1f} fps "
          f"(camera {camera_stats.mean_fps:.1f}); pipeline median {report['pipeline_ms']['median']:.1f} ms, "
          f"p95 {report['pipeline_ms']['p95']:.1f} ms" if records else "no frames")
    print(f"modes (frames): {dict(engine.mode_frames)}; entered: {dict(engine.entries)}")
    print(f"actions: {dict(controller.log)}; strokes on the canvas {len(canvas.strokes)}")
    print(f"canvas: {json_path} (+ .png)")
    print(f"report: {save_report(config, 'draw', report)}")
    return 0
