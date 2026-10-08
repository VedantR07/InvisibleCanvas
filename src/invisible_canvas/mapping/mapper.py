"""Coordinate Mapper: camera space C <-> projector/canvas space P (brain.md section 4).

Phase 1 implements C <-> P only. The view/reach transform P -> L (logical canvas,
Teacher Reach) is applied after this mapper in a later phase, so calibration never
changes because of it.
"""

from __future__ import annotations

import numpy as np

from ..geometry.homography import apply_homography, as_points, invert_homography


class CoordinateMapper:
    def __init__(self, camera_to_projector: np.ndarray, canvas_size: tuple[int, int]):
        self._h = np.asarray(camera_to_projector, dtype=np.float64)
        if self._h.shape != (3, 3):
            raise ValueError(f"homography must be 3x3, got {self._h.shape}")
        self._h_inv = invert_homography(self._h)
        self.canvas_size = (int(canvas_size[0]), int(canvas_size[1]))

    @classmethod
    def from_calibration(cls, calibration) -> CoordinateMapper:
        return cls(calibration.homography, calibration.projector_size)

    @property
    def homography(self) -> np.ndarray:
        return self._h.copy()

    def camera_to_projector(self, points) -> np.ndarray:
        """(N, 2) camera pixels -> (N, 2) projector pixels."""
        return apply_homography(self._h, points)

    def projector_to_camera(self, points) -> np.ndarray:
        """(N, 2) projector pixels -> (N, 2) camera pixels."""
        return apply_homography(self._h_inv, points)

    def map_point(self, x: float, y: float) -> tuple[float, float]:
        px, py = self.camera_to_projector([[x, y]])[0]
        return float(px), float(py)

    def inside_canvas(self, projector_points) -> np.ndarray:
        """True where a projector point lies on the canvas. Pixel centres are at
        integers, so the canvas covers [-0.5, w - 0.5) x [-0.5, h - 0.5)."""
        pts = as_points(projector_points)
        w, h = self.canvas_size
        return (pts[:, 0] >= -0.5) & (pts[:, 0] < w - 0.5) & (pts[:, 1] >= -0.5) & (pts[:, 1] < h - 0.5)

    def canvas_outline_in_camera(self) -> np.ndarray:
        """The four canvas edge corners (TL, TR, BR, BL) in camera pixels."""
        w, h = self.canvas_size
        corners = [[-0.5, -0.5], [w - 0.5, -0.5], [w - 0.5, h - 0.5], [-0.5, h - 0.5]]
        return self.projector_to_camera(corners)
