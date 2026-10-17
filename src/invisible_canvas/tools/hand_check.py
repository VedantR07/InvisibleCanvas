"""`handcheck` (Phase 1D diagnostic, brain.md D34): why is (or isn't) a hand detected?

Read-only: never touches the calibration; uses the normal camera session. For each projected
canvas brightness it runs the HandTracker exactly as `cursor` does and saves a few camera frames,
the exact image MediaPipe receives, and per-frame metadata (sizes, dtype, channel order,
letterbox, brightness of the canvas region, detection, hand size). It separates:
  - pipeline problems     -> run it on a known hand photo: `--image FILE` (positive control)
  - a scene too dark      -> canvas-region brightness near the camera's black level
  - a hand too small      -> hand length (wrist -> middle fingertip) below ~140 camera px
  - no hand in view       -> visible scene, nothing found, operator confirms no hand was shown
Output: data/diagnostics/handcheck-<stamp>/ (PNG frames) and data/reports/handcheck-<stamp>.json.
"""

from __future__ import annotations

import time
from pathlib import Path

import cv2
import numpy as np

from ..calibration.store import CalibrationError, check_compatible, load_calibration
from ..config import Config
from ..display import patterns
from ..mapping.mapper import CoordinateMapper
from ..vision.hands import HandTracker, HandTrackingError
from .common import add_device_args, current_seq, now_iso, open_session, save_report, stamp

# From the positive control with the official MediaPipe sample image through this pipeline (D34):
# detected down to a hand length of 140 camera px and a hand mean luma of 16; missed at 120 px / 10.
MIN_HAND_LENGTH_PX = 140.0
DARK_REGION_LUMA = 25.0     # canvas-region median this low: the camera sees almost nothing (black level ~16)
# Measured 2026-10-10 (D34), exposure -5, dark room: canvas grey 40 -> region 23, hand detected 0 %;
# grey 80 -> 66, grey 128 -> 142, grey 200 -> 226: hand detected 100 % at each.


def canvas_mask(mapper, camera_size: tuple[int, int]) -> np.ndarray:
    """Boolean camera-image mask of the projected canvas (from the calibration)."""
    mask = np.zeros((camera_size[1], camera_size[0]), np.uint8)
    cv2.fillPoly(mask, [np.round(mapper.canvas_outline_in_camera()).astype(np.int32)], 255)
    return mask > 0


def region_luma(frame_bgr_or_grey: np.ndarray, mask: np.ndarray) -> float:
    """Median brightness of the canvas region of a camera frame."""
    grey = frame_bgr_or_grey if frame_bgr_or_grey.ndim == 2 else cv2.cvtColor(frame_bgr_or_grey, cv2.COLOR_BGR2GRAY)
    return float(np.median(grey[mask]))


def add_parser(subparsers) -> None:
    p = subparsers.add_parser("handcheck", help="diagnostic: why a hand is or is not detected (read-only, D34)")
    add_device_args(p)
    p.add_argument("--backgrounds", default="40 128 255",
                   help='canvas grey levels to test, e.g. "40 128 255" (default)')
    p.add_argument("--frames", type=int, default=45, help="frames per level (default 45, ~1.5 s)")
    p.add_argument("--save", type=int, default=4, help="frames saved per level (default 4)")
    p.add_argument("--inference-width", type=int, default=960)
    p.add_argument("--image", nargs="+", help="analyse image file(s) instead of the camera (positive control)")
    p.set_defaults(func=run)


def diagnose(rate: float, region_luma: float | None, lengths: list[float]) -> str:
    """One-line reading of a level's results."""
    if rate > 0:
        small = [x for x in lengths if x < MIN_HAND_LENGTH_PX]
        note = f"; {len(small)} detections smaller than {MIN_HAND_LENGTH_PX:.0f} px (marginal)" if small else ""
        return f"hand detected in {100 * rate:.0f} % of frames, median length {np.median(lengths):.0f} camera px{note}"
    if region_luma is not None and region_luma < DARK_REGION_LUMA:
        return (f"no hand detected; TOO DARK: the canvas region reads {region_luma:.0f} (black level ~16), "
                "a hand there is nearly black to the camera")
    return ("no hand detected in a visible scene: no hand in view, the hand smaller than "
            f"~{MIN_HAND_LENGTH_PX:.0f} camera px (wrist to middle fingertip), or occluded")


def _frame_meta(frame, rgb, box, obs, region_mask, mapper) -> dict:
    grey = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    meta = {
        "camera_frame": {"shape": list(frame.shape), "dtype": str(frame.dtype), "channels": "BGR"},
        "mediapipe_input": {"shape": list(rgb.shape), "dtype": str(rgb.dtype), "channels": "RGB",
                            "contiguous": bool(rgb.flags["C_CONTIGUOUS"]), "image_format": "SRGB"},
        "letterbox": {"side": box.side, "pad_x": box.pad_x, "pad_y": box.pad_y,
                      "scale_x": box.scale_x, "scale_y": box.scale_y},
        "frame_luma_mean": float(grey.mean()),
        "found": obs is not None,
    }
    if region_mask is not None:
        vals = grey[region_mask]
        meta["canvas_region_luma"] = {"median": float(np.median(vals)), "p10": float(np.percentile(vals, 10)),
                                      "p90": float(np.percentile(vals, 90))}
    if obs is not None:
        meta.update(score=obs.score, handedness=obs.handedness, tip_camera=list(obs.tip),
                    hand_length_px=obs.length_px)
        if mapper is not None:
            meta["tip_projector"] = mapper.camera_to_projector([obs.tip])[0].tolist()
        xs, ys = obs.landmarks[:, 0], obs.landmarks[:, 1]
        meta["hand_bbox_camera"] = [float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max())]
    return meta


