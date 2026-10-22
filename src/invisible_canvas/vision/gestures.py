"""Hand shapes for gesture drawing (Phase 2, brain.md §9.10, D44). Pure: no I/O.

    POINT  index finger only (middle, ring and little finger curled)  -> draw
    OPEN   all five fingers open                                      -> erase
    PINCH  thumb tip on the index tip                                 -> select / press
    OTHER  anything else (fist, relaxed hand, two fingers)            -> hover

Measures, all scale-free:
- fold angle of a finger = angle between the palm direction (wrist -> knuckle) and the finger direction
  (knuckle -> tip): ~0-30 deg for an extended finger, ~90-135 deg for a curled one. It sees a finger folded at
  the knuckle, which a straightness measure (bends within the finger) misses: on the user's pointing frames of
  2026-10-21 the curled fingers were folded mainly at the knuckle (straightness 0.7-0.85, like a straight
  finger), while their fold angles were 89-118 deg (median) against 17 deg for the index (brain.md D44);
- pinch ratio = |thumb tip - index tip| / palm size (wrist -> middle knuckle);
- thumb ratio = |thumb tip - index knuckle| / palm size: large when the thumb is spread (open hand).

MediaPipe's 3-D world landmarks (metres, hand-centred) are used when given: the camera sees the back of
the hand from behind the user, and a finger pointing towards or away from the camera looks short in 2-D.
The 2-D camera landmarks are the fallback.

Multi-angle pointing (D48), from the 2-D camera landmarks when given (both rules were chosen on the recordings
of 2026-10-22 and checked against every recorded prompt, brain.md §13.2):
- the index also counts as extended when its 3-D fold is moderate (<= 65 deg) AND it reaches far from the wrist
  in the image (>= 1.6 palm sizes): pointing sideways with the hand cocked gave folds of ~54 deg for a straight
  finger, while a fist's index folds >= ~78 deg whatever the image shows;
- a "phantom" middle finger counts as curled: seen from behind, the tracker can put the middle finger on the one
  visible index finger; it then reads straight (< 45 deg) with its tip on the index tip (< 0.35 palm sizes). A
  half-curled middle finger near the index (a pinch seen from behind: 51-58 deg) stays a middle finger.

`keeps_point` (D47): looser limits that only keep a stroke going once drawing has started (the interaction
engine decides). While drawing, the user's pointing hand drifts just past the strict limits (G3 run 1: index
fold up to ~53 deg, middle down to ~54 deg) but stays far from an open hand (middle ~38 deg) or a fist (index
~90 deg). Starting a stroke still needs a strict POINT.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

POINT, OPEN, PINCH, OTHER = "point", "open", "pinch", "other"
SHAPES = (POINT, OPEN, PINCH, OTHER)

WRIST, THUMB_TIP, INDEX_MCP, INDEX_TIP, MIDDLE_MCP, MIDDLE_TIP = 0, 4, 5, 8, 9, 12
FINGERS = {
    "index": (5, 6, 7, 8),
    "middle": (9, 10, 11, 12),
    "ring": (13, 14, 15, 16),
    "pinky": (17, 18, 19, 20),
}
THUMB = (1, 2, 3, 4)
PALM = (0, 5, 9, 13, 17)          # wrist and the four finger knuckles: the palm centre


@dataclass(frozen=True)
class GestureParams:
    # From the 2026-10-21 frames (world 3-D, D44): pointing index fold median 17 deg (p95 43); curled middle /
    # ring median 101 / 118 deg; the user's little finger stays looser when pointing (52-66 deg in some frames).
    extended_max_deg: float = 45.0   # fold angle at or below: finger extended
    curled_min_deg: float = 60.0     # fold angle at or above: middle / ring finger curled
    pinky_curled_min_deg: float = 45.0   # the little finger only has to be not extended for POINT
    thumb_out_min: float = 0.5       # thumb ratio at or above: thumb spread (needed for OPEN)
    pinch_enter: float = 0.25        # pinch ratio below: pinching
    pinch_exit: float = 0.38         # ... and, once pinching, it stays a pinch until above this (hysteresis)
    # In a fist the thumb lies on the curled index, close to its tip: not a pinch. A pinching index bends
    # moderately (~30-70 deg), a fist's index folds right back (~140 deg).
    pinch_index_max_deg: float = 110.0
    # D47 keep-drawing band: each strict limit moved 15 deg towards the other side; the thumb is ignored.
    keep_extended_max_deg: float = 60.0
    keep_curled_min_deg: float = 45.0
    keep_pinky_curled_min_deg: float = 30.0
    # D48 multi-angle pointing (2-D measures in palm sizes: wrist -> middle knuckle in the image)
    alt_extended_max_deg: float = 65.0   # index fold up to this counts as extended when ...
    alt_reach_min: float = 1.6           # ... the index tip is at least this far from the wrist in the image
    phantom_gap_max: float = 0.35        # middle tip this close to the index tip, middle straight: a phantom


@dataclass(frozen=True)
class HandShape:
    shape: str
    fold_deg: dict                # finger -> fold angle (degrees)
    pinch_ratio: float
    thumb_ratio: float
    space: str                    # "world" (3-D, metres) or "image" (2-D camera px)
    keeps_point: bool = False     # within the keep-drawing band (D47); true for every strict POINT
    index_reach: float | None = None   # D48: 2-D wrist -> index tip / palm size (None without camera landmarks)
    tip_gap: float | None = None       # D48: 2-D index tip -> middle tip / palm size
    phantom_middle: bool = False       # D48: the middle finger was read as a copy of the index

    def as_dict(self) -> dict:
        return {"shape": self.shape, "space": self.space, "pinch_ratio": round(self.pinch_ratio, 3),
                "thumb_ratio": round(self.thumb_ratio, 3), "keeps_point": self.keeps_point,
                "index_reach": None if self.index_reach is None else round(self.index_reach, 3),
                "tip_gap": None if self.tip_gap is None else round(self.tip_gap, 3),
                "phantom_middle": self.phantom_middle,
                **{f"{k}_fold": round(v, 1) for k, v in self.fold_deg.items()}}


def fold_angle(points: np.ndarray, chain) -> float:
    """Degrees between the palm direction (wrist -> knuckle) and the finger direction (knuckle -> tip)."""
    knuckle, tip = points[chain[0]], points[chain[-1]]
    palm_dir, finger_dir = knuckle - points[WRIST], tip - knuckle
    norm = float(np.linalg.norm(palm_dir) * np.linalg.norm(finger_dir))
    if norm <= 1e-12:
        return 180.0          # a zero-length finger cannot count as extended
    return float(np.degrees(np.arccos(np.clip(np.dot(palm_dir, finger_dir) / norm, -1.0, 1.0))))


def palm_size(points: np.ndarray) -> float:
    return float(np.linalg.norm(points[MIDDLE_MCP] - points[WRIST]))


def classify(landmarks, world=None, *, previous: str | None = None,
             params: GestureParams = GestureParams()) -> HandShape:
    """The hand shape from 21 landmarks: `world` (21, 3) if given, else the 2-D `landmarks` (21, 2), for the
    fold angles; the 2-D `landmarks`, when given, also for the D48 measures. `previous`: the last classified
    shape (pinch hysteresis)."""
    pts = np.asarray(world if world is not None else landmarks, dtype=np.float64)
    if pts.shape[0] != 21 or pts.ndim != 2 or pts.shape[1] not in (2, 3) or not np.all(np.isfinite(pts)):
        raise ValueError(f"expected 21 finite 2-D or 3-D landmarks, got shape {pts.shape}")
    space = "world" if world is not None else "image"
    palm = palm_size(pts)
    if palm <= 1e-9:
        raise ValueError("degenerate hand: wrist and middle knuckle coincide")
    fold = {name: fold_angle(pts, chain) for name, chain in FINGERS.items()}
    pinch_ratio = float(np.linalg.norm(pts[THUMB_TIP] - pts[INDEX_TIP]) / palm)
    thumb_ratio = float(np.linalg.norm(pts[THUMB_TIP] - pts[INDEX_MCP]) / palm)

    reach = gap = None
    if landmarks is not None:
        image = np.asarray(landmarks, dtype=np.float64)[:, :2]
        palm_2d = palm_size(image)
        if image.shape[0] == 21 and np.all(np.isfinite(image)) and palm_2d > 1e-9:
            reach = float(np.linalg.norm(image[INDEX_TIP] - image[WRIST]) / palm_2d)
            gap = float(np.linalg.norm(image[INDEX_TIP] - image[MIDDLE_TIP]) / palm_2d)

    limit = params.pinch_exit if previous == PINCH else params.pinch_enter
    extended = {k: v <= params.extended_max_deg for k, v in fold.items()}
    index_extended = extended["index"] or (reach is not None and fold["index"] <= params.alt_extended_max_deg
                                           and reach >= params.alt_reach_min)
    phantom = bool(index_extended and gap is not None and gap < params.phantom_gap_max and extended["middle"])
    if pinch_ratio < limit and fold["index"] <= params.pinch_index_max_deg:
        shape = PINCH
    elif (index_extended and (fold["middle"] >= params.curled_min_deg or phantom)
          and fold["ring"] >= params.curled_min_deg and fold["pinky"] >= params.pinky_curled_min_deg):
        shape = POINT
    elif all(extended.values()) and thumb_ratio >= params.thumb_out_min:
        shape = OPEN
    else:
        shape = OTHER
    keeps = shape == POINT or (fold["index"] <= params.keep_extended_max_deg
                               and (fold["middle"] >= params.keep_curled_min_deg or phantom)
                               and fold["ring"] >= params.keep_curled_min_deg
                               and fold["pinky"] >= params.keep_pinky_curled_min_deg)
    return HandShape(shape, fold, pinch_ratio, thumb_ratio, space, keeps, reach, gap, phantom)


def palm_centre(points: np.ndarray) -> np.ndarray:
    """Mean of the wrist and the four finger knuckles (the eraser position)."""
    return np.asarray(points, dtype=np.float64)[list(PALM)].mean(axis=0)


def pinch_point(points: np.ndarray) -> np.ndarray:
    """Midway between the thumb tip and the index tip (the selection position)."""
    p = np.asarray(points, dtype=np.float64)
    return (p[THUMB_TIP] + p[INDEX_TIP]) / 2.0
