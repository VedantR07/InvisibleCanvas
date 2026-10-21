"""Canvas content as structured strokes (brain.md §5.1, D44). Pure: no I/O besides (de)serialisation.

Coordinates are projector px (the logical canvas equals the projector canvas in Phase 2). Points along a
stroke are kept at most `MAX_STEP` px apart, so the eraser can split a stroke precisely where it touches.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

MAX_STEP = 2.0            # px between consecutive stroke points (densified on append)


@dataclass
class Stroke:
    id: int
    color: tuple[int, int, int]           # BGR
    width: float                          # px
    points: list[tuple[float, float]] = field(default_factory=list)

    def append(self, point, max_step: float = MAX_STEP) -> None:
        """Add a point; straight-line points are inserted so no gap exceeds `max_step` px."""
        x, y = float(point[0]), float(point[1])
        if not (math.isfinite(x) and math.isfinite(y)):
            return
        if self.points:
            px, py = self.points[-1]
            d = math.hypot(x - px, y - py)
            if d < 1e-9:
                return
            n = int(math.ceil(d / max_step))
            for k in range(1, n):
                self.points.append((px + (x - px) * k / n, py + (y - py) * k / n))
        self.points.append((x, y))

    def array(self) -> np.ndarray:
        return np.asarray(self.points, dtype=np.float64).reshape(-1, 2)

    def bounds(self) -> tuple[float, float, float, float]:
        a = self.array()
        r = self.width / 2
        return float(a[:, 0].min() - r), float(a[:, 1].min() - r), float(a[:, 0].max() + r), float(a[:, 1].max() + r)

    def distance_to(self, point) -> float:
        """Distance from `point` to the stroke's centre line."""
        p = np.asarray(point, dtype=np.float64)
        a = self.array()
        if len(a) == 1:
            return float(np.linalg.norm(a[0] - p))
        s, e = a[:-1], a[1:]
        d = e - s
        length2 = np.maximum((d ** 2).sum(axis=1), 1e-12)
        u = np.clip(((p - s) * d).sum(axis=1) / length2, 0.0, 1.0)
        return float(np.min(np.linalg.norm(s + d * u[:, None] - p, axis=1)))

    def to_dict(self) -> dict:
        return {"id": self.id, "color": list(self.color), "width": self.width,
                "points": [[round(x, 2), round(y, 2)] for x, y in self.points]}

    @classmethod
    def from_dict(cls, d: dict) -> Stroke:
        return cls(int(d["id"]), tuple(int(c) for c in d["color"]), float(d["width"]),
                   [(float(x), float(y)) for x, y in d["points"]])


class Canvas:
    """Ordered strokes (drawing order = z-order) and a version counter for render caching."""

    def __init__(self, size: tuple[int, int]):
        self.size = (int(size[0]), int(size[1]))
        self.strokes: dict[int, Stroke] = {}
        self.version = 0
        self._next_id = 1

    def new_id(self) -> int:
        i, self._next_id = self._next_id, self._next_id + 1
        return i

    def _changed(self) -> None:
        self.version += 1

    def add(self, stroke: Stroke) -> None:
        if not stroke.points:
            raise ValueError("a stroke needs at least one point")
        if stroke.id in self.strokes:
            raise ValueError(f"stroke id {stroke.id} already on the canvas")
        self.strokes[stroke.id] = stroke
        self._next_id = max(self._next_id, stroke.id + 1)
        self._changed()

    def remove(self, stroke_id: int) -> Stroke:
        stroke = self.strokes.pop(stroke_id)
        self._changed()
        return stroke

    def erase(self, centre, radius: float) -> tuple[list[Stroke], list[Stroke]]:
        """Remove the ink within `radius` of `centre`. Touched strokes are replaced by the pieces outside the
        circle, in place (same drawing order). Returns (removed strokes, new pieces)."""
        c = np.asarray(centre, dtype=np.float64)
        if not np.all(np.isfinite(c)) or radius <= 0:
            return [], []
        removed, created, order = [], [], {}
        for sid, stroke in self.strokes.items():
            reach = radius + stroke.width / 2
            x0, y0, x1, y1 = stroke.bounds()
            if c[0] < x0 - reach or c[0] > x1 + reach or c[1] < y0 - reach or c[1] > y1 + reach:
                order[sid] = stroke
                continue
            a = stroke.array()
            keep = np.linalg.norm(a - c, axis=1) > reach
            if keep.all():
                order[sid] = stroke
                continue
            removed.append(stroke)
            start = None
            for i, k in enumerate(list(keep) + [False]):
                if k and start is None:
                    start = i
                elif not k and start is not None:
                    piece = Stroke(self.new_id(), stroke.color, stroke.width, [tuple(p) for p in a[start:i].tolist()])
                    order[piece.id] = piece
                    created.append(piece)
                    start = None
        if removed:
            self.strokes = order
            self._changed()
        return removed, created

    def hit_test(self, point, tolerance: float = 12.0) -> int | None:
        """The topmost stroke whose ink lies within `tolerance` px of `point`."""
        for sid in reversed(list(self.strokes)):
            stroke = self.strokes[sid]
            if stroke.distance_to(point) <= tolerance + stroke.width / 2:
                return sid
        return None

    def move(self, ids, dx: float, dy: float) -> None:
        if dx == 0 and dy == 0:
            return
        for sid in ids:
            s = self.strokes[sid]
            s.points = [(x + dx, y + dy) for x, y in s.points]
        self._changed()

    def clear(self) -> list[Stroke]:
        removed = list(self.strokes.values())
        if removed:
            self.strokes = {}
            self._changed()
        return removed

    def to_dict(self) -> dict:
        return {"format": "invisible-canvas/strokes", "version": 1, "size": list(self.size),
                "strokes": [s.to_dict() for s in self.strokes.values()]}

    @classmethod
    def from_dict(cls, d: dict) -> Canvas:
        if d.get("format") != "invisible-canvas/strokes" or d.get("version") != 1:
            raise ValueError("not an Invisible Canvas stroke file (format/version)")
        canvas = cls(tuple(d["size"]))
        for s in d["strokes"]:
            canvas.add(Stroke.from_dict(s))
        canvas.version = 0
        return canvas
