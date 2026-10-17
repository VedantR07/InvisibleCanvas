"""Accuracy-test diagnostics of the `cursor` tool (D35): targets, per-target statistics, shadow check."""

import numpy as np
import pytest
from test_shadow import BLACK, CANVAS_LUMA, hand, scene

from invisible_canvas.mapping.mapper import CoordinateMapper
from invisible_canvas.tools import cursor as cursor_tool
from invisible_canvas.vision.hands import HandObservation


def test_provisional_criteria_are_the_users_numbers():
    """Recorded 2026-10-10 as provisional; they must not drift to fit a measurement."""
    assert (cursor_tool.PROVISIONAL_MEAN_PX, cursor_tool.PROVISIONAL_MAX_PX) == (5.0, 12.0)


def test_the_default_instruction_does_not_need_wall_contact():
    assert "SHADOW" in cursor_tool.AIMS["shadow"] and "no wall contact" in cursor_tool.AIMS["shadow"]


def test_custom_targets_are_parsed_and_checked():
    pts = cursor_tool.parse_targets("640,690 640,690; 51,29", (1280, 720))
    assert pts.tolist() == [[640, 690], [640, 690], [51, 29]]
    with pytest.raises(ValueError, match="outside"):
        cursor_tool.parse_targets("1280,10", (1280, 720))
    with pytest.raises(ValueError):
        cursor_tool.parse_targets("  ", (1280, 720))


def _obs(score=0.9):
    lm = np.zeros((21, 2))
    lm[12] = (0.0, 200.0)
    return HandObservation((0.0, 0.0), lm, "Right", score)


def test_target_stats_report_detection_delay_drops_and_confidence():
    st = cursor_tool.TargetStats(start=10.0)
    for k in range(30):                                   # 1 s without a hand, then found, one dropout
        st.add(10.0 + k / 30, None)
    for k in range(30, 60):
        st.add(10.0 + k / 30, None if k == 45 else _obs(0.8 + 0.01 * (k % 3)))
    s = st.summary(12.0)
    assert s["frames"] == 60 and s["hand_found_fraction"] == pytest.approx(29 / 60)
    assert s["first_detection_s"] == pytest.approx(1.0) and s["detection_drops"] == 1
    assert s["handedness_score_median"] == pytest.approx(0.81) and s["handedness_score_min"] == pytest.approx(0.8)
    assert s["hand_length_px_median"] == pytest.approx(200.0)


def test_target_stats_without_any_hand():
    st = cursor_tool.TargetStats(start=0.0)
    st.add(0.0, None)
    s = st.summary(30.0)
    assert s["first_detection_s"] is None and s["handedness_score_median"] is None and s["hand_found_fraction"] == 0


def test_shadow_check_reports_parallax_in_projector_px():
    """Camera 1920x1080 -> canvas 1280x720 by a pure scale; shadow 45 px up and 14 px left of the
    fingertip in the camera, so the cursor is (+14, +45) * 2/3 projector px from the projector ray."""
    H = np.diag([2 / 3, 2 / 3, 1.0])
    mapper = CoordinateMapper(H, (1280, 720))
    lm = hand()
    shift = np.array([-14.0, -45.0])
    grey, canvas = scene(lm, shift)
    image = np.dstack([grey] * 3)
    target = mapper.camera_to_projector([lm[8] + shift])[0]          # shadow tip exactly on the target
    out, rows = cursor_tool.shadow_check([(0.0, image, lm)], mapper, canvas, BLACK, CANVAS_LUMA, target)
    assert out["frames_checked"] == 1 and out["frames_with_shadow"] == 1 and len(rows) == 1
    assert out["parallax_px"] == pytest.approx([14 * 2 / 3, 45 * 2 / 3], abs=1.0)
    assert out["parallax_magnitude_px"] == pytest.approx(np.hypot(14, 45) * 2 / 3, abs=1.0)
    assert out["shadow_minus_target_px"] == pytest.approx([0.0, 0.0], abs=1.0)


def test_shadow_check_without_a_visible_shadow():
    mapper = CoordinateMapper(np.diag([2 / 3, 2 / 3, 1.0]), (1280, 720))
    lm = hand()
    grey, canvas = scene(lm, np.zeros(2))
    out, rows = cursor_tool.shadow_check([(0.0, np.dstack([grey] * 3), lm)], mapper, canvas, BLACK, CANVAS_LUMA,
                                         (600, 400))
    assert out == {"frames_checked": 1, "frames_with_shadow": 0} and rows == []


