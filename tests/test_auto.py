"""Phase 1C (brain.md D30): automatic calibration and validation, on a synthetic camera.

These tests check the logic (association, rejection, fitting, metrics, setup check, no fallback,
report formats, the manual path). They are not evidence of real-hardware performance.
"""

import argparse
import contextlib
import copy
import json
import tomllib
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
from synthetic_camera import CAMERA, CANVAS, H_REAL, FakeSession, SyntheticScene, moved, truth

from invisible_canvas.calibration import auto
from invisible_canvas.calibration.auto import (
    AutoCalibrationError,
    associate_corners,
    auto_setup_check,
    grid_edge_mask,
    measure_targets,
    screen_for,
    validation_result,
    verify_check_target,
)
from invisible_canvas.calibration.metrics import accuracy_stats
from invisible_canvas.calibration.store import Calibration, load_calibration, load_history, save_calibration
from invisible_canvas.calibration.targets import check_target, corner_targets, grid_targets, min_distance
from invisible_canvas.config import DEFAULT_CONFIG_PATH, config_from_dict
from invisible_canvas.geometry.homography import apply_homography
from invisible_canvas.mapping.mapper import CoordinateMapper
from invisible_canvas.tools import calibrate as calibrate_tool
from invisible_canvas.tools import validate as validate_tool

CORNERS = corner_targets(*CANVAS, 0.06)
GRID = grid_targets(*CANVAS, 5, 4, 0.04)
CHECK = check_target(*CANVAS)


def auto_calibration(scene, h=None):
    m = measure_targets(scene, CANVAS, CORNERS, show_others=True)
    points = associate_corners(m, CORNERS, CAMERA)
    return Calibration.create(method="auto", camera_name="Brio 100", camera_size=CAMERA, projector_name="TEST",
                              projector_size=CANVAS, projector_points=CORNERS, camera_points=points)


# -- measurements ----------------------------------------------------------------------------------

def test_clean_measurement_is_accepted():
    m = SyntheticScene()(screen_for(CANVAS, CORNERS, 0, show_others=True))
    assert m.ok and m.problem == ""
    assert np.linalg.norm(m.center - truth(H_REAL, CORNERS[:1])[0]) < 0.05
    assert m.single_sd < 0.1 and m.summary()["single_accepted"] == 3


def test_unstable_target_is_rejected():
    m = SyntheticScene(jitter=1.5, seed=3)(screen_for(CANVAS, GRID, 7, show_others=False))
    assert not m.ok and "unstable" in m.problem


def test_blank_screen_is_rejected_with_the_detector_reason():
    scene = SyntheticScene(fail_calls={0})
    m = scene(screen_for(CANVAS, GRID, 7, show_others=False))
    assert not m.ok and "no projected target" in m.problem


def test_too_few_single_frames_is_rejected():
    frames_ok = SyntheticScene(frames=2)
    target = screen_for(CANVAS, GRID, 7, show_others=False)
    good = frames_ok(target)
    blank = SyntheticScene(frames=3, fail_calls={0})(target)
    mixed = auto.TargetMeasurement(good.detection, good.single_centres, 5, {"no projected target": 3})
    assert not blank.ok
    assert not mixed.ok and "only 2 of 5" in mixed.problem


# -- automatic calibration: correspondence and fit ------------------------------------------------

def test_check_target_is_held_out_and_off_the_symmetry_axes():
    assert min_distance(CHECK[None], CORNERS) > 200 and min_distance(CHECK[None], GRID) > 40
    centre = (np.array(CANVAS) - 1) / 2
    assert abs(CHECK[0] - centre[0]) > 100 and abs(CHECK[1] - centre[1]) > 100


def test_auto_corners_fit_the_existing_homography():
    calibration = auto_calibration(SyntheticScene())
    assert calibration.method == "auto"
    mapped = apply_homography(calibration.homography, truth(H_REAL, GRID))
    assert np.abs(mapped - GRID).max() < 0.1
    check = SyntheticScene()(screen_for(CANVAS, [CHECK], 0, show_others=False))
    assert verify_check_target(calibration.homography, check, CHECK, 12.0) < 0.2


