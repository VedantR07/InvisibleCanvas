"""Light on the hand (D50, brain.md §9.10; D70 §9.16). Pure: no I/O.

The projector paints whatever lies under the user's hand onto the hand: ink, text, the cursor. The camera then
sees a hand with dark stripes (hand finding fell from 100 % over plain white to 62 % over heavy content in a
dark room, §13.2) and the user sees a distorted copy of the drawing on the hand. HandLight gives the shape, in
projector px, that the renderer paints plain white over the hand.

D50 lit the convex outline of the 21 landmarks + 25 px, stretched over the whole way to where the hand would be
when the frame reached the wall (the display loop: ~0.26 s), and held it 1 s after a loss. On the wall (2026-10-29)
that was far bigger than the hand: while writing it was stretched a median 74 px (13 % of frames at the 150-px cap),
and it hid the writing next to the hand. D70 fits the hand: each finger bone is lit as a capsule of the finger's
half-width (from the hand's size) + a small margin, and the palm as its own outline grown the same; the shape is
moved to where the hand will be (the look-ahead), covering back only part of the way (`sweep_from`), with no
look-ahead for a hand that is nearly still, a lower cap, and a shorter hold after a loss. Chosen on the recorded
hands of 2026-10-22 (5,340 frames), the light of each frame against the hand where it was when that frame reached
the wall (0.26 s later): D50 covered 100 % of it (median) and hid 24,800 px2 of wall around it; these defaults
93 % and 11,500 px2 (-54 %); a 4-px margin 88 % and 9,200 px2. `margin_px` can be changed live in `draw` ([ / ]).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import cv2
import numpy as np

# The finger bones of MediaPipe's 21 hand landmarks (thumb, index, middle, ring, little finger), and the palm.
FINGER_BONES = ((1, 2), (2, 3), (3, 4), (5, 6), (6, 7), (7, 8), (9, 10), (10, 11), (11, 12),
                (13, 14), (14, 15), (15, 16), (17, 18), (18, 19), (19, 20))
PALM = (0, 1, 5, 9, 13, 17)


@dataclass(frozen=True)
class LightParams:
    margin_px: float = 8.0           # around the hand's own shape (D50: 25 around the convex outline)
    finger_ratio: float = 0.10       # a finger's half-width / the wrist-to-middle-finger-base length (fingers ~1/5)
    finger_min_px: float = 6.0
    finger_max_px: float = 30.0
    lookahead_s: float = 0.26        # display -> camera loop on the Kreo setup: median 262 ms (§13.2, 2026-10-19)
    max_shift_px: float = 100.0      # the look-ahead never moves the light further than this (D50: 150)
    min_speed_px_s: float = 60.0     # slower than this the hand counts as still: landmark jitter makes no look-ahead
    sweep_from: float = 0.75         # the light covers from this fraction of the look-ahead to all of it (D50: 0)
    velocity_window_s: float = 0.1   # hand speed from the landmark centroid over this window
    hold_s: float = 0.4              # after a loss the light stays this long at the last place (D50: 1.0)
    lost_extra_px: float = 8.0       # ... this much wider (the hand may have moved on)
    circle_points: int = 12          # directions used to grow an outline by its radius


def grown_hull(points: np.ndarray, margin: float, n: int = 16) -> np.ndarray:
    """Convex hull of `points` grown by `margin` (Minkowski sum with a circle sampled in n directions), as an
    int32 (K, 2) polygon for cv2.fillConvexPoly."""
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    hull = cv2.convexHull(pts.astype(np.float32)).reshape(-1, 2).astype(np.float64)
    a = np.linspace(0.0, 2 * np.pi, n, endpoint=False)
    ring = np.column_stack([np.cos(a), np.sin(a)]) * margin
    grown = (hull[:, None, :] + ring[None, :, :]).reshape(-1, 2)
    return np.round(cv2.convexHull(grown.astype(np.float32)).reshape(-1, 2)).astype(np.int32)


def finger_radius(points: np.ndarray, params: LightParams) -> float:
    """Half a finger's width, from the hand's size (the wrist to the middle finger's base)."""
    length = float(np.linalg.norm(points[0] - points[9]))
    return float(np.clip(params.finger_ratio * length, params.finger_min_px, params.finger_max_px))


def hand_shape(points: np.ndarray, radius: float, offsets=((0.0, 0.0),), n: int = 12) -> list[np.ndarray]:
    """The hand's own shape as convex polygons: a capsule of `radius` around each finger bone and the palm's outline
    grown by `radius`, each swept over `offsets` (the convex hull of a part at two offsets is its sweep between
    them). Any other number of points than 21: their grown convex outline (as D50)."""
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    off = np.asarray(offsets, dtype=np.float64).reshape(-1, 2)
    groups = [list(b) for b in FINGER_BONES] + [list(PALM)] if len(pts) == 21 else [list(range(len(pts)))]
    return [grown_hull((pts[g][None, :, :] + off[:, None, :]).reshape(-1, 2), radius, n) for g in groups]


def contains(shape, point) -> bool:
    """Whether `point` lies in the light (`shape`: a polygon or a list of them, or None)."""
    if shape is None:
        return False
    polys = [shape] if isinstance(shape, np.ndarray) else shape
    return any(cv2.pointPolygonTest(p.astype(np.float32), (float(point[0]), float(point[1])), False) >= 0
               for p in polys)


class HandLight:
    def __init__(self, params: LightParams = LightParams()):
        self.params = params
        self._track: deque = deque()                 # (t, centroid) of recent frames with a hand
        self._last_seen: float | None = None
        self._last: tuple[np.ndarray, float] | None = None   # (the predicted points, radius) of the last hand
        self.shape: list[np.ndarray] | None = None

    def update(self, t: float, points) -> list[np.ndarray] | None:
        """`points`: the hand's landmarks in projector px (None: no hand this frame). The light (convex polygons
        to paint), or None."""
        p = self.params
        pts = None if points is None else np.asarray(points, dtype=np.float64).reshape(-1, 2)
        if pts is not None and not np.all(np.isfinite(pts)):
            pts = None if len(pts) == 21 else pts[np.all(np.isfinite(pts), axis=1)]
        if pts is None or len(pts) < 3:
            self._track.clear()
            if self._last_seen is not None and t - self._last_seen <= p.hold_s:
                last, radius = self._last
                self.shape = hand_shape(last, radius + p.lost_extra_px, n=p.circle_points)
            else:
                self._last_seen, self._last, self.shape = None, None, None
            return self.shape
        centre = pts.mean(axis=0)
        self._track.append((t, centre))
        while len(self._track) > 2 and t - self._track[0][0] > p.velocity_window_s:
            self._track.popleft()
        shift = np.zeros(2)
        t0, c0 = self._track[0]
        if t - t0 > 1e-3:
            velocity = (centre - c0) / (t - t0)
            if np.linalg.norm(velocity) >= p.min_speed_px_s:
                shift = velocity * p.lookahead_s
                n = float(np.linalg.norm(shift))
                if n > p.max_shift_px:
                    shift *= p.max_shift_px / n
        radius = (finger_radius(pts, p) if len(pts) == 21 else 0.0) + p.margin_px
        self._last_seen, self._last = t, (pts + shift, radius)
        self.shape = hand_shape(pts, radius, (p.sweep_from * shift, shift), p.circle_points)
        return self.shape


def paint(image: np.ndarray, shape, colour=(255, 255, 255)) -> None:
    """Fill the light (a convex polygon, or a list of them; None: nothing) on a BGR projector image in place."""
    if shape is None:
        return
    for polygon in [shape] if isinstance(shape, np.ndarray) else shape:
        if polygon is not None and len(polygon) >= 3:
            cv2.fillConvexPoly(image, polygon, colour, cv2.LINE_AA)
