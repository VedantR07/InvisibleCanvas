"""`draw` and `gestures` tools (Phase 2) with a fake session: real setup check on the synthetic camera, a fake
tracker that returns synthetic hands of a scheduled shape, and the real engine, controller and canvas."""

import argparse
import contextlib
import copy
import dataclasses
import json
import time
import tomllib
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
from synthetic_camera import CAMERA, FakeSession, SyntheticScene
from synthetic_hand import CURLED, EXTENDED, hand, to_image
from test_auto import auto_calibration

from invisible_canvas.calibration.store import save_calibration
from invisible_canvas.config import DEFAULT_CONFIG_PATH, config_from_dict
from invisible_canvas.interaction.engine import EngineParams
from invisible_canvas.mapping.mapper import CoordinateMapper
from invisible_canvas.tools import draw as draw_tool
from invisible_canvas.tools import gestures as gestures_tool
from invisible_canvas.tools import tracking_session
from invisible_canvas.vision.gestures import OPEN, OTHER, PINCH, POINT
from invisible_canvas.vision.hands import AcquisitionStats, HandObservation

SHAPES = {
    POINT: dict(index=EXTENDED, middle=CURLED, ring=CURLED, pinky=CURLED, thumb="tucked"),
    OPEN: dict(thumb="spread"),
    PINCH: dict(index=(20, 25, 10), thumb="pinch"),
    OTHER: dict(index=CURLED, middle=CURLED, ring=CURLED, pinky=CURLED, thumb="tucked"),
}


def observation(shape, tip_camera):
    world = hand(**SHAPES[shape])
    lm = to_image(world, scale_px_per_m=900.0)
    lm = lm - lm[8] + np.asarray(tip_camera)
    return HandObservation((float(lm[8, 0]), float(lm[8, 1])), lm, "Right", 0.9, world=world)


def run_tool(tool, tmp_path, monkeypatch, argv, schedule):
    """schedule(seconds since the first tracked frame, mapper) -> (shape, tip in projector px) or None."""
    with open(DEFAULT_CONFIG_PATH, "rb") as f:
        config = config_from_dict(copy.deepcopy(tomllib.load(f)), root=tmp_path)
    scene = SyntheticScene()
    calibration = auto_calibration(scene)
    save_calibration(calibration, config.calibration_dir)
    mapper = CoordinateMapper.from_calibration(calibration)

    class Camera:
        def __init__(self):
            self.seq, self.frame = 0, None
            self.image = np.full((CAMERA[1], CAMERA[0], 3), 140, np.uint8)

        def wait_frame(self, after_seq=0, timeout=1.0):
            time.sleep(0.004)                       # a frame every few ms: time-based schedules stay stable
            self.seq += 1
            self.frame = SimpleNamespace(image=self.image, seq=self.seq, timestamp=time.perf_counter())
            return self.frame

        def latest(self):
            return self.frame or self.wait_frame()

        reset_stats = lambda self: None                                       # noqa: E731
        stats = lambda self: SimpleNamespace(mean_fps=60.0, read_failures=0)  # noqa: E731

    shown = []
    state = {}

    class FakeTracker:
        stats = AcquisitionStats()
        action = "fake"

        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *e):
            pass

        def process(self, image, t):
            state.setdefault("t0", t)
            planned = schedule(t - state["t0"], mapper)
            if planned is None:
                return None
            shape, tip, *in_view = planned                      # optional 3rd item: the fingertip in view
            obs = observation(shape, mapper.projector_to_camera([tip])[0])
            return obs if not in_view or in_view[0] else dataclasses.replace(obs, tip_in_view=False)

    @contextlib.contextmanager
    def fake_session(config, args, **kw):
        s = FakeSession()
        s.camera = Camera()
        s.projector = SimpleNamespace(show=lambda image: shown.append(image))
        yield s

    monkeypatch.setattr(tool, "open_session", fake_session)
    monkeypatch.setattr(tool, "HandTracker", FakeTracker)
    monkeypatch.setattr(tracking_session, "CameraMeasure", lambda s, title, **k: scene)
    monkeypatch.setattr(cv2, "waitKey", lambda *a: -1)
    monkeypatch.setattr(cv2, "pollKey", lambda *a: -1)
    parser = argparse.ArgumentParser()
    tool.add_parser(parser.add_subparsers())
    code = tool.run(config, parser.parse_args(argv))
    return code, config, shown


