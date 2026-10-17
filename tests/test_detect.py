"""Cross detector (calibration/detect.py) on synthetic camera images.

Images are the real projector rendering (patterns.target_screen) warped into a camera view by a
known homography, with camera-like blur, gain, ambient light and noise, so the true centre is
known exactly. These tests check the algorithm; they are not evidence of real-camera
performance (that is measured by `python -m invisible_canvas detect`, brain.md D29).
"""

import cv2
import numpy as np
import pytest

from invisible_canvas.calibration.detect import CrossDetection, DetectionError, detect_cross
from invisible_canvas.calibration.targets import corner_targets, grid_targets
from invisible_canvas.display import patterns
from invisible_canvas.geometry.homography import apply_homography, estimate_homography

CANVAS = (1280, 720)
CAMERA = (1920, 1080)
# Camera -> projector, like the 2026-10-09 setup (mild perspective, ~3 deg roll).
H_REAL = np.array([
    [0.9193, -0.01734, -241.15],
    [0.05485, 0.8773, -187.47],
    [5.837e-05, 2.885e-05, 1.0],
])


def _keystone(width_ratio):
    """Canvas seen as a trapezoid whose bottom is `width_ratio` times wider than its top."""
    top, bottom = 1100 / width_ratio ** 0.5, 1100 * width_ratio ** 0.5
    camera = [[960 - top / 2, 220], [960 + top / 2, 240], [960 + bottom / 2, 960], [960 - bottom / 2, 940]]
    return estimate_homography(camera, [[0, 0], [1279, 0], [1279, 719], [0, 719]])


# The real setup is ~1.03; 1.4 is a camera far off-axis. 1.85 is beyond the supported range:
# opposite half-arms then differ by > 40 % and such crosses are rejected (measured: up to 1.6
# all 24 targets are detected).
H_STRONG = _keystone(1.4)
H_EXTREME = _keystone(1.85)
CORNERS = corner_targets(*CANVAS, 0.06)
GRID = grid_targets(*CANVAS, 5, 4, 0.04)


def projector_image(targets, active=0, labels=None, show_others=False):
    return patterns.target_screen(CANVAS, np.asarray(targets, float), active, labels, show_others=show_others)


def camera_view(projected, h=H_REAL, *, blur=0.8, gain=1.0, ambient=0.0, gradient=0.0, noise=0.0, seed=0):
    """What the camera sees: warp (pixel centres at integers), blur, gain, ambient light, noise."""
    cam = cv2.warpPerspective(projected, h, CAMERA, flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP)
    cam = cv2.cvtColor(cam, cv2.COLOR_BGR2GRAY).astype(np.float64)
    if blur:
        cam = cv2.GaussianBlur(cam, (0, 0), blur)
    ramp = np.linspace(0.0, 1.0, CAMERA[0])[None, :] * gradient
    cam = cam * gain + ambient + ramp
    if noise:
        cam = cam + np.random.default_rng(seed).normal(0.0, noise, cam.shape)
    return np.clip(np.round(cam), 0, 255).astype(np.uint8)


def truth(target, h=H_REAL):
    """The exact camera position of a projector pixel."""
    return apply_homography(np.linalg.inv(h), [target])[0]


def error(detection: CrossDetection, target, h=H_REAL) -> float:
    assert detection.ok, detection.reason
    return float(np.linalg.norm(np.array(detection.center) - truth(target, h)))


# 1. Clean, complete crosses ---------------------------------------------------------------

@pytest.mark.parametrize("target", [[640, 360], *CORNERS.tolist(), *GRID[[6, 8, 12]].tolist()])
def test_clean_cross_centre(target):
    d = detect_cross(camera_view(projector_image([target])))
    assert error(d, target) < 0.05
    assert d.candidates == 1 and d.reason == ""
    assert d.arm_angle_deg > 80 and d.half_arm_balance > 0.8 and d.fit_sigma_px < 0.5


def test_colour_frames_are_accepted():
    target = [640, 360]
    grey = camera_view(projector_image([target]))
    d = detect_cross(cv2.cvtColor(grey, cv2.COLOR_GRAY2BGR))
    assert error(d, target) < 0.05


# 2. Crosses near image boundaries ---------------------------------------------------------

def _shifted(h, dx, dy):
    """h after moving the camera image by (dx, dy) camera px."""
    return h @ np.array([[1, 0, -dx], [0, 1, -dy], [0, 0, 1]], dtype=float)


def test_complete_cross_close_to_the_image_border_is_detected():
    target = [77, 43]
    h = _shifted(H_REAL, -(truth(target)[0] - 40), 0)      # centre 40 camera px from the left edge
    d = detect_cross(camera_view(projector_image([target]), h))
    assert truth(target, h)[0] == pytest.approx(40, abs=1e-6)
    assert error(d, target, h) < 0.05


def test_cross_cut_by_the_image_border_is_rejected():
    target = [77, 43]
    h = _shifted(H_REAL, -(truth(target)[0] - 12), 0)      # left arm runs off the image
    d = detect_cross(camera_view(projector_image([target]), h))
    assert not d.ok and d.center is None
    assert "cut off by the image border" in d.reason


