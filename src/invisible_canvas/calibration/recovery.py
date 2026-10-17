"""Automatic calibration recovery after the setup moved (brain.md D39). Pure: no camera, no GUI.

The setup check (D28/D32) refuses a calibration whose corners are no longer where it saw them. This
module turns that refusal into a new calibration, built and accepted only from fresh evidence, with
the existing parts and thresholds:

1. corners: the four corners just detected by the refused setup check (whole-frame detection, D29:
   their old camera positions are never used), checked by `associate_corners` (missing, ambiguous,
   unstable, duplicate, not convex, wrong order, mirrored) and fitted by `Calibration.create`;
2. check target: the held-out check target must map back within `required_max_px` (D30);
3. validation: the 20 held-out grid targets, detected and mapped through the candidate, must meet
   the A7 required limits (mean and max), exactly as `validate` judges a calibration;
4. confirmation: the setup check is run again, now against the candidate, after the validation; it
   must pass with the usual limit, so the setup did not move while the candidate was being measured.

Only an accepted candidate may be committed (`commit_recovery`), and only if `current.json` still
holds the calibration that was refused; the previous calibration stays in the history. A failure at
any step leaves the calibration directory untouched and says why, with hints for the operator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ..geometry.homography import GeometryError
from ..mapping.mapper import CoordinateMapper
from .auto import (AutoCalibrationError, Measure, TargetMeasurement, ValidationResult, associate_corners,
                   auto_setup_check, measure_targets, screen_for, validation_result, verify_check_target)
from .metrics import SetupCheck
from .store import Calibration, CalibrationError, archive_calibration, load_calibration, save_calibration
from .targets import CORNER_NAMES

UNCHANGED, ACCEPTED, FAILED = "unchanged", "accepted", "failed"

# Operator hints for the detector's and the checks' reasons (substring -> hint), most specific first.
HINTS = (
    ("cut off by the image border", "a marker is at or beyond the edge of the camera image: the camera no longer "
                                    "sees the whole projection; re-aim it so the projection is inside the frame "
                                    "with a margin"),
    ("extends beyond the search window", "a marker is larger than expected: check the camera distance and focus"),
    ("no projected target", "the camera cannot see the projected marker clearly enough (low contrast): dim the "
                            "room light, check projector focus and brightness, and check that the projection is "
                            "in the camera view"),
    ("crosses in the search area", "more than one marker-like pattern: reflections, a second projection or a "
                                   "bright object in view"),
    ("no cross found", "no marker shape where one was projected: something in front of the projection (a person, "
                       "a hand, an object), the marker outside the camera view, or the image out of focus"),
    ("single frames accepted", "the marker was not seen steadily: something is still moving (camera, projector, "
                               "surface), or flicker or vibration"),
    ("unstable", "the marker was not seen steadily: something is still moving (camera, projector, surface), or "
                 "flicker or vibration"),
    ("the same cross was seen twice", "two corners were detected at the same place: the projector image did not "
                                      "change between targets"),
    ("quadrilateral", "the detected corners do not form the projection's shape: a corner was found on the wrong "
                      "object, or the camera image is mirrored"),
    ("opposite direction", "the camera image is mirrored relative to the projector, or the corners are assigned "
                           "wrongly"),
    ("check target maps", "the candidate failed its held-out check: wrong corner assignment, or the setup moved "
                          "during recovery"),
    ("held-out validation", "the candidate is not accurate enough across the canvas: the setup may have moved "
                            "during recovery, the surface may not be flat, or detections are biased (glare)"),
    ("moved during recovery", "the setup moved while it was being recalibrated: fix the mounts, wait until "
                              "nothing moves, and run it again"),
)


def explain(messages) -> list[str]:
    """Operator hints for the given failure messages (each hint once, in HINTS order)."""
    text = " ".join(messages)
    hints = []
    for key, hint in HINTS:
        if key in text and hint not in hints:
            hints.append(hint)
    return hints


@dataclass(frozen=True)
class RecoveryPlan:
    """What the candidate is measured and judged with: the existing targets and thresholds."""
    check_target: np.ndarray       # held-out check target (D30), projector px
    grid: np.ndarray               # held-out validation grid (A7), projector px
    grid_cols: int
    grid_rows: int
    setup_limit_px: float          # setup-check limit for the previous calibration's method (D32), camera px
    confirm_limit_px: float        # setup-check limit for the candidate, an automatic calibration (D32)
    required_mean_px: float        # A7 required limits, projector px
    required_max_px: float


@dataclass
class RecoveryResult:
    status: str                                    # UNCHANGED, ACCEPTED or FAILED
    stage: str                                     # the step it ended in
    previous: Calibration
    setup: SetupCheck | None = None                # the setup vs the previous calibration
    corners: list[TargetMeasurement] = field(default_factory=list)
    candidate: Calibration | None = None
    check: TargetMeasurement | None = None
    check_error_px: float | None = None
    validation: ValidationResult | None = None
    validation_measurements: list[TargetMeasurement] = field(default_factory=list)
    confirmation: SetupCheck | None = None         # the setup vs the candidate, after the validation
    confirmation_corners: list[TargetMeasurement] = field(default_factory=list)
    reason: str = ""
    details: list[str] = field(default_factory=list)
    hints: list[str] = field(default_factory=list)

    @property
    def accepted(self) -> bool:
        return self.status == ACCEPTED

    def fail(self, stage: str, error: Exception) -> RecoveryResult:
        """Mark as failed at `stage`, with the error's reason, details and the operator hints."""
        self.status, self.stage, self.reason = FAILED, stage, str(error)
        self.details = list(getattr(error, "details", []))
        self.hints = explain([self.reason, *self.details])
        return self

    def to_report(self, plan: RecoveryPlan) -> dict:
        def setup_dict(c: SetupCheck | None):
            return None if c is None else {"shifts_px": c.shifts, "mean_shift_px": c.mean_shift,
                                           "variation_px": c.variation, "limit_px": c.limit,
                                           "consistent": c.consistent}

        v = self.validation
        validation = None
        if v is not None:
            stats = v.stats
            validation = {
                "stats_px": stats.__dict__, "edge_mean_px": float(v.errors[v.edge].mean()),
                "required": {"mean_px": plan.required_mean_px, "max_px": plan.required_max_px,
                             "pass": stats.meets(plan.required_mean_px, plan.required_max_px)},
                "points": [{"target": t.tolist(), "camera": c.tolist(), "mapped": m.tolist(), "error_px": float(e)}
                           for t, c, m, e in zip(v.targets, v.detected, v.mapped, v.errors)],
            }
        elif self.validation_measurements:
            validation = {"detection": [m.summary() for m in self.validation_measurements]}
        return {
            "status": self.status, "stage": self.stage, "reason": self.reason, "details": self.details,
            "hints": self.hints,
            "previous_calibration": {"created_at": self.previous.created_at, "method": self.previous.method,
                                     "camera_points": self.previous.camera_points.tolist()},
            "setup_check_vs_previous": setup_dict(self.setup),
            "corners": [dict(name=n, **m.summary()) for n, m in zip(CORNER_NAMES, self.corners)],
            "candidate": None if self.candidate is None else self.candidate.to_dict(),
            "check_target": None if self.check is None else {
                "projector": plan.check_target.tolist(), "error_px": self.check_error_px, **self.check.summary()},
            "validation": validation,
            "confirmation_vs_candidate": setup_dict(self.confirmation),
            "confirmation_corners": [dict(name=n, **m.summary())
                                     for n, m in zip(CORNER_NAMES, self.confirmation_corners)],
            "limits": {"setup_px": plan.setup_limit_px, "confirmation_px": plan.confirm_limit_px, "check_target_px": plan.required_max_px,
                       "required_mean_px": plan.required_mean_px, "required_max_px": plan.required_max_px},
        }


