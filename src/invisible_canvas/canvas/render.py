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

D71 (the user's mockup): the toolbar's rounded buttons with Segoe UI Semibold labels, the colours and the widths each
in a rounded group, the tool, colour and width in use outlined purple; the band is typeset once per state and copied
over each frame. The page label in a rounded pill. The buttons' places are unchanged.

D72: a zoomed document page (`controller.page_view`): its annotations, the stroke being drawn, the selection and the
SELECT loop are kept in the page's own coordinates and drawn at the zoom, inside the page's window only; the zoom bar
(typeset once per state, in the D71 look) with its hold-to-press progress, and a slim scroll bar along each side the
page goes beyond the window. A page shown whole is drawn exactly as before.

D74: the part of a document page chosen with SELECT, framed in magenta (at the zoom, inside the page's window).
"""

from __future__ import annotations

import cv2
import numpy as np

from ..display.handlight import paint
from ..interaction.engine import DRAW, HOVER
from . import text as typeset
from .lines import EDGE, EDGE_OFF, INK, LABEL, LABEL_OFF, PANEL_EDGE, PANEL_FILL, THUMB, TRACK, render_controls
from .model import Canvas, Stroke
from .panel import clip_lines, wrap
from .toolbar import COLOURS, WIDTHS, Toolbar

BACKGROUND = 255
TOOLBAR_BG = (242, 238, 235)          # D71: a light grey-blue band
HIGHLIGHT = (200, 60, 200)            # magenta: selection, pinch cursor, hold-to-press progress
TOOL_SELECTED = (190, 50, 105)        # D71: purple (RGB 105, 50, 190; the wall check: darker and 4 px): the tool,
                                      # colour and width in use
TOOL_EDGE, TOOL_LABEL = (200, 192, 184), (80, 50, 30)        # D71: a button's edge, its label (navy)
GROUP_FILL, GROUP_EDGE = (250, 247, 245), (215, 208, 200)    # D71: behind the colours, behind the widths
LABEL_FONT, LABEL_SIZE = "seguisb.ttf", 17                   # the toolbar's labels (smaller if one does not fit)
PAGE_FILL, PAGE_TEXT = (236, 232, 228), (60, 38, 22)         # D71: the page label's pill (text navy, 20 px)
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
# D75: the voice panel's states (label, colour BGR)
VOICE_STATES = {"off": ("Starting...", (110, 110, 110)), "loading": ("Loading speech...", (110, 110, 110)),
                "listening": ("Listening", (30, 120, 30)), "hearing": ("Hearing you...", (40, 40, 200)),
                "writing": ("Writing...", (160, 60, 10)), "paused": ("Paused", (110, 110, 110)),
                "unavailable": ("Microphone unavailable", (40, 40, 200)), "error": ("Error", (40, 40, 200))}
VOICE_TRACK, VOICE_LEVEL = (225, 220, 216), (40, 150, 40)
VOICE_TEXT = (80, 60, 50)              # the microphone line and reasons (wall test 1: the grey was faint)
PAGE_LINES = 2                        # D61: lines of "what the AI read" shown for a document page


def draw_stroke(img: np.ndarray, stroke: Stroke, colour=None, extra: int = 0, view=None, shift=(0, 0)) -> None:
    """A stroke; with a `view` (D72) one in a zoomed document page's coordinates, drawn at the zoom on an image whose
    top-left is the wall point `shift`."""
    a, width = stroke.array(), stroke.width
    if view is not None:
        a, width = view.to_wall(a) - shift, width * view.scale
    a = np.round(a).astype(np.int32)
    colour = colour or stroke.color
    thickness = max(int(round(width)) + extra, 1)
    if len(a) == 1:
        cv2.circle(img, tuple(int(v) for v in a[0]), max(thickness // 2, 1), colour, -1, cv2.LINE_AA)
    else:
        cv2.polylines(img, [a], False, colour, thickness, cv2.LINE_AA)


def ink_area(img: np.ndarray, view) -> tuple[np.ndarray, tuple[int, int]]:
    """Where a page's ink is drawn and the wall point of its top-left: the whole frame, or (D72) a zoomed document
    page's window (ink beyond it is not seen; the white margin stays white for the setup watch, D58)."""
    if view is None:
        return img, (0, 0)
    x0, y0, x1, y1 = view.window
    return img[y0:y1, x0:x1], (x0, y0)


class CanvasRenderer:
    def __init__(self, size: tuple[int, int], background: int = BACKGROUND):
        self.size = (int(size[0]), int(size[1]))
        self.background = background
        self._cache: np.ndarray | None = None
        self._canvas: Canvas | None = None             # D59: the cache is for one canvas (page) at one version
        self._under: np.ndarray | None = None          # D60: ... over one background (a document page) or none
        self._version = -1
        self.redraws = 0
        self._band: tuple | None = None                # D71: (state, the toolbar band typeset)
        self._label: tuple | None = None               # D71: (label, pill image, its shape)
        self._view = None                              # D72: the cache's page view (None: wall coordinates)
        self._zoom: tuple | None = None                # D72: (state, the zoom bar typeset, its shape)
        self._voice: tuple | None = None               # D75: (state, the voice panel typeset, its shape)

    def _strokes(self, canvas: Canvas, under: np.ndarray | None = None, view=None) -> np.ndarray:
        if (self._cache is None or canvas is not self._canvas or canvas.version != self._version
                or under is not self._under or view != self._view):
            w, h = self.size
            img = under.copy() if under is not None else np.full((h, w, 3), self.background, dtype=np.uint8)
            ink, shift = ink_area(img, view)
            for s in canvas.strokes.values():
                draw_stroke(ink, s, view=view, shift=shift)
            self._cache, self._canvas, self._version, self._under = img, canvas, canvas.version, under
            self._view = view
            self.redraws += 1
        return self._cache

    def render(self, canvas: Canvas, controller, toolbar: Toolbar, *, mode: str, cursor, status: str = "",
               light: np.ndarray | None = None) -> np.ndarray:
        view = getattr(controller, "page_view", None)                   # D72: a zoomed document page
        img = self._strokes(canvas, getattr(controller, "background", None), view).copy()   # D60: a document page
        ink, shift = ink_area(img, view)
        if controller.selected is not None and controller.selected in canvas.strokes:
            s = canvas.strokes[controller.selected]
            x0, y0, x1, y1 = s.bounds()
            if view is not None:
                (x0, y0), (x1, y1) = view.to_wall([(x0, y0), (x1, y1)]) - shift
            x0, y0, x1, y1 = (int(round(v)) for v in (x0, y0, x1, y1))
            cv2.rectangle(ink, (x0 - 6, y0 - 6), (x1 + 6, y1 + 6), HIGHLIGHT, 2, cv2.LINE_AA)
        for sid in getattr(controller, "selection", ()):               # D51: halo, then the ink on top
            if sid in canvas.strokes:
                draw_stroke(ink, canvas.strokes[sid], SELECTION_HALO, extra=12, view=view, shift=shift)
                draw_stroke(ink, canvas.strokes[sid], view=view, shift=shift)
        if controller.active is not None and controller.active.points:
            draw_stroke(ink, controller.active, view=view, shift=shift)
        region = getattr(controller, "region", None)
        if region is not None:                                          # D74: the part of the page the AI reads
            corners = np.asarray([region[:2], region[2:]], dtype=np.float64)
            if view is not None:
                corners = view.to_wall(corners) - shift
            (x0, y0), (x1, y1) = np.round(corners).astype(int)
            cv2.rectangle(ink, (int(x0) - 4, int(y0) - 4), (int(x1) + 4, int(y1) + 4), HIGHLIGHT, 3, cv2.LINE_AA)
        loop = getattr(controller, "loop", None)
        if loop is not None and len(loop) >= 2:
            points = np.asarray(loop) if view is None else view.to_wall(loop) - shift
            cv2.polylines(ink, [np.round(points).astype(np.int32)], False, HIGHLIGHT, 2, cv2.LINE_AA)
        self._toolbar(img, toolbar, controller)
        if getattr(controller, "lines_active", False):                  # D62: under the panels
            self._lines_controls(img, controller)
        bar = getattr(controller, "zoom_bar", None)
        if bar is not None:                                             # D72: under the panels
            self._zoom_bar(img, controller, bar, view)
        if getattr(controller, "voice_open", False):                    # D75
            self._voice_panel(img, controller)
        if getattr(controller, "panel", None) is not None and controller.panel_layout is not None:
            self._panel(img, controller)
        board = getattr(controller, "board", None)
        if getattr(controller, "board_open", False):
            self._board_panel(img, controller)
        elif board is not None:                        # D59 / D60: what is shown, small, top left
            self._view_label(img, controller.view_label())
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
        """The band typeset once per state (D71) and copied over the frame; then the hold-to-press progress."""
        key = (id(toolbar), controller.tool, controller.colour, controller.width,
               getattr(controller, "board_open", False), getattr(controller, "voice_open", False))   # D75
        if self._band is None or self._band[0] != key:
            self._band = (key, self._toolbar_band(toolbar, controller))
        band = self._band[1]
        img[toolbar.top:toolbar.top + band.shape[0]] = band
        progress = controller.dwell_progress
        b = None if progress is None else next((b for b in toolbar.buttons if b.name == progress[0]), None)
        if b is not None:                                               # hold-to-press feedback
            x0, y0, x1, y1 = b.rect
            fill = int((x1 - x0 - 8) * progress[1])
            cv2.rectangle(img, (x0 + 4, y1 - 9), (x0 + 4 + fill, y1 - 4), (40, 40, 215) if b.name == "clear" else
                          HIGHLIGHT, -1)

    def _toolbar_band(self, toolbar: Toolbar, controller) -> np.ndarray:
        """D71: the toolbar band: rounded buttons, the colours and the widths each in a rounded group, the tool,
        colour and width in use (and PAGES while its panel is open) outlined purple, the labels in Segoe UI
        Semibold (one size for all, the largest that fits every button)."""
        w, h = self.size
        top = toolbar.top
        band = np.full((h - top, w, 3), TOOLBAR_BG, np.uint8)
        ops = []
        for kind in ("colour", "width"):
            group = [b.rect for b in toolbar.buttons if b.kind == kind]
            ops.append(("rrect", (group[0][0] - 6, group[0][1] - top - 5, group[-1][2] + 5, group[-1][3] - top + 4),
                        14, GROUP_FILL, GROUP_EDGE))
        labels = [b.name.upper() for b in toolbar.buttons if b.kind not in ("colour", "width")]
        size, room = LABEL_SIZE, toolbar.button_w - 8             # 61-px buttons: 15 px (ERASER 52 px wide)
        while size > 10 and max(typeset.width(t, typeset.font(LABEL_FONT, size)) for t in labels) > room:
            size -= 1
        font = typeset.font(LABEL_FONT, size)
        for b in toolbar.buttons:
            x0, y0, x1, y1 = b.rect
            y0, y1 = y0 - top, y1 - top
            current = ((b.kind == "tool" and controller.tool == b.name)
                       or (b.kind == "colour" and controller.colour == b.name and controller.tool == "pen")
                       or (b.kind == "width" and controller.width == b.name)
                       or (b.kind == "board" and getattr(controller, "board_open", False))
                       or (b.kind == "voice" and getattr(controller, "voice_open", False)))     # D75
            ops.append(("rrect", (x0, y0, x1 - 1, y1 - 1), 10, (255, 255, 255), TOOL_SELECTED if current else TOOL_EDGE,
                        4 if current else 2))
            if b.kind not in ("colour", "width"):
                ops.append(("text", ((x0 + x1) / 2, (y0 + y1) / 2), b.name.upper(), font, TOOL_LABEL, "mm"))
        typeset.draw(band, ops)
        for b in toolbar.buttons:
            x0, y0, x1, y1 = b.rect
            cx, cy = (x0 + x1) // 2, (y0 + y1) // 2 - top
            if b.kind == "colour":
                cv2.circle(band, (cx, cy), 18, COLOURS[b.name], -1, cv2.LINE_AA)
            elif b.kind == "width":
                cv2.line(band, (x0 + 22, cy), (x1 - 22, cy), COLOURS[controller.colour], int(WIDTHS[b.name]),
                         cv2.LINE_AA)
        return band

    def _view_label(self, img: np.ndarray, label: str) -> None:
        """D71: what is shown ('Page 1 of 1') in a rounded pill at the top left, typeset once per label."""
        if self._label is None or self._label[0] != label:
            f = typeset.font(LABEL_FONT, 20)
            w = int(typeset.width(label, f)) + 28
            patch, shape = np.full((36, w, 3), 255, np.uint8), np.zeros((36, w, 3), np.uint8)
            typeset.draw(patch, [("rrect", (0, 0, w - 1, 35), 12, PAGE_FILL, None),
                                 ("text", (14, 18), label, f, PAGE_TEXT, "lm")])
            typeset.draw(shape, [("rrect", (0, 0, w - 1, 35), 12, (255, 255, 255), None)])
            self._label = (label, patch, shape[:, :, 0] > 127)
        _, patch, shape = self._label
        region = img[8:8 + patch.shape[0], 12:12 + patch.shape[1]]
        h, w = region.shape[:2]
        region[shape[:h, :w]] = patch[:h, :w][shape[:h, :w]]

    def _zoom_bar(self, img: np.ndarray, controller, bar, view) -> None:
        """D72: the zoom bar, typeset once per state and copied over the frame in its rounded shape, the hold-to-press
        progress; while zoomed, the scroll bars."""
        if view is not None:
            self._scroll_bars(img, view, bar)
        state = (bar.rect, controller.zoom_label(), tuple(controller.zoom_enabled(b.name) for b in bar.buttons))
        if self._zoom is None or self._zoom[0] != state:
            self._zoom = (state, *self._zoom_patch(bar, state[1], state[2]))
        _, patch, shape = self._zoom
        x0, y0 = bar.rect[:2]
        region = img[y0:y0 + patch.shape[0], x0:x0 + patch.shape[1]]
        region[shape] = patch[shape]
        progress = controller.dwell_progress
        if progress is not None and progress[0].startswith("zoom:") and controller.zoom_enabled(progress[0]):
            bx0, by0, bx1, by1 = bar.button(progress[0]).rect
            cv2.rectangle(img, (bx0 + 4, by1 - 7), (bx0 + 4 + int((bx1 - bx0 - 8) * progress[1]), by1 - 3),
                          HIGHLIGHT, -1)

    @staticmethod
    def _zoom_patch(bar, label: str, enabled: tuple) -> tuple[np.ndarray, np.ndarray]:
        """The zoom bar (a magnifier, -, the zoom level, +, FIT) and its rounded shape, in the bar's own px."""
        x0, y0, x1, y1 = bar.rect
        w, h = x1 - x0, y1 - y0
        patch, shape = np.full((h, w, 3), 255, np.uint8), np.zeros((h, w, 3), np.uint8)

        def local(r):
            return r[0] - x0, r[1] - y0, r[2] - x0, r[3] - y0

        on = dict(zip((b.name for b in bar.buttons), enabled))
        ops = [("rrect", (0, 0, w - 1, h - 1), 14, PANEL_FILL, PANEL_EDGE, 2)]
        for b in bar.buttons:
            ops.append(("rrect", local(b.rect), 10, (255, 255, 255), EDGE if on[b.name] else EDGE_OFF, 2))
        lx0, ly0, lx1, ly1 = local(bar.level)
        ops.append(("text", ((lx0 + lx1) // 2, (ly0 + ly1) // 2), label, typeset.font(LABEL_FONT, 21), INK, "mm"))
        fx0, fy0, fx1, fy1 = local(bar.button("zoom:fit").rect)
        ops.append(("text", ((fx0 + fx1) // 2, (fy0 + fy1) // 2), "FIT", typeset.font(LABEL_FONT, 17),
                    LABEL if on["zoom:fit"] else LABEL_OFF, "mm"))
        typeset.draw(patch, ops)
        typeset.draw(shape, [("rrect", (0, 0, w - 1, h - 1), 14, (255, 255, 255), None)])
        cx, cy = bar.icon[0] - x0, bar.icon[1] - y0                      # the magnifier
        cv2.circle(patch, (cx, cy), 10, LABEL, 3, cv2.LINE_AA)
        cv2.line(patch, (cx + 7, cy + 7), (cx + 14, cy + 14), LABEL, 4, cv2.LINE_AA)
        cv2.line(patch, (bar.divider - x0, ly0 + 6), (bar.divider - x0, ly1 - 6), PANEL_EDGE, 2)
        for name in ("zoom:out", "zoom:in"):                             # - and + as bars: crisp at any size
            bx0, by0, bx1, by1 = local(bar.button(name).rect)
            mx, my, colour = (bx0 + bx1) // 2, (by0 + by1) // 2, LABEL if on[name] else LABEL_OFF
            cv2.rectangle(patch, (mx - 10, my - 2), (mx + 10, my + 1), colour, -1)
            if name == "zoom:in":
                cv2.rectangle(patch, (mx - 2, my - 10), (mx + 1, my + 10), colour, -1)
        return patch, shape[:, :, 0] > 127

    def _voice_panel(self, img: np.ndarray, controller) -> None:
        """D75: the voice panel (typeset once per state and copied over the frame in its rounded shape), then the
        loudness bar (the gate marked) and the hold-to-press progress."""
        layout, status = controller.voice_panel, controller.voice_status
        buttons, rect = controller.voice_buttons, controller.voice_rect     # wall test 1: only the useful ones
        state = (status["state"], status["detail"], status["device"], controller.voice_paused, rect,
                 tuple((b.name, controller.voice_label(b.name), controller.voice_enabled(b.name)) for b in buttons))
        if self._voice is None or self._voice[0] != state:
            self._voice = (state, *self._voice_patch(layout, controller, status, buttons, rect))
        _, patch, shape = self._voice
        x0, y0, x1, _ = rect
        region = img[y0:y0 + patch.shape[0], x0:x1]
        region[shape] = patch[shape]
        sx0, sy0, sx1, sy1 = layout.status
        if status["state"] in ("listening", "hearing", "writing") and not controller.voice_paused:
            y = sy0 + 62
            frac = min(max((status["level"] + 60.0) / 40.0, 0.0), 1.0)          # -60 .. -20 dBFS
            cv2.rectangle(img, (sx0, y), (sx1, y + 6), VOICE_TRACK, -1)
            cv2.rectangle(img, (sx0, y), (sx0 + int((sx1 - sx0) * frac), y + 6), VOICE_LEVEL, -1)
            gate = getattr(controller, "voice_gate_dbfs", -42.0)
            gx = sx0 + int((sx1 - sx0) * min(max((gate + 60.0) / 40.0, 0.0), 1.0))
            cv2.line(img, (gx, y - 3), (gx, y + 9), INK, 2)
        progress = controller.dwell_progress
        if progress is not None and progress[0].startswith("voice:") and controller.voice_enabled(progress[0]):
            bx0, by0, bx1, by1 = layout.button(progress[0]).rect
            cv2.rectangle(img, (bx0 + 4, by1 - 7), (bx0 + 4 + int((bx1 - bx0 - 8) * progress[1]), by1 - 3),
                          HIGHLIGHT, -1)

    @staticmethod
    def _voice_patch(layout, controller, status, buttons, rect) -> tuple[np.ndarray, np.ndarray]:
        x0, y0, x1, y1 = rect
        w, h = x1 - x0, y1 - y0
        patch, shape = np.full((h, w, 3), 255, np.uint8), np.zeros((h, w, 3), np.uint8)
        sx0, sy0, sx1, _ = (v - o for v, o in zip(layout.status, (x0, y0, x0, y0)))
        state = "paused" if controller.voice_paused and status["state"] in ("listening", "hearing", "writing") \
            else status["state"]
        label, colour = VOICE_STATES.get(state, (state, PANEL_MUTED))
        # wall test 1: the state and the microphone faint on the wall: larger and darker
        title, text, small = typeset.font(LABEL_FONT, 21), typeset.font(LABEL_FONT, 22), typeset.font(LABEL_FONT, 16)
        ops = [("rrect", (0, 0, w - 1, h - 1), 14, PANEL_FILL, PANEL_EDGE, 2),
               ("text", (sx0, sy0 + 9), "VOICE", title, INK, "lm"),
               ("rrect", (sx0, sy0 + 28, sx0 + 16, sy0 + 44), 8, colour, None),
               ("text", (sx0 + 26, sy0 + 36), label, text, colour, "lm")]
        if state in ("unavailable", "error") and status["detail"]:
            words, line, lines = status["detail"].split(), "", []
            for word in words:                                          # the reason, on two lines at most
                if line and typeset.width(f"{line} {word}", small) > sx1 - sx0:
                    lines.append(line)
                    line = word
                else:
                    line = f"{line} {word}".strip()
            lines.append(line)
            for k, part in enumerate(lines[:2]):
                ops.append(("text", (sx0, sy0 + 62 + 18 * k), typeset.fit(part, small, sx1 - sx0), small, VOICE_TEXT,
                            "lm"))
        elif status["device"]:
            ops.append(("text", (sx0, sy0 + 84), typeset.fit("Mic: " + status["device"], small, sx1 - sx0), small,
                        VOICE_TEXT, "lm"))
        label_font = typeset.font(LABEL_FONT, 15)
        for b in buttons:
            on = controller.voice_enabled(b.name)
            bx0, by0, bx1, by1 = (b.rect[0] - x0, b.rect[1] - y0, b.rect[2] - x0, b.rect[3] - y0)
            ops.append(("rrect", (bx0, by0, bx1 - 1, by1 - 1), 10, (255, 255, 255), EDGE if on else EDGE_OFF, 2))
            ops.append(("text", ((bx0 + bx1) / 2, (by0 + by1) / 2), controller.voice_label(b.name), label_font,
                        LABEL if on else LABEL_OFF, "mm"))
        typeset.draw(patch, ops)
        typeset.draw(shape, [("rrect", (0, 0, w - 1, h - 1), 14, (255, 255, 255), None)])
        return patch, shape[:, :, 0] > 127

    @staticmethod
    def _scroll_bars(img: np.ndarray, view, bar) -> None:
        """D72: which part of the zoomed page is seen: a slim track and thumb along the right side (the page taller
        than the window) and along the bottom (wider), short of the zoom bar."""
        wx0, wy0, wx1, wy1 = view.window
        (ox, oy), (pw, ph) = view.origin, view.size
        for k, (lo, hi, o, n) in enumerate(((wy0, wy1, oy, ph), (wx0, wx1, ox, pw))):
            if n <= hi - lo:
                continue
            t0, t1 = lo + 10, (bar.rect[1] if k == 0 else bar.rect[0]) - 12
            a, b = (int(round(t0 + (t1 - t0) * (v - o) / n)) for v in (lo, hi))
            if k == 0:
                cv2.line(img, (wx1 - 10, t0), (wx1 - 10, t1), TRACK, 6, cv2.LINE_AA)
                cv2.line(img, (wx1 - 10, a), (wx1 - 10, b), THUMB, 6, cv2.LINE_AA)
            else:
                cv2.line(img, (t0, wy1 - 10), (t1, wy1 - 10), TRACK, 6, cv2.LINE_AA)
                cv2.line(img, (a, wy1 - 10), (b, wy1 - 10), THUMB, 6, cv2.LINE_AA)

    def _panel(self, img: np.ndarray, controller) -> None:
        layout, panel = controller.panel_layout, controller.panel
        x0, y0, x1, y1 = layout.rect
        cv2.rectangle(img, (x0, y0), (x1, y1), (250, 250, 250), -1)
        cv2.rectangle(img, (x0, y0), (x1, y1), (150, 150, 150), 2)
        title, scale = controller.ai_title(), 0.7                        # D61; D74: smaller if it would not fit
        while scale > 0.5 and cv2.getTextSize(title, FONT, scale, 2)[0][0] > x1 - x0 - 28:
            scale -= 0.05
        cv2.putText(img, title, (x0 + 14, y0 + 32), FONT, scale, PANEL_TEXT, 2, cv2.LINE_AA)
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
            text = ("Choose what the AI should do with the selected part." if getattr(controller, "region", None)
                    else "Choose what the AI should do with this page." if document
                    else "Choose what the AI should do with it.")                       # D74: a selected part
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
