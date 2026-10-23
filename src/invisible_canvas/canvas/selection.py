"""Loop selection and the image of a selection that the AI reads (brain.md D51, §9.11). Pure.

A stroke is selected when at least `MIN_INSIDE` of its points lie inside the loop drawn with the SELECT tool (a
word written with several strokes is selected stroke by stroke; a stroke crossing the loop's edge counts by
majority). The selection image shows the strokes in their own colours on white, cropped to them with a margin
and scaled so the longer side is at most `MAX_SIDE` px (and handwriting is not tiny); PNG for the API.
"""

from __future__ import annotations

import cv2
import numpy as np

from .model import Canvas

MIN_INSIDE = 0.6
MIN_LOOP_AREA = 400.0          # px²: a smaller loop is a slip, not a selection
MARGIN = 24
MAX_SIDE = 1024
MIN_SIDE = 320


def loop_area(points) -> float:
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    if len(pts) < 3:
        return 0.0
    x, y = pts[:, 0], pts[:, 1]
    return float(abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) / 2)


def select_in_loop(canvas: Canvas, loop, min_inside: float = MIN_INSIDE) -> list[int]:
    """Ids of the strokes with at least `min_inside` of their points inside the closed loop (drawing order)."""
    pts = np.asarray(loop, dtype=np.float64).reshape(-1, 2)
    if loop_area(pts) < MIN_LOOP_AREA:
        return []
    contour = pts.astype(np.float32).reshape(-1, 1, 2)
    chosen = []
    for sid, stroke in canvas.strokes.items():
        a = stroke.array()
        if not len(a):
            continue
        inside = sum(cv2.pointPolygonTest(contour, (float(x), float(y)), False) >= 0 for x, y in a)
        if inside / len(a) >= min_inside:
            chosen.append(sid)
    return chosen


def selection_image(canvas: Canvas, ids=None) -> np.ndarray | None:
    """BGR image of the given strokes (all strokes when `ids` is None or empty); None when there is no ink."""
    strokes = [canvas.strokes[i] for i in (ids or list(canvas.strokes)) if i in canvas.strokes]
    strokes = [s for s in strokes if s.points]
    if not strokes:
        return None
    x0 = min(s.bounds()[0] for s in strokes) - MARGIN
    y0 = min(s.bounds()[1] for s in strokes) - MARGIN
    x1 = max(s.bounds()[2] for s in strokes) + MARGIN
    y1 = max(s.bounds()[3] for s in strokes) + MARGIN
    w, h = x1 - x0, y1 - y0
    scale = min(MAX_SIDE / max(w, h), max(MIN_SIDE / max(w, h), 1.0))
    size = (max(int(round(w * scale)), 1), max(int(round(h * scale)), 1))
    img = np.full((size[1], size[0], 3), 255, np.uint8)
    for s in strokes:
        a = np.round((s.array() - (x0, y0)) * scale).astype(np.int32)
        width = max(int(round(s.width * scale)), 2)
        if len(a) == 1:
            cv2.circle(img, tuple(int(v) for v in a[0]), max(width // 2, 1), s.color, -1, cv2.LINE_AA)
        else:
            cv2.polylines(img, [a], False, s.color, width, cv2.LINE_AA)
    return img


def png_bytes(image: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", image)
    if not ok:
        raise ValueError("could not encode the selection image")
    return buf.tobytes()
