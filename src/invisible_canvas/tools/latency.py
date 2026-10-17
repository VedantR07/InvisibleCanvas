"""`latency`: display -> camera latency (brain.md A3).

The projector flips from black to white; the latency is the time from submitting the
white frame to the first camera frame whose projected area is brighter than halfway
between the black and white levels.

This loop contains every component of the interaction loop except our own processing:
OS compositor, HDMI, projector processing, light, camera exposure/readout, USB and
decoding. Resolution is limited by the camera frame interval; many trials at random
phase give a usable median.

A run is valid only if every trial was detected and the black/white levels measured again
after the trials still straddle the threshold. A miss means the white never reached the
halfway level within 1.5 s (5x the measured latency): the reference levels no longer
describe the scene (lighting, gain or camera aim changed), so the median is not trusted.
"""

from __future__ import annotations

import dataclasses
import random
import time

import cv2
import numpy as np

from ..calibration.store import CalibrationError, check_compatible, load_calibration
from ..config import Config
from ..display import patterns
from ..mapping.mapper import CoordinateMapper
from .common import add_device_args, now_iso, open_session, save_report


def add_parser(subparsers) -> None:
    p = subparsers.add_parser("latency", help="measure display -> camera latency (A3)")
    add_device_args(p)
    p.add_argument("--trials", type=int, default=20, help="number of black->white flashes (default 20)")
    p.set_defaults(func=run)


