"""`latency`: display -> camera latency (brain.md A3).

The projector flips from black to white; the latency is the time from submitting the
white frame to the first camera frame whose projected area is brighter than halfway
between the black and white levels.

This loop contains every component of the interaction loop except our own processing:
OS compositor, HDMI, projector processing, light, camera exposure/readout, USB and
decoding. Resolution is limited by the camera frame interval; many trials at random
phase give a usable median.
"""

from __future__ import annotations

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

        latencies, misses = [], 0
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
            while time.perf_counter() - t0 < 1.5:
                frame = s.camera.wait_frame(seq, 0.1)
                cv2.pollKey()
                if frame is None:
                    continue
                seq = frame.seq
                if _level(frame.image, mask) > threshold:
                    result = frame.timestamp - t0
                    break
            if result is None:
                misses += 1
            else:
                latencies.append(result)
            s.operator.show(s.camera.latest().image, lines=[
                "LATENCY TEST", f"trial {trial + 1} / {args.trials}",
                f"last: {result * 1000:.0f} ms" if result is not None else "last: missed",
            ])
        frame_interval = 1.0 / max(s.camera.stats().mean_fps, 1e-6)

    if not latencies:
        print("no successful trials")
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
    }
    print(f"report: {save_report(config, 'latency', report)}")
    return 0