def test_cross_extending_beyond_the_search_window_is_rejected():
    target = [640, 360]
    image = camera_view(projector_image([target]))
    d = detect_cross(image, expected=truth(target) + [20, 0], search_radius=25)
    assert not d.ok and d.center is None
    assert "beyond the search window" in d.reason


# 3. Clipped outer rings, intact crosses (4 % validation inset) ------------------------------

@pytest.mark.parametrize("target", [[51, 29], [640, 29], [1228, 29], [51, 690], [640, 690], [1228, 690]])
def test_clipped_ring_does_not_bias_the_centre(target):
    projected = projector_image([target])
    ring_top, ring_bottom = target[1] - 39, target[1] + 39
    assert ring_top < 0 or ring_bottom > CANVAS[1] - 1          # the ring really is clipped
    image = camera_view(projected)
    assert error(detect_cross(image), target) < 0.05
    # Why the ring is never used: a ring-inclusive centroid is biased several pixels here.
    grey = image.astype(float)
    c = truth(target)
    ys, xs = np.mgrid[0:CAMERA[1], 0:CAMERA[0]]
    win = (np.abs(xs - c[0]) < 60) & (np.abs(ys - c[1]) < 60)
    w = grey * win
    centroid = np.array([(xs * w).sum(), (ys * w).sum()]) / w.sum()
    assert np.linalg.norm(centroid - c) > 2.0


# 4. Perspective --------------------------------------------------------------------------------

@pytest.mark.parametrize("target", [*CORNERS.tolist(), *GRID.tolist()])
def test_strong_perspective(target):
    # Line intersection is exact for ideal lines; the 3-px arms' profile becomes slightly
    # asymmetric under perspective (measured <= 0.11 px at this keystone).
    d = detect_cross(camera_view(projector_image([target]), H_STRONG))
    assert error(d, target, H_STRONG) < 0.15


def test_extreme_perspective_is_rejected_never_wrong():
    results = [detect_cross(camera_view(projector_image([t]), H_EXTREME)) for t in np.vstack([CORNERS, GRID])]
    for target, d in zip(np.vstack([CORNERS, GRID]), results):
        if d.ok:
            assert error(d, target, H_EXTREME) < 0.15
        else:
            assert d.center is None and "half-arms unequal" in d.reason
    assert any(not d.ok for d in results)


def test_line_intersection_beats_a_centroid_under_perspective():
    """The arm-line intersection follows perspective; a cross-only centroid does not."""
    target = [77, 676]
    image = camera_view(projector_image([target]), H_STRONG, blur=0)
    c = truth(target, H_STRONG)
    d = detect_cross(image)
    grey = image.astype(float)
    ys, xs = np.mgrid[0:CAMERA[1], 0:CAMERA[0]]
    w = grey * (np.hypot(xs - c[0], ys - c[1]) < 30)          # cross only
    centroid = np.array([(xs * w).sum(), (ys * w).sum()]) / w.sum()
    assert error(d, target, H_STRONG) < np.linalg.norm(centroid - c)


# 5. Brightness changes and noise ---------------------------------------------------------------

@pytest.mark.parametrize("gain", [0.25, 0.5, 1.0, 3.0])          # 3.0 saturates the arms at 255
def test_brightness(gain):
    target = [345, 249]
    assert error(detect_cross(camera_view(projector_image([target]), gain=gain)), target) < 0.1


def test_ambient_light_gradient_and_noise_with_background_frame():
    target = [934, 470]
    kw = dict(ambient=60, gradient=50, noise=4.0)
    image = camera_view(projector_image([target]), gain=0.6, seed=1, **kw)
    background = camera_view(patterns.blank(CANVAS), seed=2, **kw)
    assert error(detect_cross(image, background=background), target) < 0.25


def test_ambient_light_gradient_without_background_frame():
    target = [934, 470]
    image = camera_view(projector_image([target]), gain=0.6, ambient=60, gradient=50, noise=2.0, seed=3)
    assert error(detect_cross(image), target) < 0.25


def test_target_too_faint_is_rejected():
    image = camera_view(projector_image([[640, 360]]), gain=0.03, noise=2.0, seed=4)
    d = detect_cross(image)
    assert not d.ok and "no projected target" in d.reason


# 6. Ambiguous, missing and multiple candidates -------------------------------------------------

def test_blank_frame_is_rejected():
    d = detect_cross(camera_view(patterns.blank(CANVAS), ambient=20, noise=2.0, seed=5))
    assert not d.ok and d.center is None and "no projected target" in d.reason


def test_two_crosses_are_ambiguous():
    targets = [[400, 300], [800, 420]]
    projected = projector_image(targets, 0)
    patterns.draw_target(projected, targets[1], active=True)
    d = detect_cross(camera_view(projected))
    assert not d.ok and d.candidates == 2 and "2 crosses" in d.reason


