"""Automatic calibration and validation logic (Phase 1C, brain.md D30). Pure: no camera, no GUI.

The camera side is a `measure(screen)` callable: it projects `screen` (a projector image),
captures a background and frames, and returns a TargetMeasurement. The tools pass a real
camera measurement; tests pass a synthetic one. Coordinates follow the existing conventions:
camera px and projector px, pixel centres at integers; H is fitted by Calibration.create()
(the existing normalized DLT) from the 4 corners only.

Nothing here falls back to clicks, old calibration points or guesses: any failure raises
AutoCalibrationError with a reason per target.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Callable

import numpy as np

from ..display import patterns
from ..geometry.homography import GeometryError, apply_homography, signed_area, validate_quad
from .detect import CrossDetection, CrossParams, detect_cross
from .metrics import SetupCheck, accuracy_stats, setup_check
from .targets import CORNER_NAMES

# Per-target quality gate, from the Phase 1B stability criterion B3 (D29).
MIN_SINGLE_FRACTION = 0.8      # of the single frames must be accepted
MAX_SINGLE_SD_PX = 0.3         # camera px
MAX_SINGLE_SPREAD_PX = 1.0     # max distance of a single-frame centre from their mean


class AutoCalibrationError(RuntimeError):
    """Automatic detection could not produce trustworthy points. Nothing is saved."""

    def __init__(self, message: str, details: list[str] | None = None):
        super().__init__(message)
        self.details = details or []


@dataclass(frozen=True)
class TargetMeasurement:
    detection: CrossDetection          # on the averaged frame (the centre that is used)
    single_centres: np.ndarray         # (k, 2) accepted single-frame centres
    single_frames: int
    single_rejections: dict            # reason -> count

    @property
    def single_sd(self) -> float | None:
        return float(self.single_centres.std(axis=0, ddof=1).max()) if len(self.single_centres) > 1 else None

    @property
    def single_spread(self) -> float | None:
        c = self.single_centres
        return float(np.linalg.norm(c - c.mean(axis=0), axis=1).max()) if len(c) else None

    @property
    def problem(self) -> str:
        """Why this measurement cannot be used ('' if it can)."""
        if not self.detection.ok:
            return self.detection.reason
        accepted = len(self.single_centres)
        if accepted < MIN_SINGLE_FRACTION * self.single_frames:
            return (f"only {accepted} of {self.single_frames} single frames accepted "
                    f"({', '.join(f'{k}: {v}' for k, v in self.single_rejections.items())})")
        if self.single_sd is not None and self.single_sd > MAX_SINGLE_SD_PX:
            return f"unstable: single-frame sd {self.single_sd:.2f} px > {MAX_SINGLE_SD_PX}"
        if self.single_spread is not None and self.single_spread > MAX_SINGLE_SPREAD_PX:
            return f"unstable: a single frame is {self.single_spread:.2f} px from the mean > {MAX_SINGLE_SPREAD_PX}"
        return ""

    @property
    def ok(self) -> bool:
        return not self.problem

    @property
    def center(self) -> np.ndarray:
        return np.array(self.detection.center, dtype=np.float64)

    def summary(self) -> dict:
        d = self.detection
        return {
            "ok": self.ok, "problem": self.problem, "center": d.center, "reason": d.reason,
            "contrast": d.contrast, "line_residual_px": d.line_residual_px, "half_arm_balance": d.half_arm_balance,
            "arm_angle_deg": d.arm_angle_deg, "fit_sigma_px": d.fit_sigma_px,
            "single_frames": self.single_frames, "single_accepted": int(len(self.single_centres)),
            "single_sd_px": self.single_sd, "single_spread_px": self.single_spread,
            "single_rejections": dict(self.single_rejections),
        }


Measure = Callable[[np.ndarray], TargetMeasurement]


def measurement_from_frames(background, frames, *, params: CrossParams = CrossParams(),
                            window: dict | None = None) -> TargetMeasurement:
    """Detect on the averaged frame and on every single frame (each against the background)."""
    if len(frames) == 0:
        raise ValueError("no frames")
    window = window or {}
    average = np.mean(np.stack([np.asarray(f, np.float32) for f in frames]), axis=0)
    detection = detect_cross(average, background=background, params=params, **window)
    singles = [detect_cross(f, background=background, params=params, **window) for f in frames]
    centres = np.array([s.center for s in singles if s.ok], dtype=np.float64).reshape(-1, 2)
    rejections = Counter(s.reason.split(" (")[0] for s in singles if not s.ok)
    return TargetMeasurement(detection, centres, len(frames), dict(rejections))


def screen_for(canvas_size, targets, index: int, *, show_others: bool) -> np.ndarray:
    """The detection screen: the existing target rendering, without label text (D29)."""
    return patterns.target_screen(canvas_size, np.asarray(targets, float), index, None, show_others=show_others)


def measure_targets(measure: Measure, canvas_size, targets, *, show_others: bool) -> list[TargetMeasurement]:
    return [measure(screen_for(canvas_size, targets, i, show_others=show_others)) for i in range(len(targets))]


def _require_all(measurements: list[TargetMeasurement], names: list[str], what: str) -> None:
    bad = [f"{name}: {m.problem}" for name, m in zip(names, measurements) if not m.ok]
    if bad:
        raise AutoCalibrationError(f"{len(bad)} of {len(measurements)} {what} not detected reliably", bad)


def associate_corners(measurements: list[TargetMeasurement], projector_corners, camera_size,
                      *, min_separation_px: float | None = None) -> np.ndarray:
    """Camera points for the corners TL, TR, BR, BL (each measured while only its own target was
    shown), after checking that they can only be those corners:
    - every corner detected reliably (missing / ambiguous / unstable -> rejected),
    - no two detections at the same place (a stale frame or a projector that did not update),
    - a convex quadrilateral in the same cyclic order as the projector corners and with the same
      orientation (a swapped or mirrored assignment is rejected).
    A cyclic relabelling passes these checks; the check target catches it (verify_check_target)."""
    projector_corners = np.asarray(projector_corners, dtype=np.float64)
    if len(measurements) != 4 or projector_corners.shape != (4, 2):
        raise ValueError("need 4 corner measurements and 4 projector corners")
    _require_all(measurements, list(CORNER_NAMES), "calibration corners")
    points = np.array([m.center for m in measurements])
    cw, ch = camera_size
    if min_separation_px is None:
        min_separation_px = 0.05 * min(cw, ch)
    for i in range(4):
        for j in range(i + 1, 4):
            d = float(np.linalg.norm(points[i] - points[j]))
            if d < min_separation_px:
                raise AutoCalibrationError(
                    f"{CORNER_NAMES[i]} and {CORNER_NAMES[j]} were detected {d:.1f} camera px apart "
                    f"(< {min_separation_px:.0f}): the same cross was seen twice")
    try:
        validate_quad(points, min_area=0.01 * cw * ch)
    except GeometryError as e:
        raise AutoCalibrationError(f"detected corners are not a usable quadrilateral in TL-TR-BR-BL order: {e}") from None
    if np.sign(signed_area(points)) != np.sign(signed_area(projector_corners)):
        raise AutoCalibrationError("detected corners run in the opposite direction to the projector corners "
                                   "(mirrored camera image or wrong assignment)")
    return points


def verify_check_target(h: np.ndarray, measurement: TargetMeasurement, check_target, limit_px: float) -> float:
    """Map the check target's detected centre through the new H; it must land on the check target."""
    if not measurement.ok:
        raise AutoCalibrationError(f"check target not detected reliably: {measurement.problem}")
    mapped = apply_homography(h, [measurement.center])[0]
    error = float(np.linalg.norm(mapped - np.asarray(check_target, dtype=np.float64)))
    if not np.isfinite(error) or error > limit_px:
        raise AutoCalibrationError(
            f"check target maps to ({mapped[0]:.1f}, {mapped[1]:.1f}), {error:.1f} projector px from where it was "
            f"projected (limit {limit_px:g}): the corners are assigned wrongly or the setup moved during calibration")
    return error


