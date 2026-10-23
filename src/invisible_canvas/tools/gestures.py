"""`gestures`: guided recording, acceptance tests G1' (Phase 2, brain.md §9.10, D46) and G1'' (D48).

Prompt sets: by default (G1') index finger only, open hand, fist; with `--angles` (G1'', D48) the index finger
pointing up, up-left, up-right, sideways and down-diagonal, then open hand and fist (`--rounds` times each).
A prompt starts only once a hand has been seen (`wait` phase, not scored), then has a prepare phase (not
scored: the hand changes shape) and a hold phase (scored: keep the shape and move the hand slowly around the
projection). Every frame's landmarks (camera px and 3-D world), measures and timing go to
data/diagnostics/gestures-<stamp>/frames.jsonl. With `--video` the camera frames the tracker saw also go to
video.avi there (frame k of the video = the record with "video_index" k), for `replay` (D48).

G1' (fixed 2026-10-22 before any run): POINT prompt >= 95 % of hand-present hold frames POINT; OPEN and FIST
prompts >= 95 % not POINT; the debounced engine (D46 defaults) never in DRAW during an OPEN/FIST hold. The
engine is run with each frame's keep-drawing flag (D47), as in `draw`.
G1'' (fixed 2026-10-22 before any D48 code): G1' for every pointing angle, the hand found in >= 90 % of each
pointing prompt's hold frames, and processing >= 30 fps with pipeline p95 <= 33 ms over the recording (as G6).
The hand is lit plain white (D50) only with `--light on` (off by default since 2026-10-23). G8 (fixed 2026-10-23 before any D50 code): with
`--busy --light ab` (a busy background of text and lines; rounds alternate light off, on, off, on), the hand is
found in >= 90 % of the pointing hold frames with the light on and at least as often as with it off; >= 30 fps
and pipeline p95 <= 33 ms over the light-on frames.
(G1 run 1 used the D44 shapes, including pinch and two fingers: brain.md §13.2.)
"""

from __future__ import annotations

import contextlib
import json
import time
from collections import Counter, defaultdict

import cv2
import numpy as np

from ..calibration.store import check_compatible, load_calibration
from ..config import Config
from ..canvas.render import RING_RADIUS
from ..canvas.toolbar import COLOURS
from ..display import patterns
from ..display.handlight import HandLight, paint
from ..interaction.engine import DRAW, EngineParams, HandInput, InteractionEngine
from ..vision.gestures import POINT
from ..vision.hands import HandTracker, HandTrackingError
from .common import add_device_args, current_seq, now_iso, open_session, save_report, stamp
from .tracking_session import (
    TRACKER_OPTIONS, HandPoints, brightness_check, checked_mapper, draw_skeleton, projector_landmarks,
)
from .video import VideoRecorder

NOT_POINT = "not point"
# (name, title, subtitle, expected, arrow direction on the projection or None)
PROMPTS = (
    ("point", "INDEX FINGER ONLY", "draw: point with the index finger, other fingers curled", POINT, None),
    ("open", "OPEN HAND", "not drawing: all five fingers open", NOT_POINT, None),
    ("fist", "FIST", "not drawing: all fingers closed", NOT_POINT, None),
)
ANGLE_PROMPTS = (
    ("up", "POINT UP", "index finger up, other fingers curled", POINT, (0, -1)),
    ("up_left", "POINT UP-LEFT", "index finger up and to the left, other fingers curled", POINT, (-1, -1)),
    ("up_right", "POINT UP-RIGHT", "index finger up and to the right, other fingers curled", POINT, (1, -1)),
    ("sideways", "POINT SIDEWAYS", "index finger flat along the wall, other fingers curled", POINT, (1, 0)),
    ("down", "POINT DOWN-DIAGONAL", "index finger down and to the side, other fingers curled", POINT, (1, 1)),
    ("open", "OPEN HAND", "not drawing: all five fingers open", NOT_POINT, None),
    ("fist", "FIST", "not drawing: all fingers closed", NOT_POINT, None),
)
EXPECTED = {p[0]: p[3] for p in PROMPTS}
ANGLE_EXPECTED = {p[0]: p[3] for p in ANGLE_PROMPTS}
G1_RATE = 0.95
G1PP_FOUND = 0.90                 # G1'': hand found in >= 90 % of each pointing prompt's hold frames
G6_FPS, G6_P95_MS = 30.0, 33.0
MIN_SCORED_FRAMES = 30            # fewer hand frames in a hold: that prompt is not evaluable
HAND_GATE_FRAMES, HAND_GATE_TIMEOUT_S = 10, 20.0   # a prompt starts after 10 frames with a hand (or 20 s)
G8_FOUND = 0.90                   # G8: hand found in >= 90 % of the pointing hold frames with the light on
BANNER_H = 160                    # --busy: the prompt sits in a white banner at the top
SEGMENT_GAP_S = 0.5               # timing: consecutive frames further apart belong to different segments


