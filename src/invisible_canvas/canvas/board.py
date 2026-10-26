"""Whiteboard pages (brain.md D59). Pure: no I/O besides (de)serialisation.

A board is an ordered list of pages; each page has its own canvas (strokes) and its own undo history, so
drawing, erasing, moving, clearing, undo and redo always act on the page that is shown and never on another.
A new page is inserted after the current one, blank, and becomes current. The board file keeps every page's
strokes and which page was current; a single-canvas file (`canvas-*.json`, before D59) loads as one page.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .history import History
from .model import Canvas

FORMAT = "invisible-canvas/board"
VERSION = 1


@dataclass
class Page:
    canvas: Canvas
    history: History = field(default_factory=History)


class Board:
    def __init__(self, size: tuple[int, int], first: Canvas | None = None, history: History | None = None):
        self.size = (int(size[0]), int(size[1]))
        self.pages: list[Page] = [Page(first or Canvas(self.size), history or History())]
        self.current = 0

    @property
    def page(self) -> Page:
        return self.pages[self.current]

    @property
    def count(self) -> int:
        return len(self.pages)

    @property
    def can_previous(self) -> bool:
        return self.current > 0

    @property
    def can_next(self) -> bool:
        return self.current < len(self.pages) - 1

    def label(self) -> str:
        return f"Page {self.current + 1} of {len(self.pages)}"

    def add_page(self) -> int:
        """A blank page after the current one; it becomes current. Returns its index."""
        self.pages.insert(self.current + 1, Page(Canvas(self.size)))
        self.current += 1
        return self.current

    def previous(self) -> bool:
        if not self.can_previous:
            return False
        self.current -= 1
        return True

    def next(self) -> bool:
        if not self.can_next:
            return False
        self.current += 1
        return True

    def to_dict(self) -> dict:
        return {"format": FORMAT, "version": VERSION, "size": list(self.size), "current": self.current,
                "pages": [p.canvas.to_dict() for p in self.pages]}

    @classmethod
    def from_dict(cls, d: dict) -> Board:
        """A board file, or a single canvas file (one page). Undo histories start empty."""
        if d.get("format") == FORMAT:
            if d.get("version") != VERSION or not d.get("pages"):
                raise ValueError("not a readable Invisible Canvas board file (version / pages)")
            canvases = [Canvas.from_dict(p) for p in d["pages"]]
            board = cls(tuple(d["size"]), canvases[0])
            board.pages += [Page(c) for c in canvases[1:]]
            board.current = min(max(int(d.get("current", 0)), 0), len(board.pages) - 1)
            return board
        canvas = Canvas.from_dict(d)                     # raises on anything else
        return cls(canvas.size, canvas)
