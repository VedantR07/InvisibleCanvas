"""Automatic calibration recovery after a moved setup (D39): calibration/recovery.py, the `recalibrate` tool
and the `cursor` start-up, on the synthetic camera. Real-camera behaviour is measured on the hardware."""

import argparse
import contextlib
import copy
import json
import tomllib
from types import SimpleNamespace

import numpy as np
import pytest
from synthetic_camera import CAMERA, CANVAS, H_REAL, FakeSession, SyntheticScene, moved, truth
from test_auto import CHECK, CORNERS, GRID, auto_calibration

from invisible_canvas.calibration.auto import measure_targets
from invisible_canvas.calibration.metrics import setup_check
from invisible_canvas.calibration.recovery import (ACCEPTED, FAILED, UNCHANGED, RecoveryPlan, check_and_recover,
                                                   commit_recovery, explain, recover_calibration)
from invisible_canvas.calibration.store import (HISTORY_DIR, Calibration, CalibrationError, archive_calibration,
                                                load_calibration, save_calibration)
from invisible_canvas.config import DEFAULT_CONFIG_PATH, config_from_dict
from invisible_canvas.geometry.homography import apply_homography, estimate_homography
from invisible_canvas.mapping.mapper import CoordinateMapper
from invisible_canvas.tools import calibrate as calibrate_tool
from invisible_canvas.tools import recalibrate as recalibrate_tool

PLAN = RecoveryPlan(check_target=CHECK, grid=GRID, grid_cols=5, grid_rows=4, setup_limit_px=2.0,
                    confirm_limit_px=2.0, required_mean_px=5.0, required_max_px=12.0)
NAMES = dict(canvas_size=CANVAS, camera_size=CAMERA, camera_name="Brio 100", projector_name="TEST")
# Projections per recovery: 4 corners (setup check), 1 check target, 20 grid targets, 4 corners (confirmation).
CALLS = 4 + 1 + len(GRID) + 4


@pytest.fixture(scope="module")
def previous():
    return auto_calibration(SyntheticScene())


def recover(scene, previous):
    return check_and_recover(scene, previous, PLAN, **NAMES)


class Switching:
    """The setup moves during a run: scene `a` for the first `n` projections, scene `b` afterwards."""

    def __init__(self, a, b, n):
        self.a, self.b, self.n, self.calls = a, b, n, 0

    def __call__(self, screen):
        self.calls += 1
        return (self.a if self.calls <= self.n else self.b)(screen)


# -- recovery logic -------------------------------------------------------------------------------

def test_an_unchanged_setup_is_not_recalibrated(previous):
    scene = SyntheticScene()
    result = recover(scene, previous)
    assert result.status == UNCHANGED and not result.accepted and result.candidate is None
    assert result.setup.consistent and scene.calls == 4                 # only the setup check was projected


@pytest.mark.parametrize("dx, dy", [(40.0, -12.0), (-120.0, -40.0), (-200.0, -30.0)])
def test_a_moved_setup_is_recovered_from_fresh_detections(previous, dx, dy):
    h = moved(H_REAL, dx, dy)
    scene = SyntheticScene(h)
    result = recover(scene, previous)
    assert result.status == ACCEPTED and result.stage == "accepted" and scene.calls == CALLS
    assert not result.setup.consistent                                   # the old calibration was refused
    cand = result.candidate
    assert cand.method == "auto" and cand.created_at != previous.created_at
    assert np.array_equal(cand.projector_points, previous.projector_points)
    # The new corners are where the moved projection really is, not where the old calibration saw them.
    assert np.abs(cand.camera_points - truth(h, CORNERS)).max() < 0.15
    assert np.abs(cand.camera_points - previous.camera_points).min() > 10
    assert np.abs(apply_homography(cand.homography, truth(h, GRID)) - GRID).max() < 0.2
    assert result.check_error_px < 0.3 and result.validation.stats.max < 0.3
    assert result.confirmation.consistent and result.confirmation.variation < 0.2


