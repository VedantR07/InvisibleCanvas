"""`gestures`: guided recording, acceptance test G1' (Phase 2, brain.md §9.10, D46).

The projector prompts each shape in turn: index finger only, open hand, fist (`--rounds` times). A prompt starts
only once a hand has been seen (`wait` phase, not scored), then has a prepare phase (not scored: the hand changes
shape) and a hold phase (scored: keep the shape and move the hand slowly around the projection). Every frame's
landmarks (camera px and 3-D world) and measures go to data/diagnostics/gestures-<stamp>/frames.jsonl.

G1' (fixed 2026-10-22 before any run): POINT prompt >= 95 % of hand-present hold frames POINT; OPEN and FIST
prompts >= 95 % not POINT; the debounced engine (D46 defaults) never in DRAW during an OPEN/FIST hold.
(G1 run 1 used the D44 shapes, including pinch and two fingers: brain.md §13.2.)
"""

from __future__ import annotations

import json
import time
from collections import Counter, defaultdict

import cv2
import numpy as np

from ..calibration.store import check_compatible, load_calibration
from ..config import Config
from ..display import patterns
from ..interaction.engine import DRAW, EngineParams, HandInput, InteractionEngine
from ..vision.gestures import POINT
from ..vision.hands import HandTracker, HandTrackingError
from .common import add_device_args, current_seq, now_iso, open_session, save_report, stamp
from .tracking_session import HandPoints, brightness_check, checked_mapper, draw_skeleton

NOT_POINT = "not point"
PROMPTS = (
    ("point", "INDEX FINGER ONLY", "draw: point with the index finger, other fingers curled", POINT),
    ("open", "OPEN HAND", "not drawing: all five fingers open", NOT_POINT),
    ("fist", "FIST", "not drawing: all fingers closed", NOT_POINT),
)
EXPECTED = {name: shape for name, _, _, shape in PROMPTS}
G1_RATE = 0.95
MIN_SCORED_FRAMES = 30            # fewer hand frames in a hold: that prompt is not evaluable
HAND_GATE_FRAMES, HAND_GATE_TIMEOUT_S = 10, 20.0   # a prompt starts after 10 frames with a hand (or 20 s)


def add_parser(subparsers) -> None:
    p = subparsers.add_parser("gestures", help="guided recording: pointing vs not pointing, acceptance test G1' (Phase 2)")
    add_device_args(p)
    p.add_argument("--rounds", type=int, default=2, help="times through the 3 shapes (default 2)")
    p.add_argument("--prepare", type=float, default=3.0, help="seconds to form each shape, not scored (default 3)")
    p.add_argument("--hold", type=float, default=6.0, help="seconds each shape is held and scored (default 6)")
    p.add_argument("--no-recalibrate", action="store_true", help="stop instead of recalibrating a moved setup")
    p.set_defaults(func=run)


