"""Helpers shared by the command-line tools."""

from __future__ import annotations

import contextlib
import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from ..calibration.auto import TargetMeasurement, measurement_from_frames
from ..camera.manager import CameraInfo, CameraManager
from ..config import Config
from ..display import patterns
from ..display.monitors import Display, list_displays, select_projector
from ..display.operator import OperatorWindow
from ..display.projector import ProjectorWindow


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def stamp() -> str:
    """Filesystem-safe local timestamp, e.g. 20261008-201503."""
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def report_path(config: Config, name: str, suffix: str) -> Path:
    config.reports_dir.mkdir(parents=True, exist_ok=True)
    return config.reports_dir / f"{name}-{stamp()}{suffix}"


def save_report(config: Config, name: str, data: dict) -> Path:
    """Write `data` as JSON to <reports>/<name>-<stamp>.json and return the path."""
    path = report_path(config, name, ".json")
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    return path


def add_device_args(parser, *, camera: bool = True) -> None:
    parser.add_argument("--display", help="projector override: EDID name/id or GDI name (e.g. DISPLAY2)")
    if camera:
        parser.add_argument("--camera", help="camera override: part of the DirectShow name (e.g. brio)")
    parser.add_argument("--windowed", action="store_true",
                        help="dev mode: projector canvas as a window on the laptop screen")


def resolve_projector(config: Config, windowed: bool) -> tuple[Display | None, tuple[int, int], str]:
    """(display, canvas size, description). The projector is identified explicitly."""
    expected = (config.projector.expected_width, config.projector.expected_height)
    if windowed:
        return None, expected, f"windowed dev mode ({expected[0]}x{expected[1]})"
    display, rule = select_projector(list_displays(with_modes=False), config.projector.match)
    description = f"{display.label} output={display.output} {display.width}x{display.height} ({rule})"
    if (display.width, display.height) != expected:
        description += f"  WARNING: expected {expected[0]}x{expected[1]}"
    return display, (display.width, display.height), description


def exposure_text(info: CameraInfo) -> str:
    """Effective exposure as read back from the camera when it was opened."""
    if info.exposure is None:
        return f"not read (backend {info.backend}; exposure control needs dshow)"
    return info.exposure.describe()


def lock_text(info: CameraInfo, name: str) -> str:
    """Effective focus or gain (`name`) as read back from the camera when it was opened."""
    state = getattr(info, name)
    if state is None:
        return f"not read (backend {info.backend}; {name} control needs dshow)"
    return state.describe()


SETTLE_SECONDS = 0.8      # after changing the projected image: > 2x the 275 ms display->camera latency (A3)
BACKGROUND_FRAMES = 6
SINGLE_FRAMES = 10


def current_seq(s, timeout: float = 5.0) -> int:
    """Sequence number of the newest camera frame, waiting for the first one. Raises a clear error when
    the camera delivers nothing (2026-10-10: another process, the `camera` preview, held the Brio and
    `cursor` crashed on a missing frame)."""
    frame = s.camera.latest() or s.camera.wait_frame(0, timeout)
    if frame is None:
        raise RuntimeError(f"no frames from the camera within {timeout:g} s; is another program "
                           "(e.g. a `camera` preview) using it?")
    return frame.seq


def capture_frames(s, n: int, settle: float = SETTLE_SECONDS) -> tuple[np.ndarray, list[np.ndarray]]:
    """Wait for the projector to settle, then n consecutive new frames: (average, singles), grey."""
    end = time.perf_counter() + settle
    while time.perf_counter() < end:
        cv2.waitKey(5)
    seq, singles = current_seq(s), []
    while len(singles) < n:
        frame = s.camera.wait_frame(seq, 2.0)
        if frame is None:
            raise RuntimeError("camera stopped delivering frames")
        seq = frame.seq
        singles.append(cv2.cvtColor(frame.image, cv2.COLOR_BGR2GRAY))
        cv2.pollKey()
    return np.mean(np.stack(singles), axis=0).astype(np.float32), singles


class CameraMeasure:
    """`measure(screen)` for calibration/auto.py on the real camera: project black and capture a
    background, project `screen` and capture single frames, detect (D29 detector, whole frame).
    `shift` moves every projected image by whole projector pixels: a controlled perturbation of
    the scene for testing the setup check (`validate --auto --simulate-shift`)."""

    def __init__(self, s, *, title: str, frames: int = SINGLE_FRAMES, shift: tuple[int, int] = (0, 0)):
        self.s, self.title, self.frames, self.shift = s, title, frames, shift
        self.count = 0

    def __call__(self, screen: np.ndarray) -> TargetMeasurement:
        s = self.s
        s.projector.show(np.zeros_like(screen))
        background, _ = capture_frames(s, BACKGROUND_FRAMES)
        s.projector.show(shifted(screen, *self.shift))
        _, singles = capture_frames(s, self.frames)
        m = measurement_from_frames(background, singles)
        self.count += 1
        view = cv2.cvtColor(singles[-1], cv2.COLOR_GRAY2BGR)
        if m.detection.ok:
            draw_marker(view, m.detection.center)
        s.operator.show(view, lines=[self.title, f"target {self.count}",
                                     "detected" if m.ok else "!" + m.problem[:120]])
        cv2.pollKey()
        return m


def shifted(image: np.ndarray, dx: int, dy: int) -> np.ndarray:
    """`image` moved by whole pixels (dx right, dy down); uncovered pixels are black."""
    if (dx, dy) == (0, 0):
        return image
    h, w = image.shape[:2]
    out = np.zeros_like(image)
    out[max(dy, 0):h + min(dy, 0), max(dx, 0):w + min(dx, 0)] = \
        image[max(-dy, 0):h - max(dy, 0), max(-dx, 0):w - max(dx, 0)]
    return out


def draw_marker(view: np.ndarray, center) -> None:
    patterns.draw_crosshair(view, center, patterns.GREEN, gap=6, arm=30, thickness=1)


def primary_display() -> Display | None:
    return next((d for d in list_displays(with_modes=False) if d.primary), None)


@dataclass
class Session:
    config: Config
    display: Display | None
    canvas_size: tuple[int, int]
    projector: ProjectorWindow
    camera: CameraManager
    camera_info: CameraInfo
    operator: OperatorWindow


@contextlib.contextmanager
def open_session(config: Config, args, *, allow_mode_mismatch: bool = False):
    """Projector + camera + operator window. Everything is closed on exit."""
    windowed = getattr(args, "windowed", False)
    display, canvas_size, description = resolve_projector(config, windowed)
    print(f"projector: {description}")
    camera = CameraManager(config.camera, allow_mode_mismatch=allow_mode_mismatch)
    projector = None
    operator = None
    try:
        info = camera.open()
        print(f"camera:    [{info.index}] {info.name} {info.width}x{info.height} "
              f"(requested {info.requested}; open {info.open_seconds:.1f} s)")
        print(f"exposure:  {exposure_text(info)}")
        print(f"focus:     {lock_text(info, 'focus')}")
        print(f"gain:      {lock_text(info, 'gain')}")
        projector = ProjectorWindow(display, canvas_size, windowed=windowed)
        projector.open()
        print(f"projector window: {'OK' if projector.geometry_ok else 'NOT VERIFIED'}: {projector.geometry_report}")
        operator = OperatorWindow(info.size, primary_display())
        operator.open()
        yield Session(config, display, canvas_size, projector, camera, info, operator)
    finally:
        camera.close()
        for window in (operator, projector):
            if window is not None:
                window.close()
        cv2.destroyAllWindows()
        cv2.waitKey(1)
