"""`cursor` (Phase 1D, brain.md D33): index-fingertip cursor on the projected canvas.

Camera frame -> MediaPipe hand landmarks -> index fingertip (camera px) -> the validated
calibration H -> projector px -> cursor state (tracking / holding / lost / outside) -> projector.
No drawing or erasing: the cursor only shows where the fingertip maps.

Safety: the automatic setup check (D28/D32) runs first, so a moved setup cannot drive a wrong
cursor (`--no-setup-check` skips it). Measurements are written to data/reports/cursor-*.json:
camera and processing fps, inference time, queue age, capture->display latency (to the moment
the projector image is handed to Windows; the display path itself is the A3 measurement),
detection rate, tracking losses, and, with --accuracy, fingertip error and stability on 9
targets (corners, edge midpoints, centre) at the validation inset.

Accuracy test (D35): the operator is told what "on the target" means (`--aim`, default: the
fingertip's shadow on the target centre, viewpoint-independent and without wall contact); per
target the report has the detection rate, first-detection delay, handedness confidence and hand
size, and an annotated camera frame of each capture is saved. `--targets/--labels/--pause` run
custom sequences such as hover-distance sweeps.

D36: with --aim shadow, each capture measures the fingertip's shadow centre at the target in the
hold frames (vision/shadow.shadow_tip_near) and the cursor error against it; a capture whose shadow
centre is not established reliably makes the run INVALID for the criteria. Rows/columns are
summarised. Hand acquisition is tiled by default (vision/hands, D36); --withdraw makes each target
wait until the hand has been out of view, so the first detection measures acquisition.

D37 (tracking audit): a fingertip that lies outside the image MediaPipe saw (extrapolated) is not drawn
as a detection. Each record has the drawn position and the reason for the cursor state; the report has
a motion summary (state transitions, reacquisitions, smoothing lag, still jitter, transient jumps).
--trace writes one JSON line per frame (tracker action, view, landmarks, every coordinate stage, state,
timings) to the run's diagnostics folder; it is off by default.

D38: landmark diagnostics (vision/landmark_diagnostics) run on every frame AFTER the cursor update and are only
recorded: per frame in the trace ("diag") and as a summary with episodes in the report ("landmark_diagnostics").
They never change, delay, hold or hide the cursor.

D39: when the setup check finds that the setup moved, the calibration is recovered automatically
(tools/recalibrate, calibration/recovery): a replacement is built from the corners just detected, checked,
validated on the held-out grid and confirmed before it is saved and used; on any failure nothing is saved and
the cursor does not start. `--no-recalibrate` stops at the refusal instead (the D28 behaviour).
"""

from __future__ import annotations

import dataclasses
import json
import time

import cv2
import numpy as np

from ..calibration.auto import AutoCalibrationError, auto_setup_check
from ..calibration.metrics import accuracy_stats
from ..calibration.recovery import explain
from ..calibration.store import check_compatible, load_calibration
from ..calibration.targets import grid_targets
from ..config import Config
from ..display import patterns
from ..mapping.mapper import CoordinateMapper
from ..vision.cursor import HOLDING, LOST, OUTSIDE, TRACKING, CursorTracker, OneEuroFilter, dwell
from ..vision.hands import DEFAULT_MODEL, INDEX_TIP, HandTracker, HandTrackingError
from ..vision.landmark_diagnostics import SEARCH_SOURCES, LandmarkDiagnostics
from ..vision.landmark_diagnostics import summary as landmark_summary
from ..vision.shadow import find_shadow, finger_width, hand_mask, shadow_tip_near, steady_shadow_centre
from .common import (CameraMeasure, add_device_args, capture_frames, current_seq, now_iso, open_session,
                     save_report, stamp)
from .hand_check import DARK_REGION_LUMA, canvas_mask, region_luma
from .recalibrate import TITLE as RECOVERY_TITLE
from .recalibrate import recover_in_session
from .validate import setup_limit

TRACE_LANDMARKS = (0, 5, 6, 8, 12, 16)   # --trace: wrist, index MCP/PIP/tip, middle and ring tips (finger swaps)
SPIKE_PX = 25.0              # motion summary: a jump > 25 px that returns within 3 frames is a transient (D37)
STILL_PX_S = 30.0            # motion summary: below 30 projector px/s the fingertip counts as still
# Hand-skeleton connections (MediaPipe hand model), for the operator view only.
BONES = ((0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8), (5, 9), (9, 10), (10, 11), (11, 12),
         (9, 13), (13, 14), (14, 15), (15, 16), (13, 17), (0, 17), (17, 18), (18, 19), (19, 20))
# Accuracy-test capture rule: the fingertip must stay within DWELL_RADIUS_PX of its own mean for DWELL_S.
# 4 px (first version) was mostly unreachable: a held fingertip scatters 1.7-2.4 px rms about its mean
# (D34, measured on the 4 targets that did pass), so it often leaves 4 px within a second; 8 px is
# ~3.5x the worst measured scatter. The reported error is the mean position over the window, so the
# radius only selects steady moments, it does not loosen the error.
DWELL_S, DWELL_RADIUS_PX, CAPTURE_DISTANCE_PX, TARGET_TIMEOUT_S = 1.0, 8.0, 60.0, 30.0
# The projected canvas is what lights the hand in a dark room (D34): grey 40 -> 0 % detection,
# 80/128/200 -> 100 % with the same hand. 128 is mid-range and does not saturate the wall.
DEFAULT_BACKGROUND = 128
# What "the fingertip is on the target" means without wall contact (D35). "shadow": the shadow of the
# fingertip touches the target centre, i.e. the target's projector ray passes through the fingertip.
# The shadow and the target are both on the wall, so the operator can align them from any viewpoint.
# "finger": the old instruction (fingertip on the target as the operator sees it; viewpoint-dependent).
AIMS = {
    "shadow": "point with the index finger; put the SHADOW of the fingertip on the target centre and hold still "
              "(no wall contact)",
    "finger": "hold the fingertip still on the target as you see it",
}
# PROVISIONAL fingertip-accuracy criteria (user, 2026-10-10, D35): recorded, NOT validated. Evaluated on
# the cursor-vs-target error of the standard 9-target test; they change no measurement or capture rule.
PROVISIONAL_MEAN_PX, PROVISIONAL_MAX_PX = 5.0, 12.0
WITHDRAW_S = 0.5             # --withdraw: the hand must have been out of view this long before a target activates
SHADOW_SAMPLE_EVERY = 5      # keep every 5th on-target frame (~6/s): capture image and the optional shadow check


