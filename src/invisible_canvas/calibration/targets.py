"""Where calibration and validation targets are projected (pure, projector pixels)."""

from __future__ import annotations

import numpy as np

CORNER_NAMES = ("top-left", "top-right", "bottom-right", "bottom-left")


def _inset(size: int, fraction: float) -> int:
    return int(round(fraction * (size - 1)))


def corner_targets(width: int, height: int, inset: float) -> np.ndarray:
    """Four integer-pixel targets in TL, TR, BR, BL order, inset from the edges."""
    dx, dy = _inset(width, inset), _inset(height, inset)
    right, bottom = width - 1 - dx, height - 1 - dy
    return np.array([[dx, dy], [right, dy], [right, bottom], [dx, bottom]], dtype=np.float64)


def grid_targets(width: int, height: int, cols: int, rows: int, inset: float) -> np.ndarray:
    """cols x rows integer-pixel targets, row-major from the top-left."""
    dx, dy = _inset(width, inset), _inset(height, inset)
    xs = np.round(np.linspace(dx, width - 1 - dx, cols))
    ys = np.round(np.linspace(dy, height - 1 - dy, rows))
    return np.array([[x, y] for y in ys for x in xs], dtype=np.float64)


def min_distance(points_a: np.ndarray, points_b: np.ndarray) -> float:
    """Smallest distance between any point of A and any point of B."""
    diff = points_a[:, None, :] - points_b[None, :, :]
    return float(np.min(np.linalg.norm(diff, axis=2)))
