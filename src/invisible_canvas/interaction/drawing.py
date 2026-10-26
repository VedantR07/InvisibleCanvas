"""Applies interaction events to the canvas, the toolbar and the undo history (brain.md §9.10, D44, D46). Pure.

D46: one gesture + toolbar tools. A pointing stroke (STROKE_START .. STROKE_END) uses the current tool:
- pen: draws a stroke in the current colour and width (never on the toolbar band);
- eraser: removes the ink within the eraser radius along the fingertip's path (one undo step per stroke);
- move: picks up the drawing under the fingertip where the stroke starts and drags it (one undo step).
- select (D51): the stroke draws a loop; at pen-up the strokes inside it become the selection.
A toolbar button is pressed by holding the cursor on it (`update_pointer`, every frame): 1 s, CLEAR 2 s.
The button fires once; the cursor must leave it before it can fire again.

D59: pages. The PAGES button opens the board panel (< PAGE, PAGE >, + PAGE, CLOSE; one panel at a time with the
AI panel); everything acts on the current page's canvas and undo history (`canvas`, `history`), and a page change
first finishes whatever was live on the old page.

D60: documents. OPEN FILE asks the tool for the file picker (`open_requested`); an opened image or PDF
(`set_reference`) is shown (view "doc") with its own annotation layer per page; the panel's arrows then turn its
pages, SHOW BOARD / SHOW DOC switch the view (nothing is closed), CLOSE DOC closes it. The whiteboard pages are
never touched by any of it, and closing a document (or opening another) keeps its annotations: by its file, given
back when that file is opened again (`kept_annotations`; saved with the board).

D56: the toolbar band (and an open panel) is never drawn on. A pointing stroke that starts there is refused,
and a stroke that reaches it ends there, exactly as if the pen had lifted (the pen stroke is committed, an erase or
a move becomes one undo step, a SELECT loop selects). Either way the rest of that pointing stroke draws nothing
until the pen really lifts (STROKE_END), so a stroke is never joined across the toolbar; `blocked` says why
(the renderer shows it).

AI panel (D51, only with an AI toolbar): the AI button opens a panel whose buttons (summarize, explain, simplify,
examples, questions, explore (D54), close) are pressed the same way. An action renders the selection (the whole canvas if
nothing is selected) to a PNG and queues it in `ai_jobs`; the drawing tool hands jobs to the background worker
(`take_ai_jobs`) and returns answers with `ai_answer`. The controller never talks to the network.
"""

from __future__ import annotations

import math
from collections import Counter

from ..canvas.board import Board
from ..canvas.history import AddStroke, History, MoveStrokes, ReplaceStrokes
from ..canvas.model import Canvas, Stroke
from ..canvas.panel import BOARD_LABELS, AIPanel, BoardPanel
from ..canvas.reference import document_key
from ..canvas.selection import close_loop, png_bytes, select_in_loop, selection_image
from ..canvas.toolbar import COLOURS, WIDTHS, Toolbar

ERASER_RADIUS = {"thin": 12.0, "medium": 24.0, "thick": 42.0}     # px, by the selected width