def add_parser(subparsers) -> None:
    p = subparsers.add_parser("cursor", help="index-fingertip cursor on the projection (Phase 1D)")
    add_device_args(p)
    p.add_argument("--seconds", type=float, default=0.0, help="stop after N seconds (default: until ESC)")
    p.add_argument("--accuracy", action="store_true",
                   help="9-target test: hold the fingertip still on each projected target")
    p.add_argument("--background", type=int, default=DEFAULT_BACKGROUND,
                   help=f"grey level of the projected canvas 0-255; it is the light on the hand "
                        f"(default {DEFAULT_BACKGROUND}; 40 was too dark to see a hand, D34)")
    p.add_argument("--smoothing", action="store_true", help="One Euro filter on the cursor (default: raw)")
    p.add_argument("--hold-ms", type=float, default=150.0, help="keep the cursor this long after a dropout")
    p.add_argument("--inference-width", type=int, default=960, help="frame width given to MediaPipe")
    p.add_argument("--model", default=None, help=f"hand model file (default {DEFAULT_MODEL})")
    p.add_argument("--no-setup-check", action="store_true", help="skip the automatic setup check (not recommended)")
    p.add_argument("--no-recalibrate", action="store_true",
                   help="if the setup check finds a moved setup, stop instead of recalibrating automatically (D39)")
    p.add_argument("--save-every", type=float, default=0.0,
                   help="diagnostic: save a camera frame every N seconds to data/diagnostics/ (default off)")
    p.add_argument("--aim", choices=sorted(AIMS), default="shadow",
                   help="accuracy-test instruction (D35): 'shadow' (default) = fingertip shadow on the target "
                        "centre; 'finger' = fingertip on the target as seen")
    p.add_argument("--targets", default=None,
                   help='accuracy targets in projector px instead of the 9-point grid, e.g. "640,690 640,690 640,29" '
                        "(repeats allowed: hover-distance sweeps)")
    p.add_argument("--labels", default=None,
                   help='text shown next to each target, e.g. "2cm 8cm 15cm" (one word per target)')
    p.add_argument("--shadow-check", action="store_true",
                   help="EXPERIMENTAL: look for the fingertip's shadow at each capture (D35). Off by default: on "
                        "the 2026-10-10 hardware it often matched the wrong shadow; check the capture frames")
    p.add_argument("--acquisition", choices=("tiled", "full"), default="tiled",
                   help="hand search while no hand is tracked (D36): 'tiled' (default) = full frame + higher-"
                        "resolution tiles, then tracking in a region around the hand; 'full' = D33 behaviour")
    p.add_argument("--withdraw", action="store_true",
                   help=f"each target activates only after the hand has been out of view for {WITHDRAW_S:g} s, "
                        "so the first detection measures acquisition (D36)")
    p.add_argument("--trace", action="store_true",
                   help="diagnostic: write a per-frame trace (tracker action, view, landmarks, coordinates, state, "
                        "timings) to data/diagnostics/cursor-*/trace.jsonl (default off; ~0.5 kB per frame)")
    p.add_argument("--pause", type=float, default=1.0,
                   help="seconds between a capture and the next target becoming active (default 1; a sweep "
                        "at one position needs time to change the hover distance, e.g. 5)")
    p.set_defaults(func=run)


def parse_targets(text: str, size: tuple[int, int]) -> np.ndarray:
    """'640,690 51,29' -> [[640, 690], [51, 29]]; every point must be on the canvas."""
    pts = []
    for pair in text.replace(";", " ").split():
        x, y = (float(v) for v in pair.split(","))
        if not (0 <= x <= size[0] - 1 and 0 <= y <= size[1] - 1):
            raise ValueError(f"target {pair} is outside the {size[0]}x{size[1]} canvas")
        pts.append((x, y))
    if not pts:
        raise ValueError("no targets")
    return np.array(pts, dtype=float)


