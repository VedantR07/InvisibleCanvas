"""Renders the canvas for the projector: strokes, the stroke being drawn, the selection, the toolbar (with the
hold-to-press progress) and the cursor, whose look shows the mode and tool (brain.md §9.10, D44, D46). The
committed strokes are cached and redrawn only when the canvas changes.

D51: the SELECT loop while it is drawn, a halo around the selected strokes, and the AI panel (its buttons with
the hold-to-press progress, then "thinking", the answer or an error). D61: the panel's title says what the AI reads
(the selection, the whole canvas, or the shown document page); ASK shows the question as it is typed.

D50: with a light polygon (display.handlight) the hand is painted plain white last, so no ink, text or cursor
falls on it, and the cursor becomes a ring around the fingertip, wider than the light's margin, so it lands on
the wall; a toolbar dwell fills the ring as a progress arc (the button itself is often under the hand).

D56: while the hand points but nothing can be drawn (the stroke started on, or ran into, the toolbar or the AI
panel: `controller.blocked`), the cursor is a grey ring with a slash, and over the canvas a hint at the top
says how to draw again. The hint is kept away from the hand: projected text on the hand hinders tracking (R34).

D59 / D60: the board panel (page buttons, grey when they cannot act) or else the page label at the top left; a
document page under the ink (`controller.background`; the strokes cache is kept per page and background); messages
on the wall (`controller.notice`).

D62: Smart Lines. The notes area, the writing zone and the unfinished line come with `controller.background` (drawn
by `canvas/lines.py`, cached until they change); while LINES is in use the renderer adds DONE, SCROLL UP / DOWN and
(D64) the review bar, typeset with Pillow only when what they show changes and copied over each frame, with their
hold-to-press progress (grey when they cannot act). A stroke refused outside the zone gets its own hint. D65: where
an open panel would cover them, they are drawn beside it (`controller.lines_controls`).
"""

from __future__ import annotations

import cv2
import numpy as np

from ..display.handlight import paint
from ..interaction.engine import DRAW, HOVER
from .lines import render_controls
from .model import Canvas, Stroke
from .panel import clip_lines, wrap
from .toolbar import COLOURS, WIDTHS, Toolbar

BACKGROUND = 255
TOOLBAR_BG = (232, 232, 232)
HIGHLIGHT = (200, 60, 200)            # magenta: selection, pinch cursor, current tool
ERASER = (0, 140, 255)                # orange
SELECTION_HALO = (245, 200, 245)      # light magenta behind selected strokes
PANEL_TEXT, PANEL_MUTED, PANEL_ERROR = (30, 30, 30), (110, 110, 110), (40, 40, 200)
FONT = cv2.FONT_HERSHEY_SIMPLEX
RING_RADIUS = 38                      # D50 ring cursor: just outside the light around the fingertip (D70: a
                                      # finger's half-width ~18 px + the 8-px margin, so the ring is kept)
BLOCKED = (90, 90, 90)                # D56: the "not drawing" cursor
BLOCKED_HINT = "Not drawing: open your hand, then point to draw"
ZONE_HINT = "Not drawing here: move your fingertip into the writing area to write"  # D62, D66
ASK_PROMPT = "Type your question on the laptop keyboard. Enter sends it, Esc cancels."   # D61
PAGE_LINES = 2                        # D61: lines of "what the AI read" shown for a document page


