"""Diagnostic-only landmark glitch detection (vision/landmark_diagnostics.py, brain.md D38).

Synthetic tests check the definitions, robustness and that the cursor is untouched. Trace tests replay the
four 2026-10-11 `cursor --trace` runs (local hardware data, git-ignored: skipped when absent). Genuine finger
bends are NOT in those traces: the bend tests are synthetic and validate only the detector's arithmetic.
"""

import json
import math

import numpy as np
import pytest

from invisible_canvas.config import REPO_ROOT
from invisible_canvas.vision import landmark_diagnostics as ld
from invisible_canvas.vision.landmark_diagnostics import EXTENSION, MOTION, LandmarkDiagnostics, episodes, replay, summary


def hand(wrist=(500.0, 500.0), mcp=(500.0, 420.0), tip=(440.0, 420.0)) -> np.ndarray:
    """(21, 2) camera px; only landmarks 0 (wrist), 5 (index knuckle) and 8 (index tip) matter here."""
    lm = np.zeros((21, 2))
    lm[0], lm[5], lm[8] = wrist, mcp, tip
    lm[6] = (np.asarray(mcp) + np.asarray(tip)) / 2
    return lm


# -- definitions -----------------------------------------------------------------------------------

def test_signal_definitions_in_camera_px():
    d = LandmarkDiagnostics()
    first = d.update(10, hand())                          # palm 80 px, tip-knuckle 60 px
    assert first.extension == pytest.approx(0.75) and first.extension_flag is False
    assert first.motion is None and first.motion_flag is None and first.no_decision == ("motion: no previous usable frame",)
    assert first.suspicious is None                        # one signal undecided, the other False
    at_limit = d.update(11, hand(tip=(440.0, 440.0)))      # tip-knuckle vector changes by 20 px = 0.25 palm
    assert at_limit.motion == pytest.approx(0.25) and at_limit.motion_flag is False and at_limit.suspicious is False
    above = d.update(12, hand(tip=(440.0, 461.0)))         # 21 px = 0.2625 palm: flagged
    assert above.motion == pytest.approx(21 / 80) and above.motion_flag is True and above.reasons == (MOTION,)
    curled = d.update(13, hand(tip=(500.0, 453.0)))        # tip 33 px from the knuckle: extension 0.4125
    assert curled.extension == pytest.approx(33 / 80) and curled.extension_flag is True
    assert EXTENSION in curled.reasons and curled.suspicious is True
    assert (ld.MOTION_LIMIT, ld.EXTENSION_LIMIT) == (0.25, 0.43)


def test_to_json_is_compact_and_serialisable():
    d = LandmarkDiagnostics()
    d.update(1, hand())
    j = d.update(2, hand(tip=(441.0, 420.0))).to_json()
    assert json.loads(json.dumps(j)) == j
    assert set(j) == {"motion", "extension", "motion_flag", "extension_flag", "suspicious", "reasons", "no_decision"}
    assert j["motion"] == round(1 / 80, 4)


# -- genuine motion (synthetic) ----------------------------------------------------------------------

def test_rigid_hand_translation_and_rotation_keep_relative_motion_low():
    """SYNTHETIC. Moving the whole hand 120 camera px per frame, or turning it 10 degrees per frame about the
    wrist, moves the tip with its knuckle: relative motion stays at 0 / 2 sin(5 deg) * extension."""
    d = LandmarkDiagnostics()
    base = hand()
    for k in range(20):
        r = d.update(k, base + np.array([120.0 * k, -40.0 * k]))
        if k:
            assert r.motion == pytest.approx(0.0, abs=1e-9) and r.motion_flag is False and r.suspicious is False
    d = LandmarkDiagnostics()
    for k in range(20):
        a = math.radians(10 * k)
        rot = np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
        r = d.update(k, (base - base[0]) @ rot.T + base[0])
        if k:
            assert r.motion == pytest.approx(2 * math.sin(math.radians(5)) * 0.75, abs=1e-9) and r.motion_flag is False


