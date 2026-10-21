"""Interaction engine (Phase 2, brain.md §6, §9.10, D44). Pure: no I/O.

Per camera frame: the classified hand shape (or no hand) and the hand's points in projector px -> the mode
and this frame's canvas events.

Modes: IDLE (no hand), HOVER (cursor only), DRAW, ERASE, SELECT.
- An active mode (DRAW, ERASE, SELECT) starts only after its shape was seen in `enter_frames` consecutive
  frames; a mode ends only after another shape was seen in `exit_frames` consecutive frames. A single misread
  frame therefore never starts or ends a stroke.
- The frames that confirm a new mode are buffered: once the mode starts, they are replayed, so a stroke
  begins where the shape began, not `enter_frames` later. A shape that is not confirmed is dropped.
- While a change away from DRAW is pending, no points are added; if the change is confirmed those frames are
  never drawn (no hook at the stroke's end), and if the shape comes back, drawing simply continues.
- No hand: the mode is kept for `hold_s` (a dropout, no events), then it ends cleanly.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from ..vision.gestures import OPEN, OTHER, PINCH, POINT

IDLE, HOVER, DRAW, ERASE, SELECT = "idle", "hover", "draw", "erase", "select"
ACTIVE = (DRAW, ERASE, SELECT)
MODE_OF = {POINT: DRAW, OPEN: ERASE, PINCH: SELECT, OTHER: HOVER}

STROKE_START, STROKE_POINT, STROKE_END = "stroke_start", "stroke_point", "stroke_end"
ERASE_AT, ERASE_END = "erase", "erase_end"
PINCH_DOWN, PINCH_MOVE, PINCH_UP = "pinch_down", "pinch_move", "pinch_up"


@dataclass(frozen=True)
class HandInput:
    """One frame's hand, in projector px."""
    shape: str                       # vision.gestures shape
    pointer: tuple[float, float]     # index fingertip
    pinch: tuple[float, float]       # between the thumb and index tips
    palm: tuple[float, float]        # palm centre
    eraser_radius: float = 40.0


@dataclass(frozen=True)
class Event:
    kind: str
    t: float
    point: tuple[float, float] | None = None
    radius: float = 0.0


@dataclass(frozen=True)
class EngineParams:
    enter_frames: int = 4            # ~70 ms at 54 fps
    exit_frames: int = 3
    hold_s: float = 0.15             # the cursor's dropout hold (D33)


@dataclass(frozen=True)
class Step:
    mode: str
    cursor: tuple[float, float] | None
    events: tuple[Event, ...]
    shape: str | None                # this frame's shape (None: no hand)
    pending: str | None = None       # a different mode being confirmed


class InteractionEngine:
    def __init__(self, params: EngineParams = EngineParams()):
        if params.enter_frames < 1 or params.exit_frames < 1:
            raise ValueError("enter_frames and exit_frames must be at least 1")
        self.params = params
        self.mode = IDLE
        self._candidate: str | None = None
        self._buffer: list[tuple[float, HandInput]] = []    # frames of the candidate mode, in order
        self._last_seen: float | None = None
        self._last: HandInput | None = None
        self._pinch_at: tuple[float, float] | None = None     # last pinch point while in SELECT
        self.mode_frames: Counter = Counter()                 # frames spent in each mode
        self.entries: Counter = Counter()                     # times each mode was entered

    # -- per frame -------------------------------------------------------------------------------------

    def update(self, t: float, hand: HandInput | None) -> Step:
        if hand is None:
            return self._no_hand(t)
        self._last_seen, self._last = t, hand
        if self.mode == IDLE:                       # a hand appears: the cursor shows at once
            self._switch(HOVER)
        target = MODE_OF[hand.shape]
        if target != self._candidate:
            self._candidate, self._buffer = target, []
        self._buffer.append((t, hand))
        events: list[Event] = []
        if target == self.mode:
            self._buffer = self._buffer[-1:]
            events += self._continue(t, hand)
        else:
            needed = self.params.exit_frames
            if target in ACTIVE:
                needed = max(self.params.enter_frames, self.params.exit_frames if self.mode in ACTIVE else 0)
            if len(self._buffer) >= needed:
                events += self._leave(t)
                self._switch(target)
                buffered, self._buffer = self._buffer, self._buffer[-1:]
                events += self._enter(buffered)
        self.mode_frames[self.mode] += 1
        pending = self._candidate if self._candidate != self.mode else None
        return Step(self.mode, self._cursor(hand), tuple(events), hand.shape, pending)

    def _no_hand(self, t: float) -> Step:
        if self.mode != IDLE and self._last_seen is not None and t - self._last_seen <= self.params.hold_s:
            self.mode_frames[self.mode] += 1
            return Step(self.mode, self._cursor(self._last), (), None)
        events = self._leave(t) if self.mode != IDLE else []
        if self.mode != IDLE:
            self._switch(IDLE)
        self._candidate, self._buffer = None, []
        self.mode_frames[IDLE] += 1
        return Step(IDLE, None, tuple(events), None)

    # -- mode actions -----------------------------------------------------------------------------------

    def _switch(self, mode: str) -> None:
        self.mode = mode
        self.entries[mode] += 1

    def _enter(self, frames: list[tuple[float, HandInput]]) -> list[Event]:
        t0, first = frames[0]
        if self.mode == DRAW:
            return [Event(STROKE_START, t0, first.pointer)] + [Event(STROKE_POINT, t, h.pointer) for t, h in frames[1:]]
        if self.mode == ERASE:
            return [Event(ERASE_AT, t, h.palm, h.eraser_radius) for t, h in frames]
        if self.mode == SELECT:
            self._pinch_at = frames[-1][1].pinch
            return [Event(PINCH_DOWN, t0, first.pinch)] + [Event(PINCH_MOVE, t, h.pinch) for t, h in frames[1:]]
        return []

    def _continue(self, t: float, hand: HandInput) -> list[Event]:
        if self.mode == DRAW:
            return [Event(STROKE_POINT, t, hand.pointer)]
        if self.mode == ERASE:
            return [Event(ERASE_AT, t, hand.palm, hand.eraser_radius)]
        if self.mode == SELECT:
            self._pinch_at = hand.pinch
            return [Event(PINCH_MOVE, t, hand.pinch)]
        return []

    def _leave(self, t: float) -> list[Event]:
        if self.mode == DRAW:
            return [Event(STROKE_END, t)]
        if self.mode == ERASE:
            return [Event(ERASE_END, t)]
        if self.mode == SELECT:
            return [Event(PINCH_UP, t, self._pinch_at)]   # where the pinch was, not the opening fingers
        return []

    def _cursor(self, hand: HandInput | None) -> tuple[float, float] | None:
        if hand is None or self.mode == IDLE:
            return None
        if self.mode == ERASE:
            return hand.palm
        if self.mode == SELECT:
            return hand.pinch
        return hand.pointer