def evaluate(records: list[dict], params: EngineParams = EngineParams()) -> dict:
    """G1' from per-frame records {t, prompt, phase ("wait"/"prepare"/"hold"), shape (None: no hand)}. Pure.
    A frame is correct when it is POINT for the POINT prompt and anything but POINT for the others."""
    per = defaultdict(lambda: {"hold_frames": 0, "hand_frames": 0, "correct": 0, "shapes": Counter()})
    engine = InteractionEngine(params)
    draw_in_other_holds = 0
    for r in records:
        hand = None if r["shape"] is None else HandInput(r["shape"], (0.0, 0.0), (0.0, 0.0), (0.0, 0.0))
        mode = engine.update(r["t"], hand).mode
        if r["phase"] != "hold":
            continue
        p = per[r["prompt"]]
        p["hold_frames"] += 1
        if r["shape"] is not None:
            p["hand_frames"] += 1
            p["shapes"][r["shape"]] += 1
            p["correct"] += (r["shape"] == POINT) == (EXPECTED[r["prompt"]] == POINT)
        if mode == DRAW and EXPECTED[r["prompt"]] != POINT:
            draw_in_other_holds += 1
    prompts = {}
    for name in EXPECTED:
        p = per[name]
        rate = p["correct"] / p["hand_frames"] if p["hand_frames"] else None
        evaluable = p["hand_frames"] >= MIN_SCORED_FRAMES
        prompts[name] = {"expected": EXPECTED[name], "hold_frames": p["hold_frames"], "hand_frames": p["hand_frames"],
                         "correct": p["correct"], "rate": rate, "shapes": dict(p["shapes"]), "evaluable": evaluable,
                         "pass": bool(evaluable and rate is not None and rate >= G1_RATE)}
    all_evaluable = all(p["evaluable"] for p in prompts.values())
    passed = all_evaluable and all(p["pass"] for p in prompts.values()) and draw_in_other_holds == 0
    return {"prompts": prompts, "draw_frames_in_non_point_holds": draw_in_other_holds,
            "criterion": f"G1': >= {G1_RATE:.0%} per prompt (POINT vs not), no DRAW in OPEN/FIST holds",
            "evaluable": all_evaluable,
            "pass": passed}


