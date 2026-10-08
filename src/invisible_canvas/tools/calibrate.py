"""`calibrate`: manual four-point calibration (brain.md A5, D16).

1. The projector shows four corner targets; the operator clicks each one in the camera view.
2. The quad is validated and H (camera -> projector) is computed.
3. Review: the canvas edge computed from H is drawn on the camera view, and hovering
   the mouse projects a crosshair at the mapped point. Save, redo or cancel.
"""

from __future__ import annotations

import time

import cv2
import numpy as np

from ..calibration.collect import collect_points, draw_point
from ..calibration.store import Calibration, save_calibration
from ..calibration.targets import CORNER_NAMES, corner_targets
from ..config import Config
from ..display import patterns
from ..geometry.homography import GeometryError, signed_area, validate_quad
from ..mapping.mapper import CoordinateMapper
from .common import add_device_args, open_session


def add_parser(subparsers) -> None:
    p = subparsers.add_parser("calibrate", help="manual four-point calibration (A5)")
    add_device_args(p)
    p.set_defaults(func=run)


def draw_canvas_outline(view: np.ndarray, mapper: CoordinateMapper, color=patterns.GREEN, grid_step: int = 160) -> None:
    """The canvas edge and a projector-space grid, mapped into the camera view."""
    w, h = mapper.canvas_size
    for x in range(grid_step, w, grid_step):
        a, b = mapper.projector_to_camera([[x, -0.5], [x, h - 0.5]])
        cv2.line(view, tuple(np.round(a).astype(int)), tuple(np.round(b).astype(int)), patterns.DIM, 1, cv2.LINE_AA)
    for y in range(grid_step, h, grid_step):
        a, b = mapper.projector_to_camera([[-0.5, y], [w - 0.5, y]])
        cv2.line(view, tuple(np.round(a).astype(int)), tuple(np.round(b).astype(int)), patterns.DIM, 1, cv2.LINE_AA)
    outline = np.round(mapper.canvas_outline_in_camera()).astype(np.int32)
    cv2.polylines(view, [outline], True, color, 2, cv2.LINE_AA)


def coverage(mapper: CoordinateMapper, camera_size: tuple[int, int]) -> dict:
    """How the projected canvas sits in the camera frame (brain.md A4)."""
    outline = mapper.canvas_outline_in_camera()
    cw, ch = camera_size
    margins = {
        "left": float(outline[:, 0].min()),
        "top": float(outline[:, 1].min()),
        "right": float(cw - 1 - outline[:, 0].max()),
        "bottom": float(ch - 1 - outline[:, 1].max()),
    }
    return {
        "margins_px": margins,
        "fully_visible": all(m > 0 for m in margins.values()),
        "area_fraction": abs(signed_area(outline)) / (cw * ch),
    }


def review(session, calibration: Calibration, camera_points: np.ndarray) -> str:
    """Live check before saving. Returns 'save', 'redo' or 'cancel'."""
    mapper = CoordinateMapper.from_calibration(calibration)
    size = session.canvas_size
    state = {"hover": None}

    def on_mouse(kind: str, x: float, y: float) -> None:
        if kind == "move":
            state["hover"] = (x, y)

    session.operator.on_mouse = on_mouse
    try:
        while True:
            frame = session.camera.wait_frame(0, 2.0)
            if frame is None:
                return "cancel"
            view = frame.image.copy()
            draw_canvas_outline(view, mapper)
            for k, p in enumerate(camera_points):
                draw_point(view, p, patterns.GREEN, str(k + 1))
            projected = patterns.dark_canvas(size)
            for t in calibration.projector_points:
                patterns.draw_target(projected, t, active=False)
            lines = [
                "REVIEW CALIBRATION",
                "",
                "Green outline = canvas edge computed from the calibration. It must hug the real projected edge.",
                "Hover over the camera view: a crosshair is projected at the mapped point and must land on that physical spot.",
                "",
            ]
            hover = state["hover"]
            if hover is not None:
                px, py = mapper.map_point(*hover)
                inside = bool(mapper.inside_canvas([[px, py]])[0])
                if inside:
                    patterns.draw_crosshair(projected, (px, py))
                lines.append(f"camera ({hover[0]:.1f}, {hover[1]:.1f}) -> canvas ({px:.1f}, {py:.1f})"
                             + ("" if inside else " outside canvas"))
            lines += ["", "ENTER: save | R: redo | ESC: cancel"]
            session.projector.show(projected)
            session.operator.show(view, raw=frame.image, loupe_center=hover, lines=lines)
            key = cv2.waitKey(10)
            if key in (13, 10):
                return "save"
            if key in (ord("r"), ord("R")):
                return "redo"
            if key == 27:
                return "cancel"
    finally:
        session.operator.on_mouse = None


def _show_message(session, message: str, seconds: float = 3.0) -> None:
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        frame = session.camera.latest()
        if frame is not None:
            session.operator.show(frame.image, lines=["!" + message])
        cv2.waitKey(20)


def run(config: Config, args) -> int:
    with open_session(config, args) as s:
        w, h = s.canvas_size
        cw, ch = s.camera_info.size
        targets = corner_targets(w, h, config.calibration.target_inset)
        labels = [f"{i + 1}: {name}" for i, name in enumerate(CORNER_NAMES)]
        while True:
            points = collect_points(
                s, targets, labels,
                lambda i: patterns.target_screen(s.canvas_size, targets, i, labels),
                title="CALIBRATION (manual, 4 points)",
            )
            if points is None:
                print("calibration cancelled; nothing saved")
                return 1
            try:
                validate_quad(points, min_area=0.01 * cw * ch)
                calibration = Calibration.create(
                    method="manual",
                    camera_name=s.camera_info.name,
                    camera_size=s.camera_info.size,
                    projector_name=s.display.label if s.display else "windowed dev mode",
                    projector_size=s.canvas_size,
                    projector_points=targets,
                    camera_points=points,
                )
            except GeometryError as e:
                print(f"rejected: {e}")
                _show_message(s, f"Rejected: {e}. Collect the points again.")
                continue
            if np.sign(signed_area(points)) != np.sign(signed_area(targets)):
                print("warning: the camera image is mirrored relative to the projector "
                      "(or the corners were clicked in the wrong order)")
            decision = review(s, calibration, points)
            if decision == "redo":
                continue
            if decision == "cancel":
                print("calibration cancelled; nothing saved")
                return 1
            path = save_calibration(calibration, config.calibration_dir)
            cov = coverage(CoordinateMapper.from_calibration(calibration), s.camera_info.size)
            print(f"saved: {path}")
            for name, t, p in zip(CORNER_NAMES, targets, points):
                print(f"  {name:<13} projector ({t[0]:.0f}, {t[1]:.0f})  <-  camera ({p[0]:.2f}, {p[1]:.2f})")
            m = cov["margins_px"]
            print(f"  projection fills {cov['area_fraction'] * 100:.1f} % of the camera frame; margins "
                  f"left {m['left']:.0f}, top {m['top']:.0f}, right {m['right']:.0f}, bottom {m['bottom']:.0f} px"
                  + ("" if cov["fully_visible"] else "  WARNING: canvas not fully visible"))
            return 0
