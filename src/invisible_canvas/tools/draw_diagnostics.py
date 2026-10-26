"""Per-frame diagnostics for `draw` (brain.md §9.12, mission Stage 3 item 1): for every camera frame, why the
fingertip did or did not become ink, where it was, and how long each stage of the frame took. Pure: no I/O,
and nothing here feeds back into tracking, mapping, the engine, the controller or rendering.

The outcome of each engine event is recorded by `DrawingController` inside its existing branches
(`controller.outcomes`); the hand status by `HandPoints` (`status`, `raw`); the tracker's own outcome is
`HandTracker.action`. This module only classifies and counts them.

Geometry (`where`), from the existing definitions in the code:
- the canvas covers [-0.5, w - 0.5) x [-0.5, h - 0.5) (pixel centres at integers, `CoordinateMapper.inside_canvas`);
- the controller's toolbar test is `y >= toolbar.top` (`Toolbar.in_band`, top = 648 on 1280 x 720): no x limit
  and no lower limit, so a point below the canvas also fails it. That decision is recorded as it is
  (`dropped_band`, `refused_band`); `where` only says where the point really was.
Precedence: off the canvas first, top and bottom before left and right (`below`, `above`, `left`, `right`), then
on the canvas `toolbar` (y >= top) or `canvas`.

Memory is bounded: counters over fixed key sets and fixed-bin histograms for every timing, whatever the length
of the session.
"""

from __future__ import annotations

from collections import Counter

DRAW = "draw"                       # interaction.engine.DRAW
STROKE_START, STROKE_POINT, STROKE_END = "stroke_start", "stroke_point", "stroke_end"
# Height bands of the 2026-10-26 baseline analysis (projector y; 1280 x 720 canvas, toolbar from 648)
BANDS = (("top", 216.0), ("middle", 432.0), ("lower", 560.0), ("bottom", 648.0))
# Per-frame stages in loop order (`draw`): queue = capture -> pick-up, ..., show = projector.show + pollKey (the
# end of `pipeline_ms`); then, outside `pipeline_ms`: diag (this module + the extra trace fields), trace (writing
# the trace line), post (everything after `show` until the next frame: records, diag, trace, saved frames,
# operator view, keys).
STAGES = ("queue", "inference", "hand", "engine", "controller", "ai", "render", "show", "diag", "trace", "post")
TARGET_DIAG_MS = 0.1


def where(point, size: tuple[int, int], toolbar_top: float) -> str | None:
    """Where a projector point lies: below / above / left / right of the canvas, or on it: toolbar / canvas."""
    if point is None:
        return None
    x, y = float(point[0]), float(point[1])
    w, h = size
    if y >= h - 0.5:
        return "below"
    if y < -0.5:
        return "above"
    if x < -0.5:
        return "left"
    if x >= w - 0.5:
        return "right"
    return "toolbar" if y >= toolbar_top else "canvas"


def band(point, size: tuple[int, int], toolbar_top: float) -> str | None:
    """The baseline's height band of a point: top / middle / lower / bottom, else its `where` off the bands."""
    w_ = where(point, size, toolbar_top)
    if w_ != "canvas":
        return w_
    y = float(point[1])
    return next(name for name, limit in BANDS if y < limit)


class Histogram:
    """Fixed bins (`step` wide up to `limit`, then one overflow bin) plus the exact maximum: bounded memory."""

    def __init__(self, step: float = 0.05, limit: float = 250.0):
        self.step, self.limit = step, limit
        self.bins = [0] * (int(round(limit / step)) + 1)
        self.count, self.max = 0, None

    def add(self, value: float) -> None:
        value = max(float(value), 0.0)
        self.bins[min(int(value / self.step), len(self.bins) - 1)] += 1
        self.count += 1
        self.max = value if self.max is None else max(self.max, value)

    def percentile(self, q: float) -> float | None:
        """The upper edge of the bin holding the q-th percentile (within one bin width; `max` above `limit`)."""
        if not self.count:
            return None
        rank, seen = q / 100.0 * self.count, 0
        for k, n in enumerate(self.bins):
            seen += n
            if seen >= rank and n:
                return self.max if k == len(self.bins) - 1 else min((k + 1) * self.step, self.max)
        return self.max

    def summary(self) -> dict | None:
        if not self.count:
            return None
        return {"median": self.percentile(50), "p95": self.percentile(95), "max": self.max, "count": self.count}


