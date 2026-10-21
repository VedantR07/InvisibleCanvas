"""Applies interaction events to the canvas, the toolbar and the undo history (brain.md §9.10, D44). Pure.

- draw: a stroke from STROKE_START to STROKE_END, in the current colour and width; never on the toolbar band.
- erase: every ERASE_AT removes the ink under the palm circle; one gesture (until ERASE_END) is one undo step.
- pinch: on a toolbar button it presses the button once (clear only after the pinch is held on it for
  `CLEAR_HOLD_S`); on a stroke it picks the stroke up, PINCH_MOVE drags it, PINCH_UP drops it (one undo step).
"""

from __future__ import annotations

from collections import Counter

from ..canvas.history import AddStroke, History, MoveStrokes, ReplaceStrokes
from ..canvas.model import Canvas, Stroke
from ..canvas.toolbar import CLEAR_HOLD_S, COLOURS, WIDTHS, Toolbar
from .engine import ERASE_AT, ERASE_END, PINCH_DOWN, PINCH_MOVE, PINCH_UP, STROKE_END, STROKE_POINT, STROKE_START


class DrawingController:
    def __init__(self, canvas: Canvas, toolbar: Toolbar, history: History | None = None):
        self.canvas, self.toolbar = canvas, toolbar
        self.history = history or History()
        self.colour, self.width = "black", "medium"
        self.active: Stroke | None = None
        self.selected: int | None = None
        self.clear_progress: float | None = None      # 0..1 while the pinch is held on clear
        self.log: Counter = Counter()                 # strokes, erase_gestures, press:<button>, moves, undo, ...
        self._erase_group: dict | None = None
        self._pinch: dict | None = None

    # -- events -----------------------------------------------------------------------------------------

    def handle(self, events) -> None:
        for e in events:
            getattr(self, "_" + e.kind)(e)

    def _stroke_start(self, e) -> None:
        self.active = None
        if e.point is None or self.toolbar.in_band(e.point):
            self.log["strokes_refused_on_toolbar"] += 1
            return
        self.active = Stroke(self.canvas.new_id(), COLOURS[self.colour], WIDTHS[self.width])
        self.active.append(e.point)

    def _stroke_point(self, e) -> None:
        if self.active is not None and e.point is not None and not self.toolbar.in_band(e.point):
            self.active.append(e.point)

    def _stroke_end(self, e) -> None:
        if self.active is not None and self.active.points:
            self.history.do(AddStroke(self.active), self.canvas)
            self.log["strokes"] += 1
        self.active = None

    def _erase(self, e) -> None:
        if self._erase_group is None:
            self._erase_group = {"removed": {}, "created": set()}
        removed, created = self.canvas.erase(e.point, e.radius)
        group = self._erase_group
        for s in removed:
            if s.id in group["created"]:
                group["created"].discard(s.id)      # a piece from earlier in this gesture: not an original
            else:
                group["removed"][s.id] = s
        group["created"].update(s.id for s in created)

    def _erase_end(self, e) -> None:
        group, self._erase_group = self._erase_group, None
        if group and (group["removed"] or group["created"]):
            added = [self.canvas.strokes[i] for i in sorted(group["created"]) if i in self.canvas.strokes]
            self.history.record(ReplaceStrokes(list(group["removed"].values()), added))
            self.log["erase_gestures"] += 1

    def _pinch_down(self, e) -> None:
        button = self.toolbar.hit(e.point)
        if button is not None:
            self.log[f"press:{button.name}"] += 1
            self._pinch = {"button": button, "since": e.t, "done": button.name != "clear"}
            if button.kind == "colour":
                self.colour = button.name
            elif button.kind == "width":
                self.width = button.name
            elif button.name == "undo":
                self.undo()
            elif button.name == "redo":
                self.redo()
            else:
                self.clear_progress = 0.0
            return
        sid = None if self.toolbar.in_band(e.point) else self.canvas.hit_test(e.point)
        self.selected = sid
        self._pinch = {"button": None, "ids": [] if sid is None else [sid], "last": e.point, "dx": 0.0, "dy": 0.0}

    def _pinch_move(self, e) -> None:
        p = self._pinch
        if p is None or e.point is None:
            return
        button = p["button"]
        if button is not None:
            if button.name == "clear" and not p["done"]:
                if not button.contains(e.point):
                    p["done"], self.clear_progress = True, None       # slid off: cancelled
                else:
                    self.clear_progress = min((e.t - p["since"]) / CLEAR_HOLD_S, 1.0)
                    if e.t - p["since"] >= CLEAR_HOLD_S:
                        self.clear()
                        p["done"], self.clear_progress = True, None
            return
        if p["ids"]:
            dx, dy = e.point[0] - p["last"][0], e.point[1] - p["last"][1]
            self.canvas.move(p["ids"], dx, dy)
            p["dx"] += dx
            p["dy"] += dy
            p["last"] = e.point

    def _pinch_up(self, e) -> None:
        p, self._pinch = self._pinch, None
        self.clear_progress = None
        if p is not None and p["button"] is None and p["ids"] and (p["dx"] or p["dy"]):
            self.history.record(MoveStrokes(p["ids"], p["dx"], p["dy"]))
            self.log["moves"] += 1
        self.selected = None

    # -- actions (toolbar and keyboard) ------------------------------------------------------------------

    def undo(self) -> None:
        if self.history.undo(self.canvas) is not None:
            self.log["undo"] += 1

    def redo(self) -> None:
        if self.history.redo(self.canvas) is not None:
            self.log["redo"] += 1

    def clear(self) -> None:
        removed = self.canvas.clear()
        if removed:
            self.history.record(ReplaceStrokes(removed, [], name="clear"))
            self.log["clear"] += 1


# The engine's event kinds are the handler names.
assert {STROKE_START, STROKE_POINT, STROKE_END, ERASE_AT, ERASE_END, PINCH_DOWN, PINCH_MOVE, PINCH_UP} == {
    "stroke_start", "stroke_point", "stroke_end", "erase", "erase_end", "pinch_down", "pinch_move", "pinch_up"}