def add_parser(subparsers) -> None:
    p = subparsers.add_parser("gestures", help="guided recording: pointing vs not pointing, acceptance tests G1' / G1'' (Phase 2)")
    add_device_args(p)
    p.add_argument("--angles", action="store_true", help="G1'' (D48): point up, up-left, up-right, sideways, "
                                                         "down-diagonal, then open hand and fist")
    p.add_argument("--video", action="store_true", help="also save the camera video for `replay` (D48)")
    p.add_argument("--busy", action="store_true", help="G8 (D50): a busy background of text and lines, prompt at the top")
    p.add_argument("--light", choices=("on", "off", "ab"), default="off",
                   help="light on the hand (D50): off (default), on, or ab = off/on in alternate rounds (G8)")
    p.add_argument("--rounds", type=int, default=2, help="times through the prompts (default 2)")
    p.add_argument("--prepare", type=float, default=3.0, help="seconds to form each shape, not scored (default 3)")
    p.add_argument("--hold", type=float, default=6.0, help="seconds each shape is held and scored (default 6)")
    p.add_argument("--no-recalibrate", action="store_true", help="stop instead of recalibrating a moved setup")
    p.set_defaults(func=run)


def evaluate(records: list[dict], params: EngineParams = EngineParams(), expected: dict | None = None,
             min_found: float | None = None) -> dict:
    """G1' from per-frame records {t, prompt, phase ("wait"/"prepare"/"hold"), shape (None: no hand), keeps
    (optional: the keep-drawing flag, D47)}. Pure. A frame is correct when it is POINT for a POINT prompt and
    anything but POINT for the others. expected: prompt -> POINT / NOT_POINT (default the G1' prompts).
    min_found (G1''): each POINT prompt also needs a hand in at least this fraction of its hold frames."""
    expected = EXPECTED if expected is None else expected
    per = defaultdict(lambda: {"hold_frames": 0, "hand_frames": 0, "correct": 0, "shapes": Counter()})
    engine = InteractionEngine(params)
    draw_in_other_holds = 0
    for r in records:
        hand = None if r["shape"] is None else HandInput(r["shape"], (0.0, 0.0), (0.0, 0.0), (0.0, 0.0),
                                                          keeps_draw=bool(r.get("keeps")))
        mode = engine.update(r["t"], hand).mode
        if r["phase"] != "hold":
            continue
        p = per[r["prompt"]]
        p["hold_frames"] += 1
        if r["shape"] is not None:
            p["hand_frames"] += 1
            p["shapes"][r["shape"]] += 1
            p["correct"] += (r["shape"] == POINT) == (expected[r["prompt"]] == POINT)
        if mode == DRAW and expected[r["prompt"]] != POINT:
            draw_in_other_holds += 1
    prompts = {}
    for name in expected:
        p = per[name]
        rate = p["correct"] / p["hand_frames"] if p["hand_frames"] else None
        found = p["hand_frames"] / p["hold_frames"] if p["hold_frames"] else None
        needs_found = min_found is not None and expected[name] == POINT
        found_ok = not needs_found or (found is not None and found >= min_found)
        # a pointing prompt whose hand was rarely found is a measured failure, not "not evaluable"
        evaluable = p["hand_frames"] >= MIN_SCORED_FRAMES or (needs_found and p["hold_frames"] >= MIN_SCORED_FRAMES
                                                             and not found_ok)
        prompts[name] = {"expected": expected[name], "hold_frames": p["hold_frames"], "hand_frames": p["hand_frames"],
                         "found_rate": found, "correct": p["correct"], "rate": rate, "shapes": dict(p["shapes"]),
                         "evaluable": evaluable,
                         "pass": bool(evaluable and found_ok and rate is not None and rate >= G1_RATE)}
    all_evaluable = all(p["evaluable"] for p in prompts.values())
    passed = all_evaluable and all(p["pass"] for p in prompts.values()) and draw_in_other_holds == 0
    criterion = (f"G1': >= {G1_RATE:.0%} per prompt (POINT vs not), no DRAW in OPEN/FIST holds" if min_found is None
                 else f"G1'': >= {G1_RATE:.0%} per prompt (POINT vs not), hand found in >= {min_found:.0%} of each "
                      f"pointing hold, no DRAW in OPEN/FIST holds")
    return {"prompts": prompts, "draw_frames_in_non_point_holds": draw_in_other_holds, "criterion": criterion,
            "evaluable": all_evaluable, "pass": passed}


