"""Homography estimation and point transforms. Pure numpy, no I/O.

H maps source points to destination points in homogeneous coordinates:

    [x', y', w']^T = H @ [x, y, 1]^T,    mapped point = (x'/w', y'/w')

Pixel centres are at integer coordinates (OpenCV convention) in every space.
For calibration, source = camera pixels and destination = projector pixels.
"""

from __future__ import annotations

import numpy as np


class GeometryError(ValueError):
    """The point configuration cannot give a reliable homography."""


def as_points(points, *, count: int | None = None, min_count: int = 1) -> np.ndarray:
    """Points as a finite float64 array of shape (N, 2)."""
    arr = np.asarray(points, dtype=np.float64)
    if arr.shape == (2,):
        arr = arr.reshape(1, 2)
    if arr.ndim != 2 or arr.shape[1] != 2:
        raise GeometryError(f"expected points of shape (N, 2), got {arr.shape}")
    if count is not None and len(arr) != count:
        raise GeometryError(f"expected {count} points, got {len(arr)}")
    if len(arr) < min_count:
        raise GeometryError(f"expected at least {min_count} points, got {len(arr)}")
    if not np.all(np.isfinite(arr)):
        raise GeometryError("points contain NaN or infinity")
    return arr


def _normalizing_transform(points: np.ndarray) -> np.ndarray:
    """Hartley normalization: centroid to the origin, mean distance sqrt(2)."""
    centroid = points.mean(axis=0)
    mean_distance = np.mean(np.linalg.norm(points - centroid, axis=1))
    if mean_distance < 1e-9:
        raise GeometryError("all points are identical")
    s = np.sqrt(2.0) / mean_distance
    return np.array([[s, 0.0, -s * centroid[0]], [0.0, s, -s * centroid[1]], [0.0, 0.0, 1.0]])


def _normalize_scale(h: np.ndarray) -> np.ndarray:
    if abs(h[2, 2]) > 1e-12:
        return h / h[2, 2]
    return h / np.linalg.norm(h)


def estimate_homography(src, dst) -> np.ndarray:
    """H with dst ~ H @ src from N >= 4 point pairs (normalized DLT).

    Exact for four points in general position, least squares for more.
    Raises GeometryError for degenerate configurations (e.g. three collinear points
    among four), where the solution is not unique.
    """
    src = as_points(src, min_count=4)
    dst = as_points(dst, min_count=4)
    if src.shape != dst.shape:
        raise GeometryError(f"src and dst differ: {src.shape} vs {dst.shape}")
    t_src = _normalizing_transform(src)
    t_dst = _normalizing_transform(dst)
    s = apply_homography(t_src, src)
    d = apply_homography(t_dst, dst)

    n = len(s)
    x, y = s[:, 0], s[:, 1]
    u, v = d[:, 0], d[:, 1]
    zeros, ones = np.zeros(n), np.ones(n)
    a = np.empty((2 * n, 9))
    a[0::2] = np.column_stack([zeros, zeros, zeros, -x, -y, -ones, v * x, v * y, v])
    a[1::2] = np.column_stack([x, y, ones, zeros, zeros, zeros, -u * x, -u * y, -u])

    _, singular_values, vt = np.linalg.svd(a)
    # The solution is the right singular vector of the smallest singular value. If the
    # next-smallest one (index 7) is also ~0 the null space is >1-D: no unique solution.
    if singular_values[7] < 1e-8 * singular_values[0]:
        raise GeometryError("degenerate point configuration (collinear or repeated points)")
    h_normalized = vt[-1].reshape(3, 3)
    # A singular H collapses the plane onto a line: happens when e.g. three source
    # points are collinear but their destinations are not.
    if abs(np.linalg.det(h_normalized)) < 1e-9 * np.linalg.norm(h_normalized) ** 3:
        raise GeometryError("degenerate point configuration (homography is singular)")
    return _normalize_scale(np.linalg.inv(t_dst) @ h_normalized @ t_src)


def apply_homography(h: np.ndarray, points) -> np.ndarray:
    """Map points through H. Points that map to infinity (w ~ 0) become NaN."""
    pts = as_points(points)
    homogeneous = np.column_stack([pts, np.ones(len(pts))]) @ np.asarray(h, dtype=np.float64).T
    w = homogeneous[:, 2:3]
    with np.errstate(divide="ignore", invalid="ignore"):
        mapped = homogeneous[:, :2] / w
    mapped[np.abs(w[:, 0]) < 1e-12] = np.nan
    return mapped


def invert_homography(h: np.ndarray) -> np.ndarray:
    try:
        return _normalize_scale(np.linalg.inv(np.asarray(h, dtype=np.float64)))
    except np.linalg.LinAlgError:
        raise GeometryError("homography is singular") from None


def reprojection_errors(h: np.ndarray, src, dst) -> np.ndarray:
    """Euclidean distance between H(src) and dst for each point pair."""
    return np.linalg.norm(apply_homography(h, src) - as_points(dst), axis=1)


def signed_area(points) -> float:
    """Shoelace area. Positive for TL->TR->BR->BL order in y-down image coordinates."""
    pts = as_points(points, min_count=3)
    x, y = pts[:, 0], pts[:, 1]
    return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def validate_quad(points, *, min_area: float = 1.0, min_sin_angle: float = 0.05) -> np.ndarray:
    """Check that four points form a usable convex, simple quadrilateral.

    Rejects repeated points, self-intersecting (bow-tie) or concave shapes, corners
    flatter than asin(min_sin_angle), and quads smaller than `min_area` px^2.
    Returns the points as an array.
    """
    pts = as_points(points, count=4)
    edges = np.roll(pts, -1, axis=0) - pts
    lengths = np.linalg.norm(edges, axis=1)
    if np.any(lengths < 1e-6):
        raise GeometryError("two consecutive points are identical")
    following = np.roll(edges, -1, axis=0)
    cross = edges[:, 0] * following[:, 1] - edges[:, 1] * following[:, 0]
    if not (np.all(cross > 0) or np.all(cross < 0)):
        raise GeometryError("points do not form a convex quadrilateral in order (check the click order)")
    sin_angles = np.abs(cross) / (lengths * np.roll(lengths, -1))
    if np.any(sin_angles < min_sin_angle):
        raise GeometryError("a corner angle is too flat (points nearly collinear)")
    area = abs(signed_area(pts))
    if area < min_area:
        raise GeometryError(f"quadrilateral area {area:.0f} px^2 is below the minimum {min_area:.0f} px^2")
    return pts