def test_the_real_2026_10_12_movement_is_recovered():
    """The geometry of setupcheck-20261012-191953 (refused, variation 37.26 px): the 00:52 calibration's
    corners and the corners detected at 19:19 (calibration + the reported shifts). The old calibration is
    ~66 projector px wrong on the grid; the recovered one matches the moved scene."""
    old = np.array([[266.4212, 211.5200], [1465.8181, 193.4095], [1496.1740, 890.6020], [246.5173, 918.3662]])
    shifts = np.array([[76.5962, 0.2858], [76.2449, 1.2023], [72.2964, 9.2092], [71.9598, -7.2492]])
    fresh = old + shifts
    previous = Calibration.create(method="auto", camera_name="Brio 100", camera_size=CAMERA, projector_name="TEST",
                                  projector_size=CANVAS, projector_points=CORNERS, camera_points=old)
    h_now = estimate_homography(fresh, CORNERS)
    result = recover(SyntheticScene(h_now), previous)
    assert result.status == ACCEPTED
    assert result.setup.variation == pytest.approx(37.26, abs=0.2)
    assert np.abs(result.candidate.camera_points - fresh).max() < 0.2
    grid_cam = truth(h_now, GRID)
    old_error = np.linalg.norm(CoordinateMapper.from_calibration(previous).camera_to_projector(grid_cam) - GRID, axis=1)
    assert old_error.mean() > 60
    assert result.validation.stats.mean < 0.2 and result.validation.stats.max < 0.4


def test_a_missing_corner_stops_at_the_setup_check(previous):
    result = recover(SyntheticScene(moved(H_REAL, 40, -12), fail_calls={1}), previous)
    assert result.status == FAILED and result.stage == "setup check" and result.candidate is None
    assert "top-right" in " ".join(result.details)
    assert any("low contrast" in h for h in result.hints)


def test_a_corner_outside_the_camera_image_is_refused_with_an_aiming_hint(previous):
    result = recover(SyntheticScene(moved(H_REAL, 150, 0)), previous)       # the right corners leave the image
    assert result.status == FAILED and result.stage == "setup check" and result.candidate is None
    assert any("re-aim" in h or "outside the camera view" in h for h in result.hints)


def test_an_ambiguous_corner_is_refused(previous):
    result = recover(SyntheticScene(moved(H_REAL, 40, -12), extra_cross_calls={2}), previous)
    assert result.status == FAILED and result.stage == "setup check"
    assert "bottom-right" in " ".join(result.details)
    assert any("more than one marker" in h for h in result.hints)


def test_unstable_markers_are_refused(previous):
    result = recover(SyntheticScene(moved(H_REAL, 40, -12), jitter=1.5, seed=3), previous)
    assert result.status == FAILED and result.stage == "setup check"
    assert any("not seen steadily" in h for h in result.hints)


@pytest.mark.parametrize("order, words", [((0, 2, 1, 3), "quadrilateral"), ((1, 0, 3, 2), "opposite direction")])
def test_invalid_corner_geometry_is_refused_before_anything_else_is_projected(previous, order, words):
    scene = SyntheticScene(moved(H_REAL, 40, -12))
    m = measure_targets(scene, CANVAS, CORNERS, show_others=True)
    corners = [m[i] for i in order]                                     # swapped / mirrored assignment
    setup = setup_check(previous.camera_points, [c.center for c in corners], 2.0)
    result = recover_calibration(scene, previous, setup, corners, PLAN, **NAMES)
    assert result.status == FAILED and result.stage == "corners" and words in result.reason
    assert result.candidate is None and scene.calls == 4 and result.hints


def test_a_missing_check_target_stops_recovery(previous):
    result = recover(SyntheticScene(moved(H_REAL, 40, -12), fail_calls={4}), previous)
    assert result.status == FAILED and result.stage == "check target" and result.validation is None


def test_a_missing_validation_target_stops_recovery(previous):
    result = recover(SyntheticScene(moved(H_REAL, 40, -12), fail_calls={10}), previous)
    assert result.status == FAILED and result.stage == "validation" and "point 6" in " ".join(result.details)
    assert result.confirmation is None


def test_an_inaccurate_candidate_fails_the_held_out_validation(previous):
    """The setup moves 10 camera px after the corners and the check target were measured: the candidate
    no longer describes the scene, and the held-out grid shows it (A7 required limits, not loosened)."""
    h = moved(H_REAL, 40, -12)
    scene = Switching(SyntheticScene(h), SyntheticScene(moved(h, 10, 0), seed=1), n=5)
    result = recover(scene, previous)
    assert result.status == FAILED and result.stage == "validation"
    assert "held-out validation failed" in result.reason and result.validation.stats.mean > PLAN.required_mean_px
    assert result.confirmation is None and result.hints


def test_movement_during_recovery_is_caught_by_the_confirmation(previous):
    """A 5-px move after the validation: the final setup check against the candidate refuses it."""
    h = moved(H_REAL, 40, -12)
    scene = Switching(SyntheticScene(h), SyntheticScene(moved(h, 5, 0), seed=1), n=CALLS - 4)
    result = recover(scene, previous)
    assert result.validation.stats.max < 0.3                            # the validation itself passed
    assert result.status == FAILED and result.stage == "confirmation"
    assert "moved during recovery" in result.reason and result.confirmation.variation > 2.0