def _screen(size, title: str, subtitle: str, line: str, progress: float | None, cursor, hand_seen: bool) -> np.ndarray:
    img = patterns.blank(size, 255)
    w, h = size
    cv2.putText(img, "hand: seen" if hand_seen else "hand: NOT SEEN", (16, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                (40, 150, 40) if hand_seen else (40, 40, 215), 2, cv2.LINE_AA)
    for text, y, scale, thick in ((title, h // 2 - 60, 2.0, 4), (subtitle, h // 2, 0.9, 2), (line, h // 2 + 60, 0.9, 2)):
        (tw, _), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, thick)
        cv2.putText(img, text, ((w - tw) // 2, y), cv2.FONT_HERSHEY_SIMPLEX, scale, (40, 40, 40), thick, cv2.LINE_AA)
    if progress is not None:
        x0, x1, y = w // 4, 3 * w // 4, h // 2 + 100
        cv2.rectangle(img, (x0, y), (x1, y + 14), (200, 200, 200), -1)
        cv2.rectangle(img, (x0, y), (x0 + int((x1 - x0) * progress), y + 14), (40, 150, 40), -1)
    if cursor is not None:
        cv2.circle(img, (int(cursor[0]), int(cursor[1])), 12, (110, 110, 110), 2, cv2.LINE_AA)
    return img


def run(config: Config, args) -> int:
    calibration = load_calibration(config.calibration_dir)
    try:
        tracker = HandTracker(acquisition="tiled")
    except HandTrackingError as e:
        print(f"cannot start hand tracking: {e}")
        return 2
    folder = config.reports_dir.parent / "diagnostics" / f"gestures-{stamp()}"
    folder.mkdir(parents=True, exist_ok=True)
    plan = [p for _ in range(max(args.rounds, 1)) for p in PROMPTS]
    records = []
    with tracker, open_session(config, args) as s, open(folder / "frames.jsonl", "w", encoding="utf-8") as out:
        check_compatible(calibration, s.camera_info.size, s.canvas_size)
        checked = checked_mapper(config, s, calibration, no_recalibrate=args.no_recalibrate,
                                 title="SETUP CHECK before the gesture recording")
        if checked is None:
            return 1
        mapper, calibration, setup_info = checked
        size = s.canvas_size
        brightness = brightness_check(s, mapper, patterns.blank(size, 255))
        points = HandPoints(mapper)
        seq = current_seq(s)
        start = time.perf_counter()
        quit_early = False
        for k, (name, title, subtitle, _) in enumerate(plan):
            gate_start, seen_run, prompt_start = time.perf_counter(), 0, None
            saved = 0
            while True:
                now = time.perf_counter()
                if prompt_start is None and (seen_run >= HAND_GATE_FRAMES or now - gate_start >= HAND_GATE_TIMEOUT_S):
                    prompt_start = now
                elapsed = 0.0 if prompt_start is None else now - prompt_start
                if prompt_start is not None and elapsed >= args.prepare + args.hold:
                    break
                phase = "wait" if prompt_start is None else "prepare" if elapsed < args.prepare else "hold"
                frame = s.camera.wait_frame(seq, 2.0)
                if frame is None:
                    print("camera stopped delivering frames")
                    quit_early = True
                    break
                seq = frame.seq
                obs = tracker.process(frame.image, frame.timestamp)
                shape, hand = points(frame.timestamp, obs)
                seen_run = seen_run + 1 if obs is not None else 0
                line = ("show your hand in the projection to start" if phase == "wait"
                        else f"get ready: {args.prepare - elapsed:.0f}" if phase == "prepare"
                        else "HOLD - move the hand slowly around the projection")
                progress = None if phase != "hold" else (elapsed - args.prepare) / args.hold
                s.projector.show(_screen(size, title, f"{subtitle}   ({k + 1}/{len(plan)})", line, progress,
                                         hand.pointer if hand else None, obs is not None))
                rec = {"t": frame.timestamp, "prompt": name, "round": k // len(PROMPTS) + 1, "phase": phase,
                       "shape": shape.shape if shape else None}
                records.append(rec)
                out.write(json.dumps({**rec, "t_s": round(frame.timestamp - start, 4),
                                      "measures": shape.as_dict() if shape else None,
                                      "landmarks": None if obs is None else np.round(obs.landmarks, 2).tolist(),
                                      "world": None if obs is None or obs.world is None
                                      else np.round(obs.world, 5).tolist(),
                                      "tip_in_view": None if obs is None else obs.tip_in_view}) + "\n")
                if phase == "hold" and saved < 2 and elapsed - args.prepare >= args.hold * (0.3 + 0.4 * saved):
                    cv2.imwrite(str(folder / f"{k + 1:02d}_{name}_{saved}.jpg"), frame.image, [cv2.IMWRITE_JPEG_QUALITY, 90])
                    saved += 1
                view = frame.image.copy()
                if obs is not None:
                    draw_skeleton(view, obs.landmarks)
                s.operator.show(view, lines=[f"GESTURE RECORDING {k + 1}/{len(plan)}: {title}", f"phase: {phase}",
                                             f"shape now: {shape.shape if shape else 'no hand'}", "ESC: stop"])
                if cv2.waitKey(1) == 27:
                    quit_early = True
                    break
            if quit_early:
                break
        s.projector.show(patterns.blank(size))

    result = evaluate(records)
    report = {"created_at": now_iso(), "calibration_created_at": calibration.created_at, "setup_check": setup_info,
              "brightness": brightness, "rounds": args.rounds, "prepare_s": args.prepare, "hold_s": args.hold,
              "completed": not quit_early, "frames_file": str(folder / "frames.jsonl"), "g1": result}
    print("G1' pointing recognition (hold phases, hand-present frames):")
    for name, p in result["prompts"].items():
        rate = "n/a" if p["rate"] is None else f"{100 * p['rate']:.1f} %"
        print(f"  {name:<6} expected {p['expected']:<6} {rate:>8} of {p['hand_frames']:>4} frames "
              f"(of {p['hold_frames']} hold frames) {p['shapes']} {'PASS' if p['pass'] else 'FAIL' if p['evaluable'] else 'NOT EVALUABLE'}")
    print(f"  DRAW during OPEN/FIST holds: {result['draw_frames_in_non_point_holds']} frames")
    print(f"G1': {'PASS' if result['pass'] else 'FAIL' if result['evaluable'] else 'NOT EVALUABLE'}")
    print(f"frames: {folder / 'frames.jsonl'}")
    print(f"report: {save_report(config, 'gestures', report)}")
    return 0 if result["pass"] else 1