def test_draw_draws_one_stroke_and_saves_the_canvas(tmp_path, monkeypatch):
    def schedule(s, mapper):
        if s < 0.25:
            return OTHER, (300.0, 300.0)
        if s < 0.75:
            return POINT, (300.0 + 600 * (s - 0.25), 300.0)        # a horizontal line, 300 px long
        return OTHER, (600.0, 300.0)

    code, config, shown = run_tool(draw_tool, tmp_path, monkeypatch, ["draw", "--seconds", "1.2"], schedule)
    assert code == 0
    report = json.loads(sorted(config.reports_dir.glob("draw-*.json"))[-1].read_text())
    assert report["actions"].get("strokes") == 1 and report["strokes_on_canvas"] == 1
    assert report["setup_check"]["setup_variation_px"] < 2.0 and report["mode_entries"].get("draw") == 1
    canvas = json.loads(open(report["canvas"]["json"]).read())
    (stroke,) = canvas["strokes"]
    xs = [p[0] for p in stroke["points"]]
    assert min(xs) < 320 and max(xs) > 560 and all(abs(p[1] - 300) < 3 for p in stroke["points"])
    assert shown and shown[-1].shape == (720, 1280, 3)


def test_draw_erases_with_the_eraser_tool_and_undoes_by_dwell(tmp_path, monkeypatch):
    from invisible_canvas.canvas.toolbar import Toolbar
    tb = Toolbar((1280, 720))
    eraser, undo = tb.button("eraser").centre, tb.button("undo").centre

    def schedule(s, mapper):
        if s < 0.5:
            return POINT, (300.0 + 600 * s, 200.0)                  # pen: a line from x 300 to 600
        if s < 0.6:
            return OTHER, (640.0, 400.0)
        if s < 1.9:
            return OTHER, eraser                                     # rest on ERASER for 1.3 s: press
        if s < 2.0:
            return OTHER, (450.0, 120.0)
        if s < 2.4:
            return POINT, (450.0, 120.0 + 400 * (s - 2.0))          # swipe down across the line at x 450
        if s < 2.5:
            return OTHER, (640.0, 400.0)
        if s < 3.8:
            return OTHER, undo                                       # rest on UNDO: the erase is undone
        return OTHER, (640.0, 400.0)

    code, config, _ = run_tool(draw_tool, tmp_path, monkeypatch, ["draw", "--seconds", "4.2"], schedule)
    report = json.loads(sorted(config.reports_dir.glob("draw-*.json"))[-1].read_text())
    actions = report["actions"]
    assert actions.get("strokes") == 1 and actions.get("press:eraser") == 1
    assert actions.get("erase_strokes") == 1 and actions.get("press:undo") == 1 and actions.get("undo") == 1
    assert report["strokes_on_canvas"] == 1 and report["tool_at_end"] == "eraser"


def test_open_hand_and_fist_never_draw(tmp_path, monkeypatch):
    def schedule(s, mapper):
        return (OPEN if int(s * 4) % 2 else OTHER), (300.0 + 200 * s, 300.0)

    code, config, _ = run_tool(draw_tool, tmp_path, monkeypatch, ["draw", "--seconds", "1.5"], schedule)
    report = json.loads(sorted(config.reports_dir.glob("draw-*.json"))[-1].read_text())
    assert report["strokes_on_canvas"] == 0 and "draw" not in report["mode_entries"]


