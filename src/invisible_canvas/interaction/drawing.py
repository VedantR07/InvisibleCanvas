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
examples, questions, explore (D54), ask (D61), close) are pressed the same way. An action renders the selection (the
whole canvas if nothing is selected) to a PNG and queues it in `ai_jobs` with its context; the drawing tool hands
jobs to the background worker (`take_ai_jobs`) and returns answers with `ai_answer`. The controller never talks to
the network.

D61: while a document is shown, the AI reads the shown page itself (the picture, or the PDF page rendered for the AI;
not the annotations). ASK waits for a question typed on the laptop (`typing`, `type_key`: shown live in the panel,
Enter sends, Esc cancels); the pointing gestures and the panel buttons work as before meanwhile.

D62: Smart Lines (the LINES tool, whiteboard pages only). The tools act on `target`: the shown page (`canvas`,
`history`) as before, except with LINES, where it is the page's line sheet: a pointing stroke that starts inside the
writing zone writes the unfinished line (D66: one that starts outside it waits for the zone), and UNDO / REDO /
CLEAR act on the Smart Lines only (the unfinished line's strokes and COMPLETE LINE). COMPLETE LINE and SCROLL UP /
DOWN are pressed like the toolbar. The unfinished line stays on its page when the tool, the page or the view changes;
LINES pauses (back to PEN, with a notice) while a document is shown. The renderer draws `canvas` (the page's
freehand ink) over `background`, which carries the notes area and the writing zone.

D64: what Smart Lines say. Every completed line with neither a reading nor the teacher's decision is read in the
background: `take_line_jobs` hands the drawing tool its image (each request numbered), `line_result` takes the
reading back, and a reading is used only when the line still awaits exactly that request; after an edit, a decision,
a retry or its undo a late one is ignored (`take_line_cancels` says which queued requests are no longer wanted). A
line undone meanwhile keeps its reading for the redo. The review bar (LINES only) is about `review_line`; its
buttons OK, AS WRITTEN, EDIT, KEEP INK and RETRY are pressed like the toolbar and are undoable steps of the Smart
Lines history. EDIT types the line on the laptop as ASK does (`typing`). Holding the cursor on a line in the notes
area picks that line for the review bar.

D65: while a panel is open, the Smart Lines buttons it would cover (the AI panel: DONE, the review buttons, SCROLL
UP / DOWN) stand left of it (`lines_controls`), so they stay usable; the panel still covers what lies under it.

D66 (wall test run 1): with LINES, ink is made only inside the writing zone (not on a button or panel there). A
pointing stroke that starts anywhere else waits (`blocked` "zone") and begins where the fingertip enters the zone,
instead of being refused until the lift (the hand rising into the zone from below while pointing started its strokes
just below it); a line stroke that leaves the zone ends there and begins again when it comes back. UNDO / REDO /
CLEAR with LINES say so on the wall when there is nothing for them in the Smart Lines.

D72: zoom on a document. While a document is shown, the zoom bar (ZOOM OUT, ZOOM IN, FIT; pressed like the toolbar,
left of the AI panel while it is open) zooms the page (`Reference.zoom_in` ...). Its annotations stay in the page's
own coordinates (the wall px of the page shown whole), so a pointing stroke's wall points are converted to them
(`page_view`) before any tool uses them: ink stays on the same words at every zoom, the pen's width and the eraser's
reach are divided by the zoom so they look the same on the wall as they are drawn. With MOVE, a stroke that starts
on the zoomed page where no ink is drags the page (`_pan`, wall px; not an undo step); on ink, it moves the ink.

D74: SELECT on a document chooses a part of the page (`doc_region`: the box around the loop, in the page's own
coordinates, for the page it was drawn on); the AI then reads only that part (the page's own content, rendered for
it), and the panel's title says so. A loop off the page or a slip chooses nothing (the whole page again); a page turn,
SHOW BOARD, CLOSE DOC, another document and CLEAR drop it; a zoom keeps it.

D75: voice writing (whiteboard pages only). VOICE opens the voice panel (one panel at a time) and asks the tool to
listen (`voice_requests`); the tool hands back each transcribed utterance once (`voice_result`, numbered: a number seen
before is ignored) and the listener's state (`voice_status`). An utterance that is a whole command (`voice.commands`,
while COMMANDS is on) edits; anything else is written at the end of the page's typed text (`Page.voice`), unless
paused (then only "resume listening" is heard). While the panel is open UNDO / REDO / CLEAR act on the typed text (as
with LINES); CANCEL puts back what the pages had when voice writing began; "clear current line" must be said twice.
The typed text lies under the ink, in its own area (`background`).
"""

from __future__ import annotations

import math
from collections import Counter

import cv2
import numpy as np

from ..canvas.board import Board
from ..canvas.history import AddStroke, History, MoveStrokes, ReplaceStrokes
from ..canvas.lines import (
    REVIEW, TEXT_MAX, CompleteLine, LineSheet, LinesLayout, RetryLine, ReviewLine, render_sheet,
)
from ..canvas.model import Canvas, Stroke
from ..canvas.panel import BOARD_LABELS, QUESTION_MAX, AIPanel, BoardPanel, VoicePanel, ZoomBar, answer_rows
from ..canvas.reference import ReferenceError, document_key
from ..canvas.selection import (
    MIN_LOOP_AREA, close_loop, loop_area, loop_region, png_bytes, select_in_loop, selection_image, strokes_image,
)
from ..canvas.voice_text import VoiceLayout, VoiceText
from ..canvas.voice_text import render as render_voice
from ..canvas.voice_text import text_image as voice_text_image
from ..voice.commands import MARKS
from ..voice.commands import correction as voice_correction
from ..voice.commands import match as voice_command

VOICE_LABELS = {"voice:done": "DONE", "voice:cancel": "CANCEL", "voice:mic": "MIC", "voice:delete": "DELETE",
                "voice:up": "SCROLL UP", "voice:down": "SCROLL DOWN"}
VOICE_CONFIRM_S = 6.0                                  # D75: "clear current line" said again within this
# D75 wall test 1 ("delete, scroll up and down were of no use"): DELETE shown only when it can act; scrolling is the
# scroll column beside the text (wall test 3: "a scroll button for the mike writing")
VOICE_WHEN_USEFUL = ("voice:delete",)

AI_OFF = "The AI is off (draw --no-ai): EDIT or KEEP INK."
from ..canvas.toolbar import COLOURS, WIDTHS, Button, Toolbar

ERASER_RADIUS = {"thin": 12.0, "medium": 24.0, "thick": 42.0}     # px, by the selected width


class DrawingController:
    def __init__(self, canvas: Canvas, toolbar: Toolbar, history: History | None = None, board: Board | None = None,
                 lines_layout: LinesLayout | None = None, voice_layout: VoiceLayout | None = None):
        self.toolbar = toolbar
        # D59: pages. `canvas` (and `history`) are always the current page's; the canvas given is page 1.
        self.board = board or Board(canvas.size, canvas, history)
        self.board_layout = BoardPanel(canvas.size)
        self.board_open = False                        # the board panel (PAGES button) is shown
        self.lines_layout = lines_layout or LinesLayout(canvas.size, toolbar.top)     # D62: Smart Lines
        # D64: reading the lines. `recognition`: the drawing tool has a reader (the AI is on).
        self.recognition = False
        self._requests: dict[int, tuple] = {}         # request -> (sheet, line), until its reading comes back
        self._request_no = 0
        self._cancelled: set[int] = set()
        self.review_pick: dict | None = None           # {"sheet", "line"}: picked in the notes area
        self.line_edit: dict | None = None             # {"sheet", "line", "text"}: EDIT typing on the laptop
        # D60: a reference document (image / PDF) with its own annotation layers; view "board" or "doc"
        self.reference = None
        self.view = "board"
        self.open_requested = False                    # OPEN FILE pressed: the tool shows the file picker
        self.kept_annotations: dict[str, dict] = {}    # closed documents' annotations: {key: {"path", "annotations"}}
        self.notice: dict | None = None                # {"text", "until"}: a message on the wall (D60 errors)
        self.tool, self.colour, self.width = "pen", "black", "medium"
        self.lines_eraser = False                      # D78: ERASER chosen while writing Smart Lines rubs out the line
        self.active: Stroke | None = None              # pen stroke being drawn
        self.selected: int | None = None               # stroke being moved
        self.dwell: dict | None = None                 # {"button", "since", "fired"}
        self.log: Counter = Counter()
        self._erase_group: dict | None = None          # D78: per layer erased: {id: {"layer", "removed", "created"}}
        self._erase_told = False                       # D78: the notes-area notice given in this eraser stroke
        self._drag: dict | None = None
        self.selection: list[int] = []                 # D51: strokes chosen with the SELECT loop
        self.selection_log: list[dict] = []            # every loop: when, its points' bounds, what it selected (S1)
        self.loop: list | None = None                  # the loop being drawn
        self.panel_layout = AIPanel(canvas.size, toolbar.top) if getattr(toolbar, "ai", False) else None
        for panel in (self.panel_layout, self.board_layout):           # D65: room beside each panel (ValueError)
            if panel is not None:
                self.lines_layout.beside(panel.rect)
        self._zoom_bars = {None: ZoomBar(canvas.size, toolbar.top)}    # D72: by its right edge (None: its own)
        self._pan: dict | None = None                  # D72: {"from": wall point, "origin"}: dragging the page
        self.doc_region: dict | None = None            # D74: {"page", "rect"}: a part of a document page for the AI
        # D75: voice writing
        self.voice_layout = voice_layout or VoiceLayout((40, 60, 952, 632))
        self.voice_panel = VoicePanel(canvas.size)
        self.voice_arrows = [Button("voice:up", "panel", self.voice_layout.up),           # the scroll column
                             Button("voice:down", "panel", self.voice_layout.down)]
        self.voice_open = self.voice_paused = False
        self.voice_commands = True
        self.voice_gate_dbfs = -42.0                   # shown on the panel's loudness bar (the tool sets it)
        self.voice_status = {"state": "off", "detail": "", "device": "", "level": -120.0}
        self.voice_requests: list[str] = []            # for the tool: "start", "stop", "mic"
        self.voice_scroll = 0                          # lines back from the end of the typed text
        self.voice_log: list[dict] = []                # every utterance: what it said, what it did
        self._voice_seen: set[int] = set()
        self._voice_began: dict[int, tuple] = {}       # id(page) -> (page, its tokens when voice writing began)
        self._voice_confirm: dict | None = None        # {"what", "until"}: a command to say again
        self._voice_bg: tuple | None = None            # (key, the background with the typed text, its base)
        self.voice_selected: list[int] = []            # D75 V2: token indexes chosen with SELECT
        # {"state": menu|asking|thinking|answer|error, "since", "action", "answer", "source", "title", "question"}
        self.panel: dict | None = None
        self.ai_jobs: list[tuple[str, bytes, dict]] = []    # (action, PNG, context), D61
        self.now = 0.0
        self.blocked: str | None = None                # D56: "toolbar" / "panel" / "no-point": no ink until the lift
        #                                                D66: "zone": a line stroke waiting for the writing zone
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

    def sheet(self) -> LineSheet:
        """The current whiteboard page's Smart Lines (D62), made when first used."""
        page = self.board.page
        if page.lines is None:
            page.lines = LineSheet(self.board.size)
        return page.lines

    @property
    def lines_active(self) -> bool:
        """The LINES tool is in use on a whiteboard page (D62), or (D78) ERASER chosen while it was: the eraser then
        rubs out the line being written, and UNDO / REDO / CLEAR, DONE and the review stay on the Smart Lines."""
        smart = self.tool == "lines" or (self.tool == "eraser" and self.lines_eraser)
        return smart and not (self.view == "doc" and self.reference is not None)

    @property
    def target(self):
        """What the tools act on (D62): the line sheet with LINES, else the shown page (`canvas`, `history`)."""
        return self.sheet() if self.lines_active else self._layer()

    @property
    def background(self):
        """What lies under the page's ink: the shown document page fitted on white (D60); on the whiteboard the
        page's Smart Lines (D62: notes area, writing zone, unfinished line), or None when it has none."""
        if self.view == "doc" and self.reference is not None:
            return self.reference.display(self.board.size, self.toolbar.top)
        sheet = self.board.page.lines
        if not self.lines_active and (sheet is None or not sheet.has_content):
            return self._with_voice(None)
        sheet, review = self.sheet(), self.review_line()
        return self._with_voice(render_sheet(sheet, self.lines_layout, self.lines_active or bool(sheet.canvas.strokes),
                                             self.lines_active, None if review is None else review.id,
                                             self._notes_right()))

    def _with_voice(self, base):
        """D75: the page's typed text (and, while voice writing is on, its area's frame) over `base`; the same image
        until something in it changes (the renderer keeps its ink over it)."""
        text = self.board.page.voice
        if not self.voice_open and (text is None or not text.has_content):
            return base
        column = self.voice_column_shown
        key = (id(text), None if text is None else text.version, self.voice_scroll, self.voice_open,
               tuple(self.voice_selected), column)
        cached = self._voice_bg
        if cached is None or cached[0] != key or cached[2] is not base:
            w, h = self.board.size
            img = base.copy() if base is not None else np.full((h, w, 3), 255, np.uint8)
            render_voice(img, text, self.voice_layout, active=self.voice_open, scroll=self.voice_scroll,
                         selected=self.voice_selected, column=column)
            self._voice_bg = cached = (key, img, base)
        return cached[1]

    @property
    def doc_shown(self) -> bool:
        return self.view == "doc" and self.reference is not None

    @property
    def page_view(self):
        """D72: where the shown document page lies on the wall at its zoom (a PageView), or None where a page's
        coordinates are the wall's (the whiteboard, a document page shown whole)."""
        if not self.doc_shown:
            return None
        view = self.reference.view(self.board.size, self.toolbar.top)
        return None if view.identity else view

    @property
    def zoom_bar(self) -> ZoomBar | None:
        """D72: the zoom bar while a document is shown; left of an open panel that would cover it."""
        if not self.doc_shown:
            return None
        bar = self._zoom_bars[None]
        covering = (self.panel_layout.rect if self.panel is not None and self.panel_layout is not None
                    else self.board_layout.rect if self.board_open else None)
        x0, y0, x1, y1 = bar.rect
        if covering is None or not (covering[0] < x1 and x0 < covering[2] and covering[1] < y1 and y0 < covering[3]):
            return bar
        right = covering[0] - 12
        if right not in self._zoom_bars:
            self._zoom_bars[right] = ZoomBar(self.board.size, self.toolbar.top, right=right)
        return self._zoom_bars[right]

    @property
    def region(self) -> tuple[float, float, float, float] | None:
        """D74: the part of the shown document page chosen with SELECT (page coordinates), or None: the whole page."""
        r = self.doc_region
        if r is None or not self.doc_shown or r["page"] != self.reference.current:
            return None
        return r["rect"]

    def zoom_enabled(self, name: str) -> bool:
        """D72: whether a zoom button can act now (the renderer greys out the others)."""
        if not self.doc_shown:
            return False
        ref = self.reference
        return {"zoom:in": ref.can_zoom_in, "zoom:out": ref.can_zoom_out, "zoom:fit": ref.zoom != 1.0}[name]

    def zoom_label(self) -> str:
        return f"{round(self.reference.zoom * 100)}%" if self.doc_shown else ""

    def _zoom_action(self, action: str) -> None:
        if not self.zoom_enabled(f"zoom:{action}"):    # 100 % or 400 %: greyed out
            self.log["zoom_limit"] += 1
            return
        self._leave_target()                           # anything live ends where it was drawn
        frame, ref = (self.board.size, self.toolbar.top), self.reference
        if action == "in":
            ref.zoom_in(*frame)
        elif action == "out":
            ref.zoom_out(*frame)
        else:
            ref.set_zoom(1.0, *frame)
        self.log[f"doc:zoom_{action}"] += 1

    def _notes_right(self) -> int | None:
        """D71: where the notes end while an open panel lies over their right part: left of the panel, and of the
        scroll column moved beside it (D65); None: their own width."""
        if self.panel is not None and self.panel_layout is not None:
            covering = self.panel_layout.rect
        elif self.board_open:
            covering = self.board_layout.rect
        else:
            return None
        nx0, ny0, nx1, ny1 = self.lines_layout.notes
        if not (covering[0] < nx1 and covering[1] < ny1 and ny0 < covering[3]):
            return None
        left = min(covering[0], self.lines_controls.column[0]) if self.lines_active else covering[0]
        return int(left) - 12

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
        self._pause_lines()

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
        self._leave_target()
        self._cancel_edit("left")
        self.selection, self.selected = [], None
        self.doc_region = None                         # D74: it belongs to the page it was drawn on
        self.voice_selected, self.voice_scroll = [], 0 # D75: the new page's typed text from its end

    def _leave_target(self) -> None:
        """Before `target` changes (D62: into or out of LINES): what is live ends where it was drawn, and a pointing
        stroke still going on draws nothing more (D66: also one waiting for the writing zone)."""
        self._finish()
        if self.stroke_open:
            self.blocked = "panel" if self.blocked in (None, "zone") else self.blocked

    def _pause_line_stroke(self) -> None:
        """D66: a Smart Lines button pressed while pointing: what is live ends in the line, and the pointing waits
        for the writing zone (pointing back into it writes on)."""
        self._finish()
        if self.stroke_open and self.blocked is None:
            self.blocked = "zone"

    def _pause_lines(self) -> None:
        """A document is now shown: LINES works on whiteboard pages only, so the tool goes back to PEN (D62). D75: voice
        writing ends too (it writes on whiteboard pages)."""
        if self.voice_open and self.view == "doc" and self.reference is not None:
            self._close_voice()
            self.show_notice("Voice writing ended: it writes on whiteboard pages (SHOW BOARD, then VOICE).")
        if self.lines_eraser and self.view == "doc" and self.reference is not None:
            self.lines_eraser = False                  # D78: the eraser now erases the document's annotations
        if self.tool == "lines" and self.view == "doc" and self.reference is not None:
            self.tool = "pen"
            self.show_notice(f"Smart Lines paused on the document; any unfinished line stays on whiteboard "
                             f"{self.board.label().lower()}.")
            self.log["lines:paused_doc"] += 1

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
        bar = self.zoom_bar                            # D72: never drawn on, as a panel
        return ((self.panel is not None and self.panel_layout.contains(point))
                or (self.board_open and self.board_layout.contains(point))
                or (bar is not None and bar.contains(point))
                or (self.voice_open and point is not None and self.voice_rect[0] <= point[0] < self.voice_rect[2]
                    and self.voice_rect[1] <= point[1] < self.voice_rect[3]))                  # D75: as shown

    def _ui_at(self, point) -> str | None:
        """The UI area a point lies on, where nothing is drawn: "toolbar" (the band, D46) or "panel" (D51; D62: the
        Smart Lines buttons while LINES is in use)."""
        if self.toolbar.in_band(point):
            return "toolbar"
        if self._on_voice_column(point):              # D75: the typed text's scroll column
            return "panel"
        if self._on_panel(point) or (self.lines_active and (self.lines_controls.on_control(point) or (
                self.lines_controls.in_bar(point) and self.review_line() is not None))):    # D64: the review bar
            return "panel"
        return None

    def _writes_line_at(self, point) -> bool:
        """D66: with LINES, ink is made only here: inside the writing zone and not on a button or a panel."""
        return point is not None and self.lines_layout.in_zone(point) and self._ui_at(point) is None

    def _stroke_start(self, e) -> None:
        self.attempts += 1
        self.attempt, self.stroke_open, self._refused = self.attempts, True, False
        self.blocked = None
        if self.lines_active and not self._writes_line_at(e.point):
            # D66 (R42): a line stroke that starts outside the zone (below it, on the toolbar, on a button) waits
            # and begins where the fingertip enters the zone, instead of being refused until the lift
            self.log["line_starts_outside_zone"] += 1
            self.blocked = "zone"
            self._note("outside_zone", e.point)
            self.active = self._drag = self.loop = self._pan = None
            return
        ui = "no-point" if e.point is None else self._ui_at(e.point)
        if ui is not None:
            self.log["strokes_refused_on_panel" if ui == "panel" else "strokes_refused_on_toolbar"] += 1
            self._refused, self.blocked = True, ui
            self._note("refused_no_point" if e.point is None else "refused_band" if ui == "toolbar"
                       else "refused_panel", e.point)
            self.active = self._drag = self.loop = self._pan = None
            return
        self._begin(e.point)

    def _begin(self, point) -> None:
        """The current tool's start of a stroke at the wall point `point` (D72: in a zoomed document page's own
        coordinates from here on)."""
        wall, view = point, self.page_view
        scale = 1.0 if view is None else view.scale
        if view is not None:
            point = view.to_page(point)
        if self.tool == "select":
            self.loop = [point]
            self._note("select", wall)
        elif self.tool in ("pen", "lines"):
            self.active = Stroke(self.target.canvas.new_id(), COLOURS[self.colour], WIDTHS[self.width] / scale)
            self.active.append(point)
            self._note("added" if self.active.points else "not_appended", wall)
        elif self.tool == "eraser":
            self._erase_group = {id(layer): {"layer": layer, "removed": {}, "created": set()}
                                 for layer in self._erase_layers()}
            self._erase_told = False
            self._erase_at(point)
            self._note("eraser", wall)
        else:
            sid = self.target.canvas.hit_test(point, 12.0 / scale)        # 12 px on the wall at any zoom
            self.selected = sid
            self._drag = None if sid is None else {"ids": [sid], "last": point, "dx": 0.0, "dy": 0.0}
            if sid is None and view is not None:       # D72: no ink here: drag the zoomed page
                self._pan = {"from": wall, "origin": view.origin}
                self._note("pan", wall)
                return
            self._note("move" if sid is not None else "move_nothing", wall)

    def _stroke_point(self, e) -> None:
        if self.blocked == "zone":                     # D66: a line stroke waiting for the zone
            if self.lines_active and self._writes_line_at(e.point):
                self.blocked = None
                self._begin(e.point)
                self.log["line_strokes_entered_zone"] += 1
            else:
                self._note("outside_zone", e.point)
            return
        if self.blocked is not None:                   # D56: refused, or ended on the toolbar/panel: until the lift
            self._note("after_refused_start" if self._refused else "after_ui_end", e.point)
            return
        if e.point is None:
            self._note("dropped_no_point", e.point)
            return
        if self.lines_active and self.active is not None and not self._writes_line_at(e.point):
            # D66: a line stroke ends where it leaves the zone (or reaches a button), as if the pen had lifted,
            # and the pointing goes on waiting: back in the zone, a new stroke begins
            self._note("left_zone", e.point)
            self._finish()
            self.blocked = "zone"
            self.log["line_strokes_left_zone"] += 1
            return
        ui = self._ui_at(e.point)
        if ui is not None:                             # D56: the stroke ends here, as if the pen had lifted
            self._note("ended_band" if ui == "toolbar" else "ended_panel", e.point)
            self._finish()
            self.blocked = ui
            self.log[f"strokes_ended_on_{ui}"] += 1
            return
        if self._pan is not None:                      # D72: the page follows the fingertip (wall px)
            (fx, fy), (ox, oy) = self._pan["from"], self._pan["origin"]
            self.reference.place((ox + e.point[0] - fx, oy + e.point[1] - fy), self.board.size, self.toolbar.top)
            self._note("pan", e.point)
            return
        view = self.page_view                          # D72: a zoomed page's own coordinates (notes: the wall's)
        point = e.point if view is None else view.to_page(e.point)
        if self.tool == "select" and self.loop is not None:
            self.loop.append(point)
            self._note("select", e.point)
        elif self.tool in ("pen", "lines") and self.active is not None:
            n = len(self.active.points)
            self.active.append(point)
            self._note("added" if len(self.active.points) > n                  # Stroke.append skips a repeat
                       else "duplicate" if all(math.isfinite(float(v)) for v in e.point) else "not_appended", e.point)
        elif self.tool == "eraser" and self._erase_group is not None:
            self._erase_at(point)
            self._note("eraser", e.point)
        elif self.tool == "move" and self._drag is not None:
            d = self._drag
            dx, dy = point[0] - d["last"][0], point[1] - d["last"][1]
            self.target.canvas.move(d["ids"], dx, dy)
            d["dx"], d["dy"], d["last"] = d["dx"] + dx, d["dy"] + dy, point
            self._note("move", e.point)
        else:                                          # no branch took the point (diagnostics only)
            self._note(f"ignored_{self.tool}", e.point)

    def _stroke_end(self, e) -> None:
        self.stroke_open = False
        self._finish()
        self.blocked = None

    def _finish(self) -> None:
        """What the pen lift does with the current tool: commit the stroke, record the erase or move, select."""
        target = self.target
        if self.active is not None and self.active.points:
            target.history.do(AddStroke(self.active), target.canvas)
            self.log["line_strokes" if self.lines_active else "strokes"] += 1
        groups, self._erase_group = self._erase_group, None
        for group in (groups or {}).values():           # D78: each layer's part is one undo step of its own history
            layer = group["layer"]
            if group["removed"] or group["created"]:
                added = [layer.canvas.strokes[i] for i in sorted(group["created"]) if i in layer.canvas.strokes]
                layer.history.record(ReplaceStrokes(list(group["removed"].values()), added))
                self.log["erase_strokes"] += 1
                if isinstance(layer, LineSheet):
                    self.log["lines:erased"] += 1
        drag, self._drag = self._drag, None
        if drag and (drag["dx"] or drag["dy"]):
            target.history.record(MoveStrokes(drag["ids"], drag["dx"], drag["dy"]))
            self.log["moves"] += 1
        if self._pan is not None:                      # D72: a view change, not an undo step
            self._pan = None
            self.log["doc:pans"] += 1
        loop, self.loop = self.loop, None
        if loop is not None:
            region = None
            if self.doc_shown:                         # D74: a part of the page, not the ink on it
                self.selection = []
                box = loop_region(loop)
                frame = (self.board.size, self.toolbar.top)
                if box is not None and self.reference.region_fraction(box, *frame) is not None:
                    px0, py0, px1, py1 = self.reference.page_rect(*frame)
                    region = (max(box[0], px0), max(box[1], py0), min(box[2], px1), min(box[3], py1))
                self.doc_region = None if region is None else {"page": self.reference.current, "rect": region}
                self.log["doc:selections" if region is not None else "doc:selection_none"] += 1
            else:
                self.selection = select_in_loop(target.canvas, loop)
                self.voice_selected = self._words_in_loop(loop)                 # D75 V2: typed words too
            self.log["selections"] += 1
            xs, ys = [p[0] for p in loop], [p[1] for p in loop]
            self.selection_log.append({"t": round(self.now, 3), "ids": list(self.selection),
                                       "loop_bounds": [round(min(xs)), round(min(ys)), round(max(xs)), round(max(ys))],
                                       "points": len(loop), "closed_points": len(close_loop(loop)),
                                       **({"region": [round(v) for v in region]} if region is not None else {}),
                                       **({"words": len(self.voice_selected)} if self.voice_selected else {})})
        self.active, self.selected = None, None

    def _erase_layers(self) -> list:
        """What the eraser takes. From PEN (or any tool but LINES): the shown page's ink only, never the line being
        written (D62). D78 (wall test 16:47: ink drawn with PEN in the writing area stayed while the Smart Lines eraser
        rubbed it): the Smart Lines eraser takes all the ink under it, the line being written and the page's ink;
        completed lines are not ink on the page."""
        if not self.lines_active:
            return [self._layer()]
        page = self.board.page
        return [page, self.sheet()]

    def _erase_at(self, point) -> None:
        view = self.page_view                          # D72: the same reach on the wall at any zoom
        radius = self.eraser_radius / (1.0 if view is None else view.scale)
        for group in self._erase_group.values():
            removed, created = group["layer"].canvas.erase(point, radius)
            for s in removed:
                if s.id in group["created"]:
                    group["created"].discard(s.id)      # a piece from earlier in this stroke: not an original
                else:
                    group["removed"][s.id] = s
            group["created"].update(s.id for s in created)
        sheet, (nx0, ny0, nx1, ny1) = self.board.page.lines, self.lines_layout.notes
        if (view is None and not self._erase_told and sheet is not None and sheet.lines
                and nx0 <= point[0] < nx1 and ny0 <= point[1] < ny1):
            self._erase_told = True                    # once per eraser stroke
            self.show_notice("Finished lines can't be erased. With LINES, UNDO brings the last line back into the "
                             "writing area to erase there.")
            self.log["lines:erase_notes"] += 1

    # -- toolbar: press by holding the cursor on a button ------------------------------------------------

    def update_pointer(self, t: float, cursor) -> None:
        """Every frame, with the engine's cursor (None: no hand)."""
        self.now = t
        button = None
        if cursor is not None and self._on_panel(cursor):  # an open panel covers what lies under it (D62)
            bar = self.zoom_bar                            # D72
            more = self.panel_layout.more if self.panel_layout is not None else None          # D76
            button = ((self.panel_layout.hit(cursor) if self.panel is not None else None)
                      or (more if self.ai_more_shown and more.contains(cursor) else None)
                      or (self.board_layout.hit(cursor) if self.board_open else None)
                      or (bar.hit(cursor) if bar is not None else None)
                      or (next((b for b in self.voice_buttons if b.contains(cursor)), None)
                          if self.voice_open else None))                                   # D75: the shown buttons
        elif cursor is not None:
            button = ((self._lines_hit(cursor) if self.lines_active else None) or self._voice_arrow_at(cursor)
                      or self.toolbar.hit(cursor))
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
        if name.startswith("lines:"):
            self._lines_action(name[6:])
            return
        if name.startswith("zoom:"):                   # D72
            self._zoom_action(name[5:])
            return
        if name.startswith("voice:"):                  # D75
            self._voice_action(name[6:])
            return
        button = self.toolbar.button(name)
        if button.kind == "ai":                        # one panel at a time (D59)
            self.panel = None if self.panel is not None else {"state": "menu", "since": self.now}
            self.board_open = self.board_open and self.panel is None
            if self.panel is not None:
                self._close_voice()                    # D75
        elif button.kind == "board":
            self.board_open = not self.board_open
            self.panel = None if self.board_open else self.panel
            if self.board_open:
                self._close_voice()                    # D75
        elif button.kind == "voice":                   # D75
            self._toggle_voice()
        elif button.kind == "tool":
            if name == "lines" and self.view == "doc" and self.reference is not None:
                self.show_notice("Smart Lines are on whiteboard pages: PAGES, then SHOW BOARD.")
                self.log["lines:refused_doc"] += 1
                return
            if name == "lines" and self.voice_open:     # D75: the same part of the page
                self._close_voice()
                self.show_notice("Voice writing ended: LINES uses the same part of the page.")
            # D78 (wall test: ERASER did nothing on the line being written, which is the Smart Lines' own layer):
            # ERASER chosen while writing Smart Lines erases that line; from any other tool, the page's ink as before
            lines_eraser = name == "eraser" and self.lines_active
            if (name == "lines" or lines_eraser) != self.lines_active:     # D62: the tools' target changes
                self._leave_target()
                self._cancel_edit("left")
            if lines_eraser and not (self.tool == "eraser" and self.lines_eraser):
                self.show_notice("ERASER on the Smart Line: rub out what you wrote in the writing area. "
                                 "LINES to write again.")
                self.log["lines:eraser"] += 1
            self.tool, self.lines_eraser = name, lines_eraser
        elif button.kind == "colour":                  # a colour selects PEN (D62: LINES keeps writing lines)
            self.colour = name
            if self.tool == "eraser" and self.lines_active:     # D78: from the Smart Lines eraser, writing lines again
                self.tool, self.lines_eraser = "lines", False
            elif self.tool != "lines":
                self.tool = "pen"
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
            self._pause_lines()
        elif action == "closedoc":                     # its annotations are kept (given back if it is reopened)
            self._close_reference()
            self.view = "board"
            self.log["doc:close"] += 1

    # -- voice writing (D75) ----------------------------------------------------------------------------

    def page_voice(self) -> VoiceText:
        """The shown whiteboard page's typed text, made when first written."""
        page = self.board.page
        if page.voice is None:
            page.voice = VoiceText()
        return page.voice

    @property
    def voice_active(self) -> bool:
        """Voice writing is on, on a whiteboard page."""
        return self.voice_open and not self.doc_shown

    def take_voice_requests(self) -> list[str]:
        requests, self.voice_requests = self.voice_requests, []
        return requests

    def voice_status_update(self, state: str, detail: str = "", device: str = "", level: float = -120.0) -> None:
        self.voice_status = {"state": state, "detail": detail, "device": device, "level": level}

    def _toggle_voice(self) -> None:
        if self.voice_open:
            self._close_voice()
            return
        if self.doc_shown:
            self.show_notice("Voice writing is on whiteboard pages: PAGES, then SHOW BOARD.")
            self.log["voice:refused_doc"] += 1
            return
        if self.lines_active:                          # the same part of the page: back to PEN (D78: or its eraser)
            self._leave_target()
            self._cancel_edit("left")
            self.tool, self.lines_eraser = "pen", False
            self.show_notice("LINES ended: voice writing uses the writing area of the page.")
        self.panel, self.board_open = None, False      # one panel at a time
        self.voice_open, self.voice_paused, self.voice_scroll = True, False, 0
        self._voice_began, self._voice_confirm = {}, None
        self.voice_requests.append("start")
        self.log["voice:open"] += 1

    def _close_voice(self) -> None:
        if not self.voice_open:
            return
        self.voice_open, self._voice_confirm, self._voice_began = False, None, {}
        self.voice_requests.append("stop")             # (chosen words stay chosen: the AI panel may read them)
        self.log["voice:close"] += 1

    def _words_in_loop(self, loop) -> list[int]:
        """D75 V2: the typed words shown whose middle lies inside a SELECT loop (closed at its tightest point, D53)."""
        text = self.board.page.voice
        if text is None or not text.has_content:
            return []
        pts = close_loop(loop)
        if loop_area(pts) < MIN_LOOP_AREA:
            return []
        contour = pts.astype(np.float32).reshape(-1, 1, 2)
        chosen = {index for index, (x0, y0, x1, y1) in self.voice_layout.word_boxes(text.tokens, self.voice_scroll)
                  if cv2.pointPolygonTest(contour, ((x0 + x1) / 2, (y0 + y1) / 2), False) >= 0}
        return sorted(chosen)

    def _voice_touch(self) -> None:
        """Before the first change to a page in this voice writing: what it had (for CANCEL)."""
        page = self.board.page
        self._voice_began.setdefault(id(page), (page, tuple(self.page_voice().tokens)))

    def _voice_lines(self) -> list:
        """The shown page's typed text laid out (kept until the text changes)."""
        text = self.board.page.voice
        if text is None:
            return []
        key = (id(text), text.version)
        if getattr(self, "_voice_lines_cache", (None,))[0] != key:
            self._voice_lines_cache = (key, self.voice_layout.lines(text.tokens))
        return self._voice_lines_cache[1]

    @property
    def voice_column_shown(self) -> bool:
        """The scroll column beside the typed text: while voice writing is on, and after it while the text is longer
        than the area (to read back); never on a document."""
        if self.doc_shown:
            return False
        return self.voice_open or self.voice_layout.max_scroll(self._voice_lines()) > 0

    def _voice_arrow_at(self, point):
        if point is None or not self.voice_column_shown:
            return None
        return next((b for b in self.voice_arrows if b.contains(point)), None)

    def _on_voice_column(self, point) -> bool:
        if point is None or not self.voice_column_shown:
            return False
        x0, y0, x1, y1 = self.voice_layout.column_rect
        return x0 <= point[0] < x1 and y0 <= point[1] < y1

    @property
    def voice_buttons(self) -> list:
        """The voice panel's buttons shown now: SCROLL UP / DOWN and DELETE only when they can act."""
        return [b for b in self.voice_panel.buttons if b.name not in VOICE_WHEN_USEFUL or self.voice_enabled(b.name)]

    @property
    def voice_rect(self) -> tuple[int, int, int, int]:
        """The voice panel as shown: down to its last button shown."""
        x0, y0, x1, _ = self.voice_panel.rect
        return x0, y0, x1, max(b.rect[3] for b in self.voice_buttons) + 12

    def voice_enabled(self, name: str) -> bool:
        lines = self._voice_lines()
        return {"voice:up": self.voice_scroll < self.voice_layout.max_scroll(lines),
                "voice:down": self.voice_scroll > 0,
                "voice:delete": bool(self.voice_selected)}.get(name, True)

    def voice_label(self, name: str) -> str:
        if name == "voice:pause":
            return "RESUME" if self.voice_paused else "PAUSE"
        if name == "voice:commands":
            return "COMMANDS ON" if self.voice_commands else "COMMANDS OFF"
        return VOICE_LABELS[name]

    def _voice_action(self, action: str) -> None:
        if not self.voice_enabled(f"voice:{action}"):
            self.log["voice:disabled"] += 1
            return
        if action == "pause":
            self.voice_paused = not self.voice_paused
            self.log["voice:resume" if not self.voice_paused else "voice:pause"] += 1
        elif action == "done":
            self._close_voice()
        elif action == "cancel":                       # every page back to what it had (one undo step each)
            for page, tokens in self._voice_began.values():
                page.voice.restore(tokens)
            self.log["voice:cancel"] += 1
            self._close_voice()
        elif action == "commands":
            self.voice_commands = not self.voice_commands
        elif action == "mic":
            self.voice_requests.append("mic")
        elif action in ("up", "down"):
            top = self.voice_layout.max_scroll(self._voice_lines())
            self.voice_scroll = min(max(self.voice_scroll + (3 if action == "up" else -3), 0), top)
        elif action == "delete":                       # V2: the words chosen with SELECT
            self._voice_touch()
            self.page_voice().delete_words(self.voice_selected)
            self.voice_selected = []
            self.log["voice:delete"] += 1

    def voice_result(self, number: int, text: str, latency_ms: float | None = None) -> None:
        """A transcribed utterance from the tool (once each: a number seen before is ignored)."""
        if number in self._voice_seen:
            self.log["voice:duplicates"] += 1
            return
        self._voice_seen.add(number)
        entry = {"t": round(self.now, 3), "n": number, "text": text, "latency_ms": latency_ms}
        command = voice_command(text) if self.voice_commands else None
        fix = voice_correction(text) if self.voice_commands and command is None else None
        if not self.voice_active:
            entry["ignored"] = "closed"
        elif fix is not None:                          # "I mean ...": the last phrase replaced
            entry["command"], entry["replacement"] = "correct", fix
            if self.voice_paused:
                entry["ignored"] = "paused"
            else:
                self._voice_touch()
                if self.page_voice().replace_last(fix):
                    self.voice_scroll, self.voice_selected = 0, []
                    self.log["voice:corrections"] += 1
        elif command is not None:
            entry["command"] = command
            if self.voice_paused and command != "resume":
                entry["ignored"] = "paused"
            else:
                self._voice_command(command)
        elif self.voice_paused:
            entry["ignored"] = "paused"
        else:
            self._voice_touch()
            if self.page_voice().write(text):
                self.voice_scroll = 0                  # follow the end of the text
                self.voice_selected = []               # the words chosen by place: the text changed
                self.log["voice:phrases"] += 1
        self.log["voice:ignored" if "ignored" in entry else "voice:used"] += 1
        self.voice_log.append(entry)

    def _voice_command(self, command: str) -> None:
        self.log[f"voice:cmd:{command}"] += 1
        if command == "pause":
            self.voice_paused = True
            return
        if command == "resume":
            self.voice_paused = False
            return
        text = self.page_voice()
        if command == "delete_selection":              # V2: the words chosen with SELECT
            self._voice_action("delete")
            return
        self.voice_selected = []                       # every other edit moves the words
        if command == "undo":
            text.undo()
            return
        if command == "redo":
            text.redo()
            return
        if command == "clear_line":
            confirm = self._voice_confirm
            if not (confirm and confirm["what"] == "clear_line" and self.now <= confirm["until"]):
                self._voice_confirm = {"what": "clear_line", "until": self.now + VOICE_CONFIRM_S}
                self.show_notice('Say "clear current line" again to clear the line being written.', VOICE_CONFIRM_S)
                return
            self._voice_confirm = None
        self._voice_touch()
        if command in MARKS:
            text.punctuate(MARKS[command])
        else:
            {"new_line": text.new_line, "new_paragraph": text.new_paragraph, "delete_word": text.delete_last_word,
             "delete_sentence": text.delete_last_sentence, "clear_line": text.clear_line,
             "scratch": text.scratch}[command]()
        self.voice_scroll = 0

    # -- actions (toolbar and keyboard) ------------------------------------------------------------------

    def undo(self) -> None:
        if self.voice_active:                          # D75: the typed text while voice writing is on
            self.voice_selected = []
            if self.page_voice().undo():
                self.log["undo"] += 1
                self.log["voice:undo"] += 1
            return
        target = self.target
        self._cancel_edit("undo")
        if target.history.undo(target.canvas) is not None:
            self.log["undo"] += 1
            self._after_lines_change()
        else:
            self._lines_nothing("undo", "Nothing to undo in Smart Lines. To undo drawing on the page, choose PEN.")

    def redo(self) -> None:
        if self.voice_active:                          # D75
            self.voice_selected = []
            if self.page_voice().redo():
                self.log["redo"] += 1
                self.log["voice:redo"] += 1
            return
        target = self.target
        self._cancel_edit("redo")
        if target.history.redo(target.canvas) is not None:
            self.log["redo"] += 1
            self._after_lines_change()
        else:
            self._lines_nothing("redo", "Nothing to redo in Smart Lines. To redo drawing on the page, choose PEN.")

    def clear(self) -> None:
        """CLEAR: the shown page's ink; with LINES only the unfinished line (completed lines are kept). D75: while voice
        writing is on, the page's typed text (one undo step)."""
        if self.voice_active:
            self._voice_touch()
            if self.page_voice().clear():
                self.log["clear"] += 1
                self.log["voice:clear"] += 1
            self.voice_selected, self.voice_scroll = [], 0
            return
        target = self.target
        self._cancel_edit("clear")
        removed = target.canvas.clear()
        if not self.lines_active:
            self.selection, self.doc_region = [], None
        if removed:
            target.history.record(ReplaceStrokes(removed, [], name="clear"))
            self.log["clear"] += 1
        else:
            self._lines_nothing("clear", "With LINES, CLEAR clears only the line being written, and it is empty. "
                                         "To clear the page, choose PEN.")

    def _lines_nothing(self, action: str, text: str) -> None:
        """D66: UNDO / REDO / CLEAR with LINES act on the Smart Lines only; when there is nothing to act on, say so
        on the wall (in the wall test a CLEAR with LINES did nothing, silently, while the page had ink)."""
        if self.lines_active:
            self.show_notice(text)
            self.log[f"lines:nothing_to_{action}"] += 1

    # -- Smart Lines (D62) ------------------------------------------------------------------------------

    def review_line(self):
        """The line the review bar is about (D64), on the current whiteboard page while LINES is in use: the one
        being edited, else the one picked in the notes area, else the first line waiting for the teacher (a
        suggestion, or not recognised), else the newest one still being read; None: no review bar."""
        if not self.lines_active:
            return None
        sheet = self.sheet()
        for chosen in (self.line_edit, self.review_pick):
            if chosen is not None and chosen["sheet"] is sheet and chosen["line"] in sheet.lines:
                return chosen["line"]
        waiting = next((line for line in sheet.lines if line.status in ("check", "failed")), None)
        if waiting is not None:
            return waiting
        reading = [line for line in sheet.lines if line.status == "recognizing"]
        return reading[-1] if reading else None

    def _lines_enabled(self, name: str, sheet: LineSheet, line) -> bool:
        visible = self.lines_layout.visible
        if name == "lines:complete":
            return bool(sheet.canvas.strokes)
        if name == "lines:up":
            return sheet.first_shown(visible) > 0
        if name == "lines:down":
            return sheet.first_shown(visible) < sheet.max_scroll(visible)
        if name.startswith("lines:row:"):
            return int(name[10:]) < len(sheet.lines) - sheet.first_shown(visible)
        if line is None or self.line_edit is not None:
            return False
        reading, decision, status = line.reading or {}, line.decision or {}, line.status
        if name == "lines:ok":                         # the suggestion (also over a kept ink or another decision)
            return bool(reading.get("ok")) and not (status == "confirmed" and decision["text"] == reading["text"])
        if name == "lines:written":                    # the literal reading, when it is not the suggestion
            return (bool(reading.get("ok")) and reading["written"] != reading["text"]
                    and not (status == "confirmed" and decision["text"] == reading["written"]))
        if name == "lines:ink":
            return status != "ink"
        if name == "lines:retry":
            return self.recognition and status != "recognizing"
        return name == "lines:edit"

    def lines_enabled(self, name: str) -> bool:
        """Whether a Smart Lines button can act now (the renderer greys out the others)."""
        return self._lines_enabled(name, self.sheet(), self.review_line())

    def _lines_hit(self, point):
        """The Smart Lines button under the point: DONE, SCROLL UP / DOWN, a review button (while the review bar is
        shown, not while a line is typed) or a line shown in the notes area."""
        layout, controls, sheet = self.lines_layout, self.lines_controls, self.sheet()
        button = controls.hit(point)
        if button is None and controls.in_bar(point) and self.review_line() is not None:
            return None if self.line_edit is not None else next(
                (b for b in controls.review_buttons if b.contains(point)), None)
        if button is None:
            shown = len(sheet.lines) - sheet.first_shown(layout.visible)
            button = next((b for b in layout.rows[:shown] if b.contains(point)), None)
        return button

    @property
    def lines_controls(self):
        """Where the Smart Lines buttons are now (D65): kept clear of an open panel (the AI panel lies over DONE and
        the review buttons in the layout's own places), else the layout's own. Nothing under a panel can be pressed
        through it (`update_pointer`)."""
        if self.panel is not None and self.panel_layout is not None:
            return self.lines_layout.beside(self.panel_layout.rect)
        if self.board_open:
            return self.lines_layout.beside(self.board_layout.rect)
        return self.lines_layout.controls

    def lines_view(self) -> tuple:
        """What the Smart Lines controls show now, hashable (the renderer caches their drawing by it): the enabled
        buttons, the first line shown, the number of lines and the review bar (None, or the line's number, status,
        main text, note and the text being typed, None when not editing)."""
        sheet, layout, line = self.sheet(), self.lines_layout, self.review_line()
        names = [b.name for b in layout.controls.buttons] + list(REVIEW)
        enabled = frozenset(n for n in names if self._lines_enabled(n, sheet, line))
        bar = None
        if line is not None:
            reading, status = line.reading or {}, line.status
            note = ""
            if status == "recognizing":
                main = "reading the handwriting..."
            elif status == "failed":
                main = f"not recognised - {reading.get('error') or 'nothing readable'}"
            elif status == "ink":
                main = "kept as handwriting"
                note = f"(suggestion: {reading['text']})" if reading.get("ok") else ""
            else:
                main = line.text or ""
                literal = reading.get("written", "") if reading.get("ok") else ""
                note = f"(written: {literal})" if literal and literal != main else ""
            typed = self.line_edit["text"] if self.line_edit is not None else None
            bar = (sheet.lines.index(line) + 1, status, main, note, typed)
        return enabled, sheet.first_shown(layout.visible), len(sheet.lines), bar

    def _lines_action(self, action: str) -> None:
        if not self.lines_active:
            return
        sheet, visible = self.sheet(), self.lines_layout.visible
        if action == "complete":
            self._pause_line_stroke()                  # nothing live is left half in the unfinished line
            if not sheet.canvas.strokes:
                self.show_notice("Nothing written in the writing area yet.")
                self.log["lines:complete_empty"] += 1
                return
            sheet.history.do(CompleteLine(sheet), sheet.canvas)
            sheet.scroll_to_end(visible)
            self.log["lines:complete"] += 1
        elif action in ("up", "down"):
            moved = sheet.scroll_by(-1 if action == "up" else 1, visible)
            self.log[f"lines:{action}" if moved else "lines:scroll_limit"] += 1
        elif action.startswith("row:"):                # D64: this line in the review bar
            k = sheet.first_shown(visible) + int(action[4:])
            if k < len(sheet.lines):
                self.review_pick = {"sheet": sheet, "line": sheet.lines[k]}
                self.log["lines:pick"] += 1
        else:                                          # D64: the review buttons
            line = self.review_line()
            if line is None or not self._lines_enabled(f"lines:{action}", sheet, line):
                self.log["lines:review_disabled"] += 1
                return
            self._pause_line_stroke()
            if action == "edit":
                self._start_edit(sheet, line)
                return
            if action == "retry":                      # the line stays in the bar while it is read again
                sheet.history.do(RetryLine(sheet, line), sheet.canvas)
            else:
                reading = line.reading or {}
                kind, text = {"ok": ("ok", reading.get("text")), "written": ("as_written", reading.get("written")),
                              "ink": ("ink", None)}[action]
                sheet.history.do(ReviewLine(sheet, line, kind, text), sheet.canvas)
                self.review_pick = None
            self.log[f"lines:{action}"] += 1

    def _start_edit(self, sheet: LineSheet, line) -> None:
        if self.asking:
            self.show_notice("Finish the AI question first: Enter sends it, Esc cancels.")
            self.log["lines:edit_refused_ask"] += 1
            return
        reading = line.reading or {}
        text = line.text or reading.get("text") or reading.get("written") or ""
        self.line_edit = {"sheet": sheet, "line": line, "text": text[:TEXT_MAX]}
        self.log["lines:edit"] += 1

    def _edit_key(self, key: int) -> None:
        edit = self.line_edit
        if key in (13, 10):
            text = edit["text"].strip()
            if not text:
                return
            self.line_edit = None
            sheet, line = edit["sheet"], edit["line"]
            if line not in sheet.lines:                # undone meanwhile
                self.log["lines:edit_lost"] += 1
                return
            sheet.history.do(ReviewLine(sheet, line, "edit", text), sheet.canvas)
            self.review_pick = None
            self.log["lines:edit_saved"] += 1
        elif key == 27:
            self._cancel_edit("cancelled")
        elif key == 8:
            edit["text"] = edit["text"][:-1]
        elif 32 <= key < 127 and len(edit["text"]) < TEXT_MAX:
            edit["text"] += chr(key)

    def _cancel_edit(self, why: str) -> None:
        if self.line_edit is not None:
            self.line_edit = None
            self.log[f"lines:edit_{why}"] += 1

    # -- reading the lines (D64) ------------------------------------------------------------------------

    def take_line_jobs(self) -> list[tuple[int, bytes, dict]]:
        """Recognition requests to send now: (request, PNG, context) for every completed line, on any whiteboard
        page, with neither a reading nor the teacher's decision and no request awaited (a new line, a retry, a
        decision undone before its reading came, a line from a board file). Without a reader, such a line is marked
        not recognised instead."""
        jobs = []
        for k, page in enumerate(self.board.pages):
            sheet = page.lines
            for line in [] if sheet is None else sheet.lines:
                if line.reading is not None or line.decision is not None or line.request is not None:
                    continue
                if not self.recognition:
                    line.reading = {"ok": False, "written": "", "text": "", "error": AI_OFF}
                    sheet.changed()
                    continue
                self._request_no += 1
                line.request = self._request_no
                self._requests[line.request] = (sheet, line)
                jobs.append((line.request, png_bytes(strokes_image(line.strokes)), {"page": k + 1, "line": line.id}))
                self.log["lines:requests"] += 1
        return jobs

    def take_line_cancels(self) -> list[int]:
        """Requests sent but no longer wanted (the line was decided or retried meanwhile): the reader may skip them."""
        out = [n for n, (_, line) in self._requests.items() if line.request != n and n not in self._cancelled]
        self._cancelled.update(out)
        return out

    def line_result(self, request: int, reading: dict | None) -> None:
        """A reading from the reader (None: the request was skipped). Used only when its line still awaits exactly
        this request; a line undone meanwhile keeps it (it is shown again on redo)."""
        entry = self._requests.pop(request, None)
        self._cancelled.discard(request)
        if entry is None:
            return
        sheet, line = entry
        if reading is None:
            self.log["lines:skipped"] += 1
        elif line.request != request:                  # after an edit, a decision, a retry or its undo
            self.log["lines:stale_results"] += 1
        else:
            line.reading, line.request = dict(reading), None
            sheet.changed()
            self.log["lines:read" if reading.get("ok") else "lines:not_read"] += 1

    def _after_lines_change(self) -> None:
        """After an undo / redo with LINES: keep the newest completed line in view when lines come and go."""
        if self.lines_active:
            sheet = self.sheet()
            if sheet.scroll > sheet.max_scroll(self.lines_layout.visible):
                sheet.scroll_to_end(self.lines_layout.visible)

    # -- AI panel (D51) ----------------------------------------------------------------------------------

    def ai_source(self) -> str:
        """What an AI action reads now: "document" (the shown page, D61), "voice" (D75 V2: the typed words chosen with
        SELECT, else the page's typed text when nothing is selected), "selection" or "canvas"."""
        if self.view == "doc" and self.reference is not None:
            return "document"
        if self.voice_selected:
            return "voice"
        if any(i in self.canvas.strokes for i in self.selection):
            return "selection"
        text = self.board.page.voice
        return "voice" if text is not None and text.has_content else "canvas"

    def ai_title(self) -> str:
        """The panel's title: what the AI reads, or read for the request shown (the page may have changed since)."""
        panel = self.panel or {}
        if panel.get("title") and panel.get("state") in ("thinking", "answer", "error"):
            return panel["title"]
        source = self.ai_source()
        if source == "document":
            shown = "the image" if self.reference.kind == "image" else self.reference.label()
            return f"AI on part of {shown}" if self.region is not None else f"AI on {shown}"   # D74: a selected part
        if source == "voice":                          # D75 V2
            return "AI on the selected words" if self.voice_selected else "AI on the typed text"
        return "AI on the selection" if source == "selection" else "AI on the whole canvas"

    @property
    def ai_more_shown(self) -> bool:
        """D76: MORE is shown (an answer longer than the panel shows)."""
        p, layout = self.panel, self.panel_layout
        if p is None or p.get("state") != "answer" or layout is None:
            return False
        key = id(p["answer"])
        if getattr(self, "_more_cache", (None,))[0] != key:
            rows = answer_rows(p["answer"], p["action"], p.get("question", ""), layout.text_right - layout.text_left,
                               p.get("source", self.ai_source()) == "document")
            self._more_cache = (key, len(layout.answer_pages(rows)) > 1)
        return self._more_cache[1]

    @property
    def asking(self) -> bool:
        """ASK is waiting for its question from the laptop keyboard (D61)."""
        return self.panel is not None and self.panel["state"] == "asking"

    @property
    def typing(self) -> bool:
        """The laptop keyboard types text now: an ASK question (D61) or a Smart Line being edited (D64)."""
        return self.asking or self.line_edit is not None

    def type_key(self, key: int) -> None:
        """A key typed while `typing` (to the line being edited first): Enter sends the question / saves the line,
        Esc cancels it, Backspace deletes a character."""
        if self.line_edit is not None:
            self._edit_key(key)
            return
        if not self.asking:
            return
        question = self.panel["question"]
        if key in (13, 10):
            if question.strip():
                self._ask_ai("ask", question.strip())
        elif key == 27:
            self.panel = {"state": "menu", "since": self.now}
            self.log["ask_cancelled"] += 1
        elif key == 8:
            self.panel["question"] = question[:-1]
        elif 32 <= key < 127 and len(question) < QUESTION_MAX:
            self.panel["question"] = question + chr(key)

    def _panel_action(self, action: str) -> None:
        if self.panel is None:
            return
        if action == "close":
            self.panel = None
            return
        if action == "more":                           # D76: the next page of a long answer (back to the first)
            if self.ai_more_shown:
                self.panel["page"] = self.panel.get("page", 0) + 1
                self.log["ai_more"] += 1
            return
        if self.panel["state"] == "thinking":
            self.log["ai_refused_busy"] += 1
            return
        if action == "ask":                            # D61: the question comes from the laptop keyboard
            # D75 V2: the typed text is something to ask about too (a page with typed text and no ink)
            if self.ai_source() not in ("document", "voice") and not self.canvas.strokes:
                self.panel = {"state": "error", "since": self.now, "action": action,
                              "message": "Nothing written to read yet."}
            elif self.line_edit is not None:           # D64: one text typed at a time
                self.panel = {"state": "error", "since": self.now, "action": action,
                              "message": "Finish the line being edited first: Enter saves it, Esc cancels."}
            elif not self.asking:
                self.panel = {"state": "asking", "since": self.now, "action": "ask", "question": ""}
            return
        self._ask_ai(action)

    def _ask_ai(self, action: str, question: str = "") -> None:
        source, title = self.ai_source(), self.ai_title()
        context = {"source": source}
        if source == "document":                       # D61: the page itself, as the model's image
            region = None if self.region is None else self.reference.region_fraction(
                self.region, self.board.size, self.toolbar.top)              # D74: only the selected part
            try:
                png = self.reference.ai_png() if region is None else self.reference.ai_png(region)
            except ReferenceError as e:
                self.panel = {"state": "error", "since": self.now, "action": action, "message": str(e)}
                return
            context["page"] = self.view_label()
            if region is not None:
                context["region"] = [round(v, 4) for v in region]
        elif source == "voice":                        # D75 V2: the typed text itself, set clean for the model
            tokens = self.page_voice().tokens
            if self.voice_selected:
                tokens = [tokens[i] for i in self.voice_selected if i < len(tokens)]
            png = png_bytes(voice_text_image(tokens))
            context["words"] = sum(1 for t in tokens if t.strip())
        else:
            image = selection_image(self.canvas, [i for i in self.selection if i in self.canvas.strokes])
            if image is None:
                self.panel = {"state": "error", "since": self.now, "action": action,
                              "message": "Nothing written to read yet."}
                return
            png = png_bytes(image)
        if question:
            context["question"] = question
        self.ai_jobs.append((action, png, context))
        self.panel = {"state": "thinking", "since": self.now, "action": action, "source": source, "title": title,
                      "question": question}
        self.log["ai_requests"] += 1
        self.log[f"ai_on_{source}"] += 1

    def take_ai_jobs(self) -> list[tuple[str, bytes, dict]]:
        jobs, self.ai_jobs = self.ai_jobs, []
        return jobs

    def ai_answer(self, answer) -> None:
        """An answer from the AI worker (an AIAnswer). Shown if the panel is still open and not taking a question."""
        self.log["ai_answers" if answer.ok else "ai_errors"] += 1
        if self.panel is None or self.asking:
            return
        asked = self.panel
        self.panel = {"state": "answer" if answer.ok else "error", "since": self.now, "action": answer.action,
                      "answer": answer, "message": "" if answer.ok else answer.error,
                      "source": asked.get("source"), "title": asked.get("title"), "question": asked.get("question", "")}