def test_hints_explain_the_reasons():
    assert explain(["no projected target: peak 2.0 grey levels"])[0].startswith("the camera cannot see")
    assert explain(["component at (5, 5): the cross is cut off by the image border"])[0].startswith("a marker is at")
    assert explain(["nothing known"]) == []
    assert len(explain(["unstable: x", "unstable: y"])) == 1


# -- committing: only an accepted candidate, and the previous calibration is preserved --------------

def _accepted(previous):
    return recover(SyntheticScene(moved(H_REAL, 40, -12)), previous)


def test_commit_saves_the_candidate_and_keeps_the_previous_in_the_history(tmp_path, previous):
    save_calibration(previous, tmp_path)
    old_history = {p.name: p.read_bytes() for p in (tmp_path / HISTORY_DIR).glob("*.json")}
    result = _accepted(previous)
    path = commit_recovery(result, tmp_path)
    assert path == tmp_path / "current.json"
    assert load_calibration(tmp_path).to_dict() == result.candidate.to_dict()
    new_history = {p.name: p.read_bytes() for p in (tmp_path / HISTORY_DIR).glob("*.json")}
    assert len(new_history) == 2 and all(new_history[k] == v for k, v in old_history.items())


def test_commit_restores_a_missing_history_entry_of_the_previous_calibration(tmp_path, previous):
    save_calibration(previous, tmp_path)
    for p in (tmp_path / HISTORY_DIR).glob("*.json"):
        p.unlink()
    commit_recovery(_accepted(previous), tmp_path)
    created = {json.loads(p.read_text())["created_at"] for p in (tmp_path / HISTORY_DIR).glob("*.json")}
    assert previous.created_at in created and len(created) == 2


def test_commit_refuses_a_failed_or_unchanged_result(tmp_path, previous):
    save_calibration(previous, tmp_path)
    before = (tmp_path / "current.json").read_bytes()
    for result in (recover(SyntheticScene(), previous),                                    # unchanged
                   recover(SyntheticScene(moved(H_REAL, 40, -12), fail_calls={10}), previous)):   # failed
        with pytest.raises(CalibrationError, match="not accepted"):
            commit_recovery(result, tmp_path)
    assert (tmp_path / "current.json").read_bytes() == before
    assert len(list((tmp_path / HISTORY_DIR).glob("*.json"))) == 1


def test_commit_refuses_if_the_current_calibration_changed_meanwhile(tmp_path, previous):
    result = _accepted(previous)
    other = auto_calibration(SyntheticScene(moved(H_REAL, 3, 3)))
    save_calibration(other, tmp_path)                                    # someone recalibrated meanwhile
    with pytest.raises(CalibrationError, match="changed during recovery"):
        commit_recovery(result, tmp_path)
    assert load_calibration(tmp_path).to_dict() == other.to_dict()


def test_archive_never_rewrites_a_history_entry(tmp_path, previous):
    path = archive_calibration(previous, tmp_path)
    path.write_text("kept as it is", encoding="utf-8")
    assert archive_calibration(previous, tmp_path) == path and path.read_text(encoding="utf-8") == "kept as it is"


# -- the `recalibrate` tool --------------------------------------------------------------------------

@pytest.fixture
def config(tmp_path, previous):
    with open(DEFAULT_CONFIG_PATH, "rb") as f:
        config = config_from_dict(copy.deepcopy(tomllib.load(f)), root=tmp_path)
    save_calibration(previous, config.calibration_dir)
    return config


def run_tool(config, monkeypatch, scene, dry_run=False):
    @contextlib.contextmanager
    def session(*a, **k):
        yield FakeSession()

    monkeypatch.setattr(recalibrate_tool, "open_session", session)
    monkeypatch.setattr(calibrate_tool, "camera_measure", lambda s, title, shift=(0, 0): scene)
    current = config.calibration_dir / "current.json"
    before = current.read_bytes()
    code = recalibrate_tool.run(config, argparse.Namespace(dry_run=dry_run, windowed=False, display=None, camera=None))
    [path] = sorted(config.reports_dir.glob("calibration-recovery-*.json"))
    return code, json.loads(path.read_text()), current.read_bytes() != before


def test_recalibrate_does_nothing_when_the_setup_is_unchanged(config, monkeypatch, capsys):
    code, report, changed = run_tool(config, monkeypatch, SyntheticScene())
    assert code == 0 and not changed and report["status"] == "unchanged" and report["saved"] is None
    assert "still valid" in capsys.readouterr().out


