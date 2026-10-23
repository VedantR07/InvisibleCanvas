"""Light on the hand (D50, brain.md §9.10). Pure: no I/O.

The projector paints whatever lies under the user's hand onto the hand: ink, text, the cursor. The camera then
sees a hand with dark stripes (hand finding fell from 100 % over plain white to 62 % over heavy content in a
dark room, §13.2) and the user sees a distorted copy of the drawing on the hand. HandLight gives the polygon,
in projector px, that the renderer paints plain white: the convex outline of the hand's 21 landmarks, stretched
ahead along the hand's motion by the display loop's latency (the projected image reaches the wall ~0.26 s after
the frame it was computed from, so without the look-ahead a moving fingertip runs out of its light), grown by a
margin, and held for a while at the last position after the hand is lost, so it is found again on an evenly lit
hand.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class LightParams:
    margin_px: float = 25.0          # around the landmark outline (a finger is ~15-25 projector px wide)
    lookahead_s: float = 0.26        # display -> camera loop on the Kreo setup: median 262 ms (§13.2, 2026-10-19)
    max_shift_px: float = 150.0      # the look-ahead never stretches the light further than this
    velocity_window_s: float = 0.1   # hand speed from the landmark centroid over this window
    hold_s: float = 1.0              # after a loss the light stays this long at the last position
    lost_margin_px: float = 45.0     # ... with this margin (the hand may have moved on)
    circle_points: int = 16          # directions used to grow the outline by the margin


def grown_hull(points: np.ndarray, margin: float, n: int = 16) -> np.ndarray:
    """Convex hull of `points` grown by `margin` (Minkowski sum with a circle sampled in n directions), as an
    int32 (K, 2) polygon for cv2.fillConvexPoly."""
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    hull = cv2.convexHull(pts.astype(np.float32)).reshape(-1, 2).astype(np.float64)
    a = np.linspace(0.0, 2 * np.pi, n, endpoint=False)
    ring = np.column_stack([np.cos(a), np.sin(a)]) * margin
    grown = (hull[:, None, :] + ring[None, :, :]).reshape(-1, 2)
    return np.round(cv2.convexHull(grown.astype(np.float32)).reshape(-1, 2)).astype(np.int32)


class HandLight:
    def __init__(self, params: LightParams = LightParams()):
        self.params = params
        self._track: deque = deque()                 # (t, centroid) of recent frames with a hand
        self._last_seen: float | None = None
        self._last_points: np.ndarray | None = None  # stretched landmark points of the last frame with a hand
        self.polygon: np.ndarray | None = None

    def update(self, t: float, points) -> np.ndarray | None:
        """`points`: the hand's landmarks in projector px (None: no hand this frame). The polygon to light, or None."""
        p = self.params
        pts = None if points is None else np.asarray(points, dtype=np.float64).reshape(-1, 2)
        if pts is not None:
            pts = pts[np.all(np.isfinite(pts), axis=1)]
        if pts is None or len(pts) < 3:
            self._track.clear()
            if self._last_seen is not None and t - self._last_seen <= p.hold_s:
                self.polygon = grown_hull(self._last_points, p.lost_margin_px, p.circle_points)
            else:
                self._last_seen, self._last_points, self.polygon = None, None, None
            return self.polygon
        centre = pts.mean(axis=0)
        self._track.append((t, centre))
        while len(self._track) > 2 and t - self._track[0][0] > p.velocity_window_s:
            self._track.popleft()
        shift = np.zeros(2)
        t0, c0 = self._track[0]
        if t - t0 > 1e-3:
            shift = (centre - c0) / (t - t0) * p.lookahead_s
            n = float(np.linalg.norm(shift))
            if n > p.max_shift_px:
                shift *= p.max_shift_px / n
        stretched = np.vstack([pts, pts + shift])
        self._last_seen, self._last_points = t, stretched
        self.polygon = grown_hull(stretched, p.margin_px, p.circle_points)
        return self.polygon


def paint(image: np.ndarray, polygon: np.ndarray | None, colour=(255, 255, 255)) -> None:
    """Fill the light polygon on a BGR projector image in place."""
    if polygon is not None and len(polygon) >= 3:
        cv2.fillConvexPoly(image, polygon, colour, cv2.LINE_AA)
