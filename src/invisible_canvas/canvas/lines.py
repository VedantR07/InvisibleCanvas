"""Smart Lines (brain.md D62, D64): numbered lines of handwriting on a whiteboard page, and what they say. Pure model
and layout; the notes area and the Smart Lines controls are drawn for the projector here (`render_sheet`,
`render_controls`), each cached until what it shows changes.

- The LINES tool writes into a fixed writing zone (D64: corner guides, a baseline, "Write here"; D66: drawn darker
  for the wall, and ink only inside it). What is
  written there is the page's unfinished line: its own canvas, kept when the tool or the page changes, saved with the
  board.
- DONE (D62's COMPLETE LINE) turns the unfinished line into a completed line: its strokes are moved unchanged (same
  ids, points, colours and widths) into a `Line` with a stable id. A line's number is its position in the page's list.
- D64: each completed line is read by the local vision model in the background, as two texts: `written` (a literal
  transcription) and `text` (the same line with contextual spelling corrections). Nothing is accepted on its own:
  the teacher's decision (OK = the suggestion, AS WRITTEN = the literal reading, EDIT = typed on the laptop, KEEP INK
  = the handwriting) is an undoable command, and RETRY reads the line again. A line's `status` follows from its
  reading and decision: recognizing, check (a suggestion waits for OK), failed, confirmed or ink.
- The notes area shows each line by its status: confirmed text typeset (Segoe UI, through Pillow), a suggestion in
  blue, otherwise the handwriting itself scaled to the line height; when the lines no longer fit, it scrolls.
- One undo history per page for Smart Lines (the unfinished line's strokes, DONE and the review decisions), apart
  from the page's freehand history, so undo never mixes the two. No decision or reading ever changes the strokes.
- D65: while a panel is open at the right, the buttons it would cover stand left of it (`LinesLayout.beside`).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from . import text as typeset
from .history import Command, History
from .model import Canvas, Stroke
from .toolbar import Button

FORMAT = "invisible-canvas/smart-lines"
VERSION = 2                                # D64: + each line's reading and the teacher's decision (1 still loads)
NUMBERING = {"1.": "{n}.", "1)": "{n})", "(1)": "({n})", "none": ""}
DEFAULT_ZONE = (40, 400, 1040, 590)        # x0, y0, x1, y1 projector px: the writing zone (middle height, D62)
DEFAULT_NOTES = (40, 40, 900, 336)         # the notes area: below the page label, left of the board panel
DEFAULT_FONT, DEFAULT_TEXT_SIZE = "segoeui.ttf", 30
SEMIBOLD = {"segoeui.ttf": "seguisb.ttf"}  # the review bar's text and the button labels
DECISIONS = ("ok", "as_written", "edit", "ink")
TEXT_MAX = 120                             # characters typed with EDIT
REVIEW = ("lines:ok", "lines:written", "lines:edit", "lines:ink", "lines:retry")
LABELS = {"lines:complete": "DONE", "lines:ok": "OK", "lines:written": "AS WRITTEN", "lines:edit": "EDIT",
          "lines:ink": "KEEP INK", "lines:retry": "RETRY"}
REVIEW_WIDTH = {"lines:ok": 64, "lines:written": 136, "lines:edit": 84, "lines:ink": 116, "lines:retry": 96}
BAR_GAP = 60                               # px from the review bar's top to the writing zone
# colours (BGR)
INK = (30, 30, 30)
MUTED = (125, 125, 125)
# D67 (wall test run 2: both too light on the wall): the suggestion's blue darker (RGB 25, 95, 190 -> 10, 60, 160:
# luminance 87 -> 57), still blue beside black (30) and grey ink; the handwriting while it is read darker grey
# (150 -> 105), still well apart from black handwriting and from the blue
SUGGESTION = (160, 60, 10)                 # blue: a suggestion waiting for the teacher's OK
WARN = (0, 120, 200)                       # orange: not recognised
READING_INK = (105, 105, 105)              # the handwriting while it is read (and its "reading..."), or not recognised
# D66: the wall washes light greys out (wall test run 1: 185-235 barely or not visible in the camera frames), so the
# guides and the greyed buttons are darker and thicker than on a screen
GUIDE, GUIDE_PX, GUIDE_LEN = (115, 115, 115), 3, 34    # the writing zone's corner guides
BASELINE = (165, 165, 165)
CAPTION = (110, 110, 110)                  # "Write here"
IDLE_BASELINE, IDLE_INK = (200, 200, 200), (160, 160, 160)   # an unfinished line kept while another tool is in use
REVIEW_ROW = (252, 243, 233)               # the note line the review bar is about
BAR_FILL, BAR_EDGE = (252, 247, 244), (210, 180, 160)
EDIT_FILL, EDIT_EDGE = (240, 250, 252), (150, 210, 230)
TRACK, THUMB = (200, 200, 200), (120, 120, 120)
EDGE, EDGE_OFF, LABEL, LABEL_OFF = (100, 100, 100), (170, 170, 170), (40, 40, 40), (160, 160, 160)
BUTTON_EDGE_PX = 2
PAD = 8


@dataclass(eq=False)
class Line:
    """A completed line: the handwriting as written (never resampled or moved) and a stable id. D64: its latest
    `reading` (set by the recognizer only: {"ok", "written", "text", "error", ...}) and the teacher's `decision`
    ({"kind": ok | as_written | edit | ink, "text"}); `request` is the recognition request awaited (not saved)."""
    id: int
    strokes: list[Stroke]
    reading: dict | None = None
    decision: dict | None = None
    request: int | None = None
    _ink: dict = field(default_factory=dict, repr=False)      # its handwriting drawn small, by (size, colour)

    @property
    def status(self) -> str:
        if self.decision is not None:
            return "ink" if self.decision["kind"] == "ink" else "confirmed"
        if self.reading is None:
            return "recognizing"
        return "check" if self.reading.get("ok") else "failed"

    @property
    def text(self) -> str | None:
        """The text the notes show: the teacher's (confirmed), or the suggestion waiting for OK (check)."""
        if self.decision is not None:
            return self.decision.get("text")
        if self.reading is not None and self.reading.get("ok"):
            return self.reading.get("text") or None
        return None

    def bounds(self) -> tuple[float, float, float, float]:
        b = [s.bounds() for s in self.strokes]
        return min(v[0] for v in b), min(v[1] for v in b), max(v[2] for v in b), max(v[3] for v in b)

    def to_dict(self) -> dict:
        return {"id": self.id, "strokes": [s.to_dict() for s in self.strokes], "reading": self.reading,
                "decision": self.decision}

    @classmethod
    def from_dict(cls, d: dict) -> Line:
        decision = d.get("decision")
        if decision is not None and decision.get("kind") not in DECISIONS:
            raise ValueError(f"unknown Smart Lines decision {decision.get('kind')!r}")
        return cls(int(d["id"]), [Stroke.from_dict(s) for s in d["strokes"]], d.get("reading"), decision)


