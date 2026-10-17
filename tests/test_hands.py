"""Hand tracker wrapper (vision/hands.py): coordinate conversion and model checks.
These need no camera; the MediaPipe-dependent test is skipped when the package or model is absent.
Real tracking quality is measured on hardware (`python -m invisible_canvas cursor`, brain.md D33)."""

import numpy as np
import pytest

from invisible_canvas.vision import hands
import cv2

from invisible_canvas.vision.hands import (
    HandTracker,
    HandTrackingError,
    Letterbox,
    letterboxed_to_camera,
    normalized_to_camera,
)


def test_normalized_edges_map_to_pixel_edges():
    assert normalized_to_camera(0.0, 0.0, (1920, 1080)) == (-0.5, -0.5)
    assert normalized_to_camera(1.0, 1.0, (1920, 1080)) == (1919.5, 1079.5)
    # The centre of pixel (100, 50) is 100.5 / 1920 of the width from the left edge.
    assert normalized_to_camera(100.5 / 1920, 50.5 / 1080, (1920, 1080)) == pytest.approx((100.0, 50.0))


def test_normalized_coordinates_do_not_depend_on_the_inference_scale():
    # A point found on a 960-wide copy has the same normalized coordinates as on the full frame.
    x_small = (480.0 + 0.5) / 960
    assert normalized_to_camera(x_small, 0.5, (1920, 1080))[0] == pytest.approx(2 * 480.5 - 0.5)


def test_letterbox_for_the_brio_frame():
    box = Letterbox.for_frame((1920, 1080), (960, 540))
    assert (box.side, box.pad_x, box.pad_y, box.scale_x, box.scale_y) == (960, 0, 210, 2.0, 2.0)
    assert box.pad(np.zeros((540, 960, 3), np.uint8)).shape == (960, 960, 3)


@pytest.mark.parametrize("point", [(0.0, 0.0), (1919.0, 1079.0), (731.25, 402.75), (-0.5, 1079.5)])
def test_letterboxed_coordinates_round_trip(point):
    box = Letterbox.for_frame((1920, 1080), (960, 540))
    # camera px -> continuous small-image coordinate -> padded square -> normalized
    nx = ((point[0] + 0.5) / box.scale_x + box.pad_x) / box.side
    ny = ((point[1] + 0.5) / box.scale_y + box.pad_y) / box.side
    assert letterboxed_to_camera(nx, ny, box) == pytest.approx(point)


def test_letterbox_matches_opencv_resampling():
    """A bright block, resized and padded exactly like process() does, comes back at its camera pixel."""
    frame = np.zeros((1080, 1920, 3), np.uint8)
    frame[600:604, 1200:1204] = 255                       # 4x4 block centred on camera (1201.5, 601.5)
    small = cv2.resize(frame, (960, 540), interpolation=cv2.INTER_AREA)
    box = Letterbox.for_frame((1920, 1080), (960, 540))
    square = box.pad(small)[:, :, 0].astype(float)
    ys, xs = np.nonzero(square)
    w = square[ys, xs]
    cx, cy = (xs * w).sum() / w.sum(), (ys * w).sum() / w.sum()        # pixel-centre coordinates
    nx, ny = (cx + 0.5) / box.side, (cy + 0.5) / box.side               # MediaPipe-style normalized
    assert letterboxed_to_camera(nx, ny, box) == pytest.approx((1201.5, 601.5), abs=1e-6)


def test_missing_model_is_refused(tmp_path):
    with pytest.raises(HandTrackingError, match="not found"):
        HandTracker(tmp_path / "missing.task")


def test_model_with_the_wrong_hash_is_refused(tmp_path):
    fake = tmp_path / "hand_landmarker.task"
    fake.write_bytes(b"not a model")
    with pytest.raises(HandTrackingError, match="SHA-256"):
        HandTracker(fake, expected_sha256="0" * 64)


@pytest.mark.skipif(not hands.DEFAULT_MODEL.is_file(), reason="hand model not downloaded")
def test_tracker_finds_no_hand_in_an_empty_frame():
    pytest.importorskip("mediapipe")
    with HandTracker() as tracker:
        for k in range(3):
            assert tracker.process(np.full((1080, 1920, 3), 30, np.uint8), k / 30) is None
