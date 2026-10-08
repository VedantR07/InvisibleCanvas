import json
import time

import numpy as np
import pytest

from invisible_canvas.calibration.store import (
    Calibration,
    CalibrationError,
    check_compatible,
    load_calibration,
    load_history,
    save_calibration,
)
from invisible_canvas.calibration.targets import corner_targets
from invisible_canvas.geometry.homography import apply_homography
from invisible_canvas.mapping.mapper import CoordinateMapper

# Ground truth: how projector pixels appear in a 1920x1080 camera frame.
PROJECTOR_TO_CAMERA = np.array([
    [1.02, -0.03, 310.0],
    [0.01, 0.98, 190.0],
    [-1.5e-5, 2.0e-5, 1.0],
])
PROJECTOR_POINTS = corner_targets(1280, 720, 0.06)
CAMERA_POINTS = apply_homography(PROJECTOR_TO_CAMERA, PROJECTOR_POINTS)


def make_calibration(camera_points=CAMERA_POINTS):
    return Calibration.create(
        method="manual",
        camera_name="Brio 100",
        camera_size=(1920, 1080),
        projector_name="WZATCO",
        projector_size=(1280, 720),
        projector_points=PROJECTOR_POINTS,
        camera_points=camera_points,
    )


def test_mapper_maps_held_out_points_through_calibration():
    mapper = CoordinateMapper.from_calibration(make_calibration())
    projector = np.array([[640.0, 360.0], [10.0, 700.0], [1270.0, 5.0]])  # none are calibration points
    camera = apply_homography(PROJECTOR_TO_CAMERA, projector)
    assert np.allclose(mapper.camera_to_projector(camera), projector, atol=1e-6)
    assert np.allclose(mapper.projector_to_camera(projector), camera, atol=1e-6)


def test_map_point_single():
    mapper = CoordinateMapper.from_calibration(make_calibration())
    cx, cy = apply_homography(PROJECTOR_TO_CAMERA, [[100.0, 200.0]])[0]
    assert mapper.map_point(cx, cy) == pytest.approx((100.0, 200.0), abs=1e-6)


def test_inside_canvas_uses_pixel_edges():
    mapper = CoordinateMapper(np.eye(3), (1280, 720))
    pts = [[-0.5, -0.5], [-0.6, 10], [1279.4, 719.4], [1279.5, 10], [640, 360]]
    assert mapper.inside_canvas(pts).tolist() == [True, False, True, False, True]


def test_canvas_outline_in_camera_matches_ground_truth():
    mapper = CoordinateMapper.from_calibration(make_calibration())
    corners = [[-0.5, -0.5], [1279.5, -0.5], [1279.5, 719.5], [-0.5, 719.5]]
    assert np.allclose(mapper.canvas_outline_in_camera(), apply_homography(PROJECTOR_TO_CAMERA, corners), atol=1e-6)


def test_mapper_rejects_bad_matrix():
    with pytest.raises(ValueError):
        CoordinateMapper(np.eye(2), (1280, 720))


def test_save_and_reload_round_trip(tmp_path):
    original = make_calibration()
    path = save_calibration(original, tmp_path)
    assert path == tmp_path / "current.json"
    loaded = load_calibration(tmp_path)
    assert loaded.camera_size == (1920, 1080) and loaded.projector_size == (1280, 720)
    assert loaded.created_at == original.created_at
    assert np.allclose(loaded.homography, original.homography)
    assert len(list((tmp_path / "history").glob("*.json"))) == 1


def test_missing_calibration_is_reported(tmp_path):
    with pytest.raises(CalibrationError, match="run `calibrate` first"):
        load_calibration(tmp_path)


def test_edited_file_is_refused(tmp_path):
    save_calibration(make_calibration(), tmp_path)
    path = tmp_path / "current.json"
    data = json.loads(path.read_text())
    data["camera_points"][0][0] += 5.0   # points no longer match the stored H
    path.write_text(json.dumps(data))
    with pytest.raises(CalibrationError, match="does not match"):
        load_calibration(tmp_path)


def test_wrong_schema_version_is_refused(tmp_path):
    save_calibration(make_calibration(), tmp_path)
    path = tmp_path / "current.json"
    data = json.loads(path.read_text())
    data["schema_version"] = 99
    path.write_text(json.dumps(data))
    with pytest.raises(CalibrationError, match="schema"):
        load_calibration(tmp_path)


def test_size_mismatch_is_refused():
    calibration = make_calibration()
    check_compatible(calibration, (1920, 1080), (1280, 720))
    with pytest.raises(CalibrationError, match="camera frames are 1280x720"):
        check_compatible(calibration, (1280, 720), (1280, 720))
    with pytest.raises(CalibrationError, match="projector is 1920x1080"):
        check_compatible(calibration, (1920, 1080), (1920, 1080))


def test_history_keeps_every_save_oldest_first(tmp_path):
    first = make_calibration()
    time.sleep(0.01)
    second = make_calibration(CAMERA_POINTS + 1.0)
    save_calibration(first, tmp_path)
    save_calibration(second, tmp_path)
    history = load_history(tmp_path)
    assert [c.created_at for c in history] == [first.created_at, second.created_at]
    assert load_calibration(tmp_path).created_at == second.created_at


def test_history_skips_damaged_entries(tmp_path):
    save_calibration(make_calibration(), tmp_path)
    (tmp_path / "history" / "00000000-000000-000.json").write_text("{not json")
    assert len(load_history(tmp_path)) == 1