class LineSheet:
    """A page's Smart Lines: the completed lines (in order), the unfinished line (`canvas`) and their undo
    `history`. `canvas` and `history` make the sheet usable as the layer the pen writes on."""

    def __init__(self, size: tuple[int, int]):
        self.size = (int(size[0]), int(size[1]))
        self.lines: list[Line] = []
        self.canvas = Canvas(self.size)
        self.history = History()
        self.scroll = 0                              # the first completed line shown in the notes area
        self.version = 0                             # lines, their readings / decisions or scroll changed (cache)
        self._next_id = 1
        self._image: dict = {}
        self._notes: tuple | None = None             # (key, image): the notes area alone
        self._zone: tuple | None = None              # (look, strokes drawn, image): the zone alone

    @property
    def has_content(self) -> bool:
        return bool(self.lines or self.canvas.strokes)

    def changed(self) -> None:
        self.version += 1

    def new_line_id(self) -> int:
        i, self._next_id = self._next_id, self._next_id + 1
        return i

    def max_scroll(self, visible: int) -> int:
        return max(len(self.lines) - visible, 0)

    def first_shown(self, visible: int) -> int:
        return min(max(self.scroll, 0), self.max_scroll(visible))

    def scroll_to_end(self, visible: int) -> None:
        if self.scroll != self.max_scroll(visible):
            self.scroll = self.max_scroll(visible)
            self.changed()

    def scroll_by(self, delta: int, visible: int) -> bool:
        """Scroll the notes area by `delta` lines; False at the first / last line."""
        new = min(max(self.first_shown(visible) + delta, 0), self.max_scroll(visible))
        if new == self.first_shown(visible):
            return False
        self.scroll = new
        self.changed()
        return True

    def to_dict(self) -> dict:
        return {"format": FORMAT, "version": VERSION, "next_id": self._next_id, "scroll": self.scroll,
                "lines": [line.to_dict() for line in self.lines],
                "unfinished": [s.to_dict() for s in self.canvas.strokes.values()]}

    @classmethod
    def from_dict(cls, d: dict, size: tuple[int, int]) -> LineSheet:
        if d.get("format") != FORMAT or d.get("version") not in (1, VERSION):
            raise ValueError("not an Invisible Canvas Smart Lines record (format/version)")
        sheet = cls(size)
        sheet.lines = [Line.from_dict(x) for x in d["lines"]]
        for s in d.get("unfinished", []):
            sheet.canvas.add(Stroke.from_dict(s))
        ids = [s.id for line in sheet.lines for s in line.strokes] + list(sheet.canvas.strokes)
        sheet.canvas._next_id = max([sheet.canvas._next_id] + [i + 1 for i in ids])   # stroke ids stay unique
        sheet._next_id = max([int(d.get("next_id", 1))] + [line.id + 1 for line in sheet.lines])
        sheet.scroll = int(d.get("scroll", 0))
        sheet.canvas.version = 0
        return sheet


