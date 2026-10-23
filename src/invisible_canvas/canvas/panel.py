"""The projected AI panel (brain.md D51, §9.11). Pure layout and text fitting.

The panel sits at the right of the canvas above the toolbar: six buttons (five actions and CLOSE), pressed by
holding the cursor on them like the toolbar, then the answer: what Claude read and the result, wrapped to the
panel. OpenCV draws ASCII only, so answers are reduced to ASCII first (typographic quotes and dashes mapped).
"""

from __future__ import annotations

import unicodedata

import cv2

from .toolbar import Button

PANEL_ACTIONS = ("summarize", "explain", "simplify", "examples", "questions")
FONT = cv2.FONT_HERSHEY_SIMPLEX
_ASCII = {"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-", "…": "...",
          " ": " ", "•": "-", "×": "x", "→": "->"}


def ascii_text(text: str) -> str:
    out = []
    for ch in text:
        ch = _ASCII.get(ch, ch)
        if not ch.isascii():
            ch = unicodedata.normalize("NFKD", ch).encode("ascii", "ignore").decode() or "?"
        out.append(ch)
    return "".join(out)


def wrap(text: str, width_px: int, scale: float, thickness: int = 1) -> list[str]:
    """Lines of `text` (ASCII) no wider than width_px in FONT at `scale`; long words are split."""
    lines = []
    for paragraph in ascii_text(text).splitlines() or [""]:
        line = ""
        for word in paragraph.split():
            while cv2.getTextSize(word, FONT, scale, thickness)[0][0] > width_px and len(word) > 1:
                cut = len(word)
                while cut > 1 and cv2.getTextSize(word[:cut], FONT, scale, thickness)[0][0] > width_px:
                    cut -= 1
                if line:
                    lines.append(line)
                    line = ""
                lines.append(word[:cut])
                word = word[cut:]
            candidate = f"{line} {word}".strip()
            if cv2.getTextSize(candidate, FONT, scale, thickness)[0][0] <= width_px:
                line = candidate
            else:
                lines.append(line)
                line = word
        lines.append(line)
    return lines


class AIPanel:
    """Layout of the panel on a canvas of `size` whose toolbar starts at `toolbar_top`."""

    def __init__(self, size: tuple[int, int], toolbar_top: int, width: int = 440, margin: int = 16):
        w, _ = size
        self.rect = (w - width - margin, margin, w - margin, toolbar_top - margin)
        x0, y0, x1, _ = self.rect
        bw, bh, gap = (width - 3 * 12) // 2, 52, 10
        names = [f"ai:{a}" for a in PANEL_ACTIONS] + ["ai:close"]
        self.buttons = []
        for k, name in enumerate(names):
            col, row = k % 2, k // 2
            bx, by = x0 + 12 + col * (bw + 12), y0 + 48 + row * (bh + gap)
            self.buttons.append(Button(name, "panel", (bx, by, bx + bw, by + bh)))
        self.text_top = self.buttons[-1].rect[3] + 18
        self.text_left, self.text_right = x0 + 14, x1 - 14

    def contains(self, point) -> bool:
        if point is None:
            return False
        x0, y0, x1, y1 = self.rect
        return x0 <= point[0] < x1 and y0 <= point[1] < y1

    def hit(self, point) -> Button | None:
        if point is None:
            return None
        return next((b for b in self.buttons if b.contains(point)), None)
