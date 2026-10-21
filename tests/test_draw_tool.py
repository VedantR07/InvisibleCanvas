"""`draw` and `gestures` tools (Phase 2) with a fake session: real setup check on the synthetic camera, a fake
tracker that returns synthetic hands of a scheduled shape, and the real engine, controller and canvas."""

import argparse
import contextlib
import copy
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
            shape, tip = planned
            return observation(shape, mapper.projector_to_camera([tip])[0])

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
            for phase, n in (("wait", 5), ("prepare", 10), ("hold", 60)):
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
