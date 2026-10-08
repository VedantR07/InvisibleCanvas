"""Operator window on the laptop: camera view + side panel with a zoom loupe and status.

The camera view is shown 1:1 when it fits on the screen, otherwise scaled down.
Mouse positions are converted back to camera pixels (pixel centres at integers);
clicks inside the loupe give sub-pixel camera coordinates.
"""

from __future__ import annotations

from typing import Callable

import cv2
import numpy as np

from . import patterns
from .monitors import Display

MouseHandler = Callable[[str, float, float], None]  # (kind: "move" | "click" | "rclick", x, y) in camera px


class OperatorWindow:
    NAME = "Invisible Canvas - Operator"
    PANEL_WIDTH = 340
    LOUPE_HALF = 19          # loupe shows (2*19+1)^2 camera pixels
    LOUPE_ZOOM = 8           # ... each drawn 8x8
    LOUPE_TOP = 10

    def __init__(self, frame_size: tuple[int, int], screen: Display | None):
        fw, fh = frame_size
        if screen is not None:
            avail_w = screen.width - self.PANEL_WIDTH - 40
            avail_h = screen.height - 140  # title bar and taskbar
            self.scale = min(1.0, avail_w / fw, avail_h / fh)
            self.origin = (screen.x + 10, screen.y + 10)
        else:
            self.scale, self.origin = 1.0, (10, 10)
        self.frame_size = (fw, fh)
        self.view_size = (int(round(fw * self.scale)), int(round(fh * self.scale)))
        self.on_mouse: MouseHandler | None = None
        self._loupe_origin: tuple[int, int] | None = None
        loupe_px = (2 * self.LOUPE_HALF + 1) * self.LOUPE_ZOOM
        self._loupe_rect = (self.view_size[0] + (self.PANEL_WIDTH - loupe_px) // 2, self.LOUPE_TOP, loupe_px)

    def open(self) -> None:
        cv2.namedWindow(self.NAME, cv2.WINDOW_AUTOSIZE)
        cv2.moveWindow(self.NAME, *self.origin)
        cv2.setMouseCallback(self.NAME, self._mouse)

    def close(self) -> None:
        try:
            cv2.destroyWindow(self.NAME)
        except cv2.error:
            pass

    # -- coordinates --------------------------------------------------------

    def to_camera(self, wx: float, wy: float) -> tuple[float, float]:
        return (wx + 0.5) / self.scale - 0.5, (wy + 0.5) / self.scale - 0.5

    def to_view(self, cx: float, cy: float) -> tuple[int, int]:
        return int(round((cx + 0.5) * self.scale - 0.5)), int(round((cy + 0.5) * self.scale - 0.5))

    def _mouse(self, event, x, y, _flags, _param) -> None:
        if self.on_mouse is None:
            return
        kind = {cv2.EVENT_MOUSEMOVE: "move", cv2.EVENT_LBUTTONDOWN: "click", cv2.EVENT_RBUTTONDOWN: "rclick"}.get(event)
        if kind is None:
            return
        vw, vh = self.view_size
        if x < vw and y < vh:
            self.on_mouse(kind, *self.to_camera(x, y))
            return
        lx0, ly0, size = self._loupe_rect
        if self._loupe_origin and lx0 <= x < lx0 + size and ly0 <= y < ly0 + size and kind != "move":
            ox, oy = self._loupe_origin
            z = self.LOUPE_ZOOM
            self.on_mouse(kind, ox - 0.5 + (x - lx0 + 0.5) / z, oy - 0.5 + (y - ly0 + 0.5) / z)

    # -- drawing ------------------------------------------------------------

    def _loupe(self, raw: np.ndarray, center: tuple[float, float]) -> np.ndarray:
        half, z = self.LOUPE_HALF, self.LOUPE_ZOOM
        n = 2 * half + 1
        ix, iy = int(round(center[0])), int(round(center[1]))
        ox, oy = ix - half, iy - half
        patch = np.zeros((n, n, 3), dtype=np.uint8)
        h, w = raw.shape[:2]
        sx0, sy0, sx1, sy1 = max(ox, 0), max(oy, 0), min(ox + n, w), min(oy + n, h)
        if sx0 < sx1 and sy0 < sy1:
            patch[sy0 - oy:sy1 - oy, sx0 - ox:sx1 - ox] = raw[sy0:sy1, sx0:sx1]
        big = cv2.resize(patch, (n * z, n * z), interpolation=cv2.INTER_NEAREST)
        lx = int(round((center[0] - ox + 0.5) * z - 0.5))
        ly = int(round((center[1] - oy + 0.5) * z - 0.5))
        cv2.line(big, (0, ly), (lx - z, ly), patterns.RED, 1)
        cv2.line(big, (lx + z, ly), (n * z - 1, ly), patterns.RED, 1)
        cv2.line(big, (lx, 0), (lx, ly - z), patterns.RED, 1)
        cv2.line(big, (lx, ly + z), (lx, n * z - 1), patterns.RED, 1)
        self._loupe_origin = (ox, oy)
        return big

    def show(self, view: np.ndarray, *, raw: np.ndarray | None = None,
             loupe_center: tuple[float, float] | None = None, lines=()) -> None:
        """`view`: camera frame with overlays (camera px). `raw`: unannotated frame for the loupe."""
        vw, vh = self.view_size
        canvas = np.full((max(vh, 600), vw + self.PANEL_WIDTH, 3), 24, dtype=np.uint8)
        if self.scale == 1.0:
            canvas[:vh, :vw] = view
        else:
            canvas[:vh, :vw] = cv2.resize(view, (vw, vh), interpolation=cv2.INTER_AREA)
        lx0, ly0, size = self._loupe_rect
        if raw is not None and loupe_center is not None:
            canvas[ly0:ly0 + size, lx0:lx0 + size] = self._loupe(raw, loupe_center)
        else:
            self._loupe_origin = None
            cv2.rectangle(canvas, (lx0, ly0), (lx0 + size - 1, ly0 + size - 1), patterns.DIM, 1)
        y = ly0 + size + 28
        for line in lines:
            color = patterns.WHITE
            if line.startswith("!"):
                line, color = line[1:], patterns.ORANGE
            for chunk in _wrap(line, 40):
                patterns.text(canvas, chunk, (vw + 12, y), color, 0.5)
                y += 21
        cv2.imshow(self.NAME, canvas)


def _wrap(line: str, width: int) -> list[str]:
    words, out, current = line.split(), [], ""
    for word in words:
        if current and len(current) + 1 + len(word) > width:
            out.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    return out + [current] if current else out or [""]
