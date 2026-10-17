"""Pure parts of the `detect` diagnostic (tools/detect_check.py)."""

import json
from types import SimpleNamespace

import cv2
import numpy as np

from invisible_canvas.calibration.detect import detect_cross
from invisible_canvas.tools.detect_check import _contact_sheet, _latest_validation_clicks, _two_crosses


def test_two_cross_negative_control_is_a_multiple_candidate_case():
    image = cv2.cvtColor(_two_crosses((1280, 720), (640, 360), 70), cv2.COLOR_BGR2GRAY)
    d = detect_cross(cv2.GaussianBlur(image, (0, 0), 0.8))
    assert not d.ok and d.candidates == 2 and "2 crosses" in d.reason


MANUAL = "manual clicks (includes human click error)"     # the method string manual reports carry


def _report(path, calibration_created_at, x, method=MANUAL, mode=None):
    data = {"calibration_created_at": calibration_created_at, "method": method,
            "points": [{"target": [51.0, 29.0], "camera": [x, 10.0]}]}
    if mode:
        data["mode"] = mode
    path.write_text(json.dumps(data), encoding="utf-8")


def test_manual_reference_comes_only_from_a_validation_with_the_current_calibration(tmp_path):
    _report(tmp_path / "validation-20261009-205315.json", "older calibration", 1.0)
    _report(tmp_path / "validation-20261009-232455.json", "current", 2.0)
    _report(tmp_path / "validation-20261010-090000.json", "a later, different calibration", 3.0, mode="manual")
    config = SimpleNamespace(reports_dir=tmp_path)
    targets, clicks, name = _latest_validation_clicks(config, SimpleNamespace(created_at="current"))
    assert name == "validation-20261009-232455.json" and clicks.tolist() == [[2.0, 10.0]]
    assert _latest_validation_clicks(config, SimpleNamespace(created_at="never validated")) is None


def test_automatic_validations_are_never_a_manual_reference(tmp_path):
    _report(tmp_path / "validation-20261010-100000.json", "current", 2.0)
    _report(tmp_path / "validation-auto-20261010-110000.json", "current", 9.0,
            method="automatic cross detection (calibration/detect.py), no clicks", mode="auto")
    config = SimpleNamespace(reports_dir=tmp_path)
    _, clicks, name = _latest_validation_clicks(config, SimpleNamespace(created_at="current"))
    assert name == "validation-20261010-100000.json" and clicks.tolist() == [[2.0, 10.0]]


def test_contact_sheet_marks_detected_and_manual_centres():
    image = np.zeros((1080, 1920), np.float32)
    image[500:503, 900:960] = 200
    sheet = _contact_sheet([("ok", image, (930.0, 501.0), (931.0, 502.0), (930.0, 501.0)),
                            ("rejected", image, None, None, (5.0, 5.0))])
    assert sheet.shape[2] == 3 and sheet.shape[1] == 6 * 81 * 4
    assert (sheet == (0, 220, 0)).all(axis=2).any()        # green detected marker
    assert (sheet == (0, 140, 255)).all(axis=2).any()      # orange manual marker