def test_g1_prime_evaluation_pass_and_failures():
    shape_for = {"point": POINT, "open": OPEN, "fist": OTHER}

    def records(rate_ok=True, draw_glitch=False, hand=True):
        out, t = [], 0.0
        for name in gestures_tool.EXPECTED:
            for phase, n in (("wait", 5), ("prepare", 40), ("hold", 60)):    # prepare 0.74 s > lift_s
                for k in range(n):
                    shape = shape_for[name]
                    if phase == "hold" and not rate_ok and name == "point" and k % 10 == 0:
                        shape = OTHER                                # 90 % POINT
                    if draw_glitch and name == "fist" and phase == "hold" and 20 <= k < 28:
                        shape = POINT                                # 8 frames: long enough to enter DRAW
                    out.append({"t": t, "prompt": name, "phase": phase, "shape": shape if hand else None})
                    t += 1 / 54
        return out

    ok = gestures_tool.evaluate(records())
    assert ok["pass"] and all(p["rate"] == 1.0 for p in ok["prompts"].values())
    assert gestures_tool.evaluate(records())["prompts"]["fist"]["expected"] == gestures_tool.NOT_POINT
    low = gestures_tool.evaluate(records(rate_ok=False))
    assert not low["pass"] and low["prompts"]["point"]["rate"] == pytest.approx(0.9) and low["evaluable"]
    glitch = gestures_tool.evaluate(records(draw_glitch=True))
    assert glitch["draw_frames_in_non_point_holds"] > 0 and not glitch["pass"]
    assert glitch["prompts"]["fist"]["rate"] == pytest.approx(52 / 60)
    none = gestures_tool.evaluate(records(hand=False))
    assert not none["evaluable"] and not none["pass"]


def test_gestures_tool_records_frames_and_reports(tmp_path, monkeypatch):
    plan = [POINT, OPEN, OTHER]

    def schedule(s, mapper):                     # roughly each prompt's shape (prompts last ~0.55 s each)
        return plan[min(int(s / 0.55), len(plan) - 1)], (640.0, 360.0)

    code, config, _ = run_tool(gestures_tool, tmp_path, monkeypatch,
                               ["gestures", "--rounds", "1", "--prepare", "0.15", "--hold", "0.35"], schedule)
    report = json.loads(sorted(config.reports_dir.glob("gestures-*.json"))[-1].read_text())
    assert report["completed"]
    frames = [json.loads(l) for l in open(report["frames_file"])]
    assert {f["prompt"] for f in frames} == set(gestures_tool.EXPECTED)
    with_hand = [f for f in frames if f["shape"] is not None]
    assert with_hand and len(with_hand[0]["landmarks"]) == 21 and len(with_hand[0]["world"]) == 21
    assert set(report["g1"]["prompts"]) == set(gestures_tool.EXPECTED)
    assert code in (0, 1)


def test_g1_prime_evaluation_runs_the_engine_with_the_keep_drawing_flag():
    # A hand still inside the keep-drawing band when the OPEN hold starts keeps the engine in DRAW (D47).
    out, t = [], 0.0
    for name, phase, n, shape, keeps in (("point", "hold", 30, POINT, True), ("open", "prepare", 40, OTHER, True),
                                         ("open", "hold", 60, OPEN, False)):
        for _ in range(n):
            out.append({"t": t, "prompt": name, "phase": phase, "shape": shape, "keeps": keeps})
            t += 1 / 54
    kept = gestures_tool.evaluate(out)["draw_frames_in_non_point_holds"]
    assert kept == pytest.approx(EngineParams().lift_s * 54, abs=2)          # D49: the pen lifts 0.6 s later
    for r in out:
        r.pop("keeps")
    assert gestures_tool.evaluate(out)["draw_frames_in_non_point_holds"] == 0