def draw_stroke(img: np.ndarray, stroke: Stroke, colour=None, extra: int = 0) -> None:
    a = np.round(stroke.array()).astype(np.int32)
    colour = colour or stroke.color
    thickness = max(int(round(stroke.width)) + extra, 1)
    if len(a) == 1:
        cv2.circle(img, tuple(int(v) for v in a[0]), max(thickness // 2, 1), colour, -1, cv2.LINE_AA)
    else:
        cv2.polylines(img, [a], False, colour, thickness, cv2.LINE_AA)


class CanvasRenderer:
    def __init__(self, size: tuple[int, int], background: int = BACKGROUND):
        self.size = (int(size[0]), int(size[1]))
        self.background = background
        self._cache: np.ndarray | None = None
        self._canvas: Canvas | None = None             # D59: the cache is for one canvas (page) at one version
        self._under: np.ndarray | None = None          # D60: ... over one background (a document page) or none
        self._version = -1
        self.redraws = 0

    def _strokes(self, canvas: Canvas, under: np.ndarray | None = None) -> np.ndarray:
        if (self._cache is None or canvas is not self._canvas or canvas.version != self._version
                or under is not self._under):
            w, h = self.size
            img = under.copy() if under is not None else np.full((h, w, 3), self.background, dtype=np.uint8)
            for s in canvas.strokes.values():
                draw_stroke(img, s)
            self._cache, self._canvas, self._version, self._under = img, canvas, canvas.version, under
            self.redraws += 1
        return self._cache

    def render(self, canvas: Canvas, controller, toolbar: Toolbar, *, mode: str, cursor, status: str = "",
               light: np.ndarray | None = None) -> np.ndarray:
        img = self._strokes(canvas, getattr(controller, "background", None)).copy()     # D60: a document page under it
        if controller.selected is not None and controller.selected in canvas.strokes:
            s = canvas.strokes[controller.selected]
            x0, y0, x1, y1 = (int(round(v)) for v in s.bounds())
            cv2.rectangle(img, (x0 - 6, y0 - 6), (x1 + 6, y1 + 6), HIGHLIGHT, 2, cv2.LINE_AA)
        for sid in getattr(controller, "selection", ()):               # D51: halo, then the ink on top
            if sid in canvas.strokes:
                draw_stroke(img, canvas.strokes[sid], SELECTION_HALO, extra=12)
                draw_stroke(img, canvas.strokes[sid])
        if controller.active is not None and controller.active.points:
            draw_stroke(img, controller.active)
        loop = getattr(controller, "loop", None)
        if loop is not None and len(loop) >= 2:
            cv2.polylines(img, [np.round(np.asarray(loop)).astype(np.int32)], False, HIGHLIGHT, 2, cv2.LINE_AA)
        self._toolbar(img, toolbar, controller)
        if getattr(controller, "lines_active", False):                  # D62: under the panels
            self._lines_controls(img, controller)
        if getattr(controller, "panel", None) is not None and controller.panel_layout is not None:
            self._panel(img, controller)
        board = getattr(controller, "board", None)
        if getattr(controller, "board_open", False):
            self._board_panel(img, controller)
        elif board is not None:                        # D59 / D60: what is shown, small, top left
            cv2.putText(img, controller.view_label(), (12, 28), FONT, 0.6, PANEL_MUTED, 2, cv2.LINE_AA)
        notice = getattr(controller, "notice", None)
        if notice is not None and controller.now < notice["until"]:    # D60: e.g. a file that could not be opened
            self._notice(img, notice["text"])
        if status:
            cv2.putText(img, status, (12, 26), FONT, 0.6, (120, 120, 120), 1, cv2.LINE_AA)
        blocked = mode == DRAW and getattr(controller, "blocked", None) is not None
        if blocked and cursor is not None and not toolbar.in_band(cursor):     # not while pressing a button
            self._hint(img, controller)
        if cursor is not None:
            if blocked:
                self._blocked_cursor(img, cursor, RING_RADIUS if light is not None else 16)
                if light is not None:
                    self._dwell_arc(img, cursor, controller)
            elif light is None:
                self._cursor(img, mode, cursor, controller)
            else:
                self._ring_cursor(img, mode, cursor, controller)
        paint(img, light)
        return img

    def _toolbar(self, img: np.ndarray, toolbar: Toolbar, controller) -> None:
        w, _ = self.size
        cv2.rectangle(img, (0, toolbar.top), (w - 1, self.size[1] - 1), TOOLBAR_BG, -1)
        for b in toolbar.buttons:
            x0, y0, x1, y1 = b.rect
            cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
            cv2.rectangle(img, (x0, y0), (x1 - 1, y1 - 1), (255, 255, 255), -1)
            current = ((b.kind == "tool" and controller.tool == b.name)
                       or (b.kind == "colour" and controller.colour == b.name and controller.tool == "pen")
                       or (b.kind == "width" and controller.width == b.name)
                       or (b.kind == "board" and getattr(controller, "board_open", False)))
            cv2.rectangle(img, (x0, y0), (x1 - 1, y1 - 1), HIGHLIGHT if current else (160, 160, 160), 4 if current else 1)
            if b.kind == "colour":
                cv2.circle(img, (cx, cy), 18, COLOURS[b.name], -1, cv2.LINE_AA)
            elif b.kind == "width":
                t = int(WIDTHS[b.name])
                cv2.line(img, (x0 + 22, cy), (x1 - 22, cy), COLOURS[controller.colour], t, cv2.LINE_AA)
            else:
                label, scale = b.name.upper(), 0.5
                (tw, th), _ = cv2.getTextSize(label, FONT, scale, 2)
                if tw > x1 - x0 - 4:                                    # D62: narrower buttons
                    scale *= (x1 - x0 - 4) / tw
                    (tw, th), _ = cv2.getTextSize(label, FONT, scale, 2)
                cv2.putText(img, label, (cx - tw // 2, cy + th // 2), FONT, scale, (60, 60, 60), 2, cv2.LINE_AA)
            progress = controller.dwell_progress
            if progress is not None and progress[0] == b.name:          # hold-to-press feedback
                fill = int((x1 - x0) * progress[1])
                cv2.rectangle(img, (x0, y1 - 9), (x0 + fill, y1 - 1), (40, 40, 215) if b.name == "clear" else HIGHLIGHT, -1)

    def _panel(self, img: np.ndarray, controller) -> None:
        layout, panel = controller.panel_layout, controller.panel
        x0, y0, x1, y1 = layout.rect
        cv2.rectangle(img, (x0, y0), (x1, y1), (250, 250, 250), -1)
        cv2.rectangle(img, (x0, y0), (x1, y1), (150, 150, 150), 2)
        cv2.putText(img, controller.ai_title(), (x0 + 14, y0 + 32), FONT, 0.7, PANEL_TEXT, 2, cv2.LINE_AA)   # D61
        progress = controller.dwell_progress
        for b in layout.buttons:
            bx0, by0, bx1, by1 = b.rect
            current = b.name == f"ai:{panel.get('action')}"
            cv2.rectangle(img, (bx0, by0), (bx1 - 1, by1 - 1), (255, 255, 255), -1)
            cv2.rectangle(img, (bx0, by0), (bx1 - 1, by1 - 1), HIGHLIGHT if current else (160, 160, 160),
                          3 if current else 1)
            label = b.name[3:].upper()
            (tw, th), _ = cv2.getTextSize(label, FONT, 0.55, 2)
            cv2.putText(img, label, ((bx0 + bx1 - tw) // 2, (by0 + by1 + th) // 2), FONT, 0.55, (60, 60, 60), 2,
                        cv2.LINE_AA)
            if progress is not None and progress[0] == b.name:
                cv2.rectangle(img, (bx0, by1 - 9), (bx0 + int((bx1 - bx0) * progress[1]), by1 - 1), HIGHLIGHT, -1)
        left, right, y = layout.text_left, layout.text_right, layout.text_top
        width = right - left
        state = panel["state"]
        rows: list[tuple[str, float, tuple, int]] = []
        document = panel.get("source", controller.ai_source()) == "document"
        if state == "menu":
            text = "Choose what the AI should do with this page." if document else "Choose what the AI should do with it."
            rows = [(line, 0.6, PANEL_MUTED, 1) for line in wrap(text, width, 0.6)]
        elif state == "asking":                                         # D61: the question as it is typed
            rows = [(line, 0.55, PANEL_MUTED, 1) for line in wrap(ASK_PROMPT, width, 0.55)]
            rows += [("", 0.3, PANEL_TEXT, 1)]
            rows += [(line, 0.62, PANEL_TEXT, 2) for line in wrap(panel["question"] + "_", width, 0.62, 2)]
        elif state == "thinking":
            seconds = max(controller.now - panel.get("since", controller.now), 0.0)
            rows = [(f"The AI is reading... {seconds:.0f} s", 0.65, PANEL_TEXT, 2)]
        elif state == "error":
            rows = [(line, 0.6, PANEL_ERROR, 2) for line in wrap(panel.get("message", "Error."), width, 0.6, 2)]
        else:
            answer = panel["answer"]
            rows = [("PAGE:" if document else "READ:", 0.55, PANEL_TEXT, 2)]   # what the AI read, as large as the answer
            read = wrap(answer.transcription or "-", width, 0.62)
            if document:                       # D61: the local model copied the page out in 5 of 9 answers
                read = clip_lines(read, PAGE_LINES, width, 0.62)   # (2026-10-27): the answer stays in view
            rows += [(line, 0.62, PANEL_TEXT, 1) for line in read]
            header = panel["action"].upper() + ":"
            if getattr(answer, "readable", None) and answer.topic:              # D54: EXPLORE names its topic
                header += " " + answer.topic.upper()
            if panel.get("question"):                                           # D61: ASK shows its question
                header += " " + panel["question"]
            rows += [("", 0.3, PANEL_TEXT, 1)] + [(line, 0.55, PANEL_TEXT, 2) for line in wrap(header, width, 0.55, 2)]
            rows += [(line, 0.62, PANEL_TEXT, 1) for line in wrap(answer.result, width, 0.62)]
        for k, (line, scale, colour, thick) in enumerate(rows):
            step = int(34 * scale) + 6
            if y + step > y1 - 8:                                   # no room left: mark the cut
                cv2.putText(img, "...", (left, y1 - 12), FONT, 0.6, PANEL_MUTED, 2, cv2.LINE_AA)
                break
            y += step
            cv2.putText(img, line, (left, y), FONT, scale, colour, thick, cv2.LINE_AA)

    def _board_panel(self, img: np.ndarray, controller) -> None:
        """D59: the page label and the page buttons; a button that cannot act now (first / last page) is grey."""
        layout = controller.board_layout
        x0, y0, x1, y1 = layout.rect
        cv2.rectangle(img, (x0, y0), (x1, y1), (250, 250, 250), -1)
        cv2.rectangle(img, (x0, y0), (x1, y1), (150, 150, 150), 2)
        doc = controller.view == "doc" and controller.reference is not None
        title = controller.reference.label() if doc else controller.board.label()
        cv2.putText(img, title, (layout.text_left, layout.text_baseline), FONT, 0.7, PANEL_TEXT, 2, cv2.LINE_AA)
        progress = controller.dwell_progress
        for b in layout.buttons:
            bx0, by0, bx1, by1 = b.rect
            enabled = controller.board_enabled(b.name)
            cv2.rectangle(img, (bx0, by0), (bx1 - 1, by1 - 1), (255, 255, 255), -1)
            cv2.rectangle(img, (bx0, by0), (bx1 - 1, by1 - 1), (160, 160, 160) if enabled else (215, 215, 215), 1)
            label = controller.board_label(b.name)
            (tw, th), _ = cv2.getTextSize(label, FONT, 0.55, 2)
            cv2.putText(img, label, ((bx0 + bx1 - tw) // 2, (by0 + by1 + th) // 2), FONT, 0.55,
                        (60, 60, 60) if enabled else (190, 190, 190), 2, cv2.LINE_AA)
            if enabled and progress is not None and progress[0] == b.name:
                cv2.rectangle(img, (bx0, by1 - 9), (bx0 + int((bx1 - bx0) * progress[1]), by1 - 1), HIGHLIGHT, -1)

    def _lines_controls(self, img: np.ndarray, controller) -> None:
        """D62 / D64: DONE, the scroll track with SCROLL UP / DOWN and the review bar, typeset once and cached
        (`canvas/lines.py`), copied over the frame; then the hold-to-press progress of the button held."""
        controls = controller.lines_controls                            # D65: beside an open panel
        for x, y, patch in render_controls(controller.lines_layout, controller.lines_view(), controls):
            img[y:y + patch.shape[0], x:x + patch.shape[1]] = patch
        progress = controller.dwell_progress
        if progress is not None and progress[0].startswith("lines:") and controller.lines_enabled(progress[0]):
            x0, y0, x1, y1 = controls.button(progress[0]).rect
            cv2.rectangle(img, (x0 + 4, y1 - 7), (x0 + 4 + int((x1 - x0 - 8) * progress[1]), y1 - 3), HIGHLIGHT, -1)

    def _notice(self, img: np.ndarray, text: str) -> None:
        """D60: a message box at the top centre (wrapped to two lines at most), framed red."""
        lines = wrap(text, 760, 0.65, 2)[:2]
        sizes = [cv2.getTextSize(line, FONT, 0.65, 2)[0] for line in lines]
        w = max(sz[0] for sz in sizes) + 32
        step = max(sz[1] for sz in sizes) + 14
        x0, y0 = (self.size[0] - w) // 2, 60
        cv2.rectangle(img, (x0, y0), (x0 + w, y0 + step * len(lines) + 16), (255, 255, 255), -1)
        cv2.rectangle(img, (x0, y0), (x0 + w, y0 + step * len(lines) + 16), PANEL_ERROR, 2)
        for k, line in enumerate(lines):
            cv2.putText(img, line, (x0 + 16, y0 + 8 + step * (k + 1) - 4), FONT, 0.65, (30, 30, 30), 2, cv2.LINE_AA)

    def _hint(self, img: np.ndarray, controller) -> None:
        """D56: why nothing is drawn, at the top of the canvas (left of the AI panel when it is open)."""
        right = self.size[0]
        if getattr(controller, "panel", None) is not None and controller.panel_layout is not None:
            right = controller.panel_layout.rect[0]
        hint = ZONE_HINT if getattr(controller, "blocked", None) == "zone" else BLOCKED_HINT
        scale = 0.7
        (tw, th), _ = cv2.getTextSize(hint, FONT, scale, 2)
        if tw + 40 > right:
            scale *= (right - 40) / (tw + 40)
            (tw, th), _ = cv2.getTextSize(hint, FONT, scale, 2)
        x0 = max((right - tw) // 2 - 16, 0)
        cv2.rectangle(img, (x0, 8), (x0 + tw + 32, 8 + th + 24), (255, 255, 255), -1)
        cv2.rectangle(img, (x0, 8), (x0 + tw + 32, 8 + th + 24), BLOCKED, 2)
        cv2.putText(img, hint, (x0 + 16, 8 + 12 + th), FONT, scale, (40, 40, 40), 2, cv2.LINE_AA)

    @staticmethod
    def _blocked_cursor(img: np.ndarray, cursor, radius: int) -> None:
        """D56: a ring with a slash at the fingertip: pointing, but nothing is drawn."""
        x, y = int(round(cursor[0])), int(round(cursor[1]))
        d = int(round(radius * 0.7071))
        cv2.circle(img, (x, y), radius, BLOCKED, 3, cv2.LINE_AA)
        cv2.line(img, (x - d, y + d), (x + d, y - d), BLOCKED, 3, cv2.LINE_AA)

    def _cursor(self, img: np.ndarray, mode: str, cursor, controller) -> None:
        x, y = int(round(cursor[0])), int(round(cursor[1]))
        tool = controller.tool
        if tool == "eraser":                    # the eraser shows its real size, thin when hovering
            cv2.circle(img, (x, y), max(int(round(controller.eraser_radius)), 4), ERASER, 3 if mode == DRAW else 1,
                       cv2.LINE_AA)
        elif tool == "move":
            colour = HIGHLIGHT if mode == DRAW else (110, 110, 110)
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                cv2.line(img, (x + 6 * dx, y + 6 * dy), (x + 20 * dx, y + 20 * dy), colour, 3, cv2.LINE_AA)
        elif mode == DRAW:
            r = int(WIDTHS[controller.width] / 2) + 4
            cv2.circle(img, (x, y), r + 2, (255, 255, 255), -1, cv2.LINE_AA)
            cv2.circle(img, (x, y), r, COLOURS[controller.colour], -1, cv2.LINE_AA)
        if mode == HOVER and tool == "pen":
            cv2.circle(img, (x, y), 12, (110, 110, 110), 2, cv2.LINE_AA)

    def _ring_cursor(self, img: np.ndarray, mode: str, cursor, controller) -> None:
        x, y = int(round(cursor[0])), int(round(cursor[1]))
        tool = controller.tool
        colour = ERASER if tool == "eraser" else HIGHLIGHT if tool == "move" else COLOURS[controller.colour]
        if mode == DRAW:
            cv2.circle(img, (x, y), RING_RADIUS, colour, 4, cv2.LINE_AA)
        else:
            cv2.circle(img, (x, y), RING_RADIUS, (110, 110, 110), 2, cv2.LINE_AA)
            cv2.circle(img, (x, y), RING_RADIUS + 4, colour, 2, cv2.LINE_AA)       # the tool's colour
        self._dwell_arc(img, cursor, controller)

    @staticmethod
    def _dwell_arc(img: np.ndarray, cursor, controller) -> None:
        x, y = int(round(cursor[0])), int(round(cursor[1]))
        progress = controller.dwell_progress
        if progress is not None and progress[1] > 0:                          # hold-to-press on the ring
            cv2.ellipse(img, (x, y), (RING_RADIUS, RING_RADIUS), -90, 0, 360 * progress[1],
                        (40, 40, 215) if progress[0] == "clear" else HIGHLIGHT, 7, cv2.LINE_AA)
