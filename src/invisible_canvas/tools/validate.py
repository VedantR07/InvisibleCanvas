"""`validate` (A7): held-out accuracy test. `repeatability` (A6): corner variation.

validate: the projector shows a grid of targets that were not used for calibration,
one at a time; the operator clicks each in the camera view; each click is mapped
through H and compared with where the target really is. In Phase 1A the error
includes human click error (brain.md R15).

Setup check first (D28): the four calibration corners are clicked again and compared with
the saved calibration (repeatability metric and limit, A6). If the camera or projector has
moved since calibrating, the grid is not run: a moved setup would show up as a uniform
mapping error that no validation can fix (2026-10-09: 5.87 px, all errors down-right).

Automatic (D30, the default since D31; `--auto` still accepted): the same procedure with
detection instead of clicks: the corners for the setup check and the 20 held-out targets are
detected (calibration/detect.py); the same statistics and thresholds apply. Reports are
`validation-auto-*.json` with `"mode": "auto"`; `--manual` reports carry `"mode": "manual"`.
Detection failures stop it; never a fallback to clicks.
"""

from __future__ import annotations

import cv2
import numpy as np

from ..calibration.auto import AutoCalibrationError, auto_setup_check, measure_targets, validation_result
from ..calibration.collect import collect_points
from ..calibration.metrics import accuracy_stats, corner_repeatability, setup_check
from ..calibration.store import check_compatible, load_calibration, load_history
from ..calibration.targets import CORNER_NAMES, grid_targets, min_distance
from ..config import Config
from ..display import patterns
from ..mapping.mapper import CoordinateMapper
from . import calibrate as calibrate_tool
from .calibrate import draw_canvas_outline
from .common import add_device_args, now_iso, open_session, save_report

AUTO_METHOD = "automatic cross detection (calibration/detect.py), no clicks"


def add_parser(subparsers) -> None:
    p = subparsers.add_parser("validate", help="held-out mapping accuracy test: automatic detection (default) or --manual (A7, D31)")
    add_device_args(p)
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--auto", action="store_true",
                      help="detect the setup-check corners and the 20 held-out targets automatically (the default); "
                           "stops with the reasons if any detection fails, never falls back to clicks")
    mode.add_argument("--manual", action="store_true", help="click the setup-check corners and the targets yourself")
    p.add_argument("--no-setup-check", action="store_true",
                   help="skip the setup check of the 4 calibration corners before the grid (not recommended)")
    p.add_argument("--simulate-shift", nargs=2, type=int, metavar=("DX", "DY"),
                   help="automatic mode, test only: shift every projected image by DX, DY projector px to check "
                        "that a moved setup is refused; the reports are marked as a simulation")
    p.set_defaults(func=run_validate)
    r = subparsers.add_parser("repeatability", help="corner variation across recent calibrations (A6)")
    r.add_argument("--runs", type=int, help="number of most recent calibrations to compare")
    r.set_defaults(func=run_repeatability)