def angle_records(found=1.0, rate_ok=True):
    """Synthetic G1'' records: every pointing angle POINT, open/fist not; `found` of the hold frames with a hand."""
    out, t = [], 0.0
    for name, expected in gestures_tool.ANGLE_EXPECTED.items():
        for phase, n in (("prepare", 40), ("hold", 60)):
            for k in range(n):
                shape = POINT if expected == POINT else (OPEN if name == "open" else OTHER)
                if phase == "hold" and k >= round(60 * found) and expected == POINT:
                    shape = None
                if not rate_ok and name == "up" and phase == "hold" and k % 10 == 0:
                    shape = OTHER
                out.append({"t": t, "prompt": name, "round": 1, "phase": phase, "shape": shape,
                            "keeps": shape == POINT})
                t += 1 / 54
    return out


def test_g1_double_prime_needs_the_hand_found_at_every_angle():
    args = dict(expected=gestures_tool.ANGLE_EXPECTED, min_found=gestures_tool.G1PP_FOUND)
    ok = gestures_tool.evaluate(angle_records(), **args)
    assert ok["pass"] and "G1''" in ok["criterion"] and ok["prompts"]["up"]["found_rate"] == 1.0
    lost = gestures_tool.evaluate(angle_records(found=0.8), **args)                # 48 of 60 hold frames
    assert not lost["pass"] and lost["evaluable"]
    assert lost["prompts"]["sideways"]["rate"] == 1.0 and not lost["prompts"]["sideways"]["pass"]
    assert gestures_tool.evaluate(angle_records(found=0.8), expected=gestures_tool.ANGLE_EXPECTED)["pass"]  # G1' rule
    rare = gestures_tool.evaluate(angle_records(found=0.3), **args)                # 18 hand frames: still a FAIL
    assert rare["evaluable"] and not rare["prompts"]["up"]["pass"]
    assert not gestures_tool.evaluate(angle_records(rate_ok=False), **args)["pass"]


def test_timing_uses_the_g6_limits():
    fast = [{"t": k / 50, "pipeline_ms": 20.0} for k in range(100)]
    assert gestures_tool.timing(fast)["pass"] and gestures_tool.timing(fast)["processing_fps"] == pytest.approx(50)
    assert not gestures_tool.timing([{"t": k / 50, "pipeline_ms": 40.0} for k in range(100)])["pass"]
    assert not gestures_tool.timing([{"t": k / 20, "pipeline_ms": 20.0} for k in range(100)])["pass"]


def test_angles_recording_with_video_then_replay(tmp_path, monkeypatch):
    from invisible_canvas.tools import replay as replay_tool
    names = [p[0] for p in gestures_tool.ANGLE_PROMPTS]
    shape_of = {name: (POINT if e == POINT else OPEN if name == "open" else OTHER)
                for name, e in gestures_tool.ANGLE_EXPECTED.items()}

    def schedule(s, mapper):                     # roughly each prompt's shape (prompts last ~0.55 s each)
        return shape_of[names[min(int(s / 0.55), len(names) - 1)]], (640.0, 360.0)

    code, config, shown = run_tool(gestures_tool, tmp_path, monkeypatch,
                                   ["gestures", "--angles", "--video", "--rounds", "1", "--prepare", "0.15",
                                    "--hold", "0.35"], schedule)
    report = json.loads(sorted(config.reports_dir.glob("gestures-*.json"))[-1].read_text())
    assert report["test"] == "G1''" and report["prompt_set"] == "angles" and report["completed"]
    assert set(report["g1"]["prompts"]) == set(names) and "processing_fps" in report["timing"]
    rows = [json.loads(l) for l in open(report["frames_file"])]
    with_video = [r for r in rows if r["video_index"] is not None]
    assert report["video"]["frames"] == len(with_video) > 0
    assert report["video"]["frames"] + report["video"]["dropped"] == len(rows)
    assert [r["video_index"] for r in with_video] == list(range(len(with_video)))
    assert all("pipeline_ms" in r and "keeps" in r for r in rows)

    folder = config.reports_dir.parent / "diagnostics" / report["frames_file"].replace("\\", "/").split("/")[-2]
    prompt_at = {r["t"]: r["prompt"] for r in rows}

    class PromptTracker:                         # stands in for MediaPipe: the prompted shape, every frame
        def __init__(self, *a, **k):
            self.frames = 0

        def __enter__(self):
            return self

        def __exit__(self, *e):
            pass

        def process(self, image, t):
            assert image.shape == (1080, 1920, 3)
            self.frames += 1
            return observation(shape_of[prompt_at[t]], (900.0, 500.0))

    tracker = PromptTracker()
    records = replay_tool.replay(folder, tracker)
    assert tracker.frames == len(records) == len(with_video)
    summary = replay_tool.summarize(records, gestures_tool.ANGLE_EXPECTED, gestures_tool.G1PP_FOUND)
    assert all(p["rate"] == 1.0 for p in summary["overall"]["prompts"].values() if p["hand_frames"])
    assert set(summary["rounds"]) == {"1"} and 0.0 <= summary["shape_agreement_with_live"] <= 1.0

    monkeypatch.setattr(replay_tool, "HandTracker", PromptTracker)
    parser = argparse.ArgumentParser()
    replay_tool.add_parser(parser.add_subparsers())
    replay_tool.run(config, parser.parse_args(["replay", str(folder)]))
    saved = json.loads(sorted(config.reports_dir.glob("replay-*.json"))[-1].read_text())
    assert saved["test"] == "G1''" and saved["frames"] == len(with_video)


