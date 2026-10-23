"""Renders the canvas for the projector: strokes, the stroke being drawn, the selection, the toolbar (with the
hold-to-press progress) and the cursor, whose look shows the mode and tool (brain.md §9.10, D44, D46). The
committed strokes are cached and redrawn only when the canvas changes.

D50: with a light polygon (display.handlight) the hand is painted plain white last, so no ink, text or cursor
falls on it, and the cursor becomes a ring around the fingertip, wider than the light's margin, so it lands on
the wall; a toolbar dwell fills the ring as a progress arc (the button itself is often under the hand).
"""

from __future__ import annotations

import cv2
import numpy as np

from ..display.handlight import LightParams, paint
from ..interaction.engine import DRAW, HOVER
from .model import Canvas, Stroke
from .toolbar import COLOURS, WIDTHS, Toolbar

BACKGROUND = 255
TOOLBAR_BG = (232, 232, 232)
HIGHLIGHT = (200, 60, 200)            # magenta: selection, pinch cursor, current tool
ERASER = (0, 140, 255)                # orange
FONT = cv2.FONT_HERSHEY_SIMPLEX
RING_RADIUS = int(LightParams().margin_px) + 13   # D50 ring cursor: just outside the light around the fingertip


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
        self._version = -1
        self.redraws = 0

    def _strokes(self, canvas: Canvas) -> np.ndarray:
        if self._cache is None or canvas.version != self._version:
            w, h = self.size
            img = np.full((h, w, 3), self.background, dtype=np.uint8)
            for s in canvas.strokes.values():
                draw_stroke(img, s)
            self._cache, self._version = img, canvas.version
            self.redraws += 1
        return self._cache

    def render(self, canvas: Canvas, controller, toolbar: Toolbar, *, mode: str, cursor, status: str = "",
               light: np.ndarray | None = None) -> np.ndarray:
        img = self._strokes(canvas).copy()
        if controller.selected is not None and controller.selected in canvas.strokes:
            s = canvas.strokes[controller.selected]
            x0, y0, x1, y1 = (int(round(v)) for v in s.bounds())
            cv2.rectangle(img, (x0 - 6, y0 - 6), (x1 + 6, y1 + 6), HIGHLIGHT, 2, cv2.LINE_AA)
        if controller.active is not None and controller.active.points:
            draw_stroke(img, controller.active)
        self._toolbar(img, toolbar, controller)
        if status:
            cv2.putText(img, status, (12, 26), FONT, 0.6, (120, 120, 120), 1, cv2.LINE_AA)
        if cursor is not None:
            if light is None:
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
                       or (b.kind == "width" and controller.width == b.name))
            cv2.rectangle(img, (x0, y0), (x1 - 1, y1 - 1), HIGHLIGHT if current else (160, 160, 160), 4 if current else 1)
            if b.kind == "colour":
                cv2.circle(img, (cx, cy), 18, COLOURS[b.name], -1, cv2.LINE_AA)
            elif b.kind == "width":
                t = int(WIDTHS[b.name])
                cv2.line(img, (x0 + 22, cy), (x1 - 22, cy), COLOURS[controller.colour], t, cv2.LINE_AA)
            else:
                label = b.name.upper()
                (tw, th), _ = cv2.getTextSize(label, FONT, 0.5, 2)
                cv2.putText(img, label, (cx - tw // 2, cy + th // 2), FONT, 0.5, (60, 60, 60), 2, cv2.LINE_AA)
            progress = controller.dwell_progress
            if progress is not None and progress[0] == b.name:          # hold-to-press feedback
                fill = int((x1 - x0) * progress[1])
                cv2.rectangle(img, (x0, y1 - 9), (x0 + fill, y1 - 1), (40, 40, 215) if b.name == "clear" else HIGHLIGHT, -1)

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
        progress = controller.dwell_progress
        if progress is not None and progress[1] > 0:                          # hold-to-press on the ring
            cv2.ellipse(img, (x, y), (RING_RADIUS, RING_RADIUS), -90, 0, 360 * progress[1],
                        (40, 40, 215) if progress[0] == "clear" else HIGHLIGHT, 7, cv2.LINE_AA)