@dataclasses.dataclass
class TargetStats:
    """Per-target diagnostics of the accuracy test (D35): detection, confidence, hand size."""
    start: float
    frames: int = 0
    found: int = 0
    first_found_s: float | None = None
    drops: int = 0
    armed_at: float | None = None
    first_after_arm_s: float | None = None
    scores: list = dataclasses.field(default_factory=list)
    lengths: list = dataclasses.field(default_factory=list)
    _last_found: bool = False

    def add(self, t: float, obs) -> None:
        self.frames += 1
        if obs is not None:
            self.found += 1
            self.scores.append(obs.score)
            self.lengths.append(obs.length_px)
            if self.first_found_s is None:
                self.first_found_s = t - self.start
            if self.armed_at is not None and self.first_after_arm_s is None:
                self.first_after_arm_s = t - self.armed_at
        elif self._last_found:
            self.drops += 1
        self._last_found = obs is not None

    def summary(self, t_end: float) -> dict:
        med = lambda v: float(np.median(v)) if v else None      # noqa: E731
        return {"duration_s": t_end - self.start, "frames": self.frames,
                "hand_found_fraction": self.found / self.frames if self.frames else 0.0,
                "first_detection_s": self.first_found_s, "detection_drops": self.drops,
                "first_detection_after_activation_s": self.first_after_arm_s,
                # MediaPipe's Tasks API exposes no hand-presence score; this is the handedness confidence.
                "handedness_score_median": med(self.scores), "handedness_score_min": min(self.scores, default=None),
                "hand_length_px_median": med(self.lengths)}


def shadow_check(frames, mapper, region, black: float, background: float, target) -> tuple[dict, list]:
    """The fingertip's shadow in the frames of a capture window (D35). parallax = H(fingertip) - H(shadow
    tip): how far the cursor is from the projector pixel whose light lands on the fingertip."""
    rows = []
    for _, image, landmarks in frames:
        s = find_shadow(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), landmarks, region, black, background)
        if s is not None:
            pf, ps = mapper.camera_to_projector([landmarks[INDEX_TIP], s.tip])
            rows.append((s, pf - ps, ps - np.asarray(target)))
    out = {"frames_checked": len(frames), "frames_with_shadow": len(rows)}
    if rows:
        par = np.median([r[1] for r in rows], axis=0)
        out.update(offset_camera_px=np.median([r[0].offset for r in rows], axis=0).tolist(),
                   parallax_px=par.tolist(), parallax_magnitude_px=float(np.hypot(*par)),
                   shadow_minus_target_px=np.median([r[2] for r in rows], axis=0).tolist(),
                   score_median=float(np.median([r[0].score for r in rows])))
    return out, rows


def _canvas(size, grey: int) -> np.ndarray:
    return patterns.blank(size, int(np.clip(grey, 0, 255)))


def _draw_cursor(img, position, status) -> None:
    color = patterns.CYAN if status == TRACKING else patterns.ORANGE
    patterns.draw_crosshair(img, position, color, gap=6, arm=22, thickness=3)


def motion_summary(records: list[dict]) -> dict:
    """D37: how the drawn cursor followed the mapped fingertip, from the per-frame records (t, status, raw,
    position). lag = |drawn - raw| while moving; still jitter = rms (per axis) of the drawn position about
    its centred 9-frame mean where the raw fingertip moved < STILL_PX_S; spikes = the raw fingertip jumps
    > SPIKE_PX from the previous frame and returns within SPIKE_PX / 3 of where it was in 1-3 frames."""
    n = len(records)
    raw = [np.array(r["raw"]) if r["status"] == "tracking" and r.get("raw") is not None else None for r in records]
    pos = [np.array(r["position"]) if r["status"] == "tracking" and r.get("position") is not None else None
           for r in records]
    t = [r["t"] for r in records]
    lag, jitter = [], []
    for i in range(4, n - 4):
        win = range(i - 4, i + 5)
        if any(raw[k] is None or pos[k] is None for k in win) or t[i + 4] <= t[i - 4]:
            continue
        speed = np.linalg.norm(raw[i + 4] - raw[i - 4]) / (t[i + 4] - t[i - 4])
        if speed < STILL_PX_S:
            jitter.extend(pos[i] - np.mean([pos[k] for k in win], axis=0))
        else:
            lag.append(float(np.linalg.norm(pos[i] - raw[i])))
    spikes = 0
    for i in range(1, n - 1):
        if raw[i] is None or raw[i - 1] is None or np.linalg.norm(raw[i] - raw[i - 1]) <= SPIKE_PX:
            continue
        if any(raw[k] is not None and np.linalg.norm(raw[k] - raw[i - 1]) < SPIKE_PX / 3
               for k in range(i + 1, min(i + 4, n))):
            spikes += 1
    tracked = sum(p is not None for p in raw)
    return {"lag_px": _percentiles(lag),
            "still_jitter_rms_px": float(np.sqrt(np.mean(np.square(jitter)))) if jitter else None,
            "still_samples": len(jitter) // 2,
            "spikes": spikes, "spikes_per_1000_tracked": 1000 * spikes / tracked if tracked else None}


def _percentiles(values) -> dict | None:
    v = np.asarray(values, dtype=float)
    if len(v) == 0:
        return None
    return {"median": float(np.median(v)), "p95": float(np.percentile(v, 95)), "max": float(v.max()), "n": len(v)}


def shadow_alignment(frames, target, mapper, region, black: float, background: float) -> tuple[dict, list]:
    """D36: the fingertip's shadow centre at the target over the hold frames [(t, image, landmarks)] and
    the cursor error against it, paired frame by frame (cursor = H(fingertip), reference = H(shadow
    centre); both on the wall plane only for the shadow, which is the point of the measurement)."""
    target_camera = mapper.projector_to_camera([target])[0]
    tips, pairs = [], []
    for _, image, lm in frames:
        grey = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        width = finger_width(lm)
        tip = shadow_tip_near(grey, target_camera, lm[INDEX_TIP] - lm[6], width, black, background,
                              hand_mask(grey.shape, lm, width), region)
        tips.append(tip)
        if tip.found:
            cur, centre = mapper.camera_to_projector([lm[INDEX_TIP], tip.centre])
            pairs.append((cur - centre, centre))
    c = steady_shadow_centre(tips)
    out = {"established": c.established, "reason": c.reason, "frames": c.frames, "found": c.found,
           "spread_camera_px": c.spread_px}
    if c.established:
        e = np.median([p[0] for p in pairs], axis=0)
        centre = np.median([p[1] for p in pairs], axis=0)
        out.update(error_xy=e.tolist(), error_px=float(np.hypot(*e)), centre=centre.tolist(),
                   centre_minus_target=(centre - np.asarray(target)).tolist(), centre_camera=list(c.centre))
    return out, tips