class CompleteLine(Command):
    """The unfinished line becomes the next completed line (one undo step). The same `Line` (and id) comes back on
    redo, with any reading it got meanwhile."""
    name = "complete line"

    def __init__(self, sheet: LineSheet):
        self.sheet = sheet
        self.line: Line | None = None

    def apply(self, canvas: Canvas) -> None:
        if self.line is None:
            self.line = Line(self.sheet.new_line_id(), list(canvas.strokes.values()))
        for s in self.line.strokes:
            canvas.remove(s.id)
        self.sheet.lines.append(self.line)
        self.sheet.changed()

    def revert(self, canvas: Canvas) -> None:
        self.sheet.lines.remove(self.line)
        for s in self.line.strokes:
            canvas.add(s)
        self.sheet.changed()


class ReviewLine(Command):
    """The teacher's decision on a line (D64), one undo step: OK, AS WRITTEN, EDIT or KEEP INK. A reading still
    awaited for the line is no longer wanted: if it comes, it is ignored."""

    def __init__(self, sheet: LineSheet, line: Line, kind: str, text: str | None = None):
        if kind not in DECISIONS:
            raise ValueError(f"unknown Smart Lines decision {kind!r}")
        self.sheet, self.line, self.name = sheet, line, f"line {kind}"
        self.decision = {"kind": kind, "text": None if kind == "ink" else text}
        self.before = line.decision

    def apply(self, canvas: Canvas) -> None:
        self.line.decision, self.line.request = dict(self.decision), None
        self.sheet.changed()

    def revert(self, canvas: Canvas) -> None:
        self.line.decision = self.before
        self.sheet.changed()


class RetryLine(Command):
    """RETRY (D64), one undo step: the line is read again; its reading and any decision are set aside (both come
    back on undo). A reading still awaited from before is ignored if it comes."""
    name = "retry line"

    def __init__(self, sheet: LineSheet, line: Line):
        self.sheet, self.line = sheet, line
        self.before = (line.reading, line.decision)

    def apply(self, canvas: Canvas) -> None:
        self.line.reading = self.line.decision = self.line.request = None
        self.sheet.changed()

    def revert(self, canvas: Canvas) -> None:
        self.line.reading, self.line.decision = self.before
        self.line.request = None
        self.sheet.changed()


def _check_rect(name: str, rect, w: int, bottom: int) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = (int(v) for v in rect)
    if not (0 <= x0 < x1 <= w and 0 <= y0 < y1 <= bottom):
        raise ValueError(f"Smart Lines {name} {rect} must lie inside the canvas above the toolbar (y <= {bottom})")
    return x0, y0, x1, y1


