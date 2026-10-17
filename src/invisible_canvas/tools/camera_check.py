"""`camera`: live camera check and sustained-fps measurement (brain.md A3/A4).

Shows the live feed with the negotiated mode, measured fps, frame age and the share
of saturated pixels. `--seconds 60` measures sustained fps and writes a report.

Setup aid (temporary, display only): `f` or `--preview` shows the whole camera frame
fullscreen on the laptop screen (1:1 for 1920x1080), `b` brightens that preview so the
edges of the projected rectangle are visible against the unlit wall. Neither changes
the camera, the captured frames or the measurements.
"""

from __future__ import annotations

import dataclasses
import time

import cv2
import numpy as np

from ..camera.manager import CameraManager, per_second_fps
from ..config import Config
from ..display import patterns
from ..display.operator import OperatorWindow
from .common import exposure_text, now_iso, primary_display, save_report

SATURATION_LEVEL = 250

PREVIEW = "Invisible Canvas - Camera preview (setup)"
# Display-only gamma 0.4: the unlit wall and the projector's black become distinguishable.
BRIGHTEN = np.array([round(255 * (i / 255) ** 0.4) for i in range(256)], dtype=np.uint8)


def add_parser(subparsers) -> None:
    p = subparsers.add_parser("camera", help="live camera feed, fps and saturation check (A3)")
    p.add_argument("--camera", help="camera override: part of the DirectShow name")
    p.add_argument("--seconds", type=float, default=0.0,
                   help="measure for N seconds (e.g. 60), then report and exit")
    p.add_argument("--headless", action="store_true", help="no window (measurement only)")
    p.add_argument("--preview", action="store_true",
                   help="start with the large setup preview open (same as pressing f)")
    p.set_defaults(func=run)


def preview_image(view: np.ndarray, screen_size: tuple[int, int] | None, brighten: bool) -> tuple[np.ndarray, float]:
    """The whole frame fitted to the screen (letterboxed, never stretched) and the scale used.
    Returns a new image; `view` is not modified."""
    image = cv2.LUT(view, BRIGHTEN) if brighten else view.copy()
    if screen_size is None:
        return image, 1.0
    sw, sh = screen_size
    fh, fw = image.shape[:2]
    scale = min(sw / fw, sh / fh)
    w, h = round(fw * scale), round(fh * scale)
    if (w, h) != (fw, fh):
        image = cv2.resize(image, (w, h), interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
    canvas = np.zeros((sh, sw, 3), dtype=np.uint8)
    x0, y0 = (sw - w) // 2, (sh - h) // 2
    canvas[y0:y0 + h, x0:x0 + w] = image
    return canvas, scale


class SetupPreview:
    """Temporary setup aid: fullscreen camera view on the laptop screen for aiming the camera."""

    def __init__(self, screen):
        self.screen = screen
        self.brighten = False
        self.is_open = False

    def toggle(self) -> None:
        if self.is_open:
            self.close()
            return
        cv2.namedWindow(PREVIEW, cv2.WINDOW_NORMAL)
        if self.screen is not None:
            cv2.moveWindow(PREVIEW, self.screen.x, self.screen.y)
        cv2.setWindowProperty(PREVIEW, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        self.is_open = True

    def close(self) -> None:
        if self.is_open:
            try:
                cv2.destroyWindow(PREVIEW)
            except cv2.error:
                pass
        self.is_open = False

    def show(self, view: np.ndarray, status: str) -> None:
        size = (self.screen.width, self.screen.height) if self.screen is not None else None
        canvas, scale = preview_image(view, size, self.brighten)
        message = (f"SETUP PREVIEW (display only) {view.shape[1]}x{view.shape[0]} at {scale:.0%} | "
                   f"b: brighten {'ON' if self.brighten else 'off'} | f: close | ESC: quit | {status}")
        (tw, th), _ = cv2.getTextSize(message, patterns.FONT, 0.6, 1)
        cv2.rectangle(canvas, (0, 0), (tw + 20, th + 18), (0, 0, 0), -1)
        patterns.text(canvas, message, (10, th + 9), patterns.YELLOW, 0.6)
        cv2.imshow(PREVIEW, canvas)


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
    print(f"  exposure: {exposure_text(info)}")
    operator = None
    preview = None
    if not args.headless:
        screen = primary_display()
        operator = OperatorWindow(info.size, screen)
        operator.open()
        preview = SetupPreview(screen)
        if args.preview:
            preview.toggle()
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
                    f"exposure at open: {exposure_text(info)}",
                    f"measured {s.recent_fps:.1f} fps (mean {s.mean_fps:.1f})",
                    f"frame age {np.median(ages[-30:]) * 1000:.1f} ms",
                    f"longest gap {s.max_interval * 1000:.0f} ms, failed reads {s.read_failures}",
                    f"saturated pixels {sat:.2f} %" + (" (red)" if show_saturation else ""),
                    "",
                    "s: driver settings dialog (exposure, focus, white balance)",
                    "p: print properties | z: toggle saturation overlay | ESC: quit",
                    "f: large setup preview | b: brighten preview",
                ]
                if args.seconds:
                    lines.insert(0, f"measuring: {elapsed:.0f} / {args.seconds:.0f} s")
                if camera.error:
                    lines.append("!" + camera.error)
                operator.show(view, raw=frame.image, lines=lines)
                if preview.is_open:
                    preview.show(view, f"{s.recent_fps:.1f} fps")
                key = cv2.waitKey(1)
                if key == 27:
                    break
                if key == ord("s"):
                    camera.open_settings_dialog()
                elif key == ord("p"):
                    print(camera.read_properties())
                elif key == ord("z"):
                    show_saturation = not show_saturation
                elif key == ord("f"):
                    preview.toggle()
                elif key == ord("b"):
                    preview.brighten = not preview.brighten
            if args.seconds and elapsed >= args.seconds:
                break
        stats = camera.stats()
        per_second = per_second_fps(camera.timestamps())
        properties = camera.read_properties()
        exposure_end = camera.read_exposure()
    finally:
        camera.close()
        if preview is not None:
            preview.close()
        if operator is not None:
            operator.close()
        cv2.destroyAllWindows()

    min_window = float(per_second.min()) if len(per_second) else 0.0
    print(f"frames {stats.frames} over {stats.duration:.1f} s: mean {stats.mean_fps:.2f} fps, "
          f"slowest 1-s window {min_window:.0f} frames, longest gap {stats.max_interval * 1000:.0f} ms, "
          f"failed reads {stats.read_failures}")
    print(f"frame age (capture -> consumer) median {np.median(ages) * 1000:.2f} ms")
    if exposure_end is not None:
        print(f"exposure at end: {exposure_end.describe()}; re-applied {stats.exposure_reapplied}x "
              f"after the camera reset it")
    if args.seconds:
        report = {
            "created_at": now_iso(),
            "camera": dataclasses.asdict(info),
            "duration_s": stats.duration,
            "frames": stats.frames,
            "mean_fps": stats.mean_fps,
            "per_second_frames": per_second.tolist(),
            "slowest_second_frames": min_window,
            "max_interval_ms": stats.max_interval * 1000,
            "read_failures": stats.read_failures,
            "frame_age_median_ms": float(np.median(ages) * 1000),
            "exposure_at_end": dataclasses.asdict(exposure_end) if exposure_end is not None else None,
            "exposure_reapplied": stats.exposure_reapplied,
            "properties": properties,
        }
        print(f"report: {save_report(config, 'camera', report)}")
    return 0