def rows_and_columns(entries: list[dict], value) -> dict:
    """Mean / max of value(entry) per target row and column (3x3 grid: top/middle/bottom, left/centre/right)."""
    out = {}
    for axis, names in ((1, ("top", "middle", "bottom")), (0, ("left", "centre", "right"))):
        levels = sorted({e["target"][axis] for e in entries})
        for k, level in enumerate(levels):
            vals = [value(e) for e in entries if e["target"][axis] == level and value(e) is not None]
            name = names[k] if len(levels) == 3 else f"{'xy'[axis]}={level:g}"
            out[name] = ({"mean": float(np.mean(vals)), "max": float(np.max(vals)), "n": len(vals)} if vals
                         else {"mean": None, "max": None, "n": 0})
    return out


def _accuracy_targets(w: int, h: int, inset: float) -> np.ndarray:
    return grid_targets(w, h, 3, 3, inset)     # corners, edge midpoints, centre


def _save_capture(path, last, rows, target_camera, shadow_tip=None) -> None:
    """Camera frame at a capture: fingertip (red), target centre (magenta), shadow centre at the target if
    found in this frame (cyan ring; D36), experimental global shadow tip (cyan dot)."""
    _, image, landmarks = last
    view = image.copy()
    for a, b in BONES:
        cv2.line(view, tuple(np.round(landmarks[a]).astype(int)), tuple(np.round(landmarks[b]).astype(int)),
                 patterns.GREEN, 1, cv2.LINE_AA)
    tip = tuple(np.round(landmarks[INDEX_TIP]).astype(int))
    cv2.drawMarker(view, tuple(np.round(target_camera).astype(int)), (255, 0, 255), cv2.MARKER_CROSS, 24, 2)
    if rows:
        shadow_tip = tuple(np.round(rows[-1][0].tip).astype(int))
        cv2.line(view, tip, shadow_tip, (255, 255, 0), 1, cv2.LINE_AA)
        cv2.circle(view, shadow_tip, 4, (255, 255, 0), -1)
    if shadow_tip is not None and shadow_tip.found:
        cv2.circle(view, tuple(np.round(shadow_tip.centre).astype(int)), 6, (255, 255, 0), 2)
    cv2.circle(view, tip, 4, (0, 0, 255), -1)
    cv2.imwrite(str(path), view, [cv2.IMWRITE_JPEG_QUALITY, 92])


def _trace_line(frame, start, t0, t1, t2, action, obs, mapped, u, diag=None) -> dict:
    """--trace (D37): one frame, every stage from the camera frame to the drawn cursor."""
    rnd = lambda v: None if v is None else [round(float(c), 2) for c in v]      # noqa: E731
    line = {"seq": frame.seq, "t": round(frame.timestamp - start, 4), "action": action, "hand": obs is not None,
            "status": u.status, "reason": u.reason, "raw_proj": rnd(u.raw), "drawn": rnd(u.position),
            "since_seen_ms": None if u.since_seen_s is None else round(u.since_seen_s * 1000, 1),
            "queue_ms": round((t0 - frame.timestamp) * 1000, 2), "inference_ms": round((t1 - t0) * 1000, 2),
            "pipeline_ms": round((t2 - frame.timestamp) * 1000, 2)}
    if obs is not None:
        line.update(source=obs.source, score=round(obs.score, 3), handedness=obs.handedness,
                    view=None if obs.view is None else list(obs.view), tip_norm=rnd(obs.tip_norm),
                    tip_cam=rnd(obs.tip), tip_in_view=obs.tip_in_view, mapped=rnd(mapped),
                    landmarks={str(k): rnd(obs.landmarks[k]) for k in TRACE_LANDMARKS})
    if diag is not None:
        line["diag"] = diag.to_json()
    return line