def test_smooth_finger_bend_raises_only_the_extension_flag():
    """SYNTHETIC, not validated on real bends (none in the traces): the tip curls towards the knuckle over 30
    frames; the relative motion stays below its limit and only extensions below 0.43 are flagged."""
    d = LandmarkDiagnostics()
    flags = []
    for k in range(30):
        ext = 0.9 - 0.7 * k / 29                           # 0.90 -> 0.20
        a = math.radians(180 + 120 * k / 29)                # the tip swings round the knuckle as it curls
        tip = np.array([500.0, 420.0]) + 80 * ext * np.array([math.cos(a), math.sin(a)])
        r = d.update(k, hand(tip=tuple(tip)))
        assert r.motion_flag in (None, False)
        assert r.extension == pytest.approx(ext) and r.extension_flag is (ext < 0.43)
        flags.append(r.extension_flag)
    assert any(flags) and not all(flags)


def test_a_label_flip_alone_never_flags():
    lines = [{"seq": k, "hand": True, "handedness": "Left" if k % 2 else "Right", "source": "track",
              "landmarks": {str(i): list(p) for i, p in enumerate(hand())}} for k in range(40)]
    assert not any(r.suspicious for r in replay(lines))


# -- continuity ----------------------------------------------------------------------------------------

def test_skipped_frames_gaps_and_reacquisition_reset_the_baseline():
    d = LandmarkDiagnostics()
    far = hand(tip=(380.0, 300.0))                          # a big relative jump, but never across a break
    seq = [(1, hand(), False), (2, hand(), False), (4, far, False), (5, far, False), (6, None, False),
           (7, hand(), False), (8, far, True), (9, far, False)]
    got = [d.update(s, lm, reacquired=re) for s, lm, re in seq]
    assert got[1].motion == pytest.approx(0.0)
    assert got[2].motion is None and got[2].no_decision == ("motion: skipped camera frames",)
    assert got[3].motion == pytest.approx(0.0)              # baseline restarted at the frame after the skip
    assert got[4].no_decision == ("no hand",) and got[4].suspicious is None
    assert got[5].no_decision == ("motion: no previous usable frame",)
    assert got[6].no_decision == ("motion: reacquisition",) and got[6].motion_flag is None
    assert got[7].motion == pytest.approx(0.0)
    assert not any(g.motion_flag for g in got)


def test_trace_source_marks_a_fresh_acquisition():
    lm = {str(i): list(p) for i, p in enumerate(hand())}
    lines = [{"seq": 1, "hand": True, "landmarks": lm, "source": "track"},
             {"seq": 2, "hand": True, "landmarks": lm, "source": "search-tile"},
             {"seq": 3, "hand": True, "landmarks": lm, "source": "track"}]
    r = replay(lines)
    assert r[1].no_decision == ("motion: reacquisition",) and r[2].motion == pytest.approx(0.0)


@pytest.mark.parametrize("landmarks, reason", [
    (None, "no hand"),
    ({"0": [1.0, 2.0], "8": [3.0, 4.0]}, "missing or malformed landmarks"),               # no knuckle
    ({"0": [500, 500], "5": None, "8": [440, 420]}, "missing or malformed landmarks"),
    ({"0": [500, 500], "5": [500, float("nan")], "8": [440, 420]}, "invalid coordinates"),
    ({"0": [500, 500], "5": [500, None], "8": [440, 420]}, "invalid coordinates"),
    ({"0": [500, 500], "5": [500, 420, 0], "8": [440, 420]}, "missing or malformed landmarks"),
    (np.zeros((3, 2)), "missing or malformed landmarks"),                                    # too short for index 8
    ("garbage", "missing or malformed landmarks"),
    (hand(mcp=(500.0, 500.0)), "palm length too small"),                                    # zero palm
    (hand(mcp=(500.5, 500.5)), "palm length too small"),                                    # near-zero palm
    (hand(wrist=(float("inf"), 0.0)), "invalid coordinates"),
])
def test_invalid_input_gives_no_decision_and_resets(landmarks, reason):
    d = LandmarkDiagnostics()
    d.update(1, hand())
    r = d.update(2, landmarks)
    assert (r.motion, r.extension, r.motion_flag, r.extension_flag, r.suspicious) == (None,) * 5
    assert r.no_decision == (reason,) and r.reasons == ()
    after = d.update(3, hand())                              # consecutive seq, but the previous frame was unusable
    assert after.motion is None and after.no_decision == ("motion: no previous usable frame",)


def test_a_missing_sequence_number_gives_no_motion_decision():
    d = LandmarkDiagnostics()
    d.update(1, hand())
    r = d.update(None, hand())
    assert r.motion is None and r.no_decision == ("motion: no sequence number",) and r.extension_flag is False


# -- episodes ----------------------------------------------------------------------------------------

