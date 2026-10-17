"""`calibrate`: four-point calibration (brain.md A5, D16, D30, D31).

Automatic is the default since D31 (`--auto` still accepted); `--manual` clicks.

Manual (`--manual`):
1. The projector shows four corner targets; the operator clicks each one in the camera view.
2. The quad is validated and H (camera -> projector) is computed.
3. Review: the canvas edge computed from H is drawn on the camera view, and hovering
   the mouse projects a crosshair at the mapped point. Save, redo or cancel.

Automatic (`--auto`, D30): the four corners are detected (calibration/detect.py), checked
(missing, ambiguous, unstable, duplicate, wrong order, mirrored), H is fitted the same way,
and a held-out check target must map onto itself. Any doubt stops it; it never falls back to
clicks. `--dry-run` does everything except saving.
"""

from __future__ import annotations

import time

import cv2
import numpy as np

from ..calibration.auto import AutoCalibrationError, associate_corners, measure_targets, screen_for, verify_check_target
from ..calibration.collect import collect_points, draw_point
from ..calibration.metrics import setup_check
from ..calibration.store import Calibration, CalibrationError, check_compatible, load_calibration, save_calibration
from ..calibration.targets import CORNER_NAMES, check_target, corner_targets
from ..config import Config
from ..display import patterns
from ..geometry.homography import GeometryError, signed_area, validate_quad
from ..mapping.mapper import CoordinateMapper
from .common import CameraMeasure, add_device_args, now_iso, open_session, save_report


def add_parser(subparsers) -> None:
    p = subparsers.add_parser("calibrate", help="four-point calibration: automatic detection (default) or --manual (A5, D31)")
    add_device_args(p)
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--auto", action="store_true",
                      help="detect the 4 corners automatically (the default); stops with the reasons on any "
                           "doubt, never falls back to clicks")
    mode.add_argument("--manual", action="store_true", help="click the 4 projected corners yourself")
    p.add_argument("--dry-run", action="store_true", help="automatic mode: detect, fit and verify, but do not save")
    p.set_defaults(func=run)


def is_manual(args) -> bool:
    """Automatic unless --manual was given (D31)."""
    return bool(getattr(args, "manual", False))


def camera_measure(s, title: str, shift=(0, 0)):
    """The real-camera measurement (a module function so tests can substitute a synthetic one)."""
    return CameraMeasure(s, title=title, shift=shift)


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
    if is_manual(args):
        if getattr(args, "dry_run", False):
            print("--dry-run only applies to automatic calibration (drop --manual)")
            return 2
        return run_manual(config, args)
    return run_auto(config, args)


def _previous_calibration(config: Config):
    try:
        return load_calibration(config.calibration_dir)
    except CalibrationError:
        return None


def run_auto(config: Config, args) -> int:
    """Automatic four-point calibration (D30). Saves only if every check passes."""
    v = config.validation
    previous = _previous_calibration(config)
    dry_run = bool(getattr(args, "dry_run", False))
    report = {"created_at": now_iso(), "mode": "auto", "dry_run": dry_run,
              "method": "automatic cross detection (calibration/detect.py), no clicks"}
    with open_session(config, args) as s:
        w, h = s.canvas_size
        corners = corner_targets(w, h, config.calibration.target_inset)
        check = check_target(w, h)
        measure = camera_measure(s, "AUTOMATIC CALIBRATION (detecting the 4 corners)")
        corner_m, check_m = [], None
        try:
            corner_m = measure_targets(measure, s.canvas_size, corners, show_others=True)
            points = associate_corners(corner_m, corners, s.camera_info.size)
            calibration = Calibration.create(
                method="auto",
                camera_name=s.camera_info.name,
                camera_size=s.camera_info.size,
                projector_name=s.display.label if s.display else "windowed dev mode",
                projector_size=s.canvas_size,
                projector_points=corners,
                camera_points=points,
            )
            check_m = measure(screen_for(s.canvas_size, [check], 0, show_others=False))
            check_error = verify_check_target(calibration.homography, check_m, check, v.required_max_px)
        except (AutoCalibrationError, GeometryError) as e:
            details = getattr(e, "details", [])
            print(f"automatic calibration FAILED: {e}")
            for line in details:
                print(f"  {line}")
            print("Nothing was saved. Fix the cause (aim, focus, light, a target off the camera image), "
                  "or calibrate manually: `calibrate --manual`.")
            report.update(result="failed", error=str(e), details=details,
                          corners=[dict(name=n, **m.summary()) for n, m in zip(CORNER_NAMES, corner_m)],
                          check_target={"projector": check.tolist(), **check_m.summary()} if check_m else None)
            print(f"report: {save_report(config, 'calibration-auto', report)}")
            return 1

        cov = coverage(CoordinateMapper.from_calibration(calibration), s.camera_info.size)
        comparison = None
        if previous is not None:
            try:
                check_compatible(previous, s.camera_info.size, s.canvas_size)
                if np.array_equal(previous.projector_points, corners):
                    cmp = setup_check(previous.camera_points, points,
                                      v.auto_setup_limit_px if previous.method == "auto" else v.repeatability_mean_px)
                    comparison = {"previous_created_at": previous.created_at, "previous_method": previous.method,
                                  "shifts_px": cmp.shifts, "mean_shift_px": cmp.mean_shift,
                                  "variation_px": cmp.variation, "limit_px": cmp.limit, "consistent": cmp.consistent}
            except CalibrationError:
                pass
        path = None if dry_run else save_calibration(calibration, config.calibration_dir)
        report.update(
            result="ok", calibration_created_at=calibration.created_at, saved=str(path) if path else None,
            corners=[dict(name=n, projector=t.tolist(), **m.summary()) for n, t, m in zip(CORNER_NAMES, corners, corner_m)],
            check_target={"projector": check.tolist(), "error_px": check_error, **check_m.summary()},
            coverage=cov, comparison_with_previous=comparison,
        )
        report_file = save_report(config, "calibration-auto", report)

    print(f"automatic calibration {'(dry run, NOT saved)' if dry_run else 'saved: ' + str(path)}")
    for name, t, m in zip(CORNER_NAMES, corners, corner_m):
        q = m.summary()
        print(f"  {name:<13} projector ({t[0]:.0f}, {t[1]:.0f})  <-  camera ({q['center'][0]:.2f}, {q['center'][1]:.2f})"
              f"  [single frames {q['single_accepted']}/{q['single_frames']}, sd {q['single_sd_px']:.3f} px]")
    print(f"  check target ({check[0]:.0f}, {check[1]:.0f}) maps back with error {check_error:.2f} projector px "
          f"(limit {v.required_max_px:g})")
    m_ = cov["margins_px"]
    print(f"  projection fills {cov['area_fraction'] * 100:.1f} % of the camera frame; margins left {m_['left']:.0f}, "
          f"top {m_['top']:.0f}, right {m_['right']:.0f}, bottom {m_['bottom']:.0f} px"
          + ("" if cov["fully_visible"] else "  WARNING: canvas not fully visible"))
    if comparison:
        print(f"  vs previous calibration ({comparison['previous_method']}, {comparison['previous_created_at']}): "
              f"variation {comparison['variation_px']:.2f} px (limit {comparison['limit_px']:g})")
        for name, (dx, dy) in zip(CORNER_NAMES, comparison["shifts_px"]):
            print(f"    {name:<13} detected - previous {dx:+.2f}, {dy:+.2f} camera px")
    print(f"report: {report_file}")
    return 0


def run_manual(config: Config, args) -> int:
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