def test_replay_refuses_a_recording_without_video(tmp_path):
    from invisible_canvas.tools import replay as replay_tool
    (tmp_path / "frames.jsonl").write_text("")
    with pytest.raises(replay_tool.ReplayError):
        replay_tool.load_rows(tmp_path)


def test_g8_evaluation_compares_light_off_and_on():
    def recs(found_off, found_on, fps=50.0, pipe=20.0):
        out, t = [], 0.0
        for rnd in (1, 2, 3, 4):
            on = rnd % 2 == 0
            for name, expected in gestures_tool.ANGLE_EXPECTED.items():
                for k in range(60):
                    seen = k < round(60 * (found_on if on else found_off))
                    shape = (POINT if expected == POINT else OPEN) if seen else None
                    out.append({"t": t, "prompt": name, "round": rnd, "phase": "hold", "shape": shape,
                                "light": on, "pipeline_ms": pipe})
                    t += 1 / fps
                t += 3.0                                                 # the next prompt's gate and prepare
        return out
    ok = gestures_tool.evaluate_light(recs(0.7, 0.95), gestures_tool.ANGLE_EXPECTED)
    assert ok["pass"] and ok["off"]["found_rate"] == pytest.approx(0.7, abs=0.01)
    assert ok["on"]["found_rate"] == pytest.approx(0.95, abs=0.01) and ok["timing_light_on"]["processing_fps"] == pytest.approx(50)
    assert not gestures_tool.evaluate_light(recs(0.7, 0.85), gestures_tool.ANGLE_EXPECTED)["pass"]   # < 90 %
    assert not gestures_tool.evaluate_light(recs(0.98, 0.93), gestures_tool.ANGLE_EXPECTED)["pass"]  # worse than off
    assert not gestures_tool.evaluate_light(recs(0.7, 0.95, pipe=40.0), gestures_tool.ANGLE_EXPECTED)["pass"]


def test_gestures_busy_light_ab_records_the_light_per_round(tmp_path, monkeypatch):
    names = [p[0] for p in gestures_tool.ANGLE_PROMPTS]
    shape_of = {n: (POINT if e == POINT else OPEN if n == "open" else OTHER) for n, e in gestures_tool.ANGLE_EXPECTED.items()}

    def schedule(s, mapper):
        return shape_of[names[min(int(s / 0.55), len(names) - 1) % len(names)]], (640.0, 400.0)

    code, config, shown = run_tool(gestures_tool, tmp_path, monkeypatch,
                                   ["gestures", "--angles", "--busy", "--light", "ab", "--rounds", "2",
                                    "--prepare", "0.15", "--hold", "0.35"], schedule)
    report = json.loads(sorted(config.reports_dir.glob("gestures-*.json"))[-1].read_text())
    assert report["test"] == "G8" and report["busy"] and report["light"] == "ab" and report["g8"] is not None
    rows = [json.loads(l) for l in open(report["frames_file"])]
    assert {r["light"] for r in rows if r["round"] == 1} == {False} and {r["light"] for r in rows if r["round"] == 2} == {True}
    assert shown[-2].shape == (720, 1280, 3)


