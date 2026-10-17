"""`setupcheck` diagnostic (tools/setup_check.py) on the synthetic camera: read-only, judges each
check against every limit, and reports per shift. Hardware evidence is in brain.md (D32)."""

import argparse
import contextlib
import copy
import json
import tomllib

import pytest
from synthetic_camera import CAMERA, CANVAS, H_REAL, FakeSession, SyntheticScene, moved, truth

from invisible_canvas.calibration.store import Calibration, load_calibration, save_calibration
from invisible_canvas.calibration.targets import corner_targets
from invisible_canvas.config import DEFAULT_CONFIG_PATH, config_from_dict
from invisible_canvas.tools import setup_check


@pytest.fixture
def config(tmp_path):
    with open(DEFAULT_CONFIG_PATH, "rb") as f:
        config = config_from_dict(copy.deepcopy(tomllib.load(f)), root=tmp_path)
    corners = corner_targets(*CANVAS, 0.06)
    save_calibration(Calibration.create(method="auto", camera_name="Brio 100", camera_size=CAMERA, projector_name="T",
                                        projector_size=CANVAS, projector_points=corners,
                                        camera_points=truth(H_REAL, corners)), config.calibration_dir)
    return config


def run(config, monkeypatch, h=H_REAL, **kw):
    @contextlib.contextmanager
    def session(*a, **k):
        yield FakeSession()

    monkeypatch.setattr(setup_check, "open_session", session)
    monkeypatch.setattr(setup_check, "CameraMeasure", lambda s, title, shift=(0, 0): SyntheticScene(h, shift=shift))
    args = argparse.Namespace(repeat=1, interval=0.0, shifts=[(0, 0)], limits=[1.0, 2.0],
                              windowed=False, display=None, camera=None)
    for key, value in kw.items():
        setattr(args, key, value)
    before = load_calibration(config.calibration_dir).to_dict()
    code = setup_check.run(config, args)
    assert load_calibration(config.calibration_dir).to_dict() == before          # read-only
    [path] = sorted(config.reports_dir.glob("setupcheck-*.json"))
    return code, json.loads(path.read_text())


def test_no_movement_passes_every_limit(config, monkeypatch):
    code, report = run(config, monkeypatch, repeat=3)
    assert code == 0 and report["summary"]["0,0"]["n"] == 3
    assert report["summary"]["0,0"]["max"] < 0.2
    assert report["summary"]["0,0"]["refused_at_1"] == 0 and report["summary"]["0,0"]["refused_at_2"] == 0


def test_shifts_are_judged_against_each_limit(config, monkeypatch):
    code, report = run(config, monkeypatch, shifts=[(0, 0), (2, 0), (4, 0)])
    s = report["summary"]
    assert s["2,0"]["refused_at_1"] == 1 and s["2,0"]["refused_at_2"] == 0     # between the limits
    assert s["4,0"]["refused_at_1"] == 1 and s["4,0"]["refused_at_2"] == 1
    assert [c["shift_px"] for c in report["checks"]] == [[0, 0], [2, 0], [4, 0]]


def test_a_moved_scene_is_reported(config, monkeypatch):
    _, report = run(config, monkeypatch, h=moved(H_REAL, 5.0, 0.0))
    assert report["checks"][0]["variation_px"] == pytest.approx(2.5, abs=0.15)
    assert report["checks"][0]["verdicts"] == {"1": False, "2": False}
