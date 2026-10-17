"""Fingertip cursor logic (Phase 1D, brain.md D33). Pure: no camera, no GUI, no MediaPipe.

Input per camera frame: the fingertip already mapped to projector px (or None when no hand was
found). Output: what the projector should show.

States:
- tracking  the fingertip maps onto the canvas; the cursor is drawn there.
- holding   no hand this frame, but one was seen less than `hold_s` ago: the cursor stays where
            it was (short dropouts do not make it blink). It never moves while holding.
- lost      no hand for longer than `hold_s`: the cursor is hidden.
- outside   the fingertip maps off the canvas (or to infinity): the cursor is hidden.
After lost/outside the next detection shows the cursor at the new position at once; it never
glides from a stale position, and an optional filter is reset.

D37: every update says why it has its state (`reason`) and how long ago the fingertip was last seen
(`since_seen_s`); the tracker counts state transitions and the hidden time before each reacquisition.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field

import numpy as np

TRACKING, HOLDING, LOST, OUTSIDE = "tracking", "holding", "lost", "outside"


class OneEuroFilter:
    """One Euro filter (Casiez, Roussel, Vogel, CHI 2012) for a 2-D point: little smoothing when
    the point moves fast (low lag), more when it is still (low jitter).

    beta 0.05 (D37; 0.01 before): replaying the recorded raw fingertip paths of 2026-10-11 (6 runs, 28
    tracking segments) the median lag behind the raw point fell from 5.6 to 2.1 px at 30-300 px/s and from
    8.7 to 2.8 px above 300 px/s, while the jitter of a still fingertip went from 0.48 to 0.55 px rms
    (raw 0.96). Projector px; min_cutoff and d_cutoff unchanged."""

    def __init__(self, min_cutoff_hz: float = 1.0, beta: float = 0.05, d_cutoff_hz: float = 1.0):
        self.min_cutoff, self.beta, self.d_cutoff = min_cutoff_hz, beta, d_cutoff_hz
        self.reset()

    def reset(self) -> None:
        self._x = self._dx = self._t = None

    @staticmethod
    def _alpha(cutoff: float, dt: float) -> float:
        tau = 1.0 / (2 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def __call__(self, t: float, point) -> np.ndarray:
        x = np.asarray(point, dtype=np.float64)
        if self._x is None or t <= self._t:
            self._x, self._dx, self._t = x, np.zeros(2), t
            return x.copy()
        dt = t - self._t
        dx = (x - self._x) / dt
        a_d = self._alpha(self.d_cutoff, dt)
        self._dx = a_d * dx + (1 - a_d) * self._dx
        cutoff = self.min_cutoff + self.beta * float(np.linalg.norm(self._dx))
        a = self._alpha(cutoff, dt)
        self._x = a * x + (1 - a) * self._x
        self._t = t
        return self._x.copy()


@dataclass(frozen=True)
class CursorUpdate:
    status: str
    position: tuple[float, float] | None   # projector px to draw; None = hidden
    raw: tuple[float, float] | None        # this frame's mapped fingertip, if a hand was found
    reason: str = ""                       # why this state (D37)
    since_seen_s: float | None = field(default=None, compare=False)   # since the fingertip was last on the canvas


class CursorTracker:
    def __init__(self, canvas_size: tuple[int, int], *, hold_s: float = 0.15, smoothing: OneEuroFilter | None = None):
        self.canvas_size = (int(canvas_size[0]), int(canvas_size[1]))
        self.hold_s = float(hold_s)
        self.smoothing = smoothing
        self.status = LOST
        self.position: tuple[float, float] | None = None
        self.last_seen: float | None = None
        self.losses = 0                    # tracking -> lost transitions
        self.lost_since: float | None = None
        self.transitions: Counter = Counter()      # "from->to" -> count (D37)
        self.reacquired_after_s: list[float] = []  # hidden time (lost/outside) before each reacquisition

    def inside(self, point) -> bool:
        x, y = point
        w, h = self.canvas_size
        return bool(np.isfinite(x) and np.isfinite(y) and -0.5 <= x < w - 0.5 and -0.5 <= y < h - 0.5)

    def update(self, t: float, point) -> CursorUpdate:
        before = self.status
        u = self._update(t, point)
        if u.status != before:
            self.transitions[f"{before}->{u.status}"] += 1
        since = None if self.last_seen is None else t - self.last_seen
        return CursorUpdate(u.status, u.position, u.raw, u.reason, since)

    def _update(self, t: float, point) -> CursorUpdate:
        if point is not None:
            raw = (float(point[0]), float(point[1]))
            if not self.inside(raw):
                reason = "fingertip off the canvas" if np.all(np.isfinite(raw)) else "fingertip not finite"
                self._hide(OUTSIDE, t)
                return CursorUpdate(OUTSIDE, None, raw, reason)
            reason = {TRACKING: "detected", HOLDING: "detected after a dropout"}.get(self.status, "reacquired")
            if self.status in (LOST, OUTSIDE):
                if self.lost_since is not None:
                    self.reacquired_after_s.append(t - self.lost_since)
                if self.smoothing is not None:
                    self.smoothing.reset()
            p = self.smoothing(t, raw) if self.smoothing is not None else np.asarray(raw)
            self.position = (float(p[0]), float(p[1]))
            self.status, self.last_seen, self.lost_since = TRACKING, t, None
            return CursorUpdate(TRACKING, self.position, raw, reason)
        if self.status in (TRACKING, HOLDING) and self.last_seen is not None and t - self.last_seen <= self.hold_s:
            self.status = HOLDING
            return CursorUpdate(HOLDING, self.position, None, "no fingertip: holding the last position")
        reason = "no fingertip"
        if self.status in (TRACKING, HOLDING):
            self.losses += 1
            reason = f"no fingertip for more than {self.hold_s * 1000:.0f} ms"
        self._hide(LOST, t)
        return CursorUpdate(LOST, None, None, reason)

    def _hide(self, status: str, t: float) -> None:
        if self.status not in (LOST, OUTSIDE):
            self.lost_since = t
        self.status, self.position = status, None
        if self.smoothing is not None:
            self.smoothing.reset()


@dataclass(frozen=True)
class Dwell:
    mean: tuple[float, float]
    sd: float          # radial standard deviation over the window, px
    spread: float      # max distance from the mean, px
    samples: int


def dwell(samples: list[tuple[float, tuple[float, float]]], seconds: float, radius: float) -> Dwell | None:
    """If the most recent `seconds` of (t, point) samples all lie within `radius` of their mean
    and cover the whole span, return their statistics (the fingertip is being held still)."""
    if not samples:
        return None
    t_end = samples[-1][0]
    window = [p for t, p in samples if t >= t_end - seconds]
    if len(window) < 3 or samples[0][0] > t_end - seconds:
        return None
    pts = np.array(window, dtype=np.float64)
    mean = pts.mean(axis=0)
    d = np.linalg.norm(pts - mean, axis=1)
    if d.max() > radius:
        return None
    return Dwell((float(mean[0]), float(mean[1])), float(np.sqrt(np.mean(d ** 2))), float(d.max()), len(pts))