class DrawingController:
    def __init__(self, canvas: Canvas, toolbar: Toolbar, history: History | None = None, board: Board | None = None):
        self.toolbar = toolbar
        # D59: pages. `canvas` (and `history`) are always the current page's; the canvas given is page 1.
        self.board = board or Board(canvas.size, canvas, history)
        self.board_layout = BoardPanel(canvas.size)
        self.board_open = False                        # the board panel (PAGES button) is shown
        # D60: a reference document (image / PDF) with its own annotation layers; view "board" or "doc"
        self.reference = None
        self.view = "board"
        self.open_requested = False                    # OPEN FILE pressed: the tool shows the file picker
        self.kept_annotations: dict[str, dict] = {}    # closed documents' annotations: {key: {"path", "annotations"}}
        self.notice: dict | None = None                # {"text", "until"}: a message on the wall (D60 errors)
        self.tool, self.colour, self.width = "pen", "black", "medium"
        self.active: Stroke | None = None              # pen stroke being drawn
        self.selected: int | None = None               # stroke being moved
        self.dwell: dict | None = None                 # {"button", "since", "fired"}
        self.log: Counter = Counter()
        self._erase_group: dict | None = None
        self._drag: dict | None = None
        self.selection: list[int] = []                 # D51: strokes chosen with the SELECT loop
        self.selection_log: list[dict] = []            # every loop: when, its points' bounds, what it selected (S1)
        self.loop: list | None = None                  # the loop being drawn
        self.panel_layout = AIPanel(canvas.size, toolbar.top) if getattr(toolbar, "ai", False) else None
        self.panel: dict | None = None                 # {"state": menu|thinking|answer|error, "since", "action", "answer"}
        self.ai_jobs: list[tuple[str, bytes]] = []
        self.now = 0.0
        self.blocked: str | None = None                # D56: "toolbar" / "panel" / "no-point": no ink until the lift
        # Diagnostics only (brain.md §9.12, Stage 3 item 1): what each event's point became, noted inside the
        # existing branches; kept apart from `log`, and never read by any decision here.
        self.outcomes: list[tuple[str, tuple | None, int | None]] = []   # (outcome, point, attempt), last handle()
        self.point_log: Counter = Counter()
        self.attempts = 0                              # stroke attempts: every STROKE_START, refused ones too
        self.attempt: int | None = None                # the current or most recent attempt
        self.stroke_open = False
        self._refused = False                          # the current attempt was refused at its start

    def _note(self, outcome: str, point) -> None:
        self.outcomes.append((outcome, point, self.attempt))
        self.point_log[outcome] += 1

    def _layer(self):
        """The page drawn on: the document's annotation layer of its current page while a document is shown (D60),
        else the current whiteboard page (D59)."""
        if self.view == "doc" and self.reference is not None:
            return self.reference.annotation(self.board.size)
        return self.board.page

    @property
    def canvas(self) -> Canvas:
        """What is drawn on: the current whiteboard page (D59) or the shown document page's annotations (D60)."""
        return self._layer().canvas

    @property
    def history(self) -> History:
        """That page's own undo history: undo and redo never reach another page (D59, D60)."""
        return self._layer().history

    @property
    def background(self):
        """The shown document page fitted on white (D60), or None on the whiteboard."""
        if self.view == "doc" and self.reference is not None:
            return self.reference.display(self.board.size, self.toolbar.top)
        return None

    def view_label(self) -> str:
        """What is shown, for the wall: 'Page 2 of 5', or the document page and file name."""
        if self.view == "doc" and self.reference is not None:
            name = self.reference.path.name
            return f"{self.reference.label()} - {name if len(name) <= 32 else name[:29] + '...'}"
        return self.board.label()

    def show_notice(self, text: str, seconds: float = 6.0) -> None:
        self.notice = {"text": text, "until": self.now + seconds}

    def take_open_request(self) -> bool:
        requested, self.open_requested = self.open_requested, False
        return requested

    def set_reference(self, reference) -> None:
        """Show a newly opened document (D60); the one shown before, if any, is closed (its annotations kept). A file
        opened again gets its annotations back."""
        self._leave_layer()
        if self.reference is not None:
            self._close_reference()
        kept = self.kept_annotations.pop(reference.key, None)
        if kept is not None and not reference.annotations:
            reference.annotations = {k: p for k, p in kept["annotations"].items() if k < reference.count}
            self.log["doc:annotations_back"] += 1
        self.reference, self.view = reference, "doc"
        self.log["doc:open"] += 1

    def keep_annotations(self, path, annotations: dict) -> None:
        """A closed document's annotation layers, given back when that file is opened again."""
        if any(p.canvas.strokes for p in annotations.values()):
            self.kept_annotations[document_key(path)] = {"path": str(path), "annotations": annotations}

    def _close_reference(self) -> None:
        self.keep_annotations(self.reference.path, self.reference.annotations)
        self.reference.close()
        self.reference = None

    def _leave_layer(self) -> None:
        """Before the page drawn on changes: whatever is live ends where it was drawn, the selection is dropped, and
        a pointing stroke still going on draws nothing on the new page."""
        self._finish()
        self.selection, self.selected = [], None
        if self.stroke_open:
            self.blocked = self.blocked or "panel"

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
        self.outcomes = []
        for e in events:
            handler = getattr(self, "_" + e.kind, None)
            if handler is None:
                raise ValueError(f"no handler for event {e.kind!r}")
            handler(e)

    def _on_panel(self, point) -> bool:
        return ((self.panel is not None and self.panel_layout.contains(point))
                or (self.board_open and self.board_layout.contains(point)))

    def _ui_at(self, point) -> str | None:
        """The UI area a point lies on, where nothing is drawn: "toolbar" (the band, D46) or "panel" (D51)."""
        if self.toolbar.in_band(point):
            return "toolbar"
        return "panel" if self._on_panel(point) else None

    def _stroke_start(self, e) -> None:
        self.attempts += 1
        self.attempt, self.stroke_open, self._refused = self.attempts, True, False
        self.blocked = None
        ui = "no-point" if e.point is None else self._ui_at(e.point)
        if ui is not None:
            self.log["strokes_refused_on_panel" if ui == "panel" else "strokes_refused_on_toolbar"] += 1
            self._refused, self.blocked = True, ui
            self._note("refused_no_point" if e.point is None else "refused_band" if ui == "toolbar"
                       else "refused_panel", e.point)
            self.active = self._drag = self.loop = None
            return
        if self.tool == "select":
            self.loop = [e.point]
            self._note("select", e.point)
        elif self.tool == "pen":
            self.active = Stroke(self.canvas.new_id(), COLOURS[self.colour], WIDTHS[self.width])
            self.active.append(e.point)
            self._note("added" if self.active.points else "not_appended", e.point)
        elif self.tool == "eraser":
            self._erase_group = {"removed": {}, "created": set()}
            self._erase_at(e.point)
            self._note("eraser", e.point)
        else:
            sid = self.canvas.hit_test(e.point)
            self.selected = sid
            self._drag = None if sid is None else {"ids": [sid], "last": e.point, "dx": 0.0, "dy": 0.0}
            self._note("move" if sid is not None else "move_nothing", e.point)

    def _stroke_point(self, e) -> None:
        if self.blocked is not None:                   # D56: refused, or ended on the toolbar/panel: until the lift
            self._note("after_refused_start" if self._refused else "after_ui_end", e.point)
            return
        if e.point is None:
            self._note("dropped_no_point", e.point)
            return
        ui = self._ui_at(e.point)
        if ui is not None:                             # D56: the stroke ends here, as if the pen had lifted
            self._note("ended_band" if ui == "toolbar" else "ended_panel", e.point)
            self._finish()
            self.blocked = ui
            self.log[f"strokes_ended_on_{ui}"] += 1
            return
        if self.tool == "select" and self.loop is not None:
            self.loop.append(e.point)
            self._note("select", e.point)
        elif self.tool == "pen" and self.active is not None:
            n = len(self.active.points)
            self.active.append(e.point)
            self._note("added" if len(self.active.points) > n                  # Stroke.append skips a repeat
                       else "duplicate" if all(math.isfinite(float(v)) for v in e.point) else "not_appended", e.point)
        elif self.tool == "eraser" and self._erase_group is not None:
            self._erase_at(e.point)
            self._note("eraser", e.point)
        elif self.tool == "move" and self._drag is not None:
            d = self._drag
            dx, dy = e.point[0] - d["last"][0], e.point[1] - d["last"][1]
            self.canvas.move(d["ids"], dx, dy)
            d["dx"], d["dy"], d["last"] = d["dx"] + dx, d["dy"] + dy, e.point
            self._note("move", e.point)
        else:                                          # no branch took the point (diagnostics only)
            self._note(f"ignored_{self.tool}", e.point)

    def _stroke_end(self, e) -> None:
        self.stroke_open = False
        self._finish()
        self.blocked = None

    def _finish(self) -> None:
        """What the pen lift does with the current tool: commit the stroke, record the erase or move, select."""
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
        loop, self.loop = self.loop, None
        if loop is not None:
            self.selection = select_in_loop(self.canvas, loop)
            self.log["selections"] += 1
            xs, ys = [p[0] for p in loop], [p[1] for p in loop]
            self.selection_log.append({"t": round(self.now, 3), "ids": list(self.selection),
                                       "loop_bounds": [round(min(xs)), round(min(ys)), round(max(xs)), round(max(ys))],
                                       "points": len(loop), "closed_points": len(close_loop(loop))})
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
        self.now = t
        button = None
        if cursor is not None:
            button = ((self.panel_layout.hit(cursor) if self.panel is not None else None)
                      or (self.board_layout.hit(cursor) if self.board_open else None) or self.toolbar.hit(cursor))
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
        self.log[f"press:{name}"] += 1
        if name.startswith("ai:"):
            self._panel_action(name[3:])
            return
        if name.startswith("board:"):
            self._board_action(name[6:])
            return
        button = self.toolbar.button(name)
        if button.kind == "ai":                        # one panel at a time (D59)
            self.panel = None if self.panel is not None else {"state": "menu", "since": self.now}
            self.board_open = self.board_open and self.panel is None
        elif button.kind == "board":
            self.board_open = not self.board_open
            self.panel = None if self.board_open else self.panel
        elif button.kind == "tool":
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

    # -- pages (D59) ------------------------------------------------------------------------------------

    def board_enabled(self, name: str) -> bool:
        """Whether a board panel button can act now (the renderer greys out the others). The arrows act on what is
        shown: whiteboard pages, or the document's pages (D60)."""
        doc = self.view == "doc" and self.reference is not None
        pages = self.reference if doc else self.board
        return {"board:prev": pages.can_previous, "board:next": pages.can_next, "board:add": not doc,
                "board:view": self.reference is not None, "board:closedoc": self.reference is not None}.get(name, True)

    def board_label(self, name: str) -> str:
        doc = self.view == "doc" and self.reference is not None
        if name in ("board:prev", "board:next", "board:view") and doc:
            return {"board:prev": "< DOC", "board:next": "DOC >", "board:view": "SHOW BOARD"}[name]
        return BOARD_LABELS[name]

    def _board_action(self, action: str) -> None:
        if action == "close":
            self.board_open = False
            return
        if action == "open":                           # D60: the tool shows the file picker (not the controller)
            self.open_requested = True
            return
        if not self.board_enabled(f"board:{action}"):  # first / last page, or nothing open: greyed out
            self.log["page_limit" if action in ("prev", "next") else "board_disabled"] += 1
            return
        doc = self.view == "doc" and self.reference is not None
        self._leave_layer()                            # anything live ends on the page it was drawn on
        if action in ("prev", "next"):
            getattr(self.reference if doc else self.board, "previous" if action == "prev" else "next")()
            self.log[f"{'doc' if doc else 'page'}:{action}"] += 1
        elif action == "add":
            self.board.add_page()
            self.log["page:add"] += 1
        elif action == "view":                         # board <-> document: neither is closed nor changed
            self.view = "board" if doc else "doc"
            self.log[f"view:{self.view}"] += 1
        elif action == "closedoc":                     # its annotations are kept (given back if it is reopened)
            self._close_reference()
            self.view = "board"
            self.log["doc:close"] += 1

    # -- actions (toolbar and keyboard) ------------------------------------------------------------------

    def undo(self) -> None:
        if self.history.undo(self.canvas) is not None:
            self.log["undo"] += 1

    def redo(self) -> None:
        if self.history.redo(self.canvas) is not None:
            self.log["redo"] += 1

    def clear(self) -> None:
        removed = self.canvas.clear()
        self.selection = []
        if removed:
            self.history.record(ReplaceStrokes(removed, [], name="clear"))
            self.log["clear"] += 1

    # -- AI panel (D51) ----------------------------------------------------------------------------------

    def _panel_action(self, action: str) -> None:
        if self.panel is None:
            return
        if action == "close":
            self.panel = None
            return
        if self.panel["state"] == "thinking":
            self.log["ai_refused_busy"] += 1
            return
        image = selection_image(self.canvas, [i for i in self.selection if i in self.canvas.strokes])
        if image is None:
            self.panel = {"state": "error", "since": self.now, "action": action,
                          "message": "Nothing written to read yet."}
            return
        self.ai_jobs.append((action, png_bytes(image)))
        self.panel = {"state": "thinking", "since": self.now, "action": action}
        self.log["ai_requests"] += 1

    def take_ai_jobs(self) -> list[tuple[str, bytes]]:
        jobs, self.ai_jobs = self.ai_jobs, []
        return jobs

    def ai_answer(self, answer) -> None:
        """An answer from the AI worker (an AIAnswer). Shown if the panel is still open."""
        self.log["ai_answers" if answer.ok else "ai_errors"] += 1
        if self.panel is None:
            return
        self.panel = {"state": "answer" if answer.ok else "error", "since": self.now, "action": answer.action,
                      "answer": answer, "message": "" if answer.ok else answer.error}