def test_draw_light_is_off_by_default_and_can_be_turned_on(tmp_path, monkeypatch):
    def schedule(s, mapper):
        return OTHER, (640.0, 360.0)
    for argv, lit in ((["draw", "--seconds", "0.4"], False), (["draw", "--seconds", "0.4", "--light"], True)):
        code, config, shown = run_tool(draw_tool, tmp_path / str(lit), monkeypatch, argv, schedule)
        report = json.loads(sorted(config.reports_dir.glob("draw-*.json"))[-1].read_text())
        assert report["light"] is lit
        frame = shown[-2]                                     # the last canvas frame before the closing blank
        assert (frame[360, 640].tolist() == [255, 255, 255]) or not lit


def test_draw_with_ai_asks_through_the_panel_and_reports_the_answer(tmp_path, monkeypatch):
    # D51 end to end with a fake Claude: a stroke, AI button by dwell, SUMMARIZE by dwell, the answer back.
    from invisible_canvas.ai.client import AIAnswer
    from invisible_canvas.canvas.panel import AIPanel
    from invisible_canvas.canvas.toolbar import Toolbar
    tb = Toolbar((1280, 720), ai=True)
    ai_button = tb.button("ai").centre
    summarize = next(b for b in AIPanel((1280, 720), tb.top).buttons if b.name == "ai:summarize").centre
    asked = []

    class FakeAssistant:
        def __init__(self, cfg, client=None):
            pass

        def ask(self, action, png):
            asked.append((action, png))
            time.sleep(0.3)                                       # the frame loop keeps running meanwhile
            return AIAnswer(action, ok=True, transcription="hi", result="A greeting.", latency_s=0.3)

    monkeypatch.setattr(draw_tool, "ClaudeAssistant", FakeAssistant)
    monkeypatch.setattr(draw_tool, "LocalAssistant", FakeAssistant)               # D52: local is the default

    def schedule(s, mapper):
        if s < 0.5:
            return POINT, (300.0 + 400 * s, 300.0)                # a stroke
        if s < 1.4:
            return OTHER, (500.0, 400.0)                          # pen lifts (D49: 0.6 s)
        if s < 2.7:
            return OTHER, ai_button                               # AI button: open the panel
        if s < 2.8:
            return OTHER, (500.0, 400.0)
        if s < 4.1:
            return OTHER, summarize                               # SUMMARIZE
        return OTHER, (500.0, 400.0)

    code, config, shown = run_tool(draw_tool, tmp_path, monkeypatch, ["draw", "--seconds", "5.0", "--ai", "--trace"],
                                   schedule)
    report, trace = draw_report(config)
    ai = report["ai"]
    assert sum(line["ai_busy"] for line in trace) == ai["busy_frames"]       # per frame in the trace (§9.13)
    assert report["actions"].get("press:ai") == 1 and report["actions"].get("press:ai:summarize") == 1
    assert ai["requests"] == 1 and len(ai["answers"]) == 1 and ai["answers"][0]["ok"]
    assert asked and asked[0][0] == "summarize" and asked[0][1][:4] == b"\x89PNG"
    assert ai["busy_frames"] > 5 and ai["busy_processing_fps"] > 30            # S3 in the fake session
    assert list((config.root / "data" / "ai").glob("*-summarize.json"))


