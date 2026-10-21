"""Synthetic 21-landmark hands (MediaPipe order) in metres, for gesture tests.

The palm points along +y from the wrist at the origin, the knuckles spread along x, and a straight finger
continues the wrist -> knuckle line; fingers fold towards -z (the palm side). Each finger is given its joint
bends in degrees (knuckle, middle, end joint).
"""

from __future__ import annotations

import numpy as np

KNUCKLES_X = {"index": 0.03, "middle": 0.01, "ring": -0.01, "pinky": -0.028}
KNUCKLES_Y = {"index": 0.09, "middle": 0.092, "ring": 0.088, "pinky": 0.08}
SEGMENTS = {"index": (0.042, 0.025, 0.02), "middle": (0.046, 0.028, 0.021),
            "ring": (0.042, 0.026, 0.02), "pinky": (0.033, 0.019, 0.018)}
FIRST = {"index": 5, "middle": 9, "ring": 13, "pinky": 17}

EXTENDED = (0, 0, 0)
CURLED = (85, 95, 45)


def _chain(start, bends_deg, lengths):
    """Points of a finger: straight along the wrist -> knuckle line, each joint bending towards -z."""
    start = np.asarray(start, dtype=np.float64)
    u = start / np.linalg.norm(start)            # the wrist is at the origin
    pts, p, angle = [], start, 0.0
    for bend, length in zip(bends_deg, lengths):
        angle += np.radians(bend)
        p = p + length * (np.cos(angle) * u + np.sin(angle) * np.array([0.0, 0.0, -1.0]))
        pts.append(p)
    return pts


def hand(index=EXTENDED, middle=EXTENDED, ring=EXTENDED, pinky=EXTENDED, thumb="spread") -> np.ndarray:
    """thumb: "spread" (open hand), "tucked" (across the palm), "pinch" (tip on the index tip)."""
    pts = np.zeros((21, 3))
    for name, bends in (("index", index), ("middle", middle), ("ring", ring), ("pinky", pinky)):
        knuckle = np.array([KNUCKLES_X[name], KNUCKLES_Y[name], 0.0])
        i = FIRST[name]
        pts[i] = knuckle
        pts[i + 1:i + 4] = _chain(knuckle, bends, SEGMENTS[name])
    base = np.array([0.025, 0.02, 0.0])
    pts[1] = base
    if thumb == "spread":
        direction = np.array([0.8, 0.6, 0.0]) / 1.0
        for k, d in zip((2, 3, 4), (0.035, 0.065, 0.09)):
            pts[k] = base + d * direction / np.linalg.norm(direction)
    elif thumb == "tucked":
        for k, (x, y) in zip((2, 3, 4), ((0.03, 0.045), (0.015, 0.06), (0.0, 0.065))):
            pts[k] = np.array([x, y, -0.02])
    elif thumb == "pinch":
        tip = pts[8] + np.array([-0.004, 0.0, 0.006])
        pts[4] = tip
        pts[2] = base + (tip - base) * 0.4 + np.array([0.01, 0.0, 0.0])
        pts[3] = base + (tip - base) * 0.75 + np.array([0.008, 0.0, 0.0])
    else:
        raise ValueError(thumb)
    return pts


def rotated(points: np.ndarray, yaw_deg=0.0, pitch_deg=0.0, roll_deg=0.0) -> np.ndarray:
    a, b, c = np.radians([yaw_deg, pitch_deg, roll_deg])
    rz = np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]])
    rx = np.array([[1, 0, 0], [0, np.cos(b), -np.sin(b)], [0, np.sin(b), np.cos(b)]])
    ry = np.array([[np.cos(c), 0, np.sin(c)], [0, 1, 0], [-np.sin(c), 0, np.cos(c)]])
    return points @ (rz @ rx @ ry).T


def to_image(points: np.ndarray, scale_px_per_m: float = 1500.0, centre=(900.0, 500.0)) -> np.ndarray:
    """Orthographic camera looking along -z at the hand: (21, 2) camera px (y down)."""
    xy = points[:, :2] * scale_px_per_m
    return np.column_stack([centre[0] + xy[:, 0], centre[1] - xy[:, 1]])
