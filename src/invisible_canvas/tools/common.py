"""Helpers shared by the command-line tools."""

from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import cv2

from ..camera.manager import CameraInfo, CameraManager
from ..config import Config
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