def test_auto_calibration_keeps_the_calibration_file_format(tmp_path):
    calibration = auto_calibration(SyntheticScene())
    manual = Calibration.create(method="manual", camera_name="Brio 100", camera_size=CAMERA, projector_name="TEST",
                                projector_size=CANVAS, projector_points=CORNERS,
                                camera_points=truth(H_REAL, CORNERS))
    assert set(calibration.to_dict()) == set(manual.to_dict())
    save_calibration(calibration, tmp_path)
    loaded = load_calibration(tmp_path)          # integrity check: H recomputed from the points
    assert loaded.method == "auto" and np.allclose(loaded.homography, calibration.homography)
    assert [c.method for c in load_history(tmp_path)] == ["auto"]


def _corner_measurements(**kw):
    return measure_targets(SyntheticScene(**kw), CANVAS, CORNERS, show_others=True)


def test_missing_corner_is_rejected():
    with pytest.raises(AutoCalibrationError) as e:
        associate_corners(_corner_measurements(fail_calls={1}), CORNERS, CAMERA)
    assert "1 of 4" in str(e.value) and e.value.details[0].startswith("top-right: no projected target")


def test_ambiguous_corner_is_rejected():
    with pytest.raises(AutoCalibrationError) as e:
        associate_corners(_corner_measurements(extra_cross_calls={2}), CORNERS, CAMERA)
    assert "bottom-right" in e.value.details[0] and "2 crosses" in e.value.details[0]


def test_duplicate_detection_is_rejected():
    m = _corner_measurements()
    with pytest.raises(AutoCalibrationError, match="seen twice"):
        associate_corners([m[0], m[0], m[2], m[3]], CORNERS, CAMERA)


def test_swapped_corners_are_rejected():
    m = _corner_measurements()
    with pytest.raises(AutoCalibrationError, match="not a usable quadrilateral"):
        associate_corners([m[0], m[2], m[1], m[3]], CORNERS, CAMERA)


def test_mirrored_order_is_rejected():
    m = _corner_measurements()
    with pytest.raises(AutoCalibrationError, match="opposite direction"):
        associate_corners([m[0], m[3], m[2], m[1]], CORNERS, CAMERA)


def test_cyclically_relabelled_corners_are_caught_by_the_check_target():
    m = _corner_measurements()
    rotated = [m[1], m[2], m[3], m[0]]           # convex, same orientation: association alone cannot tell
    points = associate_corners(rotated, CORNERS, CAMERA)
    calibration = Calibration.create(method="auto", camera_name="c", camera_size=CAMERA, projector_name="p",
                                     projector_size=CANVAS, projector_points=CORNERS, camera_points=points)
    check = SyntheticScene()(screen_for(CANVAS, [CHECK], 0, show_others=False))
    with pytest.raises(AutoCalibrationError, match="assigned wrongly"):
        verify_check_target(calibration.homography, check, CHECK, 12.0)


# -- automatic validation -------------------------------------------------------------------------

def test_auto_validation_metrics_use_the_existing_statistics():
    calibration = auto_calibration(SyntheticScene())
    measurements = measure_targets(SyntheticScene(seed=5), CANVAS, GRID, show_others=False)
    result = validation_result(CoordinateMapper.from_calibration(calibration), GRID, measurements, 5, 4)
    assert result.stats == accuracy_stats(result.errors)
    assert result.stats.mean < 0.1 and result.stats.max < 0.25
    rows, cols = np.divmod(np.arange(20), 5)
    assert np.array_equal(result.edge, (rows == 0) | (rows == 3) | (cols == 0) | (cols == 4))
    assert result.edge.sum() == 14 and np.array_equal(grid_edge_mask(20, 5, 4), result.edge)