def test_draw_without_ai_has_no_ai_report(tmp_path, monkeypatch):
    code, config, shown = run_tool(draw_tool, tmp_path, monkeypatch, ["draw", "--seconds", "0.3"],
                                   lambda s, mapper: (OTHER, (640.0, 360.0)))
    report = json.loads(sorted(config.reports_dir.glob("draw-*.json"))[-1].read_text())
    assert report["ai"] is None


# -- §9.12 Stage 3 item 1: diagnostics in `draw` (observation only) ------------------------------------------

OLD_TRACE_KEYS = {"t", "seq", "mode", "pending", "shape", "cursor", "events", "source", "lit"}
OLD_REPORT_KEYS = {"created_at", "calibration_created_at", "setup_check", "brightness", "duration_s", "frames",
                   "processing_fps", "camera_fps", "inference_ms", "pipeline_ms", "pipeline_ms_with_hand",
                   "mode_frames", "mode_entries", "shape_frames", "actions", "tool_at_end", "strokes_on_canvas",
                   "canvas", "trace", "light", "selections", "ai"}


def draw_report(config):
    report = json.loads(sorted(config.reports_dir.glob("draw-*.json"))[-1].read_text())
    trace = [json.loads(line) for line in open(report["trace"])] if report["trace"] else []
    return report, trace


def test_diagnostics_record_the_toolbar_trap_without_changing_it(tmp_path, monkeypatch):
    def schedule(s, mapper):
        if s < 0.3:
            return OTHER, (300.0, 690.0)                          # hovering over the toolbar strip
        if s < 0.7:
            return POINT, (300.0, 690.0)                          # pointing there: the stroke starts in the band
        if s < 1.3:
            return POINT, (300.0, 690.0 - 650 * (s - 0.7))        # still pointing, up onto the canvas
        return OTHER, (600.0, 300.0)

    code, config, _ = run_tool(draw_tool, tmp_path, monkeypatch, ["draw", "--seconds", "2.3", "--trace"], schedule)
    report, trace = draw_report(config)
    assert code == 0 and OLD_REPORT_KEYS <= set(report)
    assert report["strokes_on_canvas"] == 0 and report["actions"].get("strokes_refused_on_toolbar") == 1
    assert "strokes" not in report["actions"]                     # behaviour as before: nothing drawn
    d = report["diagnostics"]
    assert d["strokes"]["attempts"] == 1 and d["strokes"]["refused"] == {"refused_band": 1}
    assert d["strokes"]["attempts_with_points_after_refusal"] == 1
    assert d["ink"]["refused_band:toolbar"] == 1 and d["ink"]["after_refused_start:canvas"] > 10
    assert all(OLD_TRACE_KEYS <= set(line) for line in trace)
    start = next(line for line in trace if "stroke_start" in line["events"])
    assert start["state"] == "start" and start["ink"]["refused_band:toolbar"] == 1 and start["stroke"] == 1
    dead = [line for line in trace if line["ink"] and "after_refused_start:canvas" in line["ink"]]
    assert dead and all(line["stroke"] == 1 and line["stroke_id"] is None for line in dead)
    assert all(line["state"] == "blocked" and line["blocked"] == "toolbar" for line in dead)     # D56: shown
    assert all(line["status"] in ("ok", "no-hand") and line["action"] == "fake" for line in trace)