def test_a_camera_without_frames_gives_a_clear_error():
    """2026-10-10: the `camera` preview held the Brio; `cursor` crashed on latest() = None."""
    from types import SimpleNamespace

    from invisible_canvas.tools.common import capture_frames, current_seq

    silent = SimpleNamespace(camera=SimpleNamespace(latest=lambda: None, wait_frame=lambda seq, timeout: None))
    with pytest.raises(RuntimeError, match="another program"):
        current_seq(silent, timeout=0.01)
    with pytest.raises(RuntimeError, match="no frames"):
        capture_frames(silent, 1, settle=0.0)


# -- the accuracy loop end to end: fake camera, fake hand tracker, synthetic calibration ------------

def _run_cursor(tmp_path, monkeypatch, argv, tip_noise=0.5, present=None, tip_in_view=True, on_show=None,
                hand_at=(640.0, 360.0), setup_scene=None, expect=0):
    """present: optional f(seconds since the first tracked frame) -> is the hand in view. Without --targets
    the fingertip is held at hand_at (projector px). on_show(image): every image sent to the projector.
    setup_scene: run the setup check (and any recovery, D39) on this synthetic camera instead of skipping
    it. expect: the exit code; the report is read only when it is 0 (else None is returned for it)."""
    import argparse
    import contextlib
    import copy
    import json
    import time
    import tomllib
    from types import SimpleNamespace

    import cv2
    from synthetic_camera import CAMERA, H_REAL, FakeSession, SyntheticScene
    from test_auto import auto_calibration

    from invisible_canvas.calibration.store import save_calibration
    from invisible_canvas.config import DEFAULT_CONFIG_PATH, config_from_dict

    with open(DEFAULT_CONFIG_PATH, "rb") as f:
        config = config_from_dict(copy.deepcopy(tomllib.load(f)), root=tmp_path)
    calibration = auto_calibration(SyntheticScene())
    save_calibration(calibration, config.calibration_dir)
    mapper = CoordinateMapper.from_calibration(calibration)

    class Camera:
        def __init__(self):
            self.seq, self.frame = 0, None
            self.image = np.full((CAMERA[1], CAMERA[0], 3), 140, np.uint8)
        def wait_frame(self, after_seq=0, timeout=1.0):
            self.seq += 1
            self.frame = SimpleNamespace(image=self.image, seq=self.seq, timestamp=time.perf_counter())
            return self.frame
        def latest(self):
            return self.frame or self.wait_frame()
        reset_stats = lambda self: None                                       # noqa: E731
        stats = lambda self: SimpleNamespace(mean_fps=30.0, read_failures=0)  # noqa: E731
        read_exposure = lambda self: None                                     # noqa: E731

    rng = np.random.default_rng(0)
    state = {"target_camera": None}

    from invisible_canvas.vision.hands import AcquisitionStats

    class FakeTracker:
        stats = AcquisitionStats()
        action = "fake"

        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *e): pass
        def process(self, image, t):
            state.setdefault("t0", t)
            if present is not None and not present(t - state["t0"]):
                return None
            lm = hand()
            lm = lm - lm[8] + state["target_camera"] + rng.normal(0, tip_noise, 2)
            return HandObservation((float(lm[8, 0]), float(lm[8, 1])), lm, "Right", 0.9, tip_in_view=tip_in_view)

    @contextlib.contextmanager
    def fake_session(config, args, **kw):
        s = FakeSession()
        s.camera = Camera()
        if on_show is not None:
            s.projector = SimpleNamespace(show=on_show)
        yield s

    if "--targets" in argv:
        targets = cursor_tool.parse_targets(argv[argv.index("--targets") + 1], (1280, 720))
        state["target_camera"] = mapper.projector_to_camera([targets[0]])[0]
    else:
        state["target_camera"] = mapper.projector_to_camera([hand_at])[0]
    monkeypatch.setattr(cursor_tool, "open_session", fake_session)
    monkeypatch.setattr(cursor_tool, "HandTracker", FakeTracker)
    monkeypatch.setattr(cv2, "waitKey", lambda *a: -1)
    monkeypatch.setattr(cv2, "pollKey", lambda *a: -1)
    parser = argparse.ArgumentParser()
    cursor_tool.add_parser(parser.add_subparsers())
    if setup_scene is not None:
        monkeypatch.setattr(cursor_tool, "CameraMeasure", lambda s, title, **k: setup_scene)
    args = parser.parse_args(["cursor", *([] if setup_scene is not None else ["--no-setup-check"]), *argv])
    assert cursor_tool.run(config, args) == expect
    if expect != 0:
        return None, H_REAL
    report = json.loads(sorted(config.reports_dir.glob("cursor-*.json"))[-1].read_text())
    return report, H_REAL


