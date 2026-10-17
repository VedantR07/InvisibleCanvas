"""`recalibrate` (brain.md D39): automatic calibration recovery after the camera or projector moved.

The automatic setup check (D28/D32) runs against the current calibration. Unchanged: nothing happens.
Moved: a replacement is built from the corners just detected (whole frame, not their old positions),
checked with the held-out check target, validated on the 20 held-out grid targets (A7 required
limits, as `validate`), and confirmed by a final setup check against it; only then does it become
`current.json` (the previous calibration stays in the history). Any failure leaves the calibration
untouched and explains why (calibration/recovery.py). `--dry-run` does everything except saving.
Every run writes `data/reports/calibration-recovery-<stamp>.json`.

`cursor` runs the same recovery when its setup check refuses (`recover_in_session`).
"""

from __future__ import annotations

from pathlib import Path

from ..calibration.recovery import (ACCEPTED, UNCHANGED, RecoveryPlan, RecoveryResult, check_and_recover,
                                    commit_recovery, recover_calibration)
from ..calibration.store import CalibrationError, check_compatible, load_calibration
from ..calibration.targets import CORNER_NAMES, check_target, grid_targets
from ..config import Config
from ..display import patterns
from ..mapping.mapper import CoordinateMapper
from . import calibrate as calibrate_tool
from .calibrate import coverage
from .common import add_device_args, now_iso, open_session, save_report
from .validate import setup_limit

TITLE = "AUTOMATIC RECALIBRATION - keep hands and objects out of the projection"
KEEP_CLEAR = ("Keep hands and objects out of the projection until it finishes "
              "(4 corners, 1 check target, 20 validation targets, 4 corners again).")


def add_parser(subparsers) -> None:
    p = subparsers.add_parser("recalibrate",
                              help="automatic recovery after the setup moved: detect, validate, then save (D39)")
    add_device_args(p)
    p.add_argument("--dry-run", action="store_true",
                   help="detect, fit, validate and confirm a replacement, but do not save it")
    p.set_defaults(func=run)


def recovery_plan(config: Config, calibration, canvas_size) -> RecoveryPlan:
    """The existing targets and thresholds: check target (D30), validation grid and A7 required limits,
    setup-check limits for this calibration's method and for the automatic candidate (D32)."""
    v = config.validation
    w, h = canvas_size
    return RecoveryPlan(check_target=check_target(w, h),
                        grid=grid_targets(w, h, v.grid_cols, v.grid_rows, v.grid_inset),
                        grid_cols=v.grid_cols, grid_rows=v.grid_rows,
                        setup_limit_px=setup_limit(config, calibration), confirm_limit_px=v.auto_setup_limit_px,
                        required_mean_px=v.required_mean_px, required_max_px=v.required_max_px)


def _session_names(s) -> dict:
    return dict(canvas_size=s.canvas_size, camera_size=s.camera_info.size, camera_name=s.camera_info.name,
                projector_name=s.display.label if s.display else "windowed dev mode")


def finish(config: Config, s, result: RecoveryResult, plan: RecoveryPlan, *, dry_run: bool = False,
           context: str = "recalibrate") -> Path:
    """Commit an accepted candidate (unless dry run), print the outcome, write the report. Returns the
    report path. A commit that is refused marks the result failed; nothing is saved then."""
    saved = None
    if result.accepted and not dry_run:
        try:
            saved = commit_recovery(result, config.calibration_dir)
        except CalibrationError as e:
            result.fail("commit", e)
    s.projector.show(patterns.blank(s.canvas_size))
    candidate = result.candidate
    report = {"created_at": now_iso(), "context": context, "dry_run": dry_run,
              "saved": None if saved is None else str(saved), **result.to_report(plan),
              "coverage": None if candidate is None else
              coverage(CoordinateMapper.from_calibration(candidate), s.camera_info.size)}
    path = save_report(config, "calibration-recovery", report)

    previous, setup = result.previous, result.setup
    if setup is not None:
        print(f"setup check vs the calibration of {previous.created_at}: variation {setup.variation:.2f} px "
              f"(limit {setup.limit:g}), mean shift ({setup.mean_shift[0]:+.1f}, {setup.mean_shift[1]:+.1f}) camera px: "
              f"{'unchanged' if setup.consistent else 'MOVED'}")
    if result.status == UNCHANGED:
        print("The setup has not moved; the calibration is still valid. Nothing was changed.")
    elif result.status == ACCEPTED:
        stats = result.validation.stats
        for name, (dx, dy) in zip(CORNER_NAMES, setup.shifts):
            print(f"  {name:<13} moved {dx:+.1f}, {dy:+.1f} camera px")
        print(f"replacement: check target error {result.check_error_px:.2f} projector px (limit {plan.required_max_px:g}); "
              f"held-out validation mean {stats.mean:.2f} / max {stats.max:.2f} projector px "
              f"(required <= {plan.required_mean_px:g} / <= {plan.required_max_px:g}); setup unchanged during "
              f"recovery (variation {result.confirmation.variation:.2f} px)")
        cov = report["coverage"]
        if not cov["fully_visible"]:
            print("  WARNING: the projected canvas is not fully inside the camera image")
        print(f"new calibration {candidate.created_at} " + ("NOT saved (dry run)" if dry_run else
              f"saved: {saved} (the previous one, {previous.created_at}, stays in the history)"))
    else:
        print(f"automatic recalibration FAILED at the {result.stage} step: {result.reason}")
        for line in result.details:
            print(f"  {line}")
        for hint in result.hints:
            print(f"  hint: {hint}")
        print(f"The calibration was NOT changed ({previous.created_at} is still current). "
              "Fix the cause and run `recalibrate` again, or `calibrate --manual`.")
    print(f"report: {path}")
    return path


def recover_in_session(config: Config, s, previous, setup, corners, measure) -> tuple[RecoveryResult, Path]:
    """For a tool whose setup check just refused `previous` (`corners`: that check's measurements)."""
    plan = recovery_plan(config, previous, s.canvas_size)
    print("The setup has moved since the calibration: recalibrating automatically. " + KEEP_CLEAR)
    result = recover_calibration(measure, previous, setup, corners, plan, **_session_names(s))
    return result, finish(config, s, result, plan, context="cursor")


def run(config: Config, args) -> int:
    previous = load_calibration(config.calibration_dir)
    dry_run = bool(getattr(args, "dry_run", False))
    with open_session(config, args) as s:
        check_compatible(previous, s.camera_info.size, s.canvas_size)
        plan = recovery_plan(config, previous, s.canvas_size)
        print(f"calibration {previous.created_at} ({previous.method}): checking the setup; if it moved, a replacement "
              f"is detected, validated and {'shown, not saved (dry run)' if dry_run else 'saved'}. " + KEEP_CLEAR)
        result = check_and_recover(calibrate_tool.camera_measure(s, TITLE), previous, plan, **_session_names(s))
        finish(config, s, result, plan, dry_run=dry_run)
    return 0 if result.status in (UNCHANGED, ACCEPTED) else 1