def _save(folder: Path, name: str, frame, rgb, obs) -> None:
    view = frame.copy()
    if obs is not None:
        for p in np.round(obs.landmarks).astype(int):
            cv2.circle(view, tuple(p), 4, patterns.GREEN, -1)
    cv2.imwrite(str(folder / f"{name}_camera.png"), view)
    cv2.imwrite(str(folder / f"{name}_mediapipe_input.png"), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))


def run(config: Config, args) -> int:
    folder = config.reports_dir.parent / "diagnostics" / f"handcheck-{stamp()}"
    folder.mkdir(parents=True, exist_ok=True)
    levels_out = []
    try:
        make = lambda: HandTracker(inference_width=args.inference_width)     # noqa: E731
        make().close()
    except HandTrackingError as e:
        print(f"MODEL/PACKAGE PROBLEM, not a scene problem: {e}")
        return 2

    if args.image:
        for k, path in enumerate(args.image):
            frame = cv2.imread(path)
            if frame is None:
                print(f"{path}: not a readable image")
                continue
            with make() as tracker:
                rgb, box = tracker.prepare(frame)
                obs = None
                for i in range(4):                              # a still image as a few video frames
                    obs = tracker.process(frame, i / 30) or obs
            meta = _frame_meta(frame, rgb, box, obs, None, None)
            _save(folder, f"image{k}", frame, rgb, obs)
            print(f"{path}: found={obs is not None}" + (f", score {obs.score:.2f}, hand length {obs.length_px:.0f} px"
                                                       if obs else ""))
            levels_out.append({"image": path, **meta})
        save_report(config, "handcheck", {"created_at": now_iso(), "mode": "image", "results": levels_out,
                                          "frames_dir": str(folder)})
        return 0 if all(r["found"] for r in levels_out) else 1

    try:
        calibration = load_calibration(config.calibration_dir)
    except CalibrationError:
        calibration = None
    with open_session(config, args) as s:
        mapper = region = None
        if calibration is not None:
            try:
                check_compatible(calibration, s.camera_info.size, s.canvas_size)
                mapper = CoordinateMapper.from_calibration(calibration)
                region = canvas_mask(mapper, s.camera_info.size)
            except CalibrationError:
                mapper = None
        for level in (int(x) for x in args.backgrounds.split()):
            s.projector.show(patterns.blank(s.canvas_size, max(0, min(255, level))))
            end = time.perf_counter() + 0.8
            while time.perf_counter() < end:
                cv2.waitKey(5)
            frames_meta, lengths, found = [], [], 0
            save_every = max(1, args.frames // max(args.save, 1))
            seq = current_seq(s)
            with make() as tracker:
                for i in range(args.frames):
                    frame = s.camera.wait_frame(seq, 2.0)
                    seq = frame.seq
                    rgb, box = tracker.prepare(frame.image)
                    obs = tracker.process(frame.image, frame.timestamp)
                    meta = {"index": i, "t": frame.timestamp,
                            **_frame_meta(frame.image, rgb, box, obs, region, mapper)}
                    if obs is not None:
                        found += 1
                        lengths.append(obs.length_px)
                    if i % save_every == 0 and len([m for m in frames_meta if m.get("saved")]) < args.save:
                        _save(folder, f"bg{level:03d}_f{i:03d}", frame.image, rgb, obs)
                        meta["saved"] = True
                    frames_meta.append(meta)
                    s.operator.show(frame.image, lines=["HAND CHECK (diagnostic)", f"canvas grey {level}",
                                                        f"frame {i + 1}/{args.frames}", f"found {found}"])
                    cv2.pollKey()
            luma = [m["canvas_region_luma"]["median"] for m in frames_meta if "canvas_region_luma" in m]
            region_luma = float(np.median(luma)) if luma else None
            rate = found / len(frames_meta)
            verdict = diagnose(rate, region_luma, lengths)
            levels_out.append({"background": level, "frames": len(frames_meta), "detection_rate": rate,
                               "canvas_region_luma_median": region_luma,
                               "hand_length_px_median": float(np.median(lengths)) if lengths else None,
                               "verdict": verdict, "frames_meta": frames_meta})
            print(f"canvas grey {level:3d}: canvas-region luma {region_luma if region_luma is None else round(region_luma, 1)}"
                  f" | {verdict}")
        s.projector.show(patterns.blank(s.canvas_size, 0))
    path = save_report(config, "handcheck", {"created_at": now_iso(), "mode": "camera",
                                             "calibration_created_at": calibration.created_at if calibration else None,
                                             "levels": levels_out, "frames_dir": str(folder)})
    print(f"frames: {folder}")
    print(f"report: {path}")
    return 0