def test_episodes_group_consecutive_flagged_frames():
    R = ld.LandmarkDiagnostic
    res = [R(0.1, 0.8, False, False, False), R(0.6, 0.3, True, True, True, (MOTION, EXTENSION)),
           R(0.3, 0.5, True, False, True, (MOTION,)), R(None, None, None, None, None, (), ("no hand",)),
           R(None, 0.2, None, True, True, (EXTENSION,), ("motion: no previous usable frame",)), R(0.0, 0.9, False, False, False)]
    eps = episodes([1.0, 1.033, 1.066, 1.1, 1.133, 1.166], res)
    assert eps == [{"start_s": 1.033, "end_s": 1.066, "duration_s": pytest.approx(0.033), "frames": 2, "peak_motion": 0.6,
                    "min_extension": 0.3, "reasons": [EXTENSION, MOTION]},
                   {"start_s": 1.133, "end_s": 1.133, "duration_s": 0.0, "frames": 1, "peak_motion": None,
                    "min_extension": 0.2, "reasons": [EXTENSION]}]
    s = summary([1.0, 1.033, 1.066, 1.1, 1.133, 1.166], res)
    assert (s["suspicious_frames"], s["motion_flagged"], s["extension_flagged"], s["motion_decided"]) == (3, 2, 2, 4)
    assert s["observational_only"] is True and s["no_decision"] == {"no hand": 1, "motion: no previous usable frame": 1}


# -- the cursor tool: diagnostics are recorded but never change the cursor ------------------------------

def _run_tool(tmp_path, monkeypatch, frames: int, with_diagnostics: bool):
    """`cursor` end to end with a fake camera (timestamps = seq / 30 s, deterministic), a scripted fake hand
    (rigid motion, a tracking gap, a reacquisition, one landmark glitch frame, a smooth bend, label flips) and a
    stop after `frames` loop iterations. Returns the report and the trace lines."""
    import argparse
    import contextlib
    import copy
    import tomllib
    from types import SimpleNamespace

    import cv2
    from synthetic_camera import CAMERA, FakeSession, SyntheticScene
    from test_auto import auto_calibration

    from invisible_canvas.calibration.store import save_calibration
    from invisible_canvas.config import DEFAULT_CONFIG_PATH, config_from_dict
    from invisible_canvas.mapping.mapper import CoordinateMapper
    from invisible_canvas.tools import cursor as cursor_tool
    from invisible_canvas.vision.hands import AcquisitionStats, HandObservation

    with open(DEFAULT_CONFIG_PATH, "rb") as f:
        config = config_from_dict(copy.deepcopy(tomllib.load(f)), root=tmp_path)
    calibration = auto_calibration(SyntheticScene())
    save_calibration(calibration, config.calibration_dir)
    mapper = CoordinateMapper.from_calibration(calibration)
    centre = mapper.projector_to_camera([(640, 360)])[0]

    class Camera:
        def __init__(self):
            self.seq, self.frame = 0, None
            self.image = np.full((CAMERA[1], CAMERA[0], 3), 140, np.uint8)
        def wait_frame(self, after_seq=0, timeout=1.0):
            self.seq += 1 + (self.seq == 120)                   # one skipped camera frame
            self.frame = SimpleNamespace(image=self.image, seq=self.seq, timestamp=1000.0 + self.seq / 30)
            return self.frame
        def latest(self):
            return self.frame or self.wait_frame()
        reset_stats = lambda self: None                                       # noqa: E731
        stats = lambda self: SimpleNamespace(mean_fps=30.0, read_failures=0)  # noqa: E731
        read_exposure = lambda self: None                                     # noqa: E731

    class FakeTracker:
        stats = AcquisitionStats()
        action = "fake"
        calls = 0

        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *e): pass
        def process(self, image, t):
            k = FakeTracker.calls
            FakeTracker.calls += 1
            if 40 <= k < 46:
                return None                                     # tracking gap
            lm = hand(wrist=tuple(centre + (60, 80)), mcp=tuple(centre + (60, 0)), tip=tuple(centre))
            lm = lm + np.array([2.0 * (k % 50), 1.0 * (k % 30)])  # rigid hand motion
            if k == 60:
                lm[8] += (0.0, 60.0)                            # one landmark glitch frame (0.75 palm)
            if 80 <= k < 110:                                    # smooth bend: tip towards the knuckle
                lm[8] = lm[5] + (lm[8] - lm[5]) * (1 - 0.7 * (k - 80) / 29)
            return HandObservation((float(lm[8, 0]), float(lm[8, 1])), lm, "Left" if k % 2 else "Right", 0.9,
                                   source="search-tile" if k == 46 else "frame")

    if not with_diagnostics:
        class NoDiagnostics:
            def update(self, *a, **k):
                return ld.LandmarkDiagnostic(None, None, None, None, None, (), ("disabled",))
        monkeypatch.setattr(cursor_tool, "LandmarkDiagnostics", NoDiagnostics)

    @contextlib.contextmanager
    def fake_session(config, args, **kw):
        s = FakeSession()
        s.camera = Camera()
        yield s

    loop = {"n": 0}

    def wait_key(delay=0):
        if delay == 1:
            loop["n"] += 1
            return 27 if loop["n"] >= frames else -1
        return -1

    monkeypatch.setattr(cursor_tool, "open_session", fake_session)
    monkeypatch.setattr(cursor_tool, "HandTracker", FakeTracker)
    monkeypatch.setattr(cv2, "waitKey", wait_key)
    monkeypatch.setattr(cv2, "pollKey", lambda *a: -1)
    parser = argparse.ArgumentParser()
    cursor_tool.add_parser(parser.add_subparsers())
    args = parser.parse_args(["cursor", "--no-setup-check", "--smoothing", "--trace"])
    assert cursor_tool.run(config, args) == 0
    report = json.loads(sorted(config.reports_dir.glob("cursor-*.json"))[-1].read_text())
    trace = [json.loads(x) for x in open(report["trace_file"], encoding="utf-8")]
    return report, trace


