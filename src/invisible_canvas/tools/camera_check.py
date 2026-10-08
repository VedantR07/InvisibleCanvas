"""`camera`: live camera check and sustained-fps measurement (brain.md A3/A4).

Shows the live feed with the negotiated mode, measured fps, frame age and the share
of saturated pixels. `--seconds 60` measures sustained fps and writes a report.
"""

from __future__ import annotations

import time

import cv2
import numpy as np

from ..camera.manager import CameraManager, per_second_fps
from ..config import Config
from ..display import patterns
from ..display.operator import OperatorWindow
from .common import now_iso, primary_display, save_report

SATURATION_LEVEL = 250


def add_parser(subparsers) -> None:
    p = subparsers.add_parser("camera", help="live camera feed, fps and saturation check (A3)")
    p.add_argument("--camera", help="camera override: part of the DirectShow name")
    p.add_argument("--seconds", type=float, default=0.0,
                   help="measure for N seconds (e.g. 60), then report and exit")
    p.add_argument("--headless", action="store_true", help="no window (measurement only)")
    p.set_defaults(func=run)


def saturation(image: np.ndarray) -> tuple[float, np.ndarray]:
    """Percentage of pixels with any channel >= SATURATION_LEVEL, and that mask (uint8 0/255).
    OpenCV ops: numpy's max over the colour axis took ~30 ms per 1080p frame."""
    b, g, r = cv2.split(image)
    brightest = cv2.max(cv2.max(b, g), r)
    _, mask = cv2.threshold(brightest, SATURATION_LEVEL - 1, 255, cv2.THRESH_BINARY)
    return cv2.countNonZero(mask) * 100.0 / mask.size, mask


def run(config: Config, args) -> int:
    camera = CameraManager(config.camera, allow_mode_mismatch=True)
    info = camera.open()
    print(f"camera: [{info.index}] {info.name}")
    print(f"  requested {info.requested} -> delivered {info.width}x{info.height} "
          f"(driver reports {info.reported_fourcc} {info.reported_fps:g} fps; open {info.open_seconds:.2f} s)")
    operator = None
    if not args.headless:
        operator = OperatorWindow(info.size, primary_display())
        operator.open()
    show_saturation = True
    ages: list[float] = []
    camera.reset_stats()
    start = time.perf_counter()
    seq = 0
    try:
        while True:
            frame = camera.wait_frame(seq, timeout=2.0)
            if frame is None:
                print("no frame for 2 s")
                break
            seq = frame.seq
            ages.append(time.perf_counter() - frame.timestamp)
            elapsed = time.perf_counter() - start
            if operator is not None:
                sat, mask = saturation(frame.image)
                view = frame.image
                if show_saturation and sat > 0:
                    view = frame.image.copy()
                    view[mask > 0] = patterns.RED
                s = camera.stats()
                lines = [
                    f"{info.name}",
                    f"{info.width}x{info.height} (requested {info.requested})",
                    f"driver reports {info.reported_fourcc} {info.reported_fps:g} fps",
                    f"measured {s.recent_fps:.1f} fps (mean {s.mean_fps:.1f})",
                    f"frame age {np.median(ages[-30:]) * 1000:.1f} ms",
                    f"longest gap {s.max_interval * 1000:.0f} ms, failed reads {s.read_failures}",
                    f"saturated pixels {sat:.2f} %" + (" (red)" if show_saturation else ""),
                    "",
                    "s: driver settings dialog (exposure, focus, white balance)",
                    "p: print properties | z: toggle saturation overlay | ESC: quit",
                ]
                if args.seconds:
                    lines.insert(0, f"measuring: {elapsed:.0f} / {args.seconds:.0f} s")
                if camera.error:
                    lines.append("!" + camera.error)
                operator.show(view, raw=frame.image, lines=lines)
                key = cv2.waitKey(1)
                if key == 27:
                    break
                if key == ord("s"):
                    camera.open_settings_dialog()
                elif key == ord("p"):
                    print(camera.read_properties())
                elif key == ord("z"):
                    show_saturation = not show_saturation
            if args.seconds and elapsed >= args.seconds:
                break
        stats = camera.stats()
        per_second = per_second_fps(camera.timestamps())
        properties = camera.read_properties()
    finally:
        camera.close()
        if operator is not None:
            operator.close()
        cv2.destroyAllWindows()

    min_window = float(per_second.min()) if len(per_second) else 0.0
    print(f"frames {stats.frames} over {stats.duration:.1f} s: mean {stats.mean_fps:.2f} fps, "
          f"slowest 1-s window {min_window:.0f} frames, longest gap {stats.max_interval * 1000:.0f} ms, "
          f"failed reads {stats.read_failures}")
    print(f"frame age (capture -> consumer) median {np.median(ages) * 1000:.2f} ms")
    if args.seconds:
        report = {
            "created_at": now_iso(),
            "camera": info.__dict__,
            "duration_s": stats.duration,
            "frames": stats.frames,
            "mean_fps": stats.mean_fps,
            "per_second_frames": per_second.tolist(),
            "slowest_second_frames": min_window,
            "max_interval_ms": stats.max_interval * 1000,
            "read_failures": stats.read_failures,
            "frame_age_median_ms": float(np.median(ages) * 1000),
            "properties": properties,
        }
        print(f"report: {save_report(config, 'camera', report)}")
    return 0
