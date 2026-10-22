"""Shared by the gesture tools (`draw`, `gestures`, `replay`; brain.md §9.10): the setup check with the
validated automatic recovery (D28, D39, as in `cursor`), the brightness pre-check (D34), one frame's hand shape
(ShapeReader), and one frame's hand as smoothed projector points with its shape (HandPoints).
"""

from __future__ import annotations

import cv2
import numpy as np

from ..calibration.auto import AutoCalibrationError, auto_setup_check
from ..calibration.recovery import explain
from ..display import patterns
from ..interaction.engine import HandInput
from ..mapping.mapper import CoordinateMapper
from ..vision.cursor import OneEuroFilter
from ..vision.gestures import GestureParams, HandShape, classify, palm_centre, pinch_point
from ..vision.hands import INDEX_TIP
from .common import CameraMeasure, capture_frames
from .hand_check import DARK_REGION_LUMA, canvas_mask, region_luma
from .recalibrate import TITLE as RECOVERY_TITLE
from .recalibrate import recover_in_session
from .validate import setup_limit

# MediaPipe hand skeleton, for the operator view.
BONES = ((0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8), (5, 9), (9, 10), (10, 11), (11, 12),
         (9, 13), (13, 14), (14, 15), (15, 16), (13, 17), (0, 17), (17, 18), (18, 19), (19, 20))
ERASER_SCALE, ERASER_MIN, ERASER_MAX = 0.6, 25.0, 140.0     # eraser radius = 0.6 x palm length (projector px)
# The hand tracker of the gesture tools (`draw`, `gestures`, `replay`: one setting, so a replay matches the live
# run). D48: hand presence and tracking confidence 0.3 (MediaPipe default 0.5) keep a pointing hand seen from
# behind; on the 2026-10-22 angle recording (replay) up-left round 2 82.7 -> 99.6 % of hold frames with a hand,
# all frames 90.0 -> 92.2 %. Detection confidence stays 0.5 (0.3 did not help). `cursor` keeps its own setting.
TRACKER_OPTIONS = {"acquisition": "tiled", "min_presence": 0.3, "min_tracking": 0.3}


def checked_mapper(config, s, calibration, *, no_recalibrate: bool, title: str):
    """(mapper, calibration, info) for a setup that matches its calibration, or None (with the reason printed).
    A moved setup is recovered automatically, validated before it is used (D39), unless `no_recalibrate`."""
    limit = setup_limit(config, calibration)
    try:
        setup, corners = auto_setup_check(CameraMeasure(s, title=title), calibration, s.canvas_size, limit)
    except AutoCalibrationError as e:
        print(f"setup check failed, corners not detected: {e}")
        for hint in explain([str(e), *e.details]):
            print(f"  hint: {hint}")
        return None
    print(f"setup check: variation {setup.variation:.2f} px (limit {limit:g}): "
          f"{'unchanged' if setup.consistent else 'MOVED'}")
    info = {"setup_variation_px": setup.variation, "limit_px": limit, "recovery": None}
    if not setup.consistent:
        if no_recalibrate:
            print("The setup has moved since the calibration. Run `recalibrate` or `calibrate` first.")
            return None
        result, report = recover_in_session(config, s, calibration, setup, corners, CameraMeasure(s, title=RECOVERY_TITLE))
        info["recovery"] = {"status": result.status, "stage": result.stage, "report": str(report),
                            "previous_calibration_created_at": calibration.created_at}
        if not result.accepted:
            print("Not starting with a calibration the setup check refused.")
            return None
        calibration, setup = result.candidate, result.confirmation
        info["setup_variation_px"] = setup.variation
    return CoordinateMapper.from_calibration(calibration), calibration, info


def brightness_check(s, mapper, screen: np.ndarray) -> dict:
    """Project `screen` and measure how bright the canvas region is for the camera (hand detection, D34)."""
    s.projector.show(screen)
    _, frames = capture_frames(s, 5)
    still = np.median(np.stack(frames), axis=0).astype(np.uint8)
    region = canvas_mask(mapper, s.camera_info.size)
    luma = region_luma(still, region)
    too_dark = luma < DARK_REGION_LUMA
    print(f"canvas region brightness {luma:.0f}" + (f"  WARNING: too dark (< {DARK_REGION_LUMA:g}) for hand detection"
                                                    if too_dark else ""))
    return {"canvas_region_luma": luma, "too_dark": bool(too_dark)}


class ShapeReader:
    """One frame's hand -> its HandShape, keeping the previous shape for the pinch hysteresis. None (and reset)
    for no hand or an extrapolated fingertip (D37: never drawn). The live tools and `replay` share it, so a
    replay classifies exactly as the live run did."""

    def __init__(self, params: GestureParams = GestureParams()):
        self.params = params
        self.previous: str | None = None

    def reset(self) -> None:
        self.previous = None

    def __call__(self, obs) -> HandShape | None:
        if obs is None or not obs.tip_in_view:
            self.reset()
            return None
        shape = classify(obs.landmarks, obs.world, previous=self.previous, params=self.params)
        self.previous = shape.shape
        return shape


class HandPoints:
    """One frame's hand -> (HandShape, HandInput in projector px), with One Euro smoothing per point (D37)."""

    def __init__(self, mapper: CoordinateMapper):
        self.mapper = mapper
        self.shapes = ShapeReader()
        self._filters = {k: OneEuroFilter() for k in ("pointer", "pinch", "palm")}

    def reset(self) -> None:
        self.shapes.reset()
        for f in self._filters.values():
            f.reset()

    def __call__(self, t: float, obs):
        """None (and reset) for no hand or an extrapolated fingertip (D37: never drawn)."""
        shape = self.shapes(obs)
        if shape is None:
            self.reset()
            return None, None
        cam = obs.landmarks
        proj = self.mapper.camera_to_projector(np.array([cam[INDEX_TIP], pinch_point(cam), palm_centre(cam),
                                                         cam[0], cam[9]]))
        if not np.all(np.isfinite(proj)):
            self.reset()
            return shape, None
        radius = float(np.clip(ERASER_SCALE * np.linalg.norm(proj[4] - proj[3]), ERASER_MIN, ERASER_MAX))
        pointer, pinch, palm = (tuple(float(v) for v in self._filters[k](t, p))
                                for k, p in zip(("pointer", "pinch", "palm"), proj[:3]))
        return shape, HandInput(shape.shape, pointer, pinch, palm, radius, keeps_draw=shape.keeps_point)


def draw_skeleton(view: np.ndarray, landmarks: np.ndarray, colour=patterns.GREEN) -> None:
    pts = np.round(landmarks).astype(int)
    for a, b in BONES:
        cv2.line(view, tuple(pts[a]), tuple(pts[b]), colour, 2, cv2.LINE_AA)
