"""Applies interaction events to the canvas, the toolbar and the undo history (brain.md §9.10, D44, D46). Pure.

D46: one gesture + toolbar tools. A pointing stroke (STROKE_START .. STROKE_END) uses the current tool:
- pen: draws a stroke in the current colour and width (never on the toolbar band);
- eraser: removes the ink within the eraser radius along the fingertip's path (one undo step per stroke);
- move: picks up the drawing under the fingertip where the stroke starts and drags it (one undo step).
A toolbar button is pressed by holding the cursor on it (`update_pointer`, every frame): 1 s, CLEAR 2 s.
The button fires once; the cursor must leave it before it can fire again.
"""

from __future__ import annotations

from collections import Counter

from ..canvas.history import AddStroke, History, MoveStrokes, ReplaceStrokes
from ..canvas.model import Canvas, Stroke
from ..canvas.toolbar import COLOURS, WIDTHS, Toolbar

ERASER_RADIUS = {"thin": 12.0, "medium": 24.0, "thick": 42.0}     # px, by the selected width


class DrawingController:
    def __init__(self, canvas: Canvas, toolbar: Toolbar, history: History | None = None):
        self.canvas, self.toolbar = canvas, toolbar
        self.history = history or History()
        self.tool, self.colour, self.width = "pen", "black", "medium"
        self.active: Stroke | None = None              # pen stroke being drawn
        self.selected: int | None = None               # stroke being moved
        self.dwell: dict | None = None                 # {"button", "since", "fired"}
        self.log: Counter = Counter()
        self._erase_group: dict | None = None
        self._drag: dict | None = None

    @property
    def eraser_radius(self) -> float:
        return ERASER_RADIUS[self.width]

    @property
    def dwell_progress(self) -> tuple[str, float] | None:
        """(button name, 0..1) while the cursor rests on a button that has not fired yet."""
        d = self.dwell
        if d is None or d["fired"]:
            return None
        return d["button"].name, min(d["elapsed"] / self.toolbar.dwell_s(d["button"]), 1.0)

    # -- pointing strokes: the current tool --------------------------------------------------------------

    def handle(self, events) -> None:
        for e in events:
            handler = getattr(self, "_" + e.kind, None)
            if handler is None:
                raise ValueError(f"no handler for event {e.kind!r}")
            handler(e)

    def _stroke_start(self, e) -> None:
        if e.point is None or self.toolbar.in_band(e.point):
            self.log["strokes_refused_on_toolbar"] += 1
            self.active = self._drag = None
            return
        if self.tool == "pen":
            self.active = Stroke(self.canvas.new_id(), COLOURS[self.colour], WIDTHS[self.width])
            self.active.append(e.point)
        elif self.tool == "eraser":
            self._erase_group = {"removed": {}, "created": set()}
            self._erase_at(e.point)
        else:
            sid = self.canvas.hit_test(e.point)
            self.selected = sid
            self._drag = None if sid is None else {"ids": [sid], "last": e.point, "dx": 0.0, "dy": 0.0}

    def _stroke_point(self, e) -> None:
        if e.point is None or self.toolbar.in_band(e.point):
            return
        if self.tool == "pen" and self.active is not None:
            self.active.append(e.point)
        elif self.tool == "eraser" and self._erase_group is not None:
            self._erase_at(e.point)
        elif self.tool == "move" and self._drag is not None:
            d = self._drag
            dx, dy = e.point[0] - d["last"][0], e.point[1] - d["last"][1]
            self.canvas.move(d["ids"], dx, dy)
            d["dx"], d["dy"], d["last"] = d["dx"] + dx, d["dy"] + dy, e.point

    def _stroke_end(self, e) -> None:
        if self.active is not None and self.active.points:
            self.history.do(AddStroke(self.active), self.canvas)
            self.log["strokes"] += 1
        group, self._erase_group = self._erase_group, None
        if group and (group["removed"] or group["created"]):
            added = [self.canvas.strokes[i] for i in sorted(group["created"]) if i in self.canvas.strokes]
            self.history.record(ReplaceStrokes(list(group["removed"].values()), added))
            self.log["erase_strokes"] += 1
        drag, self._drag = self._drag, None
        if drag and (drag["dx"] or drag["dy"]):
            self.history.record(MoveStrokes(drag["ids"], drag["dx"], drag["dy"]))
            self.log["moves"] += 1
        self.active, self.selected = None, None

    def _erase_at(self, point) -> None:
        removed, created = self.canvas.erase(point, self.eraser_radius)
        group = self._erase_group
        for s in removed:
            if s.id in group["created"]:
                group["created"].discard(s.id)          # a piece from earlier in this stroke: not an original
            else:
                group["removed"][s.id] = s
        group["created"].update(s.id for s in created)

    # -- toolbar: press by holding the cursor on a button ------------------------------------------------

    def update_pointer(self, t: float, cursor) -> None:
        """Every frame, with the engine's cursor (None: no hand)."""
        button = self.toolbar.hit(cursor) if cursor is not None else None
        d = self.dwell
        if button is None:
            self.dwell = None
            return
        if d is None or d["button"] is not button:
            self.dwell = {"button": button, "since": t, "elapsed": 0.0, "fired": False}
            return
        d["elapsed"] = t - d["since"]
        if not d["fired"] and d["elapsed"] >= self.toolbar.dwell_s(button):
            d["fired"] = True
            self.press(button.name)

    def press(self, name: str) -> None:
        button = self.toolbar.button(name)
        self.log[f"press:{name}"] += 1
        if button.kind == "tool":
            self.tool = name
        elif button.kind == "colour":
            self.colour, self.tool = name, "pen"
        elif button.kind == "width":
            self.width = name
        elif name == "undo":
            self.undo()
        elif name == "redo":
            self.redo()
        elif name == "clear":
            self.clear()

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
