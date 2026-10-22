"""`replay`: a recorded `gestures --video` session run offline through the hand tracker, the shape classifier
and the interaction engine (D48), so tracking and recognition changes are measured on the same frames
without the user repeating the poses.

The recorded timestamps drive MediaPipe's VIDEO mode, so the tracker sees the frames in the live order and
timing; a frame the recorder dropped is a gap, as a slow frame would be. Shapes come from the ShapeReader the
live tools use. Reported per prompt (overall and per round, round 2 being held out when round 1 was used to
design a change): hand found, POINT rate, DRAW frames in OPEN/FIST holds, the G1' / G1'' result, how often the
replay's shape matches the live one (fidelity of the replay itself), and the tracker's time per frame offline.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import cv2
import numpy as np

from ..config import Config
from ..vision.hands import HandTracker, HandTrackingError
from .common import now_iso, save_report
from .gestures import ANGLE_EXPECTED, EXPECTED, G1PP_FOUND, evaluate, print_result
from .tracking_session import ShapeReader


class ReplayError(RuntimeError):
    """The recording cannot be replayed (missing files, a video shorter than its frame records)."""


def add_parser(subparsers) -> None:
    p = subparsers.add_parser("replay", help="replay a recorded `gestures --video` session offline (D48)")
    p.add_argument("recording", type=Path, help="the data/diagnostics/gestures-<stamp> folder (frames.jsonl, video.avi)")
    p.set_defaults(func=run)


def load_rows(folder: Path) -> list[dict]:
    frames, video = folder / "frames.jsonl", folder / "video.avi"
    if not frames.is_file() or not video.is_file():
        raise ReplayError(f"{folder} has no frames.jsonl and video.avi (record with `gestures --video`)")
    with open(frames, encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def prompt_set(rows: list[dict]) -> tuple[dict, float | None, str]:
    """(expected, min_found, test name) of a recording, from its prompt names."""
    names = {r["prompt"] for r in rows}
    if names <= set(EXPECTED):
        return EXPECTED, None, "G1'"
    if names <= set(ANGLE_EXPECTED):
        return ANGLE_EXPECTED, G1PP_FOUND, "G1''"
    raise ReplayError(f"unknown prompts in the recording: {sorted(names - set(EXPECTED) - set(ANGLE_EXPECTED))}")


def replay(folder: Path, tracker, reader: ShapeReader | None = None, rows: list[dict] | None = None) -> list[dict]:
    """One record per recorded frame that is in the video: {t, prompt, round, phase, shape, keeps, process_ms,
    live_shape}. `tracker`: anything with process(image, t) -> HandObservation | None (a fresh HandTracker)."""
    rows = load_rows(folder) if rows is None else rows
    reader = ShapeReader() if reader is None else reader
    cap = cv2.VideoCapture(str(folder / "video.avi"))
    if not cap.isOpened():
        raise ReplayError(f"cannot open {folder / 'video.avi'}")
    out, position = [], 0
    try:
        for r in rows:
            index = r.get("video_index")
            if index is None:                 # dropped by the recorder: a gap for the tracker
                continue
            image = None
            while position <= index:
                ok, image = cap.read()
                if not ok:
                    raise ReplayError(f"the video ends at frame {position}, the records need frame {index}")
                position += 1
            t0 = time.perf_counter()
            obs = tracker.process(image, r["t"])
            ms = (time.perf_counter() - t0) * 1000
            shape = reader(obs)
            out.append({"t": r["t"], "prompt": r["prompt"], "round": r.get("round", 1), "phase": r["phase"],
                        "shape": shape.shape if shape else None, "keeps": bool(shape and shape.keeps_point),
                        "process_ms": ms, "live_shape": r["shape"]})
    finally:
        cap.release()
    return out


def summarize(records: list[dict], expected: dict, min_found: float | None) -> dict:
    rounds = sorted({r["round"] for r in records})
    agree = [r["shape"] == r["live_shape"] for r in records]
    ms = np.array([r["process_ms"] for r in records]) if records else np.zeros(0)
    return {"overall": evaluate(records, expected=expected, min_found=min_found),
            "rounds": {str(k): evaluate([r for r in records if r["round"] == k], expected=expected, min_found=min_found)
                       for k in rounds},
            "frames": len(records),
            "shape_agreement_with_live": float(np.mean(agree)) if agree else None,
            "process_ms": None if not len(ms) else {"median": float(np.median(ms)), "p95": float(np.percentile(ms, 95))}}


def run(config: Config, args) -> int:
    folder = args.recording
    try:
        rows = load_rows(folder)
        expected, min_found, test = prompt_set(rows)
        with HandTracker(acquisition="tiled") as tracker:
            records = replay(folder, tracker, rows=rows)
    except (ReplayError, HandTrackingError) as e:
        print(f"cannot replay: {e}")
        return 2
    summary = summarize(records, expected, min_found)
    for name, result in (("overall", summary["overall"]), *((f"round {k}", v) for k, v in summary["rounds"].items())):
        print(f"--- {name} ---")
        print_result(result, test)
    agreement = summary["shape_agreement_with_live"]
    print(f"{summary['frames']} frames replayed; shape equal to the live run in "
          f"{'n/a' if agreement is None else f'{100 * agreement:.1f} %'} of frames")
    if summary["process_ms"]:
        print(f"tracker time per frame (offline): median {summary['process_ms']['median']:.1f} ms, "
              f"p95 {summary['process_ms']['p95']:.1f} ms")
    print(f"{test} (replay, overall): {'PASS' if summary['overall']['pass'] else 'FAIL'}")
    report = {"created_at": now_iso(), "recording": str(folder), "test": test, **summary}
    print(f"report: {save_report(config, 'replay', report)}")
    return 0 if summary["overall"]["pass"] else 1