def _verdict(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def _setup_check(s, calibration, limit: float):
    """Click the calibration corners again (rendered exactly as in `calibrate`) and compare."""
    corners = calibration.projector_points
    labels = [f"{i + 1}: {name}" for i, name in enumerate(CORNER_NAMES)]
    fresh = collect_points(
        s, corners, labels,
        lambda i: patterns.target_screen(s.canvas_size, corners, i, labels),
        title="SETUP CHECK: the 4 calibration corners again",
    )
    if fresh is None:
        return None
    check = setup_check(calibration.camera_points, fresh, limit)
    _print_setup_check(check, calibration, limit, "clicked again")
    return check


def _print_setup_check(check, calibration, limit: float, how: str) -> None:
    print(f"setup check: calibration corners {how} vs the calibration of {calibration.created_at} "
          f"({calibration.method})")
    for name, (dx, dy) in zip(CORNER_NAMES, check.shifts):
        print(f"  {name:<13} shift {dx:+.2f}, {dy:+.2f} camera px")
    print(f"  mean shift ({check.mean_shift[0]:+.2f}, {check.mean_shift[1]:+.2f}); variation "
          f"{check.variation:.2f} px vs limit {limit:g} px (repeatability metric): "
          f"{'unchanged' if check.consistent else 'CHANGED'}")


def _setup_check_report(check) -> dict | None:
    if check is None:
        return None
    return {"shifts_px": check.shifts, "mean_shift_px": check.mean_shift, "variation_px": check.variation,
            "limit_px": check.limit, "consistent": check.consistent}


def setup_limit(config: Config, calibration) -> float:
    """Setup-check limit for detected corners (D32): automatic calibrations were detected the same way,
    so they get the stricter automatic limit; a manual calibration's corners carry click error, so it
    keeps the manual limit even when it is checked by detection."""
    v = config.validation
    return v.auto_setup_limit_px if calibration.method == "auto" else v.repeatability_mean_px


MOVED_MESSAGE = ("The camera or projector has moved since this calibration, so the mapping no longer "
                 "describes the setup. Recalibrate (`recalibrate`: automatic, validated before it is saved; "
                 "or `calibrate`), then run `validate` without touching the hardware. No validation recorded.")


def run_validate(config: Config, args) -> int:
    if calibrate_tool.is_manual(args):
        if getattr(args, "simulate_shift", None):
            print("--simulate-shift only applies to automatic validation (drop --manual)")
            return 2
        return run_validate_manual(config, args)
    return run_validate_auto(config, args)


def run_validate_auto(config: Config, args) -> int:
    """Automatic held-out validation (D30): detected setup-check corners and grid, no clicks."""
    v = config.validation
    calibration = load_calibration(config.calibration_dir)
    shift = tuple(args.simulate_shift) if getattr(args, "simulate_shift", None) else (0, 0)
    common = {"mode": "auto", "method": AUTO_METHOD, "calibration_created_at": calibration.created_at,
              "calibration_method": calibration.method,
              "simulated_shift_px": list(shift) if shift != (0, 0) else None}
    if shift != (0, 0):
        print(f"SIMULATION: every projected image is shifted by {shift} projector px; results are not a validation")
    with open_session(config, args) as s:
        check_compatible(calibration, s.camera_info.size, s.canvas_size)
        mapper = CoordinateMapper.from_calibration(calibration)
        measure = calibrate_tool.camera_measure(s, "AUTOMATIC VALIDATION", shift)
        setup = None
        if not args.no_setup_check:
            try:
                setup, corner_m = auto_setup_check(measure, calibration, s.canvas_size, setup_limit(config, calibration))
            except AutoCalibrationError as e:
                print(f"setup check FAILED, corners not detected: {e}")
                for line in e.details:
                    print(f"  {line}")
                path = save_report(config, "setup-check", {"created_at": now_iso(), **common, "result": "detection failed",
                                                           "error": str(e), "details": e.details})
                print(f"No validation recorded. report: {path}")
                return 1
            _print_setup_check(setup, calibration, setup.limit, "detected")
            if not setup.consistent:
                path = save_report(config, "setup-check", {
                    "created_at": now_iso(), **common, **_setup_check_report(setup),
                    "detection": [dict(name=n, **m.summary()) for n, m in zip(CORNER_NAMES, corner_m)],
                })
                print(MOVED_MESSAGE)
                print(f"report: {path}")
                return 1
        w, h = s.canvas_size
        grid = grid_targets(w, h, v.grid_cols, v.grid_rows, v.grid_inset)
        measurements = measure_targets(measure, s.canvas_size, grid, show_others=False)
        try:
            result = validation_result(mapper, grid, measurements, v.grid_cols, v.grid_rows)
        except AutoCalibrationError as e:
            print(f"automatic validation FAILED: {e}")
            for line in e.details:
                print(f"  {line}")
            path = save_report(config, "validation-auto-failed", {
                "created_at": now_iso(), **common, "error": str(e), "details": e.details,
                "setup_check": _setup_check_report(setup),
                "detection": [m.summary() for m in measurements],
            })
            print("No validation recorded (validate --manual remains available). report: " + str(path))
            return 1
        s.projector.show(patterns.blank(s.canvas_size))

    stats = result.stats
    required = stats.meets(v.required_mean_px, v.required_max_px)
    stretch = stats.meets(v.stretch_mean_px, v.stretch_max_px)
    edge = result.edge
    mm_per_px = config.surface.width_mm / w if config.surface.width_mm > 0 else None
    caption = (f"AUTO mean {stats.mean:.2f} px, max {stats.max:.2f} px | required {_verdict(required)} | "
               f"stretch {_verdict(stretch)}" + (" | SIMULATED SHIFT" if shift != (0, 0) else ""))
    image = patterns.error_map((w, h), grid, result.mapped, result.errors,
                               limits=(v.required_mean_px, v.required_max_px), caption=caption)
    report = {
        "created_at": now_iso(),
        **common,
        "setup_check": _setup_check_report(setup),
        "camera": s.camera_info.name,
        "camera_size": s.camera_info.size,
        "canvas_size": (w, h),
        "grid": {"cols": v.grid_cols, "rows": v.grid_rows, "inset": v.grid_inset,
                 "min_distance_to_calibration_targets_px": min_distance(grid, calibration.projector_points)},
        "stats_px": stats.__dict__,
        "edge_mean_px": float(result.errors[edge].mean()),
        "interior_mean_px": float(result.errors[~edge].mean()) if np.any(~edge) else None,
        "mm_per_px": mm_per_px,
        "stats_mm": {k: val * mm_per_px for k, val in stats.__dict__.items() if k != "count"} if mm_per_px else None,
        "required": {"mean_px": v.required_mean_px, "max_px": v.required_max_px, "pass": required},
        "stretch": {"mean_px": v.stretch_mean_px, "max_px": v.stretch_max_px, "pass": stretch},
        "points": [
            {"target": t.tolist(), "camera": c.tolist(), "mapped": m.tolist(), "error_px": float(e),
             "detection": meas.summary()}
            for t, c, m, e, meas in zip(grid, result.detected, result.mapped, result.errors, measurements)
        ],
    }
    path = save_report(config, "validation-auto", report)
    cv2.imwrite(str(path.with_suffix(".png")), image)
    worst_sd = max(m.single_sd or 0.0 for m in measurements)
    print(f"held-out points: {len(grid)}  (AUTOMATIC detection, no clicks; calibration {calibration.method} "
          f"{calibration.created_at})" + (f"  SIMULATED SHIFT {shift}" if shift != (0, 0) else ""))
    print(f"error px: mean {stats.mean:.2f}, median {stats.median:.2f}, p95 {stats.p95:.2f}, "
          f"max {stats.max:.2f}, rms {stats.rms:.2f}")
    print(f"edge points mean {report['edge_mean_px']:.2f} px, interior mean {report['interior_mean_px']:.2f} px")
    print(f"detection: {len(measurements)}/{len(grid)} targets, worst single-frame sd {worst_sd:.3f} camera px")
    print(f"required (mean <= {v.required_mean_px:g}, max <= {v.required_max_px:g}): {_verdict(required)}")
    print(f"stretch  (mean <= {v.stretch_mean_px:g}, max <= {v.stretch_max_px:g}): {_verdict(stretch)}")
    print(f"report: {path} (+ .png error map)")
    return 0 if required else 1


def run_validate_manual(config: Config, args) -> int:
    v = config.validation
    calibration = load_calibration(config.calibration_dir)
    with open_session(config, args) as s:
        check_compatible(calibration, s.camera_info.size, s.canvas_size)
        mapper = CoordinateMapper.from_calibration(calibration)
        setup = None
        if not args.no_setup_check:
            setup = _setup_check(s, calibration, v.repeatability_mean_px)
            if setup is None:
                print("validation cancelled; nothing recorded")
                return 1
            if not setup.consistent:
                path = save_report(config, "setup-check", {
                    "created_at": now_iso(), "mode": "manual", "calibration_created_at": calibration.created_at,
                    **_setup_check_report(setup),
                })
                print("The camera or projector has moved since this calibration, so the mapping no longer "
                      "describes the setup. Recalibrate (`calibrate`), then run `validate` without touching "
                      "the hardware. No validation recorded.")
                print(f"report: {path}")
                return 1
        w, h = s.canvas_size
        grid = grid_targets(w, h, v.grid_cols, v.grid_rows, v.grid_inset)
        n = len(grid)
        labels = [f"point {i + 1} of {n} at ({x:.0f}, {y:.0f})" for i, (x, y) in enumerate(grid)]
        points = collect_points(
            s, grid, labels,
            lambda i: patterns.target_screen(s.canvas_size, grid, i, labels, show_others=False),
            title=f"VALIDATION ({n} held-out points)",
            overlay=lambda view: draw_canvas_outline(view, mapper, patterns.DIM),
        )
        if points is None:
            print("validation cancelled; nothing recorded")
            return 1

        mapped = mapper.camera_to_projector(points)
        errors = np.linalg.norm(mapped - grid, axis=1)
        stats = accuracy_stats(errors)
        required = stats.meets(v.required_mean_px, v.required_max_px)
        stretch = stats.meets(v.stretch_mean_px, v.stretch_max_px)
        rows, cols = np.divmod(np.arange(n), v.grid_cols)
        edge = (rows == 0) | (rows == v.grid_rows - 1) | (cols == 0) | (cols == v.grid_cols - 1)
        mm_per_px = config.surface.width_mm / w if config.surface.width_mm > 0 else None

        caption = (f"mean {stats.mean:.2f} px, max {stats.max:.2f} px | required {_verdict(required)} | "
                   f"stretch {_verdict(stretch)}")
        image = patterns.error_map(s.canvas_size, grid, mapped, errors,
                                   limits=(v.required_mean_px, v.required_max_px), caption=caption)
        report = {
            "created_at": now_iso(),
            "mode": "manual",
            "calibration_created_at": calibration.created_at,
            "method": "manual clicks (includes human click error)",
            "setup_check": _setup_check_report(setup),
            "camera": s.camera_info.name,
            "camera_size": s.camera_info.size,
            "canvas_size": s.canvas_size,
            "grid": {"cols": v.grid_cols, "rows": v.grid_rows, "inset": v.grid_inset,
                     "min_distance_to_calibration_targets_px": min_distance(grid, calibration.projector_points)},
            "stats_px": stats.__dict__,
            "edge_mean_px": float(errors[edge].mean()),
            "interior_mean_px": float(errors[~edge].mean()) if np.any(~edge) else None,
            "mm_per_px": mm_per_px,
            "stats_mm": {k: val * mm_per_px for k, val in stats.__dict__.items() if k != "count"} if mm_per_px else None,
            "required": {"mean_px": v.required_mean_px, "max_px": v.required_max_px, "pass": required},
            "stretch": {"mean_px": v.stretch_mean_px, "max_px": v.stretch_max_px, "pass": stretch},
            "points": [
                {"target": t.tolist(), "camera": c.tolist(), "mapped": m.tolist(), "error_px": float(e)}
                for t, c, m, e in zip(grid, points, mapped, errors)
            ],
        }
        path = save_report(config, "validation", report)
        cv2.imwrite(str(path.with_suffix(".png")), image)

        print(f"held-out points: {n}  (manual clicks; includes click error)")
        print(f"error px: mean {stats.mean:.2f}, median {stats.median:.2f}, p95 {stats.p95:.2f}, "
              f"max {stats.max:.2f}, rms {stats.rms:.2f}")
        print(f"edge points mean {report['edge_mean_px']:.2f} px, interior mean "
              f"{report['interior_mean_px']:.2f} px" if report["interior_mean_px"] is not None else "")
        if mm_per_px:
            print(f"error mm: mean {stats.mean * mm_per_px:.1f}, max {stats.max * mm_per_px:.1f}")
        print(f"required (mean <= {v.required_mean_px:g}, max <= {v.required_max_px:g}): {_verdict(required)}")
        print(f"stretch  (mean <= {v.stretch_mean_px:g}, max <= {v.stretch_max_px:g}): {_verdict(stretch)}")
        print(f"report: {path} (+ .png error map)")

        s.projector.show(image)
        frame = s.camera.latest()
        s.operator.show(frame.image, lines=["VALIDATION RESULT", caption, "", "Error map is on the projector.",
                                            "Press any key to finish."])
        cv2.waitKey(0)
    return 0 if required else 1


def run_repeatability(config: Config, args) -> int:
    v = config.validation
    runs = args.runs or v.repeatability_runs
    current = load_calibration(config.calibration_dir)
    # Only calibrations made the same way: manual click spread and detection spread are different
    # quantities and must not be mixed (D30).
    same_setup = [
        c for c in load_history(config.calibration_dir)
        if (c.camera_name, c.camera_size, c.projector_size, c.method)
        == (current.camera_name, current.camera_size, current.projector_size, current.method)
    ]
    if len(same_setup) < runs:
        flag = "--auto" if current.method == "auto" else "--manual"
        print(f"need {runs} {current.method} calibrations of this setup, found {len(same_setup)}. Run `calibrate {flag}` "
              f"{runs - len(same_setup)} more time(s) without touching the hardware.")
        return 1
    used = same_setup[-runs:]
    stats = corner_repeatability([c.camera_points for c in used])
    passed = stats.mean_variation <= v.repeatability_mean_px
    print(f"comparing the {runs} most recent {current.method} calibrations (they must come from one unchanged setup):")
    for c in used:
        print(f"  {c.created_at}")
    for name, value in zip(CORNER_NAMES, stats.per_corner_mean):
        print(f"  {name:<13} mean variation {value:.2f} camera px")
    print(f"mean corner variation {stats.mean_variation:.2f} px (max {stats.max_variation:.2f} px); "
          f"target <= {v.repeatability_mean_px:g} px: {_verdict(passed)}")
    report = {
        "created_at": now_iso(),
        "method": current.method,
        "runs": [c.created_at for c in used],
        "corner_points": [c.camera_points.tolist() for c in used],
        "per_corner_mean_px": stats.per_corner_mean,
        "mean_variation_px": stats.mean_variation,
        "max_variation_px": stats.max_variation,
        "target_mean_px": v.repeatability_mean_px,
        "pass": passed,
    }
    print(f"report: {save_report(config, 'repeatability', report)}")
    return 0 if passed else 1