def test_the_cursor_is_identical_with_and_without_landmark_diagnostics(tmp_path, monkeypatch):
    with_d, trace_with = _run_tool(tmp_path / "with", monkeypatch, 150, with_diagnostics=True)
    without, _ = _run_tool(tmp_path / "without", monkeypatch, 150, with_diagnostics=False)
    keys = ("hand", "status", "raw", "position", "reason", "score", "source", "tip_valid", "target")
    a = [tuple(json.dumps(r[k]) for k in keys) for r in with_d["records"]]
    b = [tuple(json.dumps(r[k]) for k in keys) for r in without["records"]]
    assert len(a) == len(b) == 150 and a == b
    for key in ("tracking_losses", "transitions", "reacquired_after_s", "status_fractions", "motion"):
        assert with_d[key] == without[key], key
    # the diagnostics did run and flag, and the flagged frames were still drawn as detections
    s = with_d["landmark_diagnostics"]
    assert s["observational_only"] is True and s["motion_flagged"] >= 1 and s["extension_flagged"] >= 1
    glitch = next(i for i, x in enumerate(trace_with) if x.get("diag") and x["diag"]["motion_flag"])
    assert trace_with[glitch]["status"] == "tracking" and trace_with[glitch]["drawn"] is not None
    assert all("diag" in x for x in trace_with)
    assert any(x["diag"]["no_decision"] == ["motion: skipped camera frames"] for x in trace_with)
    assert any(x["diag"]["no_decision"] == ["motion: reacquisition"] for x in trace_with)
    assert all(not x["diag"]["motion_flag"] for x in trace_with if x["diag"]["no_decision"])


# -- the four 2026-10-11 traces (local data) -----------------------------------------------------------

TRACES = {"20:29": ("202914", "203023"), "21:24": ("212416", "212712"), "21:37": ("213733", "214038"),
          "22:40": ("224039", "224326")}
TRACE_FILES = {n: REPO_ROOT / f"data/diagnostics/cursor-20261011-{t}/trace.jsonl" for n, (t, _) in TRACES.items()}
REPORT_FILES = {n: REPO_ROOT / f"data/reports/cursor-20261011-{r}.json" for n, (_, r) in TRACES.items()}
needs_traces = pytest.mark.skipif(not all(p.is_file() for p in [*TRACE_FILES.values(), *REPORT_FILES.values()]),
                                  reason="local 2026-10-11 trace/report files not present")
# Glitch events labelled in the offline analysis (D38): trajectory evidence, visual where a saved frame exists.
KNOWN = [("20:29", 2.550, 2.583, "K1"), ("21:24", 133.706, 133.738, "K2"), ("21:24", 151.243, 151.643, "K3"),
         ("21:37", 121.852, 121.852, "K4a"), ("21:37", 122.140, 122.251, "K4b"), ("21:37", 163.980, 164.253, "K5"),
         ("22:40", 24.470, 24.534, "K6"), ("22:40", 146.601, 146.633, "K7"), ("21:24", 132.170, 133.242, "N1")]