def test_accuracy_run_records_per_target_diagnostics_and_a_capture_image(tmp_path, monkeypatch):
    report, _ = _run_cursor(tmp_path, monkeypatch, ["--targets", "640,360"])
    (entry,) = report["accuracy"]
    assert entry["measured"] and entry["error_px"] < 3.0
    assert entry["hand_found_fraction"] == 1.0 and entry["first_detection_s"] == 0.0
    assert entry["handedness_score_median"] == pytest.approx(0.9) and "shadow" not in entry
    assert report["options"]["aim"] == "shadow" and report["instruction"] == cursor_tool.AIMS["shadow"]
    assert report["shadow_parallax_px"] is None and report["provisional_criteria"] is None   # custom targets
    from pathlib import Path
    assert (Path(report["frames_dir"]) / "capture_target1.jpg").is_file()


def test_shadow_check_runs_only_when_asked(tmp_path, monkeypatch):
    report, _ = _run_cursor(tmp_path, monkeypatch, ["--targets", "640,360", "--shadow-check"])
    (entry,) = report["accuracy"]
    assert entry["shadow"]["frames_checked"] >= 1 and report["options"]["shadow_check"] is True


def test_a_repeated_target_is_not_captured_before_the_pause(tmp_path, monkeypatch):
    """2026-10-10 sweep bug: samples collected during the pause let the next hold at the same
    position be captured at once. The second capture now needs the pause plus a full 1-s hold."""
    report, _ = _run_cursor(tmp_path, monkeypatch, ["--targets", "640,360 640,360", "--pause", "0.6"])
    first, second = report["accuracy"]
    assert first["measured"] and second["measured"]
    assert second["duration_s"] >= 0.6 + cursor_tool.DWELL_S - 0.05


@pytest.fixture
def withdraw_report(tmp_path, monkeypatch):
    """D36: the hand is seen at first (0-0.6 s), leaves (0.6-1.4 s) and comes back. With --withdraw the
    target activates 0.5 s after it left, so the first detection after activation measures acquisition."""
    present = lambda s: s < 0.6 or s >= 1.4                                   # noqa: E731
    report, _ = _run_cursor(tmp_path, monkeypatch, ["--targets", "640,360", "--withdraw"], present=present)
    return report


def test_withdraw_measures_acquisition_after_activation(withdraw_report):
    (entry,) = withdraw_report["accuracy"]
    assert entry["measured"] and entry["first_detection_s"] == pytest.approx(0.0, abs=0.05)   # seen before
    assert 0.1 <= entry["first_detection_after_activation_s"] <= 0.6                         # 1.4 - (0.6 + 0.5)
    assert withdraw_report["options"]["withdraw"] is True


def test_rows_and_columns_summarise_a_3x3_grid():
    entries = [{"target": [x, y], "error_px": float(e)} for (x, y), e in
               zip([(51, 29), (640, 29), (1228, 29), (51, 360), (640, 360), (1228, 360), (51, 690), (640, 690),
                    (1228, 690)], [1, 2, 3, 4, 5, 6, 7, 8, 9])]
    rc = cursor_tool.rows_and_columns(entries, lambda e: e["error_px"])
    assert rc["top"] == {"mean": 2.0, "max": 3.0, "n": 3} and rc["bottom"]["mean"] == 8.0
    assert rc["left"] == {"mean": 4.0, "max": 7.0, "n": 3} and rc["right"]["max"] == 9.0
    rc = cursor_tool.rows_and_columns(entries, lambda e: None if e["error_px"] > 8 else e["error_px"])
    assert rc["right"]["n"] == 2 and rc["bottom"]["max"] == 8.0