def run(config: Config, args) -> int:
    calibration = load_calibration(config.calibration_dir)
    v = config.validation
    try:
        tracker = HandTracker(args.model, inference_width=args.inference_width, acquisition=args.acquisition)
    except HandTrackingError as e:
        print(f"cannot start hand tracking: {e}")
        return 2
    records, accuracy = [], []
    diagnostics, diag_times, diag_results = LandmarkDiagnostics(), [], []     # D38, observational only
    save_dir = config.reports_dir.parent / "diagnostics" / f"cursor-{stamp()}"
    last_saved = -1e9
    trace = None
    if args.trace:
        save_dir.mkdir(parents=True, exist_ok=True)
        trace = open(save_dir / "trace.jsonl", "w", encoding="utf-8")
    with tracker, open_session(config, args) as s:
        check_compatible(calibration, s.camera_info.size, s.canvas_size)
        mapper = CoordinateMapper.from_calibration(calibration)
        w, h = s.canvas_size
        setup, recovery = None, None
        if not args.no_setup_check:
            limit = setup_limit(config, calibration)
            try:
                setup, corner_m = auto_setup_check(CameraMeasure(s, title="SETUP CHECK before tracking"),
                                                   calibration, s.canvas_size, limit)
            except AutoCalibrationError as e:
                print(f"setup check failed, corners not detected: {e}")
                for hint in explain([str(e), *e.details]):
                    print(f"  hint: {hint}")
                return 1
            print(f"setup check: variation {setup.variation:.2f} px (limit {limit:g}): "
                  f"{'unchanged' if setup.consistent else 'MOVED'}")
            if not setup.consistent:
                if args.no_recalibrate:
                    print("The setup has moved since the calibration; the cursor would be wrong. Run `recalibrate` "
                          "(automatic, validated) or `calibrate` first.")
                    return 1
                # D39: replace the calibration only with a validated, confirmed one, then use it
                result, recovery_report = recover_in_session(config, s, calibration, setup, corner_m,
                                                             CameraMeasure(s, title=RECOVERY_TITLE))
                recovery = {"status": result.status, "stage": result.stage, "report": str(recovery_report),
                            "previous_calibration_created_at": calibration.created_at,
                            "refused_variation_px": setup.variation}
                if not result.accepted:
                    print("The cursor does not start with a calibration the setup check refused.")
                    return 1
                calibration, setup = result.candidate, result.confirmation
                mapper = CoordinateMapper.from_calibration(calibration)

        targets = None
        if args.accuracy or args.targets:
            try:
                targets = parse_targets(args.targets, (w, h)) if args.targets else _accuracy_targets(w, h, v.grid_inset)
            except ValueError as e:
                print(f"--targets: {e}")
                return 2
        labels = args.labels.split() if args.labels else None
        if labels is not None and (targets is None or len(labels) != len(targets)):
            print(f"--labels: need one label per target ({0 if targets is None else len(targets)})")
            return 2

        # Brightness pre-check (D34): with the canvas shown, can the camera see anything there?
        s.projector.show(_canvas((w, h), args.background))
        _, check_frames = capture_frames(s, 5)
        region = canvas_mask(mapper, s.camera_info.size)
        still = np.median(np.stack(check_frames), axis=0).astype(np.uint8)
        scene_luma = region_luma(still, region)
        grey_still = still if still.ndim == 2 else cv2.cvtColor(still, cv2.COLOR_BGR2GRAY)
        # Unlit surface level, for the shadow check (D35): the surround of the projection.
        black_luma = float(np.median(grey_still[~region])) if (~region).sum() > 1000 else 16.0
        too_dark = scene_luma < DARK_REGION_LUMA
        print(f"canvas region brightness {scene_luma:.0f} at grey {args.background}, unlit surround {black_luma:.0f}"
              + (f"  WARNING: too dark (< {DARK_REGION_LUMA:g}): a hand there is nearly invisible to the camera; "
                 "raise --background (80-200 worked, D34) or add room light" if too_dark else ""))
        if targets is not None:
            print(f"accuracy test, {len(targets)} targets. Instruction ({args.aim}): {AIMS[args.aim]}")
        cursor = CursorTracker((w, h), hold_s=args.hold_ms / 1000.0,
                               smoothing=OneEuroFilter() if args.smoothing else None)
        target_i, target_start, samples, result_shown_until = 0, None, [], 0.0
        stats, window, last_seen = None, [], -1e9
        s.camera.reset_stats()
        start = time.perf_counter()
        seq = current_seq(s)
        while True:
            frame = s.camera.wait_frame(seq, 2.0)
            if frame is None:
                print("camera stopped delivering frames")
                break
            seq = frame.seq
            t0 = time.perf_counter()
            obs = tracker.process(frame.image, frame.timestamp)
            t1 = time.perf_counter()
            if obs is not None:
                last_seen = frame.timestamp
            mapped = mapper.camera_to_projector([obs.tip])[0] if obs is not None else None
            # D37: a fingertip outside the image MediaPipe saw was extrapolated, not seen: never drawn as one
            tip_valid = obs is not None and obs.tip_in_view
            u = cursor.update(frame.timestamp, mapped if tip_valid else None)
            # D38: diagnostics only - computed after the cursor update and never read back into it
            landmark_diag = diagnostics.update(frame.seq, None if obs is None else obs.landmarks,
                                               reacquired=obs is not None and obs.source in SEARCH_SOURCES)
            diag_times.append(frame.timestamp - start)
            diag_results.append(landmark_diag)

            canvas = _canvas((w, h), args.background)
            now = time.perf_counter()
            if targets is not None and target_i < len(targets):
                t = targets[target_i]
                if target_start is None:
                    target_start, stats = now, TargetStats(frame.timestamp)
                # Armed only after the pause: no samples are collected before, so a repeated target at the
                # same position cannot be captured from the previous hold (2026-10-10 sweep bug). With
                # --withdraw the hand must also have been out of view (a fresh acquisition, D36).
                if stats.armed_at is None and now >= result_shown_until and (
                        not args.withdraw or frame.timestamp - last_seen >= WITHDRAW_S):
                    stats.armed_at = frame.timestamp
                armed = stats.armed_at is not None
                stats.add(frame.timestamp, obs)
                label = labels[target_i] if labels else None
                if not armed and args.withdraw and now >= result_shown_until:
                    label = "hand away"
                patterns.draw_target(canvas, t, active=armed, label=label)
                if armed and u.raw is not None and np.hypot(*(np.subtract(u.raw, t))) <= CAPTURE_DISTANCE_PX:
                    samples.append((frame.timestamp, u.raw))
                    cv2.circle(canvas, (int(t[0]), int(t[1])), 46, patterns.GREEN, 3)     # on target: hold still
                    if obs is not None and len(samples) % SHADOW_SAMPLE_EVERY == 1:     # capture frames
                        window.append((frame.timestamp, frame.image, obs.landmarks))
                        window = [f for f in window if f[0] >= frame.timestamp - DWELL_S - 0.2][-8:]   # bounded
                else:
                    samples.clear()
                    window.clear()
                held = dwell(samples, DWELL_S, DWELL_RADIUS_PX) if armed else None
                timed_out = now - target_start > TARGET_TIMEOUT_S
                if held is not None or timed_out:
                    entry = {"target": t.tolist(), "measured": held is not None, **stats.summary(frame.timestamp)}
                    tag = f"  target {target_i + 1}/{len(targets)} {t.tolist()}"
                    target_status = (f"hand found {100 * entry['hand_found_fraction']:.0f} %, first detection "
                            + ("none" if entry["first_detection_s"] is None else f"{entry['first_detection_s']:.1f} s")
                            + (f", score {entry['handedness_score_median']:.2f}"
                               if entry["handedness_score_median"] is not None else ""))
                    if held is not None:
                        err = np.subtract(held.mean, t)
                        entry.update(mean=list(held.mean), error_px=float(np.hypot(*err)), error_xy=err.tolist(),
                                     sd_px=held.sd, spread_px=held.spread, samples=held.samples)
                        in_window = [f for f in window if f[0] >= frame.timestamp - DWELL_S]
                        rows, note, tips = [], "", []
                        if args.aim == "shadow":      # D36: the reference is the fingertip's shadow centre
                            entry["shadow_centre"], tips = shadow_alignment(in_window, t, mapper, region,
                                                                            black_luma, scene_luma)
                            sc = entry["shadow_centre"]
                            note = (f" | vs SHADOW CENTRE {sc['error_px']:.2f} px ({sc['error_xy'][0]:+.1f}, "
                                    f"{sc['error_xy'][1]:+.1f}), shadow-target ({sc['centre_minus_target'][0]:+.1f}, "
                                    f"{sc['centre_minus_target'][1]:+.1f})" if sc["established"]
                                    else f" | shadow centre NOT established: {sc['reason']}")
                        if args.shadow_check:        # experimental, unreliable on the 2026-10-10 hardware (D35)
                            entry["shadow"], rows = shadow_check(in_window, mapper, region, black_luma, scene_luma, t)
                            sh = entry["shadow"]
                            note += " | shadow (experimental) " + (
                                f"in {sh['frames_with_shadow']}/{sh['frames_checked']} frames: parallax "
                                f"{sh['parallax_magnitude_px']:.1f} px" if rows else "not found")
                        print(f"{tag}: error {entry['error_px']:.2f} px ({err[0]:+.1f}, {err[1]:+.1f}), "
                              f"sd {held.sd:.2f} | {target_status}{note}")
                        if in_window:
                            save_dir.mkdir(parents=True, exist_ok=True)
                            _save_capture(save_dir / f"capture_target{target_i + 1}.jpg", in_window[-1], rows,
                                          mapper.projector_to_camera([t])[0], tips[-1] if tips else None)
                    else:
                        print(f"{tag}: no steady fingertip in {TARGET_TIMEOUT_S:.0f} s, skipped | {target_status}")
                    accuracy.append(entry)
                    target_i, target_start, samples, result_shown_until = target_i + 1, None, [], now + args.pause
                    window = []
            if u.position is not None:
                _draw_cursor(canvas, u.position, u.status)
            s.projector.show(canvas)
            cv2.pollKey()
            t2 = time.perf_counter()
            records.append({"t": frame.timestamp - start, "queue_ms": (t0 - frame.timestamp) * 1000,
                            "inference_ms": (t1 - t0) * 1000, "pipeline_ms": (t2 - frame.timestamp) * 1000,
                            "hand": obs is not None, "status": u.status,
                            "raw": None if u.raw is None else list(u.raw), "score": obs.score if obs else None,
                            "source": obs.source if obs else None,
                            "target": target_i if targets is not None and target_i < len(targets) else None,
                            "position": None if u.position is None else list(u.position), "reason": u.reason,
                            "tip_valid": tip_valid})
            if trace is not None:
                trace.write(json.dumps(_trace_line(frame, start, t0, t1, t2, tracker.action, obs, mapped, u, landmark_diag)) + "\n")
            if args.save_every and frame.timestamp - last_saved >= args.save_every:
                last_saved = frame.timestamp
                save_dir.mkdir(parents=True, exist_ok=True)
                name = f"t{frame.timestamp - start:06.1f}_{u.status}" + (
                    f"_target{target_i + 1}" if targets is not None and target_i < len(targets) else "")
                cv2.imwrite(str(save_dir / f"{name}.jpg"), frame.image, [cv2.IMWRITE_JPEG_QUALITY, 90])

            if len(records) % 2 == 0:
                view = frame.image.copy()
                if obs is not None:
                    pts = np.round(obs.landmarks).astype(int)
                    for a, b in BONES:
                        cv2.line(view, tuple(pts[a]), tuple(pts[b]), patterns.GREEN, 2, cv2.LINE_AA)
                    patterns.draw_crosshair(view, obs.tip, patterns.CYAN, gap=4, arm=18, thickness=2)
                recent = records[-60:]
                fps = (len(recent) - 1) / max(recent[-1]["t"] - recent[0]["t"], 1e-6) if len(recent) > 1 else 0.0
                lines = ["FINGERTIP CURSOR (Phase 1D)", f"status: {u.status}",
                         f"processing {fps:.1f} fps, inference {np.median([r['inference_ms'] for r in recent]):.1f} ms",
                         f"capture -> projector {np.median([r['pipeline_ms'] for r in recent]):.0f} ms (+ display path)",
                         f"hand in {100 * np.mean([r['hand'] for r in recent]):.0f} % of recent frames",
                         f"tracking losses {cursor.losses}"]
                if targets is not None:
                    lines.append(f"accuracy target {min(target_i + 1, len(targets))} / {len(targets)} ({args.aim}):")
                    lines.append(AIMS[args.aim])
                lines += ["", "ESC: quit"]
                s.operator.show(view, lines=lines)
            key = cv2.waitKey(1)
            elapsed = time.perf_counter() - start
            if key == 27 or (args.seconds and elapsed >= args.seconds) or (targets is not None and target_i >= len(targets)):
                break
        if trace is not None:
            trace.close()
        camera_stats = s.camera.stats()
        exposure_end = s.camera.read_exposure()
        s.projector.show(_canvas((w, h), 0))

    if not records:
        return 1
    duration = records[-1]["t"] - records[0]["t"]
    statuses = [r["status"] for r in records]
    lost_runs, run_len = [], 0
    for st in statuses + [TRACKING]:
        if st in (LOST, HOLDING):
            run_len += 1
        elif run_len:
            lost_runs.append(run_len)
            run_len = 0
    report = {
        "created_at": now_iso(), "calibration_created_at": calibration.created_at,
        "calibration_method": calibration.method,
        "setup_check": None if setup is None else {"variation_px": setup.variation, "limit_px": setup.limit},
        "calibration_recovery": recovery,
        "scene_check": {"canvas_region_luma": scene_luma, "too_dark": too_dark, "limit": DARK_REGION_LUMA,
                        "unlit_surround_luma": black_luma},
        "options": {"background": args.background, "smoothing": args.smoothing, "hold_ms": args.hold_ms,
                    "inference_width": args.inference_width, "accuracy": args.accuracy,
                    "save_every_s": args.save_every, "aim": args.aim, "targets": args.targets,
                    "labels": args.labels, "pause_s": args.pause, "shadow_check": args.shadow_check,
                    "acquisition": args.acquisition, "withdraw": args.withdraw, "trace": args.trace,
                    "smoothing_params": None if cursor.smoothing is None else {
                        "min_cutoff_hz": cursor.smoothing.min_cutoff, "beta": cursor.smoothing.beta,
                        "d_cutoff_hz": cursor.smoothing.d_cutoff}},
        "acquisition_stats": {**{k: v for k, v in dataclasses.asdict(tracker.stats).items() if k != "search_ms"},
                              "search_ms": _percentiles(tracker.stats.search_ms)},
        "instruction": AIMS[args.aim] if targets is not None else None,
        "frames_dir": str(save_dir) if save_dir.is_dir() else None,
        "frames": len(records), "duration_s": duration,
        "processing_fps": (len(records) - 1) / duration if duration > 0 else 0.0,
        "camera": {"fps": camera_stats.mean_fps, "read_failures": camera_stats.read_failures,
                   "exposure_end": None if exposure_end is None else exposure_end.describe()},
        "inference_ms": _percentiles([r["inference_ms"] for r in records]),
        "queue_ms": _percentiles([r["queue_ms"] for r in records]),
        "pipeline_ms": _percentiles([r["pipeline_ms"] for r in records]),
        "hand_frames_fraction": float(np.mean([r["hand"] for r in records])),
        "status_fractions": {st: statuses.count(st) / len(statuses) for st in (TRACKING, HOLDING, LOST, OUTSIDE)},
        "tracking_losses": cursor.losses,
        "dropout_frames": _percentiles(lost_runs),
        "transitions": dict(cursor.transitions),
        "reacquired_after_s": _percentiles(cursor.reacquired_after_s),
        "tip_outside_view_frames": sum(1 for r in records if r["hand"] and not r["tip_valid"]),
        "motion": motion_summary(records),
        "landmark_diagnostics": landmark_summary(diag_times, diag_results),
        "trace_file": str(save_dir / "trace.jsonl") if args.trace else None,
        "accuracy": accuracy,
        "records": records,
    }
    measured = [a for a in accuracy if a["measured"]]
    provisional = None
    if measured:
        err = np.array([a["error_px"] for a in measured])
        err_stats = accuracy_stats(err)
        centre = np.array([w - 1, h - 1]) / 2
        is_centre = [np.allclose(a["target"], np.round(centre)) for a in measured]
        report["accuracy_stats_px"] = dataclasses.asdict(err_stats)
        report["accuracy_edge_mean_px"] = float(err[~np.array(is_centre)].mean()) if not all(is_centre) else None
        report["stability_sd_px"] = _percentiles([a["sd_px"] for a in measured])
        parallax = [a["shadow"]["parallax_magnitude_px"] for a in measured
                    if "parallax_magnitude_px" in (a.get("shadow") or {})]
        report["shadow_parallax_px"] = _percentiles(parallax) if args.shadow_check else None
        report["rows_columns_vs_target_px"] = rows_and_columns(measured, lambda e: e["error_px"])
        if args.aim == "shadow":
            sc_entries = [a for a in measured if a.get("shadow_centre", {}).get("established")]
            not_established = [i + 1 for i, a in enumerate(accuracy)
                               if not (a["measured"] and a.get("shadow_centre", {}).get("established"))]
            report["shadow_centre_established"] = f"{len(sc_entries)}/{len(accuracy)}"
            report["rows_columns_vs_shadow_centre_px"] = rows_and_columns(
                measured, lambda e: e["shadow_centre"]["error_px"] if e.get("shadow_centre", {}).get("established")
                else None)
            if sc_entries:
                sc_err = np.array([a["shadow_centre"]["error_px"] for a in sc_entries])
                report["accuracy_vs_shadow_centre_px"] = dataclasses.asdict(accuracy_stats(sc_err))
            # D36: a run counts only if every target's shadow centre was established reliably
            report["run_valid"] = not not_established
            report["invalid_reason"] = (None if not not_established else
                                        f"shadow centre not established at target(s) {not_established}")
        if not args.targets:      # the provisional criteria are defined for the standard 9-target test only
            if args.aim == "shadow":
                st = report.get("accuracy_vs_shadow_centre_px")
                valid = report["run_valid"]
                provisional = {"mean_limit_px": PROVISIONAL_MEAN_PX, "max_limit_px": PROVISIONAL_MAX_PX,
                               "reference": "shadow centre", "run_valid": valid,
                               "mean_met": bool(valid and st and st["mean"] <= PROVISIONAL_MEAN_PX),
                               "max_met": bool(valid and st and st["max"] <= PROVISIONAL_MAX_PX),
                               "all_targets_measured": len(measured) == len(accuracy),
                               "status": "provisional, not validated"}
            else:
                provisional = {"mean_limit_px": PROVISIONAL_MEAN_PX, "max_limit_px": PROVISIONAL_MAX_PX,
                               "reference": "target (fingertip aim, viewpoint-dependent)",
                               "all_targets_measured": len(measured) == len(accuracy),
                               "mean_met": err_stats.mean <= PROVISIONAL_MEAN_PX,
                               "max_met": err_stats.max <= PROVISIONAL_MAX_PX, "status": "provisional, not validated"}
    report["provisional_criteria"] = provisional
    path = save_report(config, "cursor", report)

    print(f"frames {len(records)} over {duration:.1f} s: processing {report['processing_fps']:.1f} fps "
          f"(camera {camera_stats.mean_fps:.1f} fps, failed reads {camera_stats.read_failures})")
    for key in ("inference_ms", "queue_ms", "pipeline_ms"):
        st = report[key]
        print(f"{key:>13}: median {st['median']:.1f}, p95 {st['p95']:.1f}, max {st['max']:.1f}")
    print(f"hand found in {100 * report['hand_frames_fraction']:.1f} % of frames; status " +
          ", ".join(f"{k} {100 * f:.1f} %" for k, f in report["status_fractions"].items()) +
          f"; tracking losses {cursor.losses}")
    if measured:
        st = report["accuracy_stats_px"]
        print(f"accuracy ({len(measured)}/{len(accuracy)} targets, aim {args.aim}): mean {st['mean']:.2f}, "
              f"max {st['max']:.2f} projector px; stability sd median {report['stability_sd_px']['median']:.2f} px")
        if report["shadow_parallax_px"]:
            sp = report["shadow_parallax_px"]
            print(f"shadow parallax (EXPERIMENTAL; cursor vs projector ray through the fingertip) on {sp['n']} "
                  f"targets: median {sp['median']:.1f}, max {sp['max']:.1f} projector px")
        if "run_valid" in report:
            stc = report.get("accuracy_vs_shadow_centre_px")
            print(f"vs shadow centre: established {report['shadow_centre_established']}"
                  + (f", mean {stc['mean']:.2f}, max {stc['max']:.2f} projector px" if stc else "")
                  + ("" if report["run_valid"] else f"  ->  RUN INVALID: {report['invalid_reason']}"))
            for name, v in report["rows_columns_vs_shadow_centre_px"].items():
                if v["n"]:
                    print(f"    {name:>7}: mean {v['mean']:.2f}, max {v['max']:.2f} (n {v['n']})")
        if provisional:
            yes = lambda ok: "met" if ok else "NOT met"      # noqa: E731
            print(f"PROVISIONAL criteria (D35, not validated; reference {provisional['reference']}): mean <= "
                  f"{PROVISIONAL_MEAN_PX:g}: {yes(provisional['mean_met'])}; max <= {PROVISIONAL_MAX_PX:g}: "
                  f"{yes(provisional['max_met'])}; all targets measured: {yes(provisional['all_targets_measured'])}"
                  + ("" if provisional.get("run_valid", True) else "  (run INVALID)"))
    a = report["acquisition_stats"]
    print(f"acquisition ({args.acquisition}): {a['acquisitions']} in {a['search_frames']} search frames"
          + (f" (search {a['search_ms']['median']:.0f} ms median)" if a["search_ms"] else "")
          + f", unconfirmed {a['unconfirmed']}, track losses {a['track_losses']}, region losses {a['region_losses']}"
          + f", fingertip outside the view {a['tip_outside_view']}")
    m, ra = report["motion"], report["reacquired_after_s"]
    print("motion: lag behind the raw fingertip " + (f"median {m['lag_px']['median']:.1f} px" if m["lag_px"] else "n/a")
          + "; still jitter " + (f"{m['still_jitter_rms_px']:.2f} px rms" if m["still_jitter_rms_px"] is not None
                                 else "n/a")
          + f"; transient jumps {m['spikes']}"
          + "; reacquired after " + (f"median {ra['median']:.2f} s, max {ra['max']:.2f} s (n {ra['n']})" if ra
                                     else "n/a"))
    ld = report["landmark_diagnostics"]
    print(f"landmark diagnostics (observational only, D38): {ld['suspicious_frames']} suspicious frames in "
          f"{len(ld['episodes'])} episodes (relative motion {ld['motion_flagged']}, low extension {ld['extension_flagged']})")
    if args.trace:
        print(f"trace: {report['trace_file']}")
    print(f"report: {path}")
    return 0