def test_search_window_isolates_one_of_two_crosses():
    targets = [[400, 300], [800, 420]]
    projected = projector_image(targets, 0)
    patterns.draw_target(projected, targets[1], active=True)
    image = camera_view(projected)
    d = detect_cross(image, expected=truth(targets[1]) + [6, -4], search_radius=70)
    assert error(d, targets[1]) < 0.05


def test_calibration_screen_with_dim_other_targets():
    """`calibrate` shows the other corners dimmed; only the active cross may be found."""
    for i, target in enumerate(CORNERS):
        projected = projector_image(CORNERS, i, labels=["1: top-left"] * 4, show_others=True)
        assert error(detect_cross(camera_view(projected)), target) < 0.05


@pytest.mark.parametrize("shape", ["ring", "bar", "blob", "text"])
def test_things_that_are_not_crosses_are_rejected(shape):
    projected = patterns.blank(CANVAS)
    if shape == "ring":
        cv2.circle(projected, (640, 360), 36, patterns.WHITE, 3)
    elif shape == "bar":
        cv2.line(projected, (600, 360), (680, 360), patterns.WHITE, 3)
    elif shape == "blob":
        cv2.rectangle(projected, (620, 340), (660, 380), patterns.WHITE, -1)
    else:
        patterns.text(projected, "point 7 of 20 at (345, 249) +t+", (500, 360), patterns.WHITE, 0.6)
    d = detect_cross(camera_view(projected))
    assert not d.ok and d.center is None and d.reason


def test_overlapping_label_text_does_not_bias_the_centre():
    """`validate` draws the label of right-column targets across the upper arm."""
    target = [1228, 690]
    projected = projector_image([target], labels=["point 20 of 20 at (1228, 690)"])
    assert error(detect_cross(camera_view(projected)), target) < 0.05


# 7. Coordinate conversion ----------------------------------------------------------------------

def test_pixel_centre_convention_without_any_warp():
    """A cross centred on camera pixel (col, row) is reported at exactly (col, row)."""
    image = np.zeros((CAMERA[1], CAMERA[0], 3), np.uint8)
    patterns.draw_target(image, (731, 402), active=True)
    d = detect_cross(image)
    assert d.ok and d.center == pytest.approx((731.0, 402.0), abs=0.01)


def test_search_window_reports_full_frame_coordinates():
    target = [345, 470]
    image = camera_view(projector_image([target]), noise=2.0, seed=6)
    full = detect_cross(image)
    windowed = detect_cross(image, expected=truth(target) + [9, -7], search_radius=70)
    assert full.ok and windowed.ok
    assert np.allclose(full.center, windowed.center, atol=1e-3)


def test_detected_camera_centre_maps_to_the_projector_target():
    for target in GRID:
        d = detect_cross(camera_view(projector_image([target])))
        mapped = apply_homography(H_REAL, [d.center])[0]
        assert np.allclose(mapped, target, atol=0.05)


# 8. Repeated detections and stability ----------------------------------------------------------

def test_repeated_noisy_frames_are_stable():
    target = [640, 249]
    centres = []
    for seed in range(10):
        d = detect_cross(camera_view(projector_image([target]), gain=0.6, noise=3.0, seed=seed))
        centres.append(d.center)
        assert d.ok, d.reason
    centres = np.array(centres)
    assert centres.std(axis=0).max() < 0.05
    assert np.linalg.norm(centres - truth(target), axis=1).max() < 0.15


@pytest.mark.parametrize("dx, dy", [(0.25, 0.0), (0.5, 0.0), (0.0, 0.25), (0.37, -0.41)])
def test_sub_pixel_shifts_are_followed(dx, dy):
    target = [640, 360]
    base = detect_cross(camera_view(projector_image([target])))
    h = _shifted(H_REAL, dx, dy)
    moved = detect_cross(camera_view(projector_image([target]), h))
    assert np.allclose(np.subtract(moved.center, base.center), (dx, dy), atol=0.03)


# 9. Errors and invalid input -------------------------------------------------------------------

@pytest.mark.parametrize("image", [
    None,
    np.zeros(10, np.uint8),
    np.zeros((0, 0), np.uint8),
    np.zeros((10, 10, 4), np.uint8),
    np.zeros((10, 10, 3), np.float32),
    np.full((10, 10), np.nan, np.float32),
    np.zeros((10, 10), bool),
    np.array([["a"]]),
])
def test_invalid_images_raise(image):
    with pytest.raises(DetectionError):
        detect_cross(image)


@pytest.mark.parametrize("kw", [
    dict(background=np.zeros((5, 5), np.uint8)),
    dict(expected=(10, 10)),
    dict(search_radius=10),
    dict(expected=(5000, 10), search_radius=10),
    dict(expected=(np.nan, 10), search_radius=10),
    dict(expected=(10, 10), search_radius=0),
    dict(expected=(10, 10), search_radius=-5),
])
def test_invalid_arguments_raise(kw):
    with pytest.raises(DetectionError):
        detect_cross(np.zeros((100, 100), np.uint8), **kw)