def test_diagnostics_record_the_bottom_strip_a_hand_loss_and_the_lift(tmp_path, monkeypatch):
    def schedule(s, mapper):
        if s < 0.2:
            return OTHER, (200.0, 600.0)
        if s < 1.0:                                               # along the bottom strip, dipping to y 690
            x = 200.0 + 500 * (s - 0.2)
            return POINT, (x, 600.0 + (90.0 if 0.45 < s < 0.65 else 0.0))
        if s < 1.25:
            return None                                           # hand lost 0.25 s (< the 0.6-s window)
        if s < 1.7:
            return POINT, (600.0 + 500 * (s - 1.25), 600.0)
        if s < 2.6:
            return None                                           # gone: the pen lifts
        return OTHER, (640.0, 300.0)

    code, config, _ = run_tool(draw_tool, tmp_path, monkeypatch, ["draw", "--seconds", "3.0", "--trace"], schedule)
    report, trace = draw_report(config)
    # D56: the stroke ends at the dip into the toolbar; the writing after it (and after the dropout) is not drawn
    assert report["strokes_on_canvas"] == 1 and report["actions"]["strokes"] == 1
    assert report["actions"]["strokes_ended_on_toolbar"] == 1
    d = report["diagnostics"]
    assert d["ink"]["ended_band:toolbar"] == 1 and d["ink"]["added:canvas"] > 20
    assert d["strokes"]["ended_on_ui"] == 1 and d["strokes"]["points_after_ui_end"] > 20
    (stroke,) = json.load(open(report["canvas"]["json"], encoding="utf-8"))["strokes"]
    assert max(p[0] for p in stroke["points"]) < 200 + 500 * 0.45 and all(p[1] < 648 for p in stroke["points"])
    blocked = [line for line in trace if line["state"] == "blocked"]
    assert blocked and all(line["blocked"] == "toolbar" and line["mode"] == "draw" for line in blocked)
    assert d["states"]["held"] > 0 and d["states"]["lifted"] == 1 and d["states"]["start"] == 1
    assert d["bands"]["bottom"]["losses"] >= 1 and d["bands"]["bottom"]["hand_frames"] > 0
    assert d["hand_status"]["no-hand"] > 0
    held = [line for line in trace if line["state"] == "held"]
    assert held and all(line["mode"] == "draw" and line["status"] == "no-hand" for line in held)


def test_diagnostics_record_a_fingertip_outside_the_view_and_below_the_canvas(tmp_path, monkeypatch):
    def schedule(s, mapper):
        if s < 0.4:
            return POINT, (640.0, 300.0), False                   # fingertip outside MediaPipe's view
        if s < 0.6:
            return OTHER, (640.0, 760.0)
        if s < 1.2:
            return POINT, (640.0, 760.0)                          # pointing below the canvas
        return OTHER, (640.0, 300.0)

    code, config, _ = run_tool(draw_tool, tmp_path, monkeypatch, ["draw", "--seconds", "1.8", "--trace"], schedule)
    report, trace = draw_report(config)
    d = report["diagnostics"]
    assert d["hand_status"]["tip-outside-view"] > 0 and d["states"]["tip-outside-view"] > 0
    assert d["ink"]["refused_band:below"] == 1 and report["strokes_on_canvas"] == 0
    outside = [line for line in trace if line["status"] == "tip-outside-view"]
    assert outside and all(line["tip_in_view"] is False and line["raw_proj"] is None for line in outside)
    below = [line for line in trace if line["where"] == "below"]
    assert below and all(line["raw_proj"][1] > 719 for line in below if line["raw_proj"])


def test_diagnostics_timing_and_overhead_are_reported(tmp_path, monkeypatch):
    code, config, _ = run_tool(draw_tool, tmp_path, monkeypatch, ["draw", "--seconds", "0.8", "--trace"],
                               lambda s, mapper: (POINT, (300.0 + 300 * s, 300.0)))
    report, trace = draw_report(config)
    d = report["diagnostics"]
    assert set(d["stage_ms"]) == {"queue", "inference", "hand", "engine", "controller", "ai", "render", "show",
                                  "diag", "trace", "post"}
    assert all(d["stage_ms"][s]["count"] >= len(trace) - 1 for s in ("hand", "engine", "render", "diag", "post"))
    assert d["overhead"]["diag_ms"]["median"] is not None and d["loop_ms"]["count"] == len(trace) - 1
    line = trace[-1]
    assert set(line["stage_ms"]) == {"hand", "engine", "controller", "ai", "render", "show"}
    assert line["pipeline_ms"] >= line["inference_ms"] and line["queue_ms"] >= 0