def _roi_mask(config: Config, session) -> tuple[np.ndarray, str]:
    w, h = session.camera_info.size
    mask = np.zeros((h, w), dtype=np.uint8)
    try:
        calibration = load_calibration(config.calibration_dir)
        check_compatible(calibration, session.camera_info.size, session.canvas_size)
        outline = CoordinateMapper.from_calibration(calibration).canvas_outline_in_camera()
        centre = outline.mean(axis=0)
        inner = centre + 0.8 * (outline - centre)
        cv2.fillPoly(mask, [np.round(inner).astype(np.int32)], 255)
        return mask[::4, ::4] > 0, "projected area from calibration (inner 80 %)"
    except CalibrationError:
        mask[h // 4:3 * h // 4, w // 4:3 * w // 4] = 255
        return mask[::4, ::4] > 0, "central half of the camera frame (no calibration)"


def _level(image: np.ndarray, mask: np.ndarray) -> float:
    return float(image[::4, ::4][mask].mean())


def _pump(seconds: float) -> None:
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        cv2.waitKey(1)


def validity_problems(outcomes: list[float | None], threshold: float, black_end: float, white_end: float,
                      exposure_error: str = "") -> list[str]:
    """Why a run cannot be trusted (empty = valid). `outcomes`: latency per trial, None = missed."""
    problems = []
    missed = [i + 1 for i, r in enumerate(outcomes) if r is None]
    if missed:
        problems.append(f"{len(missed)} of {len(outcomes)} trials missed (trials {', '.join(map(str, missed))}): "
                        f"the white never crossed the threshold within 1.5 s")
    if not black_end < threshold < white_end:
        problems.append(f"levels changed during the run: at the end black {black_end:.1f}, white {white_end:.1f} "
                        f"vs threshold {threshold:.1f} (lighting, gain or camera aim changed)")
    if exposure_error:
        problems.append(f"exposure at the end: {exposure_error}")
    return problems


def run(config: Config, args) -> int:
    with open_session(config, args) as s:
        size = s.canvas_size
        black, white = patterns.blank(size, 0), patterns.blank(size, 255)
        mask, roi = _roi_mask(config, s)
        print(f"brightness measured over: {roi}")

        def steady_level(image) -> float:
            s.projector.show(image)
            _pump(1.0)
            levels, seq, end = [], 0, time.perf_counter() + 0.4
            while time.perf_counter() < end:
                frame = s.camera.wait_frame(seq, 0.5)
                cv2.pollKey()
                if frame is not None:
                    seq = frame.seq
                    levels.append(_level(frame.image, mask))
            return float(np.mean(levels))

        black_level = steady_level(black)
        white_level = steady_level(white)
        threshold = (black_level + white_level) / 2
        print(f"black level {black_level:.1f}, white level {white_level:.1f}, threshold {threshold:.1f}")
        if white_level - black_level < 15:
            print("The camera barely sees the projector change. Point it at the projection and retry.")
            return 1

        outcomes, peaks = [], []   # per trial: latency (None = missed), highest level after white
        for trial in range(args.trials):
            s.projector.show(black)
            deadline = time.perf_counter() + 2.0
            seq = 0
            while time.perf_counter() < deadline:  # wait until the camera sees black
                frame = s.camera.wait_frame(seq, 0.2)
                cv2.pollKey()
                if frame is not None:
                    seq = frame.seq
                    if _level(frame.image, mask) < threshold:
                        break
            _pump(random.uniform(0.25, 0.6))  # random phase relative to camera frames
            seq = s.camera.latest().seq
            s.projector.show(white)
            cv2.pollKey()
            t0 = time.perf_counter()
            result = None
            peak = float("nan")
            while time.perf_counter() - t0 < 1.5:
                frame = s.camera.wait_frame(seq, 0.1)
                cv2.pollKey()
                if frame is None:
                    continue
                seq = frame.seq
                level = _level(frame.image, mask)
                peak = level if np.isnan(peak) else max(peak, level)
                if level > threshold:
                    result = frame.timestamp - t0
                    break
            outcomes.append(result)
            peaks.append(peak)
            s.operator.show(s.camera.latest().image, lines=[
                "LATENCY TEST", f"trial {trial + 1} / {args.trials}",
                f"last: {result * 1000:.0f} ms" if result is not None else f"last: missed (peak {peak:.1f})",
            ])
        black_end = steady_level(black)
        white_end = steady_level(white)
        exposure_end = s.camera.read_exposure()
        stats = s.camera.stats()
        frame_interval = 1.0 / max(stats.mean_fps, 1e-6)

    problems = validity_problems(outcomes, threshold, black_end, white_end,
                                 exposure_end.describe() if exposure_end is not None and not exposure_end.ok else "")
    latencies = [r for r in outcomes if r is not None]
    misses = len(outcomes) - len(latencies)
    print(f"levels after the trials: black {black_end:.1f}, white {white_end:.1f}")
    if not latencies:
        print("no successful trials")
        print("NOT VALID: " + "; ".join(problems))
        return 1
    ms = np.array(latencies) * 1000
    summary = {
        "median_ms": float(np.median(ms)), "p10_ms": float(np.percentile(ms, 10)),
        "p90_ms": float(np.percentile(ms, 90)), "min_ms": float(ms.min()), "max_ms": float(ms.max()),
    }
    print(f"display -> camera latency over {len(ms)} trials ({misses} missed): "
          f"median {summary['median_ms']:.0f} ms, p10 {summary['p10_ms']:.0f}, p90 {summary['p90_ms']:.0f}, "
          f"min {summary['min_ms']:.0f}, max {summary['max_ms']:.0f} "
          f"(camera frame interval {frame_interval * 1000:.1f} ms)")
    report = {
        "created_at": now_iso(), "roi": roi, "black_level": black_level, "white_level": white_level,
        "trials_ms": ms.tolist(), "missed": misses, "frame_interval_ms": frame_interval * 1000, **summary,
        "threshold": threshold, "black_level_end": black_end, "white_level_end": white_end,
        "trials": [{"ms": None if r is None else r * 1000, "peak_level": None if np.isnan(p) else p}
                   for r, p in zip(outcomes, peaks)],
        "exposure_end": dataclasses.asdict(exposure_end) if exposure_end is not None else None,
        "exposure_reapplied": stats.exposure_reapplied,
        "valid": not problems, "problems": problems,
    }
    print("valid: every trial detected, levels held" if not problems else "NOT VALID: " + "; ".join(problems))
    print(f"report: {save_report(config, 'latency', report)}")
    return 0 if not problems else 1
