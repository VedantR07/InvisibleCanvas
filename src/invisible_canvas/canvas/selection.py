"""Loop selection and the image of a selection that the AI reads (brain.md D51, §9.11). Pure.

A stroke is selected when at least `MIN_INSIDE` of its points lie inside the loop drawn with the SELECT tool (a
word written with several strokes is selected stroke by stroke; a stroke crossing the loop's edge counts by
majority). The loop is first closed at its tightest point (D53, `close_loop`), so the path of the finger moving to
where the loop begins, and any run-on past the start, are not part of it. The selection image shows the strokes in
their own colours on white, cropped to them with a margin and scaled so the longer side is at most `MAX_SIDE` px
(and handwriting is not tiny); PNG for the API. D74: on a document the loop chooses a part of the page instead
(`loop_region`: the box around the closed loop).
"""

from __future__ import annotations

import cv2
import numpy as np

from .model import Canvas

MIN_INSIDE = 0.6
MIN_LOOP_AREA = 400.0          # px²: a smaller loop is a slip, not a selection
# D53: the loop closes between a point of its first third and a point of its last third. On the 17 loops of S1
# run 1, windows of 25-40 % gave the same selections (12 of 12 completed loops exact); at 50 % they meet mid-loop.
CLOSE_PART = 1 / 3
MIN_CLOSE_POINTS = 8           # shorter loops are used as drawn
MARGIN = 24
MAX_SIDE = 1024
MIN_SIDE = 320


def loop_area(points) -> float:
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    if len(pts) < 3:
        return 0.0
    x, y = pts[:, 0], pts[:, 1]
    return float(abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) / 2)


def close_loop(points, part: float = CLOSE_PART) -> np.ndarray:
    """The closed part of a drawn loop (D53): from the point of its first `part` to the point of its last `part`
    that lie closest together. A stroke starts where pointing starts, so the finger's way to the loop's start is
    drawn too; joined end-to-start, that lead-in took a neighbouring word's stroke into the polygon or cut one of
    the word's own strokes out of it (S1 run 1, loops 8 and 9). Unchanged when the drawn ends are already the
    closest pair or the loop has fewer than MIN_CLOSE_POINTS points."""
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    n = len(pts)
    if n < MIN_CLOSE_POINTS:
        return pts
    k = max(1, int(n * part))
    d = np.linalg.norm(pts[:k, None, :] - pts[None, n - k:, :], axis=2)
    i, j = np.unravel_index(np.argmin(d), d.shape)
    if d[i, j] >= np.linalg.norm(pts[0] - pts[-1]):
        return pts
    return pts[i:n - k + j + 1]


def loop_region(loop) -> tuple[float, float, float, float] | None:
    """D74: the box around a loop closed at its tightest point (x0, y0, x1, y1), or None for a slip (as
    `select_in_loop`): on a document, the part of the page the AI reads."""
    pts = close_loop(loop)
    if loop_area(pts) < MIN_LOOP_AREA:
        return None
    return float(pts[:, 0].min()), float(pts[:, 1].min()), float(pts[:, 0].max()), float(pts[:, 1].max())


def select_in_loop(canvas: Canvas, loop, min_inside: float = MIN_INSIDE) -> list[int]:
    """Ids of the strokes with at least `min_inside` of their points inside the loop, closed at its tightest point
    (drawing order)."""
    pts = close_loop(loop)
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
    return strokes_image([canvas.strokes[i] for i in (ids or list(canvas.strokes)) if i in canvas.strokes])


def strokes_image(strokes) -> np.ndarray | None:
    """The same image for a list of strokes (D64: a completed Smart Line for its recognition)."""
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