def timing(records: list[dict]) -> dict:
    """Processing rate and capture -> projector time over a recording or a subset of its frames (G1'' and G8 use
    the G6 limits). The rate counts only intervals between consecutive frames < SEGMENT_GAP_S apart, so a subset
    made of separate blocks (G8's light-on rounds) is not diluted by the time between them."""
    ts = [r["t"] for r in records]
    pipe = [r["pipeline_ms"] for r in records if r.get("pipeline_ms") is not None]
    dts = [b - a for a, b in zip(ts, ts[1:]) if 0 < b - a < SEGMENT_GAP_S]
    fps = len(dts) / sum(dts) if dts else 0.0
    p95 = float(np.percentile(pipe, 95)) if pipe else None
    return {"processing_fps": fps, "pipeline_ms_median": float(np.median(pipe)) if pipe else None,
            "pipeline_ms_p95": p95, "limits": {"fps_min": G6_FPS, "pipeline_p95_max_ms": G6_P95_MS},
            "pass": bool(fps >= G6_FPS and p95 is not None and p95 <= G6_P95_MS)}


def evaluate_light(records: list[dict], expected: dict) -> dict:
    """G8 (D50) from per-frame records with a "light" flag: hand found over the pointing hold frames with the light
    off and on, and timing over the light-on frames. Pure."""
    out = {}
    for name, cond in (("off", False), ("on", True)):
        sel = [r for r in records if r["phase"] == "hold" and expected.get(r["prompt"]) == POINT
               and bool(r.get("light")) == cond]
        hand = sum(r["shape"] is not None for r in sel)
        out[name] = {"hold_frames": len(sel), "hand_frames": hand, "found_rate": hand / len(sel) if sel else None,
                     "point_rate": (sum(r["shape"] == POINT for r in sel) / hand) if hand else None}
    times = timing([r for r in records if r.get("light")])
    on, off = out["on"]["found_rate"], out["off"]["found_rate"]
    evaluable = on is not None and off is not None and out["on"]["hold_frames"] >= MIN_SCORED_FRAMES
    passed = bool(evaluable and on >= G8_FOUND and on >= off and times["pass"])
    return {**out, "timing_light_on": times, "evaluable": evaluable, "pass": passed,
            "criterion": f"G8: hand found >= {G8_FOUND:.0%} of pointing hold frames with the light on and >= with it "
                         f"off; light-on frames >= {G6_FPS:g} fps, pipeline p95 <= {G6_P95_MS:g} ms"}


def busy_background(size, seed: int = 50) -> np.ndarray:
    """A deterministic 'full canvas' below the prompt banner: dark strokes in the ink colours and lines of text."""
    w, h = size
    rng = np.random.default_rng(seed)
    img = patterns.blank(size, 255)
    colours = list(COLOURS.values())
    for _ in range(45):
        n = int(rng.integers(8, 20))
        steps = rng.normal(0, 28, size=(n, 2))
        start = np.array([rng.uniform(0, w), rng.uniform(BANNER_H, h)])
        pts = np.round(start + np.cumsum(steps, axis=0)).astype(np.int32)
        cv2.polylines(img, [pts], False, colours[int(rng.integers(len(colours)))], int(rng.choice([4, 8, 14])),
                      cv2.LINE_AA)
    words = "the quick brown fox jumps over the lazy dog 0123456789 invisible canvas".split()
    for y in range(BANNER_H + 40, h, 70):
        x = int(rng.integers(0, 120))
        while x < w:
            word = words[int(rng.integers(len(words)))]
            cv2.putText(img, word, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (50, 50, 50), 2, cv2.LINE_AA)
            x += 30 * len(word) + int(rng.integers(20, 60))
    cv2.rectangle(img, (0, 0), (w - 1, BANNER_H), (255, 255, 255), -1)
    return img


