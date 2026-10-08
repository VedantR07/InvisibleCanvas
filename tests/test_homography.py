import cv2
import numpy as np
import pytest

from invisible_canvas.geometry.homography import (
    GeometryError,
    apply_homography,
    estimate_homography,
    invert_homography,
    reprojection_errors,
    signed_area,
    validate_quad,
)

# A realistic camera->projector mapping: scale, slight rotation/shear, perspective.
H_TRUE = np.array([
    [1.12, 0.05, -140.0],
    [0.02, 1.08, -60.0],
    [1.2e-5, 3.0e-5, 1.0],
])
# Where the projected canvas corners might appear in a 1920x1080 camera frame.
CAMERA_QUAD = np.array([[300.0, 180.0], [1620.0, 210.0], [1580.0, 930.0], [340.0, 900.0]])


def interior_points(n=50, seed=0):
    rng = np.random.default_rng(seed)
    return np.column_stack([rng.uniform(350, 1550, n), rng.uniform(220, 880, n)])


def test_four_points_recover_known_homography_exactly():
    projector_quad = apply_homography(H_TRUE, CAMERA_QUAD)
    h = estimate_homography(CAMERA_QUAD, projector_quad)
    assert np.allclose(h, H_TRUE, rtol=1e-9, atol=1e-12)
    pts = interior_points()
    assert np.max(np.abs(apply_homography(h, pts) - apply_homography(H_TRUE, pts))) < 1e-6


def test_agrees_with_opencv_get_perspective_transform():
    projector_quad = apply_homography(H_TRUE, CAMERA_QUAD)
    h_cv = cv2.getPerspectiveTransform(CAMERA_QUAD.astype(np.float32), projector_quad.astype(np.float32))
    h = estimate_homography(CAMERA_QUAD, projector_quad)
    pts = interior_points()
    # OpenCV takes float32 inputs, so agreement is limited to ~1e-3 px.
    assert np.max(np.abs(apply_homography(h, pts) - apply_homography(h_cv, pts))) < 1e-2


def test_least_squares_averages_out_click_noise():
    rng = np.random.default_rng(1)
    camera = interior_points(30, seed=2)
    projector = apply_homography(H_TRUE, camera) + rng.normal(0.0, 0.5, (30, 2))
    h = estimate_homography(camera, projector)
    test = interior_points(200, seed=3)
    error = np.linalg.norm(apply_homography(h, test) - apply_homography(H_TRUE, test), axis=1)
    assert error.mean() < 0.3


def test_identity():
    h = estimate_homography(CAMERA_QUAD, CAMERA_QUAD)
    assert np.allclose(h, np.eye(3), atol=1e-12)


def test_inverse_round_trip():
    h_inv = invert_homography(H_TRUE)
    pts = interior_points()
    assert np.allclose(apply_homography(h_inv, apply_homography(H_TRUE, pts)), pts, atol=1e-9)
    assert h_inv[2, 2] == pytest.approx(1.0)


def test_reprojection_errors():
    projector = apply_homography(H_TRUE, CAMERA_QUAD)
    shifted = projector + np.array([[3.0, 4.0], [0, 0], [0, 0], [0, 0]])
    assert np.allclose(reprojection_errors(H_TRUE, CAMERA_QUAD, shifted), [5.0, 0, 0, 0])


def test_rejects_repeated_points():
    src = np.array([[0.0, 0], [0, 0], [100, 100], [0, 100]])
    with pytest.raises(GeometryError):
        estimate_homography(src, CAMERA_QUAD)


def test_rejects_three_collinear_points_on_both_sides():
    src = np.array([[0.0, 0], [50, 0], [100, 0], [0, 100]])
    dst = np.array([[0.0, 0], [60, 0], [120, 0], [0, 90]])
    with pytest.raises(GeometryError):
        estimate_homography(src, dst)


def test_rejects_collinear_source_with_non_collinear_destination():
    src = np.array([[0.0, 0], [50, 0], [100, 0], [0, 100]])
    dst = np.array([[0.0, 0], [100, 0], [100, 100], [0, 100]])
    with pytest.raises(GeometryError):
        estimate_homography(src, dst)


@pytest.mark.parametrize(
    "src,dst",
    [
        (CAMERA_QUAD[:3], CAMERA_QUAD[:3]),           # too few points
        (CAMERA_QUAD, CAMERA_QUAD[:3]),               # shape mismatch
        (np.full((4, 2), np.nan), CAMERA_QUAD),       # NaN
        (np.zeros((4, 3)), CAMERA_QUAD),              # wrong shape
    ],
)
def test_rejects_bad_input(src, dst):
    with pytest.raises(GeometryError):
        estimate_homography(src, dst)


def test_point_at_infinity_maps_to_nan():
    h = np.array([[1.0, 0, 0], [0, 1.0, 0], [1.0, 0, 0]])  # w = x
    mapped = apply_homography(h, [[0.0, 5.0], [2.0, 4.0]])
    assert np.all(np.isnan(mapped[0]))
    assert np.allclose(mapped[1], [1.0, 2.0])


def test_invert_singular_raises():
    with pytest.raises(GeometryError):
        invert_homography(np.zeros((3, 3)))


def test_signed_area_orientation():
    tl_tr_br_bl = [[0, 0], [10, 0], [10, 10], [0, 10]]
    assert signed_area(tl_tr_br_bl) == pytest.approx(100.0)
    assert signed_area(tl_tr_br_bl[::-1]) == pytest.approx(-100.0)


def test_validate_quad_accepts_perspective_quad_in_either_orientation():
    validate_quad(CAMERA_QUAD)
    validate_quad(CAMERA_QUAD[::-1])


@pytest.mark.parametrize(
    "quad",
    [
        [[0, 0], [100, 100], [100, 0], [0, 100]],    # bow-tie: clicked in the wrong order
        [[0, 0], [100, 0], [30, 30], [0, 100]],      # concave
        [[0, 0], [100, 0], [200, 0.5], [0, 100]],    # flat corner, nearly collinear
        [[0, 0], [0, 0], [100, 100], [0, 100]],      # repeated point
    ],
)
def test_validate_quad_rejects_bad_shapes(quad):
    with pytest.raises(GeometryError):
        validate_quad(quad)


def test_validate_quad_rejects_small_area():
    with pytest.raises(GeometryError, match="area"):
        validate_quad([[0, 0], [10, 0], [10, 10], [0, 10]], min_area=1000)


def test_validate_quad_requires_four_points():
    with pytest.raises(GeometryError):
        validate_quad(CAMERA_QUAD[:3])
