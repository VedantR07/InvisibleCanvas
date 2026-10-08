"""Interactive point collection, shared by calibration and validation.

The projector shows one target at a time. The operator clicks its centre in the
live camera view, refines it (click inside the loupe for sub-pixel precision, or
use the arrow keys for 1-px steps) and confirms. Returns camera coordinates.
"""

from __future__ import annotations

from typing import Callable

import cv2
import numpy as np

from ..display import patterns

KEY_ESC = 27
KEY_ENTER = (13, 10)
KEY_SPACE = 32
KEY_BACKSPACE = 8
# cv2.waitKeyEx codes on Windows
ARROWS = {2424832: (-1, 0), 2555904: (1, 0), 2490368: (0, -1), 2621440: (0, 1)}


def draw_point(img: np.ndarray, point, color, label: str | None = None, radius: int = 6) -> None:
    x, y = int(round(point[0])), int(round(point[1]))
    cv2.circle(img, (x, y), radius, color, 1, cv2.LINE_AA)
    cv2.line(img, (x - radius - 6, y), (x - 2, y), color, 1)
    cv2.line(img, (x + 2, y), (x + radius + 6, y), color, 1)
    cv2.line(img, (x, y - radius - 6), (x, y - 2), color, 1)
    cv2.line(img, (x, y + 2), (x, y + radius + 6), color, 1)
    if label:
        patterns.text(img, label, (x + radius + 8, y - radius - 4), color, 0.5)


def collect_points(
    session,
    targets: np.ndarray,
    labels: list[str],
    render_projector: Callable[[int], np.ndarray],
    *,
    title: str,
    overlay: Callable[[np.ndarray], None] | None = None,
) -> np.ndarray | None:
    """Collect one camera point per target. Returns (N, 2) or None if cancelled."""
    camera, projector, operator = session.camera, session.projector, session.operator
    n = len(targets)
    points: list[tuple[float, float]] = []
    state = {"candidate": None, "mouse": None}

    def on_mouse(kind: str, x: float, y: float) -> None:
        if kind == "move":
            state["mouse"] = (x, y)
        elif kind == "click":
            state["candidate"] = (x, y)
        elif kind == "rclick":
            state["candidate"] = None

    operator.on_mouse = on_mouse
    shown = -1
    try:
        while len(points) < n:
            i = len(points)
            if shown != i:
                projector.show(render_projector(i))
                shown = i
            frame = camera.wait_frame(0, timeout=2.0)
            if frame is None:
                return None
            view = frame.image.copy()
            if overlay:
                overlay(view)
            for k, p in enumerate(points):
                draw_point(view, p, patterns.GREEN, str(k + 1))
            candidate = state["candidate"]
            if candidate:
                draw_point(view, candidate, patterns.YELLOW, f"{i + 1}?")
            loupe_center = candidate or state["mouse"]
            fps = camera.stats().recent_fps
            lines = [
                title,
                f"Target {i + 1} of {n}: {labels[i]}",
                "",
                "Click the centre of the bright projected cross.",
                "Refine: click inside the loupe (sub-pixel) or use the arrow keys (1 px).",
                "ENTER/SPACE accept | BACKSPACE undo | right-click clear | ESC cancel",
                "",
                f"candidate: {candidate[0]:.2f}, {candidate[1]:.2f}" if candidate else "candidate: -",
                f"camera {fps:.1f} fps",
            ]
            if camera.error:
                lines.append("!" + camera.error)
            operator.show(view, raw=frame.image, loupe_center=loupe_center, lines=lines)

            key = cv2.waitKeyEx(10)
            if key == -1:
                continue
            if key == KEY_ESC:
                return None
            if key in KEY_ENTER or key == KEY_SPACE:
                if candidate:
                    points.append(candidate)
                    state["candidate"] = None
            elif key == KEY_BACKSPACE:
                if candidate:
                    state["candidate"] = None
                elif points:
                    state["candidate"] = points.pop()
            elif key in ARROWS and candidate:
                dx, dy = ARROWS[key]
                state["candidate"] = (candidate[0] + dx, candidate[1] + dy)
        return np.array(points, dtype=np.float64)
    finally:
        operator.on_mouse = None