def recover_calibration(measure: Measure, previous: Calibration, setup: SetupCheck,
                        corners: list[TargetMeasurement], plan: RecoveryPlan, *, canvas_size, camera_size,
                        camera_name: str, projector_name: str) -> RecoveryResult:
    """Steps 1-4 (module docstring), starting from a setup check that refused `previous`. `corners` are
    that check's four measurements of `previous.projector_points`. Nothing is saved here."""
    result = RecoveryResult(UNCHANGED, "setup check", previous, setup, list(corners))
    if setup.consistent:
        return result
    try:
        points = associate_corners(corners, previous.projector_points, camera_size)
        candidate = Calibration.create(method="auto", camera_name=camera_name, camera_size=camera_size,
                                       projector_name=projector_name, projector_size=canvas_size,
                                       projector_points=previous.projector_points, camera_points=points)
    except (AutoCalibrationError, GeometryError) as e:
        return result.fail("corners", e)
    result.candidate = candidate

    try:
        result.check = measure(screen_for(canvas_size, [plan.check_target], 0, show_others=False))
        result.check_error_px = verify_check_target(candidate.homography, result.check, plan.check_target,
                                                    plan.required_max_px)
    except AutoCalibrationError as e:
        return result.fail("check target", e)

    result.validation_measurements = measure_targets(measure, canvas_size, plan.grid, show_others=False)
    try:
        result.validation = validation_result(CoordinateMapper.from_calibration(candidate), plan.grid,
                                              result.validation_measurements, plan.grid_cols, plan.grid_rows)
    except AutoCalibrationError as e:
        return result.fail("validation", e)
    stats = result.validation.stats
    if not stats.meets(plan.required_mean_px, plan.required_max_px):
        return result.fail("validation", AutoCalibrationError(
            f"held-out validation failed: mean {stats.mean:.2f} / max {stats.max:.2f} projector px "
            f"(required <= {plan.required_mean_px:g} / <= {plan.required_max_px:g})"))

    try:
        result.confirmation, result.confirmation_corners = auto_setup_check(measure, candidate, canvas_size,
                                                                            plan.confirm_limit_px)
    except AutoCalibrationError as e:
        return result.fail("confirmation", e)
    if not result.confirmation.consistent:
        return result.fail("confirmation", AutoCalibrationError(
            f"the setup moved during recovery: the corners changed by {result.confirmation.variation:.2f} camera px "
            f"(setup-check metric, limit {plan.confirm_limit_px:g}) between the candidate and the end of its validation"))
    result.status, result.stage = ACCEPTED, "accepted"
    return result