def test_auto_validation_stops_if_a_grid_target_is_not_detected():
    calibration = auto_calibration(SyntheticScene())
    scene = SyntheticScene(fail_calls={1})
    good = scene(screen_for(CANVAS, GRID, 12, show_others=False))
    missing = scene(screen_for(CANVAS, GRID, 13, show_others=False))
    measurements = [good] * 13 + [missing] + [good] * 6      # only point 14 is missing
    with pytest.raises(AutoCalibrationError) as e:
        validation_result(CoordinateMapper.from_calibration(calibration), GRID, measurements, 5, 4)
    assert str(e.value) == "1 of 20 validation targets not detected reliably"
    assert len(e.value.details) == 1 and e.value.details[0].startswith("point 14 at (934, 470): no projected target")


@pytest.mark.parametrize("dx, dy, consistent", [(0.4, -0.3, True), (6.0, 0.0, False), (-3.0, 5.0, False)])
def test_auto_setup_check_detects_a_moved_setup(dx, dy, consistent):
    calibration = auto_calibration(SyntheticScene())
    check, _ = auto_setup_check(SyntheticScene(moved(H_REAL, dx, dy), seed=9), calibration, CANVAS, 2.0)
    assert check.consistent is consistent
    assert check.mean_shift == pytest.approx((dx, dy), abs=0.15)


def test_auto_setup_check_refuses_a_shifted_projection():
    calibration = auto_calibration(SyntheticScene())
    check, _ = auto_setup_check(SyntheticScene(shift=(5, 5)), calibration, CANVAS, 2.0)
    assert not check.consistent


def test_auto_setup_check_needs_every_corner():
    calibration = auto_calibration(SyntheticScene())
    with pytest.raises(AutoCalibrationError, match="setup check"):
        auto_setup_check(SyntheticScene(fail_calls={0}), calibration, CANVAS, 2.0)


# -- the tools, with a fake session (no camera, no windows) ---------------------------------------

@pytest.fixture
def config(tmp_path):
    with open(DEFAULT_CONFIG_PATH, "rb") as f:
        return config_from_dict(copy.deepcopy(tomllib.load(f)), root=tmp_path)


@pytest.fixture
def rig(monkeypatch):
    """Patches the tools: fake session, synthetic camera, and a tripwire on manual clicks."""
    state = SimpleNamespace(scene_kw={}, manual_clicks=None)

    @contextlib.contextmanager
    def fake_session(config, args, **kw):
        yield FakeSession()

    def fake_measure(s, title, shift=(0, 0)):
        return SyntheticScene(shift=shift, **state.scene_kw)

    def collect_points(*a, **k):
        if state.manual_clicks is None:
            raise AssertionError("manual clicks were requested")
        return state.manual_clicks.pop(0)

    for module in (calibrate_tool, validate_tool):
        monkeypatch.setattr(module, "open_session", fake_session)
        monkeypatch.setattr(module, "collect_points", collect_points)
    monkeypatch.setattr(calibrate_tool, "camera_measure", fake_measure)
    monkeypatch.setattr(calibrate_tool, "review", lambda *a, **k: "save")
    monkeypatch.setattr(cv2, "waitKey", lambda *a: 27)
    return state


def args(**kw):
    base = dict(auto=False, manual=False, dry_run=False, no_setup_check=False, simulate_shift=None,
                windowed=False, display=None, camera=None, runs=None)
    base.update(kw)
    return argparse.Namespace(**base)


def reports(config, prefix):
    return sorted(p for p in config.reports_dir.glob(f"{prefix}-*.json")
                  if not (prefix == "validation" and p.name.startswith("validation-auto")))


def test_calibrate_auto_saves_an_auto_calibration(config, rig):
    assert calibrate_tool.run(config, args(auto=True)) == 0
    calibration = load_calibration(config.calibration_dir)
    assert calibration.method == "auto"
    assert np.abs(apply_homography(calibration.homography, truth(H_REAL, GRID)) - GRID).max() < 0.15
    report = json.loads(reports(config, "calibration-auto")[-1].read_text())
    assert report["result"] == "ok" and report["mode"] == "auto" and report["check_target"]["error_px"] < 0.3
    assert [c["name"] for c in report["corners"]] == ["top-left", "top-right", "bottom-right", "bottom-left"]


def test_calibrate_auto_dry_run_saves_nothing(config, rig):
    assert calibrate_tool.run(config, args(auto=True, dry_run=True)) == 0
    assert not (config.calibration_dir / "current.json").exists()
    assert json.loads(reports(config, "calibration-auto")[-1].read_text())["saved"] is None