# Every labelled window (glitches, probable, ambiguous, edge, the sustained misfit and an unverified reacquisition
# frame at 21:24 131.323): flags must stay inside these (+-5 frames).
WINDOWS = {"20:29": [(2.550, 2.583)],
           "21:24": [(0.855, 1.015), (1.511, 1.575), (31.127, 31.159), (74.121, 77.130), (102.890, 103.321),
                     (130.555, 130.730), (131.323, 131.323), (132.170, 133.242), (133.706, 133.738), (133.770, 133.834),
                     (136.570, 136.603), (136.875, 136.938), (151.243, 151.643)],
           "21:37": [(51.30, 57.85), (119.067, 119.099), (121.852, 121.852), (122.140, 122.251), (163.980, 164.253)],
           "22:40": [(24.470, 24.534), (146.601, 146.633)]}
# Golden replay totals (frames, motion decided, extension decided, motion flagged, extension flagged, suspicious, episodes)
GOLDEN = {"20:29": (1523, 1463, 1465, 2, 0, 2, 1), "21:24": (4670, 4243, 4338, 38, 59, 77, 35),
          "21:37": (4967, 4551, 4654, 15, 28, 36, 11), "22:40": (4456, 4278, 4311, 4, 2, 4, 3)}


@pytest.fixture(scope="module")
def traces():
    return {n: [json.loads(x) for x in open(p, encoding="utf-8")] for n, p in TRACE_FILES.items()}


def _at(lines, t):
    return min(range(len(lines)), key=lambda i: abs(lines[i]["t"] - t))


@needs_traces
@pytest.mark.parametrize("run, onset, end, name", KNOWN, ids=[k[3] for k in KNOWN])
def test_each_known_glitch_event_is_flagged_within_two_frames(traces, run, onset, end, name):
    T = traces[run]
    res = replay(T)
    i0, i1 = _at(T, onset), _at(T, end)
    first = next(i for i in range(i0, i1 + 2) if res[i].suspicious)
    assert first - i0 <= 2, name
    assert MOTION in res[first].reasons, name


@needs_traces
def test_the_two_2240_glitches_are_flagged_at_their_first_frame(traces):
    T = traces["22:40"]
    res = replay(T)
    for t, motion_min in ((24.470, 0.6), (146.601, 1.0)):
        r = res[_at(T, t)]
        assert r.suspicious and r.motion_flag and r.motion > motion_min and EXTENSION in r.reasons
    assert res[_at(T, 146.633)].motion_flag                  # and the return frame of the 2-frame jump


@needs_traces
def test_the_2124_sustained_misfit_raises_the_extension_flag(traces):
    """21:24 74.12-77.13 s: the index pointed up but the skeleton was read as curled; landmark 8 sat ~59 camera px
    (~55 projector px) below the fingertip in all 8 saved frames, so the cursor was drawn that far off for ~3 s
    (offline analysis, visual; not re-verifiable here). The extension flag covers 25 of the 52 hand frames: the
    misfit is reported, but not every frame of it (the others read 0.43-0.7)."""
    T = traces["21:24"]
    res = replay(T)
    idx = [i for i in range(_at(T, 74.121), _at(T, 77.130) + 1) if T[i]["hand"]]
    flagged = [i for i in idx if res[i].extension_flag]
    assert len(idx) == 52 and len(flagged) == 25
    assert min(res[i].extension for i in flagged) < 0.25
    s = summary([a["t"] for a in T], res)
    in_window = [e for e in s["episodes"] if 74.1 <= e["start_s"] <= 77.2]
    assert len(in_window) >= 10 and all(EXTENSION in e["reasons"] for e in in_window)