def _pointing_hand(tip, u, w=18.0):
    """Landmarks of a pointing hand: index along u ending at tip, other fingers curled at the knuckles."""
    u = np.asarray(u, float) / np.linalg.norm(u)
    n = np.array([-u[1], u[0]])
    lm = np.zeros((21, 2))
    base = np.asarray(tip) - 110 * u
    lm[5:9] = [base, base + 45 * u, base + 80 * u, tip]                       # index MCP, PIP, DIP, TIP
    for k, f in enumerate((9, 13, 17)):                                       # curled fingers, away from n
        knuckle = base - (k + 1) * w * n
        lm[f:f + 4] = [knuckle, knuckle + 15 * u, knuckle + 5 * u, knuckle - 5 * u]
    lm[0] = base - 70 * u - 1.5 * w * n
    lm[1:5] = [lm[0] + 20 * n, lm[0] + 35 * n + 15 * u, lm[0] + 45 * n + 30 * u, lm[0] + 50 * n + 45 * u]
    return lm


def test_shadow_alignment_measures_the_cursor_against_the_shadow_centre():
    """Camera -> canvas by a pure scale 2/3. The shadow of the fingertip ends 33 px beside it; the operator
    put that shadow on the target. Error = H(fingertip) - H(shadow centre), established over 4 frames."""
    from test_shadow import finger_scene
    H = np.diag([2 / 3, 2 / 3, 1.0])
    mapper = CoordinateMapper(H, (1280, 720))
    tip, u = np.array([900.0, 500.0]), np.array([-1.0, -0.4])
    un = u / np.linalg.norm(u)
    end = tip + np.array([10.0, -30.0])
    grey, canvas, _ = finger_scene(tip, u, end)
    lm = _pointing_hand(tip, u)
    centre = end - 9 * un
    target = mapper.camera_to_projector([centre])[0]
    frames = [(k / 30, np.dstack([grey] * 3), lm) for k in range(4)]
    out, tips = cursor_tool.shadow_alignment(frames, target, mapper, canvas, BLACK, CANVAS_LUMA)
    assert out["established"], out["reason"]
    assert out["found"] == 4 and len(tips) == 4
    assert out["error_xy"] == pytest.approx(list((tip - centre) * 2 / 3), abs=1.0)
    assert out["centre_minus_target"] == pytest.approx([0.0, 0.0], abs=1.0)


def test_shadow_alignment_without_a_shadow_is_not_established():
    from test_shadow import finger_scene
    mapper = CoordinateMapper(np.diag([2 / 3, 2 / 3, 1.0]), (1280, 720))
    tip, u = np.array([900.0, 500.0]), np.array([-1.0, -0.4])
    grey, canvas, _ = finger_scene(tip, u, tip, shadow=False)
    frames = [(k / 30, np.dstack([grey] * 3), _pointing_hand(tip, u)) for k in range(4)]
    out, _ = cursor_tool.shadow_alignment(frames, (600.0, 333.0), mapper, canvas, BLACK, CANVAS_LUMA)
    assert not out["established"] and "found in 0/4" in out["reason"] and "error_px" not in out


# -- D37 tracking audit -----------------------------------------------------------------------------

def _cyan_pixels(image) -> int:
    from invisible_canvas.display import patterns
    return int(np.all(image == patterns.CYAN, axis=2).sum())


def test_live_cursor_is_hidden_while_the_detector_finds_no_hand(tmp_path, monkeypatch):
    shown = []
    report, _ = _run_cursor(tmp_path, monkeypatch, ["--seconds", "0.4"], present=lambda s: False,
                            on_show=lambda img: shown.append(_cyan_pixels(img)))
    statuses = {r["status"] for r in report["records"]}
    assert statuses == {"lost"} and all(r["position"] is None for r in report["records"])
    assert report["hand_frames_fraction"] == 0 and report["tracking_losses"] == 0
    assert all(r["reason"] == "no fingertip" for r in report["records"])
    assert len(shown) > len(report["records"]) // 2 and max(shown) == 0          # never a cursor on the projector