def check_and_recover(measure: Measure, previous: Calibration, plan: RecoveryPlan, *, canvas_size, camera_size,
                      camera_name: str, projector_name: str) -> RecoveryResult:
    """The setup check against `previous`, then, only if it refuses, `recover_calibration`."""
    try:
        setup, corners = auto_setup_check(measure, previous, canvas_size, plan.setup_limit_px)
    except AutoCalibrationError as e:
        return RecoveryResult(FAILED, "setup check", previous).fail("setup check", e)
    return recover_calibration(measure, previous, setup, corners, plan, canvas_size=canvas_size,
                               camera_size=camera_size, camera_name=camera_name, projector_name=projector_name)


def commit_recovery(result: RecoveryResult, directory: Path) -> Path:
    """Make an accepted candidate the current calibration. Refuses anything else, and refuses if
    `current.json` no longer holds the refused calibration (changed by someone else meanwhile). The
    previous calibration is kept in the history (written there first if it was missing)."""
    if not result.accepted or result.candidate is None:
        raise CalibrationError(f"recovery was not accepted ({result.status}, {result.stage}); nothing saved")
    current = load_calibration(directory)
    if current.to_dict() != result.previous.to_dict():
        raise CalibrationError(f"the current calibration changed during recovery (now {current.created_at}, "
                               f"recovery started from {result.previous.created_at}); nothing saved")
    archive_calibration(result.previous, directory)
    return save_calibration(result.candidate, directory)