def test_calibrate_auto_failure_stops_without_manual_fallback(config, rig, capsys):
    rig.scene_kw = {"fail_calls": {2}}                       # bottom-right not shown
    assert calibrate_tool.run(config, args(auto=True)) == 1  # collect_points would raise if called
    assert not (config.calibration_dir / "current.json").exists()
    out = capsys.readouterr().out
    assert "automatic calibration FAILED" in out and "bottom-right" in out and "calibrate --manual" in out
    assert json.loads(reports(config, "calibration-auto")[-1].read_text())["result"] == "failed"


def test_calibrate_auto_rejects_an_ambiguous_corner(config, rig):
    rig.scene_kw = {"extra_cross_calls": {0}}
    assert calibrate_tool.run(config, args(auto=True)) == 1
    assert not (config.calibration_dir / "current.json").exists()


def test_validate_auto_passes_and_is_distinguishable_from_manual(config, rig):
    assert calibrate_tool.run(config, args(auto=True)) == 0
    assert validate_tool.run_validate(config, args(auto=True)) == 0
    [path] = sorted(config.reports_dir.glob("validation-auto-*.json"))
    report = json.loads(path.read_text())
    assert report["mode"] == "auto" and report["method"] == validate_tool.AUTO_METHOD
    assert report["calibration_method"] == "auto" and report["simulated_shift_px"] is None
    assert report["setup_check"]["consistent"] and report["required"]["pass"] and report["stretch"]["pass"]
    assert report["stats_px"]["mean"] < 0.15 and len(report["points"]) == 20
    assert all(p["detection"]["ok"] for p in report["points"])
    assert path.with_suffix(".png").exists()
    assert reports(config, "validation") == []               # no manual-looking report
    assert LEGACY_VALIDATION_KEYS <= set(report)             # every key of the manual format is there


def test_validate_auto_refuses_a_moved_setup(config, rig, capsys):
    assert calibrate_tool.run(config, args(auto=True)) == 0
    rig.scene_kw = {"h": moved(H_REAL, 8.0, -3.0)}
    assert validate_tool.run_validate(config, args(auto=True)) == 1
    assert "has moved since this calibration" in capsys.readouterr().out
    check = json.loads(reports(config, "setup-check")[-1].read_text())
    assert check["mode"] == "auto" and check["consistent"] is False
    assert not list(config.reports_dir.glob("validation-auto-*.json"))


def test_validate_auto_refuses_a_simulated_shift(config, rig):
    assert calibrate_tool.run(config, args(auto=True)) == 0
    assert validate_tool.run_validate(config, args(auto=True, simulate_shift=[5, 5])) == 1
    check = json.loads(reports(config, "setup-check")[-1].read_text())
    assert check["simulated_shift_px"] == [5, 5] and check["consistent"] is False


def test_validate_auto_stops_on_a_detection_failure(config, rig, capsys):
    assert calibrate_tool.run(config, args(auto=True)) == 0
    rig.scene_kw = {"fail_calls": {4 + 9}}                   # 4 setup-check corners, then grid point 10
    assert validate_tool.run_validate(config, args(auto=True)) == 1
    out = capsys.readouterr().out
    assert "automatic validation FAILED" in out and "point 10 at (1228, 249)" in out
    assert not list(config.reports_dir.glob("validation-auto-2*.json"))
    assert len(list(config.reports_dir.glob("validation-auto-failed-*.json"))) == 1


def cli_parser():
    import invisible_canvas.__main__ as cli
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    for tool in cli.TOOLS:
        tool.add_parser(sub)
    return parser


