"""`validate` (A7): held-out accuracy test. `repeatability` (A6): corner variation.

validate: the projector shows a grid of targets that were not used for calibration,
one at a time; the operator clicks each in the camera view; each click is mapped
through H and compared with where the target really is. In Phase 1A the error
includes human click error (brain.md R15).
"""

from __future__ import annotations

import cv2
import numpy as np

from ..calibration.collect import collect_points
from ..calibration.metrics import accuracy_stats, corner_repeatability
from ..calibration.store import check_compatible, load_calibration, load_history
from ..calibration.targets import CORNER_NAMES, grid_targets, min_distance
from ..config import Config
from ..display import patterns
from ..mapping.mapper import CoordinateMapper
from .calibrate import draw_canvas_outline
from .common import add_device_args, now_iso, open_session, save_report


def add_parser(subparsers) -> None:
    p = subparsers.add_parser("validate", help="held-out mapping accuracy test, manual clicks (A7)")
    add_device_args(p)
    p.set_defaults(func=run_validate)
    r = subparsers.add_parser("repeatability", help="corner variation across recent calibrations (A6)")
    r.add_argument("--runs", type=int, help="number of most recent calibrations to compare")
    r.set_defaults(func=run_repeatability)


def _verdict(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def run_validate(config: Config, args) -> int:
    v = config.validation
    calibration = load_calibration(config.calibration_dir)
    with open_session(config, args) as s:
        check_compatible(calibration, s.camera_info.size, s.canvas_size)
        mapper = CoordinateMapper.from_calibration(calibration)
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
            "calibration_created_at": calibration.created_at,
            "method": "manual clicks (includes human click error)",
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
    same_setup = [
        c for c in load_history(config.calibration_dir)
        if (c.camera_name, c.camera_size, c.projector_size)
        == (current.camera_name, current.camera_size, current.projector_size)
    ]
    if len(same_setup) < runs:
        print(f"need {runs} calibrations of this setup, found {len(same_setup)}. Run `calibrate` "
              f"{runs - len(same_setup)} more time(s) without touching the hardware.")
        return 1
    used = same_setup[-runs:]
    stats = corner_repeatability([c.camera_points for c in used])
    passed = stats.mean_variation <= v.repeatability_mean_px
    print(f"comparing the {runs} most recent calibrations (they must come from one unchanged setup):")
    for c in used:
        print(f"  {c.created_at}")
    for name, value in zip(CORNER_NAMES, stats.per_corner_mean):
        print(f"  {name:<13} mean variation {value:.2f} camera px")
    print(f"mean corner variation {stats.mean_variation:.2f} px (max {stats.max_variation:.2f} px); "
          f"target <= {v.repeatability_mean_px:g} px: {_verdict(passed)}")
    report = {
        "created_at": now_iso(),
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