def test_recalibrate_replaces_a_moved_calibration(config, monkeypatch, capsys, previous):
    code, report, changed = run_tool(config, monkeypatch, SyntheticScene(moved(H_REAL, -120, -40)))
    assert code == 0 and changed and report["status"] == "accepted" and report["saved"]
    current = load_calibration(config.calibration_dir)
    assert current.to_dict() == report["candidate"] and current.created_at != previous.created_at
    assert report["validation"]["required"]["pass"] and report["confirmation_vs_candidate"]["consistent"]
    assert report["setup_check_vs_previous"]["consistent"] is False and report["coverage"]["fully_visible"] is not None
    created = {json.loads(p.read_text())["created_at"] for p in (config.calibration_dir / HISTORY_DIR).glob("*.json")}
    assert created == {previous.created_at, current.created_at}
    assert "saved" in capsys.readouterr().out


def test_recalibrate_dry_run_validates_but_saves_nothing(config, monkeypatch, capsys):
    code, report, changed = run_tool(config, monkeypatch, SyntheticScene(moved(H_REAL, -120, -40)), dry_run=True)
    assert code == 0 and not changed and report["status"] == "accepted" and report["dry_run"]
    assert report["saved"] is None and report["candidate"] is not None
    assert len(list((config.calibration_dir / HISTORY_DIR).glob("*.json"))) == 1
    assert "NOT saved (dry run)" in capsys.readouterr().out


def test_recalibrate_failure_keeps_the_calibration_and_explains(config, monkeypatch, capsys):
    code, report, changed = run_tool(config, monkeypatch, SyntheticScene(moved(H_REAL, -120, -40), fail_calls={10}))
    assert code == 1 and not changed and report["status"] == "failed" and report["stage"] == "validation"
    assert report["saved"] is None and report["hints"]
    out = capsys.readouterr().out
    assert "FAILED at the validation step" in out and "NOT changed" in out and "hint:" in out
    assert len(list((config.calibration_dir / HISTORY_DIR).glob("*.json"))) == 1


# -- `cursor` start-up ------------------------------------------------------------------------------

def _cursor(tmp_path, monkeypatch, scene, *extra, expect=0):
    from test_cursor_tool import _run_cursor
    return _run_cursor(tmp_path, monkeypatch, ["--seconds", "0.3", *extra], setup_scene=scene, expect=expect)


def test_cursor_recovers_a_moved_setup_and_runs_on_the_new_calibration(tmp_path, monkeypatch):
    report, _ = _cursor(tmp_path, monkeypatch, SyntheticScene(moved(H_REAL, 40, -12)))
    rec = report["calibration_recovery"]
    assert rec["status"] == "accepted" and rec["refused_variation_px"] > 2.0
    current = load_calibration(tmp_path / "data" / "calibration")
    assert report["calibration_created_at"] == current.created_at != rec["previous_calibration_created_at"]
    assert report["setup_check"]["variation_px"] < 0.2                   # the confirmation vs the new calibration
    assert json.loads(open(rec["report"]).read())["context"] == "cursor"


def test_cursor_does_not_start_when_recovery_fails(tmp_path, monkeypatch, capsys):
    report, _ = _cursor(tmp_path, monkeypatch, SyntheticScene(moved(H_REAL, 40, -12), fail_calls={10}), expect=1)
    assert report is None
    out = capsys.readouterr().out
    assert "FAILED at the validation step" in out and "does not start" in out
    assert len(list((tmp_path / "data" / "calibration" / HISTORY_DIR).glob("*.json"))) == 1


def test_cursor_no_recalibrate_keeps_the_old_refusal(tmp_path, monkeypatch, capsys):
    report, _ = _cursor(tmp_path, monkeypatch, SyntheticScene(moved(H_REAL, 40, -12)), "--no-recalibrate", expect=1)
    assert report is None and "Run `recalibrate`" in capsys.readouterr().out
    assert not list((tmp_path / "data" / "reports").glob("calibration-recovery-*.json"))


def test_the_plan_uses_the_existing_targets_and_thresholds(config):
    """No new thresholds: A7 required limits, the D30 check target, the D32 setup limits by method."""
    v = config.validation
    for method, limit in (("auto", v.auto_setup_limit_px), ("manual", v.repeatability_mean_px)):
        plan = recalibrate_tool.recovery_plan(config, SimpleNamespace(method=method), CANVAS)
        assert plan.setup_limit_px == limit and plan.confirm_limit_px == v.auto_setup_limit_px
        assert (plan.required_mean_px, plan.required_max_px) == (v.required_mean_px, v.required_max_px)
        assert np.array_equal(plan.check_target, CHECK) and np.array_equal(plan.grid, GRID)


def test_cursor_with_an_unchanged_setup_does_not_recalibrate(tmp_path, monkeypatch):
    report, _ = _cursor(tmp_path, monkeypatch, SyntheticScene())
    assert report["calibration_recovery"] is None and report["setup_check"]["variation_px"] < 0.2
