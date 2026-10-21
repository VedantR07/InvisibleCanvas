"""The projected toolbar along the bottom edge (brain.md §9.10, D44, D46). Pure layout.

A button is pressed by holding the cursor on it for `DWELL_S` (CLEAR: `CLEAR_DWELL_S`, so it cannot be hit
by accident); D46 replaced the pinch, which the camera cannot see from behind the user. Buttons are 80 x 56
projector px (about 8 x 6 cm on the 2026-10 wall).
"""

from __future__ import annotations

from dataclasses import dataclass

COLOURS = {          # BGR, dark ink on the white canvas
    "black": (25, 25, 25),
    "red": (40, 40, 215),
    "blue": (190, 90, 20),
    "green": (40, 150, 40),
}
WIDTHS = {"thin": 4.0, "medium": 8.0, "thick": 14.0}
TOOLS = ("pen", "eraser", "move")
ACTIONS = ("undo", "redo", "clear")
DWELL_S = 1.0
CLEAR_DWELL_S = 2.0


@dataclass(frozen=True)
class Button:
    name: str                     # "black", "thin", "undo", ...
    kind: str                     # "tool", "colour", "width" or "action"
    rect: tuple[int, int, int, int]   # x0, y0, x1, y1 (inclusive-exclusive)

    def contains(self, point) -> bool:
        x, y = point
        x0, y0, x1, y1 = self.rect
        return x0 <= x < x1 and y0 <= y < y1

    @property
    def centre(self) -> tuple[float, float]:
        x0, y0, x1, y1 = self.rect
        return (x0 + x1) / 2, (y0 + y1) / 2


class Toolbar:
    def __init__(self, size: tuple[int, int], *, height: int = 72, button: int = 80, gap: int = 8,
                 group_gap: int = 28):
        w, h = int(size[0]), int(size[1])
        self.size, self.height = (w, h), height
        self.top = h - height
        names = ([(n, "tool") for n in TOOLS] + [(n, "colour") for n in COLOURS] + [(n, "width") for n in WIDTHS]
                 + [(n, "action") for n in ACTIONS])
        groups = [len(TOOLS), len(COLOURS), len(WIDTHS), len(ACTIONS)]
        total = len(names) * button + (len(names) - len(groups)) * gap + (len(groups) - 1) * group_gap
        x = max((w - total) // 2, 0)
        y0, y1 = self.top + (height - 56) // 2, self.top + (height - 56) // 2 + 56
        self.buttons: list[Button] = []
        i = 0
        for g, count in enumerate(groups):
            for k in range(count):
                name, kind = names[i]
                self.buttons.append(Button(name, kind, (x, y0, x + button, y1)))
                x += button + (gap if k < count - 1 else 0)
                i += 1
            x += group_gap
        if self.buttons[-1].rect[2] > w:
            raise ValueError(f"toolbar does not fit a {w}-px canvas")

    def in_band(self, point) -> bool:
        """Whether a point lies on the toolbar band (no drawing there)."""
        return point is not None and point[1] >= self.top

    def hit(self, point) -> Button | None:
        if point is None:
            return None
        for b in self.buttons:
            if b.contains(point):
                return b
        return None

    def button(self, name: str) -> Button:
        return next(b for b in self.buttons if b.name == name)

    @staticmethod
    def dwell_s(button: Button) -> float:
        return CLEAR_DWELL_S if button.name == "clear" else DWELL_S