@needs_traces
@pytest.mark.parametrize("run", list(TRACES))
def test_clean_replay_of_each_trace(traces, run):
    T = traces[run]
    res = replay(T)
    s = summary([a["t"] for a in T], res)
    got = (s["frames"], s["motion_decided"], s["extension_decided"], s["motion_flagged"], s["extension_flagged"],
           s["suspicious_frames"], len(s["episodes"]))
    assert got == GOLDEN[run]
    for a, r in zip(T, res):
        assert (r.motion is None) == (r.motion_flag is None) and (r.extension is None) == (r.extension_flag is None)
        assert r.suspicious == (True if (r.motion_flag or r.extension_flag) else
                                False if (r.motion_flag is False and r.extension_flag is False) else None)
        if not a["hand"]:
            assert r.no_decision == ("no hand",)
        if r.motion is None:
            assert r.no_decision and not r.motion_flag
    assert sum(e["frames"] for e in s["episodes"]) == s["suspicious_frames"]
    assert all(set(e["reasons"]) <= {MOTION, EXTENSION} and e["duration_s"] >= 0 for e in s["episodes"])
    allowed = set()
    for a, b in WINDOWS[run]:
        allowed.update(range(_at(T, a) - 5, _at(T, b) + 6))
    assert [T[i]["t"] for i, r in enumerate(res) if r.suspicious and i not in allowed] == []


@needs_traces
def test_label_flips_in_the_traces_never_flag_on_their_own(traces):
    n = 0
    for T in traces.values():
        res = replay(T)
        for i in range(1, len(T)):
            a, b = T[i - 1], T[i]
            if a["hand"] and b["hand"] and a["handedness"] != b["handedness"] and res[i].suspicious:
                assert res[i].motion_flag or res[i].extension_flag
                n += 1
    assert n < 40                                           # thousands of flips, a few dozen inside glitch windows


@needs_traces
@pytest.mark.parametrize("run", list(TRACES))
def test_cursor_outputs_and_jump_counter_match_the_recorded_run(traces, run):
    """The recorded traces/reports were written by the pre-D38 code: replaying the cursor state machine and One
    Euro filter reproduces every recorded state and drawn position, and the jump counter reproduces the report."""
    from invisible_canvas.tools.cursor import motion_summary
    from invisible_canvas.vision.cursor import CursorTracker, OneEuroFilter
    T = traces[run]
    rep = json.loads(REPORT_FILES[run].read_text())
    cur = CursorTracker((1280, 720), hold_s=rep["options"]["hold_ms"] / 1000, smoothing=OneEuroFilter())
    for a, r in zip(T, rep["records"]):
        # the report's "raw" is the exact cursor input (mapped fingertip, or None when there was none / it was invalid)
        assert (r["raw"] is None) == (not (a["hand"] and a["tip_in_view"]))
        u = cur.update(r["t"], r["raw"])
        assert u.status == a["status"] == r["status"]
        assert (None if u.position is None else list(u.position)) == r["position"]          # bit-identical
        if u.position is not None:
            assert np.allclose(u.position, a["drawn"], atol=0.006)                          # trace rounds to 0.01
    assert cur.losses == rep["tracking_losses"] and dict(cur.transitions) == rep["transitions"]
    m = motion_summary(rep["records"])
    assert m["spikes"] == rep["motion"]["spikes"] and m["still_samples"] == rep["motion"]["still_samples"]
    assert m["still_jitter_rms_px"] == pytest.approx(rep["motion"]["still_jitter_rms_px"], abs=1e-12)
    assert m["lag_px"] == pytest.approx(rep["motion"]["lag_px"], abs=1e-12)


def test_trace_with_targets_records_diagnostics_on_capture_frames(tmp_path, monkeypatch):
    """Regression (2026-10-12 review of D38): with --trace and targets, the capture frame reused the name of the
    landmark diagnostic for the target status text, and writing the trace line raised AttributeError ('str' object
    has no attribute 'to_json'). The run must complete, every trace line must carry the diagnostic dict, and the
    capture must be recorded as before."""
    from test_cursor_tool import _run_cursor
    report, _ = _run_cursor(tmp_path, monkeypatch, ["--targets", "640,360 640,360", "--pause", "0.2", "--trace"])
    assert [a["measured"] for a in report["accuracy"]] == [True, True]
    lines = [json.loads(x) for x in open(report["trace_file"], encoding="utf-8")]
    assert len(lines) == report["frames"]
    assert all(isinstance(x.get("diag"), dict) and "suspicious" in x["diag"] for x in lines)
    capture_t = [r["t"] for k, r in enumerate(report["records"]) if k and r["target"] != report["records"][k - 1]["target"]]
    assert len(capture_t) == 2                               # the frames on which each target was captured
    traced_t = {round(x["t"], 3) for x in lines}
    assert all(round(t, 3) in traced_t for t in capture_t)