def test_mode_options(config, monkeypatch):
    parser = cli_parser()
    for command in ("calibrate", "validate"):
        assert not calibrate_tool.is_manual(parser.parse_args([command]))             # automatic by default (D31)
        assert not calibrate_tool.is_manual(parser.parse_args([command, "--auto"]))   # still accepted
        assert calibrate_tool.is_manual(parser.parse_args([command, "--manual"]))
        with pytest.raises(SystemExit):
            parser.parse_args([command, "--auto", "--manual"])

    def no_session(*a, **k):
        raise AssertionError("a session was opened")

    monkeypatch.setattr(calibrate_tool, "open_session", no_session)
    monkeypatch.setattr(validate_tool, "open_session", no_session)
    assert calibrate_tool.run(config, parser.parse_args(["calibrate", "--manual", "--dry-run"])) == 2
    assert validate_tool.run_validate(config, parser.parse_args(["validate", "--manual", "--simulate-shift", "5", "5"])) == 2


def test_default_commands_run_the_automatic_path(config, rig):
    """`calibrate` and `validate` with no mode flag detect; manual clicks are never requested."""
    parser = cli_parser()
    assert calibrate_tool.run(config, parser.parse_args(["calibrate"])) == 0
    assert load_calibration(config.calibration_dir).method == "auto"
    assert validate_tool.run_validate(config, parser.parse_args(["validate"])) == 0
    [path] = sorted(config.reports_dir.glob("validation-auto-*.json"))
    assert json.loads(path.read_text())["mode"] == "auto"
    assert reports(config, "validation") == []


def test_default_dry_run_and_simulated_shift_need_no_flag(config, rig):
    parser = cli_parser()
    assert calibrate_tool.run(config, parser.parse_args(["calibrate", "--dry-run"])) == 0
    assert not (config.calibration_dir / "current.json").exists()
    assert calibrate_tool.run(config, parser.parse_args(["calibrate"])) == 0
    assert validate_tool.run_validate(config, parser.parse_args(["validate", "--simulate-shift", "5", "5"])) == 1


def test_default_automatic_failure_does_not_fall_back(config, rig, capsys):
    rig.scene_kw = {"fail_calls": {0}}
    assert calibrate_tool.run(config, cli_parser().parse_args(["calibrate"])) == 1     # tripwire on clicks
    assert "calibrate --manual" in capsys.readouterr().out
    assert not (config.calibration_dir / "current.json").exists()


# -- the manual workflow is unchanged ---------------------------------------------------------------

LEGACY_VALIDATION_KEYS = {"created_at", "calibration_created_at", "method", "setup_check", "camera", "camera_size",
                          "canvas_size", "grid", "stats_px", "edge_mean_px", "interior_mean_px", "mm_per_px",
                          "stats_mm", "required", "stretch", "points"}


def test_manual_calibrate_and_validate_still_work(config, rig):
    clicks = truth(H_REAL, CORNERS) + 0.3
    rig.manual_clicks = [clicks]
    assert calibrate_tool.run(config, args(manual=True)) == 0
    calibration = load_calibration(config.calibration_dir)
    assert calibration.method == "manual" and np.allclose(calibration.camera_points, clicks)

    rig.manual_clicks = [clicks + [[0.2, -0.1], [0.0, 0.3], [-0.2, 0.1], [0.1, 0.0]], truth(H_REAL, GRID) + 0.3]
    assert validate_tool.run_validate(config, args(manual=True)) == 0
    [path] = reports(config, "validation")
    report = json.loads(path.read_text())
    assert set(report) == LEGACY_VALIDATION_KEYS | {"mode"} and report["mode"] == "manual"
    assert report["method"].startswith("manual clicks") and report["setup_check"]["consistent"]
    assert report["stats_px"]["mean"] < 0.1 and set(report["points"][0]) == {"target", "camera", "mapped", "error_px"}
    assert rig.manual_clicks == []


def test_repeatability_compares_only_calibrations_of_the_same_method(config, rig, capsys):
    for k in range(3):
        rig.manual_clicks = [truth(H_REAL, CORNERS) + 0.2 * k]
        assert calibrate_tool.run(config, args(manual=True)) == 0
    assert validate_tool.run_repeatability(config, args()) == 0
    assert "3 most recent manual calibrations" in capsys.readouterr().out
    assert calibrate_tool.run(config, args()) == 0                   # default: automatic; current is now auto
    assert validate_tool.run_repeatability(config, args()) == 1
    assert "need 3 auto calibrations of this setup, found 1" in capsys.readouterr().out