def frame_state(status: str, mode: str, events, prev_candidate, candidate) -> str:
    """Why this frame did or did not draw, from the engine's own state (its candidate before and after the
    update), not from a later frame.

    start / lifted: a stroke began / ended in this frame. In DRAW: drawing (points went to the controller),
    held (no usable hand: the engine bridges), gap (a hand outside the keep band: no point, bridged or lifted
    later). Otherwise: start-unconfirmed (the engine discarded its buffered POINT frames in this frame),
    pending-start (POINT frames still being confirmed, also while a short dropout is held), the hand status
    (no-hand / tip-outside-view / mapping-failed), or the mode (hover, ...)."""
    kinds = [e if isinstance(e, str) else e.kind for e in events]
    if STROKE_START in kinds:
        return "start"
    if STROKE_END in kinds and mode != DRAW:
        return "lifted"
    if mode == DRAW:
        if status != "ok":
            return "held"
        return "drawing" if STROKE_POINT in kinds else "gap"
    if prev_candidate == DRAW and candidate != DRAW:
        return "start-unconfirmed"
    if candidate == DRAW:
        return "pending-start"
    if status != "ok":
        return status
    return mode


class DrawDiagnostics:
    """Counts per session; `frame()` returns the per-frame fields for the trace."""

    def __init__(self, size: tuple[int, int], toolbar_top: float):
        self.size, self.top = (int(size[0]), int(size[1])), float(toolbar_top)
        self.frames = 0
        self.actions, self.status, self.states, self.ink = Counter(), Counter(), Counter(), Counter()
        self.band_frames, self.band_losses = Counter(), Counter()
        self.refind = {}                                 # band -> Histogram of seconds to see the hand again
        self.stages = {s: Histogram() for s in STAGES}
        self.stages["diag"] = Histogram(0.005, 50.0)     # fine bins: the < 0.1 ms target must be decidable
        self.loop = Histogram()
        self.attempts_after_refusal = set()              # attempt numbers that had points after a refused start
        self._prev_candidate = None
        self._last_hand_band, self._lost_at = None, None

    def frame(self, *, t: float, action: str, status: str, cursor, step, prev_candidate, candidate,
              outcomes, stage_ms: dict, loop_ms: float | None = None) -> dict:
        self.frames += 1
        self.actions[action] += 1
        self.status[status] += 1
        state = frame_state(status, step.mode, step.events, prev_candidate, candidate)
        self.states[state] += 1
        # hand frames and losses per band, as the baseline analysis counted them (shape present, cursor shown)
        if status == "ok" and cursor is not None:
            b = band(cursor, self.size, self.top)
            self.band_frames[b] += 1
            if self._lost_at is not None and self._last_hand_band is not None:
                self.refind.setdefault(self._last_hand_band, Histogram(0.01, 30.0)).add(t - self._lost_at)
            self._lost_at, self._last_hand_band = None, b
        elif self._last_hand_band is not None and self._lost_at is None:
            self._lost_at = t
            self.band_losses[self._last_hand_band] += 1
        ink = Counter()
        for outcome, point, attempt in outcomes:
            key = outcome if point is None else f"{outcome}:{where(point, self.size, self.top)}"
            ink[key] += 1
            if outcome == "after_refused_start":
                self.attempts_after_refusal.add(attempt)
        self.ink.update(ink)
        for name, value in stage_ms.items():
            if value is not None:
                self.stages[name].add(value)
        if loop_ms is not None:
            self.loop.add(loop_ms)
        return {"state": state, "where": where(cursor, self.size, self.top), "ink": dict(ink) or None}

    def report(self, strokes_committed: int, attempts: int) -> dict:
        bands = {}
        for name in [b for b, _ in BANDS] + ["toolbar", "below", "above", "left", "right"]:
            frames, losses = self.band_frames[name], self.band_losses[name]
            if frames or losses:
                refind = self.refind.get(name)
                bands[name] = {"hand_frames": frames, "losses": losses,
                               "losses_per_1000": round(1000 * losses / frames, 1) if frames else None,
                               "refind_s": refind.summary() if refind else None}
        refused = {k.split(":")[0]: 0 for k in self.ink if k.startswith("refused_")}
        for k, n in self.ink.items():
            if k.startswith("refused_"):
                refused[k.split(":")[0]] += n
        diag = self.stages["diag"].summary()
        return {
            "frames": self.frames,
            "tracker_actions": dict(self.actions),
            "hand_status": dict(self.status),
            "states": dict(self.states),
            "ink": dict(sorted(self.ink.items())),
            "bands": bands,
            "strokes": {"attempts": attempts, "committed": strokes_committed, "refused": refused,
                        "attempts_with_points_after_refusal": len(self.attempts_after_refusal),
                        "points_after_refused_start": sum(n for k, n in self.ink.items()
                                                          if k.startswith("after_refused_start"))},
            "stage_ms": {s: h.summary() for s, h in self.stages.items()},
            "loop_ms": self.loop.summary(),
            "overhead": {"diag_ms": diag, "target_ms": TARGET_DIAG_MS,
                         "median_below_target": None if diag is None else diag["median"] < TARGET_DIAG_MS},
        }
