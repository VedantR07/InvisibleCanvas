"""Regression tests from the 2026-10-09 validation FAIL (mean 5.87 px, all errors down-right).

Finding: the mapping chain is consistent; the calibration's corner clicks no longer matched
the scene (setup moved ~5 camera px after calibration). These tests pin both facts and the
setup check that now runs before `validate` (brain.md D28).
"""

import cv2
import numpy as np
import pytest

from invisible_canvas.calibration.metrics import corner_repeatability, setup_check
from invisible_canvas.calibration.targets import corner_targets, grid_targets
from invisible_canvas.display import patterns
from invisible_canvas.geometry.homography import apply_homography, estimate_homography

CANVAS = (1280, 720)
CAMERA = (1920, 1080)
# Camera -> projector, close to the real 2026-10-09 calibration (mild perspective, rotation).
H_TRUE = np.array([
    [0.9193, -0.01734, -241.15],
    [0.05485, 0.8773, -187.47],
    [5.837e-05, 2.885e-05, 1.0],
])
CORNERS = corner_targets(*CANVAS, 0.06)
GRID = grid_targets(*CANVAS, 5, 4, 0.04)


def camera_position(projector_points):
    """Where the camera sees projector points (inverse of camera -> projector)."""
    return apply_homography(np.linalg.inv(H_TRUE), projector_points)


def _seen_centre_mapped_back(h, target):
    projected = patterns.target_screen(CANVAS, np.array([target], float), 0, None, show_others=False)
    # Camera pixel (x, y) shows projector pixel h(x, y) (pixel centres at integers).
    seen = cv2.warpPerspective(projected, h, CAMERA, flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP)
    grey = cv2.cvtColor(seen, cv2.COLOR_BGR2GRAY).astype(np.float64)
    ys, xs = np.nonzero(grey)
    w = grey[ys, xs]
    centroid = [(xs * w).sum() / w.sum(), (ys * w).sum() / w.sum()]
    return apply_homography(h, [centroid])[0]


@pytest.mark.parametrize("target", [[640, 360], [345, 249], [1202, 676]])
def test_projected_target_centre_maps_back_to_its_pixel(target):
    """Target drawing, pixel-centre convention and H direction agree: the centroid of a target
    as the camera sees it, mapped camera -> projector, is the target's integer pixel.
    A half-pixel convention slip would show as ~0.5 px here."""
    affine = H_TRUE.copy()
    affine[2] = [0.0, 0.0, 1.0]
    assert np.allclose(_seen_centre_mapped_back(affine, target), target, atol=0.05)
    # With perspective the centroid of a symmetric shape shifts slightly (measured ~0.13 px for
    # the 39-px ring), far below the 4-5 px of the 2026-10-09 failure.
    assert np.allclose(_seen_centre_mapped_back(H_TRUE, target), target, atol=0.2)


def test_constant_click_bias_cancels():
    """A click offset shared by calibration and validation is absorbed by H exactly, so a
    uniform validation error cannot come from a consistent clicking habit."""
    bias = np.array([5.5, 4.9])
    h = estimate_homography(camera_position(CORNERS) + bias, CORNERS)
    errors = apply_homography(h, camera_position(GRID) + bias) - GRID
    assert np.abs(errors).max() < 1e-6


def test_setup_moved_after_calibration_gives_a_uniform_down_right_error():
    """The incident: calibration clicked before the scene moved ~5 camera px down-right,
    validation clicked after. Every validation error points down-right."""
    moved = np.array([5.5, 4.9])
    h = estimate_homography(camera_position(CORNERS), CORNERS)
    errors = apply_homography(h, camera_position(GRID) + moved) - GRID
    assert np.all(errors[:, 0] > 0) and np.all(errors[:, 1] > 0)
    assert 4.0 < np.linalg.norm(errors, axis=1).mean() < 8.0
    # Nearly a pure translation: removing the mean error leaves little.
    assert np.linalg.norm(errors - errors.mean(axis=0), axis=1).max() < 1.0


def test_setup_check_flags_a_moved_setup_and_accepts_click_noise():
    calibration = camera_position(CORNERS)
    moved = setup_check(calibration, calibration + [5.5, 4.9], limit=2.0)
    assert not moved.consistent
    assert moved.mean_shift == pytest.approx((5.5, 4.9))
    assert moved.variation == pytest.approx(np.hypot(5.5, 4.9) / 2)
    noise = np.array([[0.6, -0.4], [-0.5, 0.7], [0.3, 0.5], [-0.7, -0.2]])
    assert setup_check(calibration, calibration + noise, limit=2.0).consistent


def test_setup_check_uses_the_repeatability_metric():
    calibration = camera_position(CORNERS)
    fresh = calibration + [[1.0, 2.0], [-3.0, 0.5], [0.0, -1.0], [2.0, 2.0]]
    assert setup_check(calibration, fresh, limit=2.0).variation == pytest.approx(
        corner_repeatability([calibration, fresh]).mean_variation)


def test_setup_check_on_the_2026_10_09_measurements():
    """Saved corner clicks (19:53) vs the corner centres detected at 20:09 (scene unchanged
    since 19:59): flagged. The three calibrations of 19:46-19:53 among themselves: consistent."""
    clicks_1953 = [[352.95, 241.99], [1709.42, 160.95], [1759.29, 975.08], [369.16, 1000.02]]
    detected_2009 = [[359.57, 248.28], [1713.44, 164.43], [1764.33, 978.67], [375.59, 1006.24]]
    check = setup_check(clicks_1953, detected_2009, limit=2.0)
    assert not check.consistent and check.variation > 3.0
    runs = [
        [[352.95, 241.99], [1710.67, 158.46], [1758.05, 975.08], [369.16, 1001.27]],
        [[352.95, 240.75], [1710.67, 159.71], [1759.29, 975.08], [367.92, 1000.02]],
        clicks_1953,
    ]
    for a in runs:
        for b in runs:
            assert setup_check(a, b, limit=2.0).consistent


def test_every_target_cross_is_inside_the_canvas():
    """Operators click the cross; it must be complete for every calibration and validation
    target (the ring may be clipped at the 4 % validation inset, the cross is not)."""
    arm, half_thickness = 26, 1
    for x, y in np.vstack([CORNERS, GRID]):
        assert arm <= x <= CANVAS[0] - 1 - arm and arm <= y <= CANVAS[1] - 1 - arm
        assert half_thickness <= x and half_thickness <= y
