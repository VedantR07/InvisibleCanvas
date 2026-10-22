"""Interaction engine (Phase 2, brain.md §6, §9.10, D44, D46). Pure: no I/O.

Per camera frame: the classified hand shape (or no hand) and the hand's points in projector px -> the mode
and this frame's canvas events.

Modes: IDLE (no hand), HOVER (cursor only), DRAW, ERASE, SELECT. Which hand shape leads to which mode is the
`mode_of` mapping: the default (D46) is index finger only -> DRAW (the current tool), everything else -> HOVER;
GESTURE_MODES is the original D44 mapping (open hand -> ERASE, pinch -> SELECT).
- An active mode (DRAW, ERASE, SELECT) starts only after its shape was seen in `enter_frames` consecutive
  frames; a mode ends only after another shape was seen in `exit_frames` consecutive frames. A single misread
  frame therefore never starts or ends a stroke.
- The frames that confirm a new mode are buffered: once the mode starts, they are replayed, so a stroke
  begins where the shape began, not `enter_frames` later. A shape that is not confirmed is dropped.
- While a change away from DRAW is pending, no points are added; if the change is confirmed those frames are
  never drawn (no hook at the stroke's end), and if the shape comes back, drawing simply continues.
- No hand: the mode is kept for `hold_s` (a dropout, no events), then it ends cleanly.
- Keep drawing (D47): once in DRAW, a frame whose hand is still within the looser keep-drawing band
  (`HandInput.keeps_draw`, from vision.gestures) continues the stroke whatever its strict shape. Starting a
  stroke still needs `enter_frames` strict POINT frames.
- Pen-lift delay (D49): DRAW ends only once no frame has continued the stroke for `lift_s` (other shapes and
  no hand alike), and after at least `exit_frames` frames of the new shape. A shorter interruption (a finger
  turned towards the wall, a misread, a lost hand) is bridged: drawing goes on from the next continuing frame
  with a straight join, and the interrupted frames are never drawn.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from ..vision.gestures import OPEN, OTHER, PINCH, POINT

IDLE, HOVER, DRAW, ERASE, SELECT = "idle", "hover", "draw", "erase", "select"
ACTIVE = (DRAW, ERASE, SELECT)
GESTURE_MODES = {POINT: DRAW, OPEN: ERASE, PINCH: SELECT, OTHER: HOVER}   # D44 (pinch not observable, D46)
TOOL_MODES = {POINT: DRAW, OPEN: HOVER, PINCH: HOVER, OTHER: HOVER}       # D46: one gesture + toolbar tools

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
    keeps_draw: bool = False         # within the keep-drawing band (D47): continues a stroke, never starts one


@dataclass(frozen=True)
class Event:
    kind: str
    t: float
    point: tuple[float, float] | None = None
    radius: float = 0.0


@dataclass(frozen=True)
class EngineParams:
    # D46: G1 run 1 had non-pointing shapes misread as POINT for up to 6 consecutive frames (pinch-like); open
    # hand and fist at most 3. 7 frames (~130 ms at 54 fps) blocks those; the stroke start is buffered, not lost.
    enter_frames: int = 7
    exit_frames: int = 3
    hold_s: float = 0.15             # the cursor's dropout hold (D33)
    # D49: G3 runs 1-2 broke strokes on 0.2-1.1 s interruptions while the user kept pointing; deliberate lifts took
    # >= 1.1 s. On their traces a 0.6-s delay left no break shorter than 1 s (run 2: 20 -> 16 strokes; G2: 0).
    lift_s: float = 0.6


@dataclass(frozen=True)
class Step:
    mode: str
    cursor: tuple[float, float] | None
    events: tuple[Event, ...]
    shape: str | None                # this frame's shape (None: no hand)
    pending: str | None = None       # a different mode being confirmed


class InteractionEngine:
    def __init__(self, params: EngineParams = EngineParams(), mode_of: dict | None = None):
        if params.enter_frames < 1 or params.exit_frames < 1:
            raise ValueError("enter_frames and exit_frames must be at least 1")
        if params.lift_s < 0:
            raise ValueError("lift_s must not be negative")
        self.params = params
        self.mode_of = dict(TOOL_MODES if mode_of is None else mode_of)
        self.mode = IDLE
        self._candidate: str | None = None
        self._buffer: list[tuple[float, HandInput]] = []    # frames of the candidate mode, in order
        self._last_seen: float | None = None
        self._last: HandInput | None = None
        self._pinch_at: tuple[float, float] | None = None     # last pinch point while in SELECT
        self._kept_at: float | None = None                    # last frame that continued DRAW (D49)
        self.mode_frames: Counter = Counter()                 # frames spent in each mode
        self.entries: Counter = Counter()                     # times each mode was entered

    # -- per frame -------------------------------------------------------------------------------------

    def update(self, t: float, hand: HandInput | None) -> Step:
        if hand is None:
            return self._no_hand(t)
        self._last_seen, self._last = t, hand
        if self.mode == IDLE:                       # a hand appears: the cursor shows at once
            self._switch(HOVER)
        target = self.mode_of[hand.shape]
        if self.mode == DRAW and hand.keeps_draw:
            target = DRAW
        if target != self._candidate:
            self._candidate, self._buffer = target, []
        self._buffer.append((t, hand))
        events: list[Event] = []
        if target == self.mode:
            self._buffer = self._buffer[-1:]
            events += self._continue(t, hand)
            if self.mode == DRAW:
                self._kept_at = t
        else:
            needed = self.params.exit_frames
            if target in ACTIVE:
                needed = max(self.params.enter_frames, self.params.exit_frames if self.mode in ACTIVE else 0)
            lifting = self.mode == DRAW and t - self._kept_at < self.params.lift_s
            if len(self._buffer) >= needed and not lifting:
                events += self._leave(t)
                self._switch(target)
                buffered, self._buffer = self._buffer, self._buffer[-1:]
                events += self._enter(buffered)
                if self.mode == DRAW:
                    self._kept_at = t
        self.mode_frames[self.mode] += 1
        pending = self._candidate if self._candidate != self.mode else None
        return Step(self.mode, self._cursor(hand), tuple(events), hand.shape, pending)

    def _no_hand(self, t: float) -> Step:
        holding = self.mode != IDLE and self._last_seen is not None and t - self._last_seen <= self.params.hold_s
        if self.mode == DRAW:                       # D49: the pen-lift delay, at least the dropout hold
            holding = holding or t - self._kept_at < self.params.lift_s
        if holding:
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
