"""Voice writing (brain.md §9.19, D75): the typed text of a whiteboard page, written by voice. Pure: no I/O.

The text is a list of tokens: words (each with its own punctuation, as the recognizer wrote it) and breaks
(`NEW_LINE`, `NEW_PARAGRAPH`). Each change is one step of the text's own undo history (the tokens before it), so UNDO
and REDO of voice writing never touch the page's ink. It is kept apart from the ink (`Page.voice`) and saved with the
board.

Layout (`VoiceLayout`): the words are set left to right in the writing area with one space between them; a word that
would cross the area's right edge starts the next line (a word wider than a whole line, and only such a word, is
split); a new line breaks the line, a new paragraph leaves an empty line; every line has the same height. When the
lines do not fit, the view follows the end of the text, `scroll` lines from it to see earlier ones; nothing is drawn
outside the area.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import text as typeset

NEW_LINE, NEW_PARAGRAPH = "\n", "\n\n"
BREAKS = (NEW_LINE, NEW_PARAGRAPH)
SENTENCE_END = (".", "?", "!")
PUNCTUATION = ".,?!;:"

INK = (60, 38, 22)                 # D71 navy, as the Smart Lines notes
FRAME, CARET = (208, 200, 192), (160, 60, 10)   # the area's frame while voice writing is on; the writing position
ARROW_EDGE, ARROW_OFF = (90, 60, 40), (170, 170, 170)        # the scroll column (the Lines page's look, D71)
TRACK, THUMB = (200, 196, 192), (160, 60, 10)


class VoiceText:
    def __init__(self, tokens=()):
        self.tokens: list[str] = list(tokens)
        self._undo: list[tuple] = []
        self._redo: list[tuple] = []
        self.version = 0
        self._last: tuple | None = None        # (first token, end, version): the last phrase written, while unchanged

    @property
    def has_content(self) -> bool:
        return any(t not in BREAKS for t in self.tokens)

    @property
    def words(self) -> list[str]:
        return [t for t in self.tokens if t not in BREAKS]

    def _set(self, tokens) -> bool:
        tokens = list(tokens)
        if tokens == self.tokens:
            return False
        self._undo.append(tuple(self.tokens))
        self._redo.clear()
        self.tokens = tokens
        self.version += 1
        return True

    def _last_word(self) -> int | None:
        return next((i for i in range(len(self.tokens) - 1, -1, -1) if self.tokens[i] not in BREAKS), None)

    # -- writing -------------------------------------------------------------------------------------------------

    def write(self, text: str) -> bool:
        """A transcribed phrase, after what is there (its words split at white space)."""
        words = text.split()
        start = len(self.tokens)
        if not (words and self._set(self.tokens + words)):
            return False
        self._last = (start, len(self.tokens), self.version)
        return True

    def _phrase(self) -> tuple[int, int] | None:
        """Where the last phrase written lies, if nothing changed since; else the last sentence (back to the previous
        sentence's end or paragraph)."""
        if self._last is not None and self._last[2] == self.version:
            return self._last[0], self._last[1]
        i = self._last_word()
        if i is None:
            return None
        j = i - 1
        while j >= 0 and not (self.tokens[j] == NEW_PARAGRAPH
                              or (self.tokens[j] not in BREAKS and self.tokens[j].endswith(SENTENCE_END))):
            j -= 1
        k = j + 1
        while k < i and self.tokens[k] in BREAKS:
            k += 1
        return k, i + 1

    def replace_last(self, text: str) -> bool:
        """"I mean ...": the last phrase written (or the last sentence) replaced by `text`, as one step."""
        words, span = text.split(), self._phrase()
        if not words or span is None:
            return False
        a, b = span
        if not self._set(self.tokens[:a] + words + self.tokens[b:]):
            return False
        self._last = (a, a + len(words), self.version)
        return True

    def scratch(self) -> bool:
        """"Scratch that": the last phrase written (or the last sentence) and the breaks after it."""
        span = self._phrase()
        return span is not None and self._set(self.tokens[:span[0]])

    def punctuate(self, mark: str) -> bool:
        """`mark` (one of PUNCTUATION) at the end of the last word, replacing the punctuation it ended with."""
        i = self._last_word()
        if i is None:
            return False
        word = self.tokens[i].rstrip(PUNCTUATION) or self.tokens[i]
        return self._set(self.tokens[:i] + [word + mark] + self.tokens[i + 1:])

    def new_line(self) -> bool:
        return self.has_content and self._set(self.tokens + [NEW_LINE])

    def new_paragraph(self) -> bool:
        if not self.has_content:
            return False
        tokens = self.tokens[:-1] if self.tokens[-1] in BREAKS else self.tokens
        return self._set(tokens + [NEW_PARAGRAPH])

    # -- deleting --------------------------------------------------------------------------------------------------

    def delete_last_word(self) -> bool:
        """The last word, and the breaks written after it."""
        i = self._last_word()
        return i is not None and self._set(self.tokens[:i])

    def delete_last_sentence(self) -> bool:
        """The last sentence: back to the previous sentence's end or paragraph (and the breaks written after the last
        sentence); a break said between the two sentences stays (the writing goes on on that line)."""
        i = self._last_word()
        if i is None:
            return False
        j = i - 1
        while j >= 0 and not (self.tokens[j] == NEW_PARAGRAPH
                              or (self.tokens[j] not in BREAKS and self.tokens[j].endswith(SENTENCE_END))):
            j -= 1
        k = j + 1
        while k < i and self.tokens[k] in BREAKS:
            k += 1
        return self._set(self.tokens[:k])

    def clear_line(self) -> bool:
        """The words of the line being written (after the last break)."""
        k = next((i for i in range(len(self.tokens) - 1, -1, -1) if self.tokens[i] in BREAKS), -1)
        return k < len(self.tokens) - 1 and self._set(self.tokens[:k + 1])

    def delete_words(self, indexes) -> bool:
        """D75 V2: the words at these token indexes (SELECT + DELETE)."""
        drop = set(indexes)
        return bool(drop) and self._set([t for i, t in enumerate(self.tokens) if i not in drop])

    def clear(self) -> bool:
        return self._set([])

    def restore(self, tokens) -> bool:
        """Back to earlier tokens as one step (CANCEL: what was there when voice writing began)."""
        return self._set(tokens)

    # -- undo ------------------------------------------------------------------------------------------------------

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(tuple(self.tokens))
        self.tokens = list(self._undo.pop())
        self.version += 1
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(tuple(self.tokens))
        self.tokens = list(self._redo.pop())
        self.version += 1
        return True

    def to_dict(self) -> dict:
        return {"tokens": list(self.tokens)}

    @classmethod
    def from_dict(cls, d: dict) -> VoiceText:
        return cls([str(t) for t in d.get("tokens", [])])


@dataclass(frozen=True)
class Line:
    words: tuple                   # ((x offset, word, token index), ...)


class VoiceLayout:
    """Where the words go in the writing area `area` (x0, y0, x1, y1, projector px). Its right `column` px hold the
    scroll column (user, after wall test 3: "a scroll button for the mike writing"): ▲ at the top, ▼ at the bottom,
    a track with a thumb between them (`up`, `down`, `track`); the words stay left of it."""

    def __init__(self, area, font: str = "segoeui.ttf", size: int = 30, pad: int = 18, column: int = 58):
        self.area = tuple(int(v) for v in area)
        self.font = typeset.font(font, size)
        self.size, self.pad, self.column = size, pad, column
        self.line_height = int(round(size * 1.45))
        self.space = typeset.width(" ", self.font)
        self._widths: dict[str, float] = {}
        x0, y0, x1, y1 = self.area
        cx0, cx1 = x1 - column, x1 - 8
        self.up = (cx0, y0 + 8, cx1, y0 + 58)
        self.down = (cx0, y1 - 58, cx1, y1 - 8)
        self.track = ((cx0 + cx1) // 2 - 3, self.up[3] + 12, (cx0 + cx1) // 2 + 3, self.down[1] - 12)
        self.column_rect = (cx0 - 6, y0, x1, y1)

    @property
    def width(self) -> int:
        return self.area[2] - self.area[0] - 2 * self.pad - self.column

    @property
    def rows(self) -> int:
        """Lines that fit in the area."""
        return max((self.area[3] - self.area[1] - 2 * self.pad) // self.line_height, 1)

    def _w(self, word: str) -> float:
        if word not in self._widths:
            self._widths[word] = typeset.width(word, self.font)
        return self._widths[word]

    def _pieces(self, word: str) -> list[str]:
        """A word wider than a whole line, cut so each piece fits (only such a word is ever split)."""
        out, rest = [], word
        while rest and self._w(rest) > self.width:
            n = len(rest) - 1
            while n > 1 and self._w(rest[:n]) > self.width:
                n -= 1
            out.append(rest[:n])
            rest = rest[n:]
        return out + ([rest] if rest else [])

    def lines(self, tokens) -> list[Line]:
        lines, current, x = [], [], 0.0
        for index, token in enumerate(tokens):
            if token in BREAKS:
                lines.append(Line(tuple(current)))
                if token == NEW_PARAGRAPH:
                    lines.append(Line(()))
                current, x = [], 0.0
                continue
            for piece in self._pieces(token):
                w = self._w(piece)
                if current and x + self.space + w > self.width:
                    lines.append(Line(tuple(current)))
                    current, x = [], 0.0
                if current:
                    x += self.space
                current.append((int(round(x)), piece, index))
                x += w
        lines.append(Line(tuple(current)))
        return lines

    def visible(self, lines: list[Line], scroll: int = 0) -> tuple[int, list[Line]]:
        """(index of the first line shown, the lines shown): the end of the text, `scroll` lines back from it."""
        first = max(len(lines) - self.rows - max(scroll, 0), 0)
        return first, lines[first:first + self.rows]

    def max_scroll(self, lines: list[Line]) -> int:
        return max(len(lines) - self.rows, 0)

    def word_boxes(self, tokens, scroll: int = 0) -> list[tuple[int, tuple[int, int, int, int]]]:
        """(token index, its box on the wall) for every word shown (D75 V2: SELECT)."""
        first, shown = self.visible(self.lines(tokens), scroll)
        x0, y0 = self.area[0] + self.pad, self.area[1] + self.pad
        out = []
        for row, line in enumerate(shown):
            top = y0 + row * self.line_height
            for dx, piece, index in line.words:
                out.append((index, (x0 + dx, top, x0 + dx + int(round(self._w(piece))), top + self.line_height)))
        return out


def text_image(tokens, width: int = 1200, font: str = "segoeui.ttf", size: int = 34,
               max_side: int = 1600) -> np.ndarray:
    """D75 V2: typed text for the AI: all its lines (not only those the area shows), black on white, `width` px wide;
    a very long text is reduced so its longer side is at most `max_side`."""
    layout = VoiceLayout((0, 0, width, 10 ** 6), font, size, column=0)
    lines = layout.lines(list(tokens))
    while lines and not lines[-1].words:
        lines.pop()
    h = 2 * layout.pad + max(len(lines), 1) * layout.line_height
    img = np.full((h, width, 3), 255, np.uint8)
    typeset.draw(img, [("text", (layout.pad, layout.pad + row * layout.line_height + layout.line_height // 2),
                        " ".join(p for _, p, _ in line.words), layout.font, (0, 0, 0), "lm")
                       for row, line in enumerate(lines) if line.words])
    if h > max_side:
        import cv2
        scale = max_side / h
        img = cv2.resize(img, (max(int(width * scale), 1), max_side), interpolation=cv2.INTER_AREA)
    return img


def render(img: np.ndarray, text: VoiceText | None, layout: VoiceLayout, *, active: bool, scroll: int = 0,
           selected=(), column: bool = False) -> None:
    """Draw the page's typed text in its area on `img` (in place); while voice writing is on, the area's frame and
    the writing position after the last word. `selected`: token indexes shown highlighted (D75 V2). `column`: the
    scroll column (arrows greyed at an end; the thumb shows which lines are in view)."""
    x0, y0, x1, y1 = layout.area
    ops = []
    if active:
        ops.append(("rrect", (x0, y0, x1, y1), 12, None, FRAME, 2))
    tokens = text.tokens if text is not None else []
    lines = layout.lines(tokens)
    first, shown = layout.visible(lines, scroll)
    if column:
        can_up, can_down = scroll < layout.max_scroll(lines), scroll > 0
        for rect, on in ((layout.up, can_up), (layout.down, can_down)):
            ops.append(("rrect", rect, 10, (255, 255, 255), ARROW_EDGE if on else ARROW_OFF, 2))
        tx0, ty0, tx1, ty1 = layout.track
        ops.append(("rrect", (tx0, ty0, tx1, ty1), 3, TRACK, None))
        n = max(len(lines), 1)
        a = ty0 + (ty1 - ty0) * first / n
        b = ty0 + (ty1 - ty0) * min(first + len(shown), n) / n
        ops.append(("rrect", (tx0, int(a), tx1, max(int(b), int(a) + 8)), 3, THUMB, None))
        for rect, on, point in ((layout.up, can_up, -1), (layout.down, can_down, 1)):
            cx, cy = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
            tri = [(cx - 11, cy - 6 * point), (cx + 11, cy - 6 * point), (cx, cy + 7 * point)]
            ops.append(("poly", tri, CARET if on else ARROW_OFF))
    left, top = x0 + layout.pad, y0 + layout.pad
    chosen = set(selected)
    for row, line in enumerate(shown):
        y = top + row * layout.line_height + layout.line_height // 2
        for dx, piece, index in line.words:
            if index in chosen:
                ops.append(("rrect", (left + dx - 4, y - layout.line_height // 2 + 2,
                                      left + dx + int(round(layout._w(piece))) + 4, y + layout.line_height // 2 - 2),
                            6, (245, 200, 245), None))
        if line.words:
            ops.append(("text", (left, y), " ".join(p for _, p, _ in line.words), layout.font, INK, "lm"))
    if active and first + len(shown) == len(lines):        # the writing position: after the last word
        last = shown[-1] if shown else Line(())
        row = len(shown) - 1 if shown else 0
        cx = left + (last.words[-1][0] + int(round(layout._w(last.words[-1][1]))) + 6 if last.words else 0)
        cy = top + row * layout.line_height
        ops.append(("rrect", (cx, cy + 8, cx + 3, cy + layout.line_height - 8), 1, CARET, None))
    typeset.draw(img, ops)