def _overlap(a, b) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


class Controls:
    """Where the Smart Lines buttons are: DONE, SCROLL UP / DOWN with the scroll track, and the review bar with its
    buttons right-aligned in it (D64). A layout has its own (`LinesLayout.controls`) and, for an open panel, a set
    that keeps clear of it (`LinesLayout.beside`, D65); the note rows never move."""

    def __init__(self, complete, up, down, track, bar, rows):
        self.buttons = [Button("lines:complete", "lines", complete), Button("lines:up", "lines", up),
                        Button("lines:down", "lines", down)]
        self.track, self.bar = track, bar
        x, self.review_buttons = bar[2] - 8, []
        for name in reversed(REVIEW):                # right-aligned: OK, AS WRITTEN, EDIT, KEEP INK, RETRY
            self.review_buttons.insert(0, Button(name, "lines", (x - REVIEW_WIDTH[name], bar[1] + 6, x, bar[3] - 6)))
            x -= REVIEW_WIDTH[name] + 8
        if x < bar[0] + 200:
            raise ValueError("the review bar is too narrow for its buttons")
        self.bar_text_right = x - 4
        self._by_name = {b.name: b for b in self.buttons + self.review_buttons + rows}

    def rects(self) -> list:
        return [b.rect for b in self.buttons] + [self.track, self.bar]

    def hit(self, point) -> Button | None:
        """DONE, SCROLL UP or SCROLL DOWN under the point (the review buttons and note rows depend on what is
        shown: the controller hits those)."""
        if point is None:
            return None
        return next((b for b in self.buttons if b.contains(point)), None)

    def on_control(self, point) -> bool:
        return self.hit(point) is not None

    def in_bar(self, point) -> bool:
        x0, y0, x1, y1 = self.bar
        return point is not None and x0 <= point[0] < x1 and y0 <= point[1] < y1

    def button(self, name: str) -> Button:
        return self._by_name[name]


