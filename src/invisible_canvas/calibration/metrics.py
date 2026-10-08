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
