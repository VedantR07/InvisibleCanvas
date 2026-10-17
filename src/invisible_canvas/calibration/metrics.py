"""Accuracy and repeatability statistics (pure). Definitions: brain.md section 9.6."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class AccuracyStats:
    count: int
    mean: float
    median: float
    p95: float
    max: float
    rms: float

    def meets(self, mean_limit: float, max_limit: float) -> bool:
        return self.mean <= mean_limit and self.max <= max_limit


def accuracy_stats(errors) -> AccuracyStats:
    e = np.asarray(errors, dtype=np.float64)
    if e.ndim != 1 or len(e) == 0 or not np.all(np.isfinite(e)):
        raise ValueError("errors must be a non-empty 1-D array of finite values")
    return AccuracyStats(
        count=len(e),
        mean=float(e.mean()),
        median=float(np.median(e)),
        p95=float(np.percentile(e, 95)),
        max=float(e.max()),
        rms=float(np.sqrt(np.mean(e**2))),
    )


@dataclass(frozen=True)
class RepeatabilityStats:
    runs: int
    mean_variation: float           # mean over corners and runs of |c - corner mean|
    max_variation: float
    per_corner_mean: tuple[float, ...]


def corner_repeatability(corner_sets) -> RepeatabilityStats:
    """Variation of the clicked camera corners across repeated calibrations.

    `corner_sets` has shape (runs, corners, 2). For each corner k the mean position
    m_k over runs is taken; the variation of run r is |c_kr - m_k|.
    """
    c = np.asarray(corner_sets, dtype=np.float64)
    if c.ndim != 3 or c.shape[2] != 2 or c.shape[0] < 2:
        raise ValueError("need an array of shape (runs >= 2, corners, 2)")
    deviation = np.linalg.norm(c - c.mean(axis=0, keepdims=True), axis=2)  # (runs, corners)
    return RepeatabilityStats(
        runs=c.shape[0],
        mean_variation=float(deviation.mean()),
        max_variation=float(deviation.max()),
        per_corner_mean=tuple(float(v) for v in deviation.mean(axis=0)),
    )


@dataclass(frozen=True)
class SetupCheck:
    shifts: tuple[tuple[float, float], ...]   # fresh - calibration, per corner (camera px)
    mean_shift: tuple[float, float]
    variation: float                          # corner_repeatability of the two sets
    limit: float

    @property
    def consistent(self) -> bool:
        return self.variation <= self.limit


def setup_check(calibration_points, fresh_points, limit: float) -> SetupCheck:
    """Does the setup still match the calibration? (brain.md D28)

    The calibration corners are clicked again and compared with the saved clicks using the
    repeatability metric (A6), so "same setup" means the same as for repeated calibrations.
    A moved camera or projector shows up here, before it shows up as a mapping error.
    """
    calibration = np.asarray(calibration_points, dtype=np.float64)
    fresh = np.asarray(fresh_points, dtype=np.float64)
    if calibration.shape != fresh.shape:
        raise ValueError(f"point sets differ in shape: {calibration.shape} vs {fresh.shape}")
    shifts = fresh - calibration
    return SetupCheck(
        shifts=tuple((float(dx), float(dy)) for dx, dy in shifts),
        mean_shift=(float(shifts[:, 0].mean()), float(shifts[:, 1].mean())),
        variation=corner_repeatability([calibration, fresh]).mean_variation,
        limit=float(limit),
    )