def auto_setup_check(measure: Measure, calibration, canvas_size, limit_px: float
                     ) -> tuple[SetupCheck, list[TargetMeasurement]]:
    """D28 with detection instead of clicks: the 4 calibration corners are detected again and
    compared with the calibration's camera points (repeatability metric, same limit)."""
    measurements = measure_targets(measure, canvas_size, calibration.projector_points, show_others=True)
    _require_all(measurements, list(CORNER_NAMES), "calibration corners (setup check)")
    fresh = np.array([m.center for m in measurements])
    return setup_check(calibration.camera_points, fresh, limit_px), measurements


@dataclass(frozen=True)
class ValidationResult:
    targets: np.ndarray
    detected: np.ndarray       # camera px
    mapped: np.ndarray         # projector px
    errors: np.ndarray         # projector px
    edge: np.ndarray           # bool per target

    @property
    def stats(self):
        return accuracy_stats(self.errors)


def grid_edge_mask(count: int, cols: int, rows: int) -> np.ndarray:
    r, c = np.divmod(np.arange(count), cols)
    return (r == 0) | (r == rows - 1) | (c == 0) | (c == cols - 1)


def validation_result(mapper, targets, measurements: list[TargetMeasurement], cols: int, rows: int) -> ValidationResult:
    """Errors of the detected held-out targets mapped through the calibration (no clicks)."""
    targets = np.asarray(targets, dtype=np.float64)
    names = [f"point {i + 1} at ({x:.0f}, {y:.0f})" for i, (x, y) in enumerate(targets)]
    _require_all(measurements, names, "validation targets")
    detected = np.array([m.center for m in measurements])
    mapped = mapper.camera_to_projector(detected)
    errors = np.linalg.norm(mapped - targets, axis=1)
    return ValidationResult(targets, detected, mapped, errors, grid_edge_mask(len(targets), cols, rows))