def test_live_cursor_follows_a_present_hand_and_records_the_drawn_position(tmp_path, monkeypatch):
    shown = []
    report, _ = _run_cursor(tmp_path, monkeypatch, ["--seconds", "0.3", "--smoothing"], hand_at=(300.0, 200.0),
                            on_show=lambda img: shown.append(_cyan_pixels(img)))
    tracked = [r for r in report["records"] if r["status"] == "tracking"]
    assert len(tracked) == len(report["records"]) and max(shown) > 0
    assert all(np.hypot(*np.subtract(r["position"], (300.0, 200.0))) < 3.0 for r in tracked)
    assert report["options"]["smoothing_params"] == {"min_cutoff_hz": 1.0, "beta": 0.05, "d_cutoff_hz": 1.0}
    assert report["transitions"] == {"lost->tracking": 1} and report["motion"]["spikes"] == 0


def test_an_extrapolated_fingertip_is_never_drawn_as_a_detection(tmp_path, monkeypatch):
    shown = []
    report, _ = _run_cursor(tmp_path, monkeypatch, ["--seconds", "0.3"], tip_in_view=False,
                            on_show=lambda img: shown.append(_cyan_pixels(img)))
    assert all(r["hand"] and not r["tip_valid"] and r["status"] == "lost" for r in report["records"])
    assert report["tip_outside_view_frames"] == len(report["records"]) and max(shown) == 0


def test_trace_is_off_by_default_and_has_one_line_per_frame_when_asked(tmp_path, monkeypatch):
    import json
    report, _ = _run_cursor(tmp_path, monkeypatch, ["--seconds", "0.3"])
    assert report["trace_file"] is None and report["options"]["trace"] is False
    report, _ = _run_cursor(tmp_path, monkeypatch, ["--seconds", "0.3", "--trace"], present=lambda s: s < 0.1)
    lines = [json.loads(x) for x in open(report["trace_file"], encoding="utf-8")]
    assert len(lines) == report["frames"]
    seen = lines[0]
    assert seen["hand"] and seen["action"] == "fake" and seen["tip_in_view"] and set(seen["landmarks"]) == {
        "0", "5", "6", "8", "12", "16"}
    assert seen["mapped"] == pytest.approx(seen["raw_proj"]) and seen["drawn"] == pytest.approx(seen["raw_proj"])
    assert {"status", "reason", "since_seen_ms", "queue_ms", "inference_ms", "pipeline_ms", "tip_cam",
            "tip_norm", "view"} <= set(seen)
    gone = lines[-1]
    assert not gone["hand"] and gone["status"] == "lost" and gone["since_seen_ms"] >= 150


def test_the_cursor_is_drawn_in_projector_local_pixels():
    """The projector window shows the canvas image 1:1 at the display's origin (geometry verified when it
    opens), so the cursor is drawn at projector px of the canvas, never at desktop coordinates."""
    from invisible_canvas.display.projector import ProjectorWindow
    canvas = np.zeros((720, 1280, 3), np.uint8)
    cursor_tool._draw_cursor(canvas, (100.0, 50.0), "tracking")
    ys, xs = np.nonzero(np.all(canvas == cursor_tool.patterns.CYAN, axis=2))
    assert (xs.min() + xs.max()) / 2 == pytest.approx(100, abs=1) and (ys.min() + ys.max()) / 2 == pytest.approx(50, abs=1)
    held = np.zeros_like(canvas)
    cursor_tool._draw_cursor(held, (100.0, 50.0), "holding")
    assert _cyan_pixels(held) == 0                                                # a held point is not drawn as live
    with pytest.raises(ValueError, match="1280x720"):
        ProjectorWindow(None, (1280, 720), windowed=True).show(np.zeros((1080, 3200, 3), np.uint8))


def test_motion_summary_measures_lag_jitter_and_transient_jumps():
    rng = np.random.default_rng(2)
    recs = []
    for k in range(60):                                         # still, 1 px noise, drawn = raw
        p = [500 + rng.normal(0, 1), 300 + rng.normal(0, 1)]
        recs.append({"t": k / 30, "status": "tracking", "raw": p, "position": p})
    recs[30]["raw"] = [560.0, 300.0]                            # one-frame jump that comes back
    for k in range(60, 120):                                    # moving 300 px/s, drawn 4 px behind
        x = 500 + 300 * (k - 60) / 30
        recs.append({"t": k / 30, "status": "tracking", "raw": [x, 300.0], "position": [x - 4.0, 300.0]})
    m = cursor_tool.motion_summary(recs)
    assert m["spikes"] == 1 and m["lag_px"]["median"] == pytest.approx(4.0)
    assert 0.6 < m["still_jitter_rms_px"] < 1.2