def print_result(result: dict, name: str) -> None:
    print(f"{name} pointing recognition (hold phases, hand-present frames):")
    for prompt, p in result["prompts"].items():
        rate = "n/a" if p["rate"] is None else f"{100 * p['rate']:.1f} %"
        found = "" if p["found_rate"] is None else f", hand {100 * p['found_rate']:.0f} %"
        print(f"  {prompt:<9} expected {p['expected']:<9} {rate:>8} of {p['hand_frames']:>4} frames "
              f"(of {p['hold_frames']} hold frames{found}) {p['shapes']} "
              f"{'PASS' if p['pass'] else 'FAIL' if p['evaluable'] else 'NOT EVALUABLE'}")
    print(f"  DRAW during OPEN/FIST holds: {result['draw_frames_in_non_point_holds']} frames")


def _screen(size, title: str, subtitle: str, line: str, progress: float | None, cursor, hand_seen: bool,
            arrow=None, background: np.ndarray | None = None, light: np.ndarray | None = None) -> np.ndarray:
    """The prompt screen. With a (busy) `background` the prompt sits in the white banner at the top; with a
    `light` polygon the hand is painted white last and the cursor is a ring outside it (D50)."""
    w, h = size
    busy = background is not None
    img = background.copy() if busy else patterns.blank(size, 255)
    cv2.putText(img, "hand: seen" if hand_seen else "hand: NOT SEEN", (16, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                (40, 150, 40) if hand_seen else (40, 40, 215), 2, cv2.LINE_AA)
    rows = (((title, 60, 1.4, 3), (subtitle, 98, 0.7, 2), (line, 126, 0.7, 2)) if busy else
            ((title, h // 2 - 60, 2.0, 4), (subtitle, h // 2, 0.9, 2), (line, h // 2 + 60, 0.9, 2)))
    for text, y, scale, thick in rows:
        (tw, _), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, thick)
        cv2.putText(img, text, ((w - tw) // 2, y), cv2.FONT_HERSHEY_SIMPLEX, scale, (40, 40, 40), thick, cv2.LINE_AA)
    if arrow is not None:                  # which way to point (D48 angle prompts)
        d = np.asarray(arrow, dtype=np.float64)
        d = (45 if busy else 90) * d / np.linalg.norm(d)
        c = np.array([w - 110, 80]) if busy else np.array([w / 2, h / 2 - 190])
        cv2.arrowedLine(img, tuple(int(v) for v in c - d), tuple(int(v) for v in c + d), (40, 40, 40), 6,
                        cv2.LINE_AA, tipLength=0.35)
    if progress is not None:
        x0, x1, y = (w // 4, 3 * w // 4, 138) if busy else (w // 4, 3 * w // 4, h // 2 + 100)
        cv2.rectangle(img, (x0, y), (x1, y + (10 if busy else 14)), (200, 200, 200), -1)
        cv2.rectangle(img, (x0, y), (x0 + int((x1 - x0) * progress), y + (10 if busy else 14)), (40, 150, 40), -1)
    if cursor is not None:
        r = 12 if light is None else RING_RADIUS
        cv2.circle(img, (int(cursor[0]), int(cursor[1])), r, (110, 110, 110), 2, cv2.LINE_AA)
    paint(img, light)
    return img


def run(config: Config, args) -> int:
    prompts = ANGLE_PROMPTS if args.angles else PROMPTS
    expected = {p[0]: p[3] for p in prompts}
    test, min_found = ("G1''", G1PP_FOUND) if args.angles else ("G1'", None)
    background = busy_background((1280, 720)) if args.busy else None
    calibration = load_calibration(config.calibration_dir)
    try:
        tracker = HandTracker(**TRACKER_OPTIONS)
    except HandTrackingError as e:
        print(f"cannot start hand tracking: {e}")
        return 2
    folder = config.reports_dir.parent / "diagnostics" / f"gestures-{stamp()}"
    folder.mkdir(parents=True, exist_ok=True)
    plan = [p for _ in range(max(args.rounds, 1)) for p in prompts]
    records = []
    video_info = None
    with tracker, open_session(config, args) as s, open(folder / "frames.jsonl", "w", encoding="utf-8") as out, \
            (VideoRecorder(folder / "video.avi", s.camera_info.size) if args.video
             else contextlib.nullcontext()) as video:
        check_compatible(calibration, s.camera_info.size, s.canvas_size)
        checked = checked_mapper(config, s, calibration, no_recalibrate=args.no_recalibrate,
                                 title="SETUP CHECK before the gesture recording")
        if checked is None:
            return 1
        mapper, calibration, setup_info = checked
        size = s.canvas_size
        brightness = brightness_check(s, mapper, patterns.blank(size, 255))
        points = HandPoints(mapper)
        light = HandLight()
        if background is not None and background.shape[:2] != (size[1], size[0]):
            background = busy_background(size)
        seq = current_seq(s)
        start = time.perf_counter()
        quit_early = False
        for k, (name, title, subtitle, _, arrow) in enumerate(plan):
            round_no = k // len(prompts) + 1
            light_on = args.light == "on" or (args.light == "ab" and round_no % 2 == 0)   # ab: off, on, off, on
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
                t0 = time.perf_counter()
                obs = tracker.process(frame.image, frame.timestamp)
                process_ms = (time.perf_counter() - t0) * 1000
                shape, hand = points(frame.timestamp, obs)
                seen_run = seen_run + 1 if obs is not None else 0
                line = ("show your hand in the projection to start" if phase == "wait"
                        else f"get ready: {args.prepare - elapsed:.0f}" if phase == "prepare"
                        else "HOLD - move the hand slowly around the projection")
                progress = None if phase != "hold" else (elapsed - args.prepare) / args.hold
                lit = light.update(frame.timestamp, projector_landmarks(mapper, obs)) if light_on else None
                s.projector.show(_screen(size, title, f"{subtitle}   ({k + 1}/{len(plan)})", line, progress,
                                         hand.pointer if hand else None, obs is not None, arrow, background, lit))
                pipeline_ms = (time.perf_counter() - frame.timestamp) * 1000
                rec = {"t": frame.timestamp, "prompt": name, "round": round_no, "phase": phase, "light": light_on,
                       "shape": shape.shape if shape else None, "keeps": bool(shape and shape.keeps_point),
                       "process_ms": round(process_ms, 2), "pipeline_ms": round(pipeline_ms, 2),
                       "video_index": video.add(frame.image) if video is not None else None}
                records.append(rec)
                out.write(json.dumps({**rec, "t_s": round(frame.timestamp - start, 4), "seq": frame.seq,
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
        if video is not None:
            video.close()
            video_info = video.summary()

    result = evaluate(records, expected=expected, min_found=min_found)
    times = timing(records)
    passed = result["pass"] and (times["pass"] or not args.angles)
    g8 = evaluate_light(records, expected) if args.light == "ab" else None
    if g8 is not None:
        test, passed = "G8", g8["pass"]
    report = {"created_at": now_iso(), "calibration_created_at": calibration.created_at, "setup_check": setup_info,
              "brightness": brightness, "test": test, "prompt_set": "angles" if args.angles else "point",
              "rounds": args.rounds, "prepare_s": args.prepare, "hold_s": args.hold, "completed": not quit_early,
              "frames_file": str(folder / "frames.jsonl"), "video": video_info, "g1": result, "timing": times,
              "light": args.light, "busy": args.busy, "g8": g8, "pass": passed}
    print_result(result, test)
    p95 = times["pipeline_ms_p95"]
    print(f"  timing: processing {times['processing_fps']:.1f} fps, pipeline p95 "
          + ("n/a" if p95 is None else f"{p95:.1f} ms")
          + (f" ({'PASS' if times['pass'] else 'FAIL'}: >= {G6_FPS:g} fps, <= {G6_P95_MS:g} ms)" if args.angles else ""))
    if video_info:
        print(f"  video: {video_info['frames']} frames, {video_info['dropped']} dropped: {video_info['file']}")
    if g8 is not None:
        for cond in ("off", "on"):
            c = g8[cond]
            found = "n/a" if c["found_rate"] is None else f"{100 * c['found_rate']:.1f} %"
            pt = "n/a" if c["point_rate"] is None else f"{100 * c['point_rate']:.1f} %"
            print(f"  G8 light {cond:<3}: hand found {found} of {c['hold_frames']} pointing hold frames; POINT {pt} of hand frames")
        tl = g8["timing_light_on"]
        print(f"  G8 light-on timing: {tl['processing_fps']:.1f} fps, pipeline p95 "
              + ("n/a" if tl["pipeline_ms_p95"] is None else f"{tl['pipeline_ms_p95']:.1f} ms"))
    print(f"{test}: {'PASS' if passed else 'FAIL' if result['evaluable'] else 'NOT EVALUABLE'}")
    print(f"frames: {folder / 'frames.jsonl'}")
    print(f"report: {save_report(config, 'gestures', report)}")
    return 0 if passed else 1