class LinesLayout:
    """Where Smart Lines sit on the projector canvas (config `[smart_lines]`) and how their text looks: the writing
    zone with DONE at its right, the notes area (one row per line shown) with a slim scroll track and SCROLL UP /
    DOWN at its right, and the review bar between the notes area and the zone (D64). `buttons`, `track`, `bar`,
    `review_buttons` and `bar_text_right` are the layout's own `controls`; `beside(rect)` keeps them clear of an open
    panel (D65)."""

    def __init__(self, size: tuple[int, int], toolbar_top: int, zone=DEFAULT_ZONE, notes=DEFAULT_NOTES,
                 line_height: int = 40, line_spacing: int = 6, numbering: str = "1.", font: str = DEFAULT_FONT,
                 text_size: int = DEFAULT_TEXT_SIZE, margin: int = 16):
        w, _ = int(size[0]), int(size[1])
        self.zone = _check_rect("zone", zone, w, toolbar_top)
        self.notes = _check_rect("notes area", notes, w, toolbar_top)
        if _overlap(self.zone, self.notes):
            raise ValueError("the Smart Lines zone and notes area must not overlap")
        if numbering not in NUMBERING:
            raise ValueError(f"numbering must be one of {', '.join(NUMBERING)}")
        if not 16 <= line_height <= 200 or not 0 <= line_spacing <= 100:
            raise ValueError("line_height must be 16-200 px and line_spacing 0-100 px")
        if not 12 <= text_size <= line_height:
            raise ValueError("text_size must be 12 px or more, and not more than line_height")
        self.line_height, self.line_spacing, self.numbering = int(line_height), int(line_spacing), numbering
        zx0, zy0, zx1, zy1 = self.zone
        nx0, ny0, nx1, ny1 = self.notes
        complete = (zx1 + 24, zy1 - 78, zx1 + 144, zy1 - 22)
        up, down = (nx1 + 16, ny0, nx1 + 56, ny0 + 40), (nx1 + 16, ny1 - 40, nx1 + 56, ny1)
        for name, r in (("DONE", complete), ("SCROLL UP", up), ("SCROLL DOWN", down)):
            if r[2] > w - margin // 2 or r[1] < 0:
                raise ValueError(f"no room for {name} next to the Smart Lines zone / notes area")
        if up[3] > down[1]:
            raise ValueError("the notes area is too short for SCROLL UP / DOWN (at least 80 px)")
        bar = (min(nx0, zx0), zy0 - BAR_GAP, w - 40, zy0 - 8)
        if bar[1] < ny1:
            raise ValueError(f"the review bar needs {BAR_GAP} px between the bottom of the notes area and the "
                             f"top of the writing zone below it")
        step = line_height + line_spacing
        self.visible = max((ny1 - ny0 - 2 * PAD + line_spacing) // step, 1)
        self.rows = [Button(f"lines:row:{k}", "lines", (nx0, ny0 + PAD + k * step, nx1, ny0 + PAD + k * step +
                                                         line_height)) for k in range(self.visible)]
        self.controls = Controls(complete, up, down, (nx1 + 2, ny0 + 2, nx1 + 8, ny1 - 2), bar, self.rows)
        c = self.controls
        self.buttons, self.track, self.bar, self.review_buttons, self.bar_text_right = (
            c.buttons, c.track, c.bar, c.review_buttons, c.bar_text_right)
        self._beside: dict = {}
        self.baseline = zy0 + round((zy1 - zy0) * 0.76)
        self.font, self.text_size = font, int(text_size)
        bold = SEMIBOLD.get(font.lower(), font)
        self.fonts = {"text": typeset.font(font, text_size), "number": typeset.font(font, round(text_size * 0.8)),
                      "small": typeset.font(font, max(round(text_size * 0.57), 12)),
                      "bar": typeset.font(bold, text_size), "label": typeset.font(bold, max(round(text_size * 0.6), 12))}

    def in_zone(self, point) -> bool:
        if point is None:
            return False
        x0, y0, x1, y1 = self.zone
        return x0 <= point[0] < x1 and y0 <= point[1] < y1

    def in_bar(self, point) -> bool:
        return self.controls.in_bar(point)

    def hit(self, point) -> Button | None:
        return self.controls.hit(point)

    def on_control(self, point) -> bool:
        return self.controls.on_control(point)

    def button(self, name: str) -> Button:
        return self.controls.button(name)

    def beside(self, rect) -> Controls:
        """The controls while a panel at the right of the canvas is open over `rect` (D65): DONE, the scroll column
        and the review bar's right end move left of it (16 px apart) when it would cover them; the layout's own
        controls when it covers none. Kept per panel, so a button stays the same object while the panel is open.
        Raises ValueError when there is no room left of the panel."""
        key = tuple(int(v) for v in rect)
        if key not in self._beside:
            self._beside[key] = self._controls_beside(key)
        return self._beside[key]

    def _controls_beside(self, rect) -> Controls:
        c = self.controls
        if not any(_overlap(r, rect) for r in c.rects()):
            return c
        edge = rect[0] - 16
        complete, up, down = (b.rect for b in c.buttons)
        track, bar = c.track, c.bar
        if _overlap(complete, rect):                 # to the right end of the writing zone left uncovered
            complete = (edge - (complete[2] - complete[0]), complete[1], edge, complete[3])
            if complete[0] < self.zone[0] + 200:
                raise ValueError("an open panel would leave too little of the writing zone beside DONE")
        if any(_overlap(r, rect) for r in (up, down, track)):     # to the right end of the notes area
            width = up[2] - up[0]
            up, down = (edge - width, up[1], edge, up[3]), (edge - width, down[1], edge, down[3])
            track = (edge - width - 14, track[1], edge - width - 8, track[3])
            if track[0] < self.notes[0] + 200:
                raise ValueError("an open panel would leave too little of the notes area beside SCROLL UP / DOWN")
        if _overlap(bar, rect):
            bar = (bar[0], bar[1], edge, bar[3])
        return Controls(complete, up, down, track, bar, self.rows)

    def number_label(self, n: int) -> str:
        return NUMBERING[self.numbering].format(n=n)


def _draw_strokes(img: np.ndarray, strokes, scale: float = 1.0, offset=(0.0, 0.0), shift=(0.0, 0.0),
                  colour=None) -> None:
    """Strokes in their own colours (or `colour`); points mapped as (p - offset) * scale + shift."""
    for s in strokes:
        a = np.round((s.array() - offset) * scale + shift).astype(np.int32)
        width = max(int(round(s.width * scale)), 2)
        if len(a) == 1:
            cv2.circle(img, tuple(int(v) for v in a[0]), max(width // 2, 1), colour or s.color, -1, cv2.LINE_AA)
        else:
            cv2.polylines(img, [a], False, colour or s.color, width, cv2.LINE_AA)


def _draw_line_ink(img: np.ndarray, line: Line, box, colour=None) -> int:
    """A line's handwriting scaled into box (x0, y0, x1, y1), aspect kept, left-aligned and vertically centred;
    returns the right end of the ink. The small drawing is kept on the line (thick anti-aliased strokes cost ~0.25
    ms each to draw) and laid over the image darkest-wins, so a highlighted row stays highlighted around the ink."""
    x0, y0, x1, y1 = (int(round(v)) for v in box)
    key = (x1 - x0, y1 - y0, colour)
    if key not in line._ink:
        bx0, by0, bx1, by1 = line.bounds()
        scale = min((y1 - y0) / max(by1 - by0, 1.0), (x1 - x0) / max(bx1 - bx0, 1.0))
        patch = np.full((y1 - y0, x1 - x0, 3), 255, np.uint8)
        _draw_strokes(patch, line.strokes, scale, (bx0, by0), (0, ((y1 - y0) - (by1 - by0) * scale) / 2), colour)
        line._ink.clear()
        line._ink[key] = (patch, int(round((bx1 - bx0) * scale)))
    patch, right = line._ink[key]
    region = img[y0:y1, x0:x1]
    np.minimum(region, patch[:region.shape[0], :region.shape[1]], out=region)
    return x0 + right


def render_sheet(sheet: LineSheet, layout: LinesLayout, show_zone: bool, active: bool = True,
                 review: int | None = None) -> np.ndarray:
    """The page's Smart Lines on white, full projector size: the notes area (numbered lines by status, scrolled;
    `review`: the id of the line the review bar is about, highlighted) and, with `show_zone`, the writing guide with
    the unfinished line (`active`: the LINES tool is in use, else it is drawn fainter). Cached until the sheet, the
    unfinished line or the view changes. The notes and the zone are kept as separate layers and laid together
    darkest-wins: a new stroke draws only itself on the zone layer, a line's new status redraws only the notes."""
    key = (sheet.version, sheet.canvas.version, sheet.scroll, show_zone, active, review, id(layout))
    if key in sheet._image:
        return sheet._image[key]
    img = _notes_image(sheet, layout, review)
    if show_zone:
        img = np.minimum(img, _zone_image(sheet, layout, active))
    sheet._image = {key: img}                        # only the current view is kept
    return img


def _zone_image(sheet: LineSheet, layout: LinesLayout, active: bool) -> np.ndarray:
    """The writing guide and the unfinished line alone on white. A stroke added since the last call is drawn on it
    in place (this layer is never handed out); any other change (undo, erase, move) draws it again."""
    strokes = list(sheet.canvas.strokes.values())
    drawn = [(s.id, len(s.points), s.points[0] if s.points else None, s.points[-1] if s.points else None)
             for s in strokes]
    look, last = (active, id(layout)), sheet._zone
    if last is not None and last[0] == look and last[1] == drawn[:len(last[1])]:
        img = last[2]
        _draw_strokes(img, strokes[len(last[1]):], colour=None if active else IDLE_INK)
    else:
        w, h = sheet.size
        img = np.full((h, w, 3), 255, np.uint8)
        f, ops = layout.fonts, []
        zx0, zy0, zx1, zy1 = layout.zone
        if active:
            inset = GUIDE_PX // 2                    # the corners' lines lie just inside the zone
            for cx, cy, dx, dy in ((zx0 + inset, zy0 + inset, 1, 1), (zx1 - 1 - inset, zy0 + inset, -1, 1),
                                   (zx0 + inset, zy1 - 1 - inset, 1, -1), (zx1 - 1 - inset, zy1 - 1 - inset, -1, -1)):
                cv2.line(img, (cx, cy), (cx + GUIDE_LEN * dx, cy), GUIDE, GUIDE_PX, cv2.LINE_AA)
                cv2.line(img, (cx, cy), (cx, cy + GUIDE_LEN * dy), GUIDE, GUIDE_PX, cv2.LINE_AA)
            cv2.line(img, (zx0 + 30, layout.baseline), (zx1 - 30, layout.baseline), BASELINE, 2, cv2.LINE_AA)
            ops.append(("text", (zx0 + 4, zy1 + 4), "Write here", f["number"], CAPTION, "la"))
        else:
            cv2.line(img, (zx0 + 30, layout.baseline), (zx1 - 30, layout.baseline), IDLE_BASELINE, 2, cv2.LINE_AA)
            ops.append(("text", (zx0 + 4, zy1 + 4), "Unfinished line kept - LINES to continue", f["small"], MUTED,
                        "la"))
        typeset.draw(img, ops)
        _draw_strokes(img, strokes, colour=None if active else IDLE_INK)
    sheet._zone = (look, drawn, img)
    return img


def _notes_image(sheet: LineSheet, layout: LinesLayout, review: int | None) -> np.ndarray:
    """The notes area alone on white (cached on the sheet until a line, its status or the scroll changes)."""
    key = (sheet.version, sheet.scroll, review, id(layout))
    if sheet._notes is not None and sheet._notes[0] == key:
        return sheet._notes[1]
    w, h = sheet.size
    img = np.full((h, w, 3), 255, np.uint8)
    f, ops = layout.fonts, []
    nx0, ny0, nx1, ny1 = layout.notes
    if sheet.lines:
        first = sheet.first_shown(layout.visible)
        shown = sheet.lines[first:first + layout.visible]
        number_w = max(typeset.width(layout.number_label(first + k + 1), f["number"]) for k in range(len(shown)))
        x = nx0 + 16 + number_w + (14 if number_w else 0)
        for k, line in enumerate(shown):
            _, top, _, bottom = layout.rows[k].rect
            cy = (top + bottom) / 2
            if line.id == review:
                cv2.rectangle(img, (nx0 - 4, top - 3), (nx1 - 1, bottom + 2), REVIEW_ROW, -1)
            label = layout.number_label(first + k + 1)
            if label:
                ops.append(("text", (nx0 + 16 + number_w, cy), label, f["number"], MUTED, "rm"))
            status = line.status
            if status in ("confirmed", "check"):
                if status == "check":                                   # waiting for the teacher's OK
                    cv2.circle(img, (nx0 + 5, int(round(cy))), 5, SUGGESTION, -1, cv2.LINE_AA)
                ops.append(("text", (x, cy), typeset.fit(line.text or "", f["text"], nx1 - PAD - x), f["text"],
                            INK if status == "confirmed" else SUGGESTION, "lm"))
            elif status == "ink":
                _draw_line_ink(img, line, (x, top, nx1 - PAD, bottom))
            else:
                note = "reading..." if status == "recognizing" else "not recognised - RETRY or EDIT"
                right = max(x + 40, min(x + 420, int(nx1 - PAD - typeset.width(note, f["small"]) - 12)))
                end = _draw_line_ink(img, line, (x, top + 6, right, bottom - 6), READING_INK)
                ops.append(("text", (end + 12, cy), note, f["small"], READING_INK if status == "recognizing" else WARN,
                            "lm"))
        if len(sheet.lines) > layout.visible:
            ops.append(("text", (nx1 - PAD, ny1), f"{first + 1}-{first + len(shown)} of {len(sheet.lines)}",
                        f["small"], MUTED, "rd"))
    typeset.draw(img, ops)
    sheet._notes = (key, img)
    return img


def _button_ops(rect, origin, label: str, on: bool, f) -> list:
    x0, y0, x1, y1 = (v - o for v, o in zip(rect, origin + origin))
    ops = [("rrect", (x0, y0, x1 - 1, y1 - 1), 8, (255, 255, 255), EDGE if on else EDGE_OFF, BUTTON_EDGE_PX)]
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    if label in ("up", "down"):
        d = -1 if label == "up" else 1
        ops.append(("poly", [(cx - 10, cy - 6 * d), (cx + 10, cy - 6 * d), (cx, cy + 7 * d)],
                    LABEL if on else LABEL_OFF))
    else:
        ops.append(("text", (cx, cy), label, f, LABEL if on else LABEL_OFF, "mm"))
    return ops


def _patch(rect, ops) -> tuple[int, int, np.ndarray]:
    x0, y0, x1, y1 = rect
    img = np.full((y1 - y0, x1 - x0, 3), 255, np.uint8)
    typeset.draw(img, ops)
    return x0, y0, img


_controls: dict = {}


def render_controls(layout: LinesLayout, view, controls: Controls | None = None) -> list[tuple[int, int, np.ndarray]]:
    """The Smart Lines controls while LINES is in use (D64), as opaque patches (x, y, image) the renderer copies over
    the frame: DONE, the scroll track and SCROLL UP / DOWN, and the review bar, where `controls` puts them (D65:
    beside an open panel; default the layout's own). `view` is what they show, from the controller (hashable):
    (enabled button names, first line shown, number of lines, bar), the bar None or (line number, status, main
    text, note, text being typed or None). Cached by it."""
    controls = controls or layout.controls
    key = (id(layout), id(controls), view)
    if key in _controls:
        return _controls[key]
    enabled, first, total, bar = view
    f = layout.fonts
    patches = []
    for b in controls.buttons:
        label = {"lines:up": "up", "lines:down": "down"}.get(b.name, LABELS.get(b.name, ""))
        patches.append(_patch(b.rect, _button_ops(b.rect, b.rect[:2], label, b.name in enabled, f["label"])))
    tx0, ty0, tx1, ty1 = controls.track
    ops = [("rrect", (0, 0, tx1 - tx0 - 1, ty1 - ty0 - 1), 3, TRACK, None)]
    if total > layout.visible:                       # the thumb: which part of the lines is shown
        th = ty1 - ty0
        a, b = round(th * first / total), round(th * (first + layout.visible) / total)
        ops.append(("rrect", (0, a, tx1 - tx0 - 1, max(b - 1, a + 8)), 3, THUMB, None))
    patches.append(_patch(controls.track, ops))
    if bar is not None:
        number, status, main, note, typed = bar
        bx0, by0, bx1, by1 = controls.bar
        bw, bh = bx1 - bx0, by1 - by0
        cy = bh / 2
        if typed is not None:                        # EDIT: typed on the laptop, shown live
            prompt, keys = f"Line {number} - type on the laptop:", "Enter saves   Esc cancels"
            x = 16 + typeset.width(prompt, f["small"]) + 12
            room = bw - 16 - typeset.width(keys, f["small"]) - 24 - x
            ops = [("rrect", (0, 0, bw - 1, bh - 1), 10, EDIT_FILL, EDIT_EDGE),
                   ("text", (16, cy), prompt, f["small"], MUTED, "lm"),
                   ("text", (x, cy), typeset.fit_end(typed + "_", f["bar"], room), f["bar"], INK, "lm"),
                   ("text", (bw - 16, cy), keys, f["small"], MUTED, "rm")]
        else:
            head = f"Line {number}:"
            x, right = 16 + typeset.width(head, f["small"]) + 10, controls.bar_text_right - bx0
            big = status in ("check", "confirmed")
            main_font = f["bar"] if big else f["number"]
            colour = {"check": SUGGESTION, "failed": WARN, "recognizing": MUTED}.get(status, INK)
            main = typeset.fit(main, main_font, right - x)
            ops = [("rrect", (0, 0, bw - 1, bh - 1), 10, BAR_FILL, BAR_EDGE),
                   ("text", (16, cy), head, f["small"], MUTED, "lm"), ("text", (x, cy), main, main_font, colour, "lm")]
            x2 = x + typeset.width(main, main_font) + 12
            if note and right - x2 > 80:
                ops.append(("text", (x2, cy), typeset.fit(note, f["small"], right - x2), f["small"], MUTED, "lm"))
            for b in controls.review_buttons:
                ops += _button_ops(b.rect, (bx0, by0), LABELS[b.name], b.name in enabled, f["label"])
        patches.append(_patch(controls.bar, ops))
    if len(_controls) > 32:
        _controls.clear()
    _controls[key] = patches
    return patches
