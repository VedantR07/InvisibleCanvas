"""Reference documents (brain.md D60): an image (PNG, JPG) or a PDF chosen by the user, shown on the projection for
teaching and for the AI (D61), with its own annotation layer per page. The file is only read, never written.

- An image is decoded from its bytes (works with any Windows path); a PDF is read into memory once (so Windows does
  not lock the file while it is shown) and its pages rendered by PDFium (pypdfium2: free, Apache-2.0 / BSD; only
  imported when a PDF is opened).
- On the wall the page is fitted into the canvas area above the toolbar, aspect ratio kept, centred on white, with
  at least `MARGIN` px of white all round: the setup watch (D58) keeps seeing the projected canvas's outline whatever
  the page shows. The fitted page is rendered once per page and cached.
- Annotations: each page has its own canvas and undo history (as a whiteboard page, D59), drawn over the page and
  never mixed into the file; they are kept with the board file (`to_dict`), and the drawing controller keeps a closed
  document's annotations by its file (`document_key`) for when it is opened again.
- Failures (unsupported type, missing, damaged or protected file, a page that cannot be rendered) raise
  `ReferenceError` with a short message for the wall.
- D72: zoom. 100 % is the page fitted whole (as above, unchanged); at a higher `zoom` the page is drawn larger in
  the window inside the white margin (the margin stays white: D58), at `origin` (where the page's top-left lies on
  the wall; None: centred across, from the top). Page coordinates are the wall px of the page fitted whole, so the
  annotations (kept in them) stay on the same words at every zoom; `view` converts between the two. A zoom keeps the
  window's centre on the same place of the page; a page turn keeps the zoom and starts at the top.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .board import Page
from .model import Canvas

SUPPORTED = {".png": "image", ".jpg": "image", ".jpeg": "image", ".pdf": "pdf"}
MARGIN = 12            # projector px of white around the page (the setup watch sees the canvas edge, D58)
AI_MAX_SIDE = 1600     # px: the longer side of the page image the AI reads (D61)
POINTS_PER_INCH = 72.0
ZOOMS = (1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0)     # D72: of the page fitted whole


class ReferenceError(Exception):
    """A reference that cannot be opened or shown; the message is for the wall."""


@dataclass(frozen=True)
class PageView:
    """D72: where the shown page lies on the wall. Page coordinates (the wall px of the page fitted whole, where the
    annotations are kept) to wall px: wall = (p - page) * scale + origin; the page is seen only inside `window`."""
    scale: float
    page: tuple[int, int]                  # the fitted page's top-left, in page coordinates
    origin: tuple[int, int]                # where that corner lies on the wall
    size: tuple[int, int]                  # the page's size on the wall at this zoom
    window: tuple[int, int, int, int]      # x0, y0, x1, y1: inside the white margin, above the toolbar

    @property
    def identity(self) -> bool:
        return self.scale == 1.0 and self.page == self.origin

    def to_wall(self, points) -> np.ndarray:
        a = np.asarray(points, dtype=np.float64)
        return (a - self.page) * self.scale + self.origin

    def to_page(self, point) -> tuple[float, float]:
        return ((point[0] - self.origin[0]) / self.scale + self.page[0],
                (point[1] - self.origin[1]) / self.scale + self.page[1])


def document_key(path) -> str:
    """The same file whatever the path's spelling (Windows paths ignore case)."""
    return os.path.normcase(os.path.abspath(path))


def annotations_dict(annotations: dict[int, Page]) -> dict:
    """Annotation layers for a file: {page index: canvas}, only the pages with ink."""
    return {str(k): p.canvas.to_dict() for k, p in annotations.items() if p.canvas.strokes}


def annotations_from(d: dict, count: int | None = None) -> dict[int, Page]:
    return {int(k): Page(Canvas.from_dict(c)) for k, c in d.items() if count is None or 0 <= int(k) < count}


class Reference:
    def __init__(self, path: Path, kind: str, count: int, *, image: np.ndarray | None = None, document=None):
        self.path, self.kind, self.count = Path(path), kind, count
        self.current = 0
        self._image, self._document = image, document
        self._display: dict[tuple, np.ndarray] = {}
        self._fit: tuple | None = None                   # (key, the page fitted whole, x0, y0)
        self._zoomed: tuple | None = None                # D72: (key, the page drawn at the zoom)
        self.annotations: dict[int, Page] = {}
        self.zoom = 1.0                                  # D72: one of ZOOMS
        self.origin: tuple[int, int] | None = None       # D72: the page's top-left on the wall; None: from the top

    # -- opening ------------------------------------------------------------------------------------------------

    @classmethod
    def open(cls, path) -> Reference:
        path = Path(path)
        kind = SUPPORTED.get(path.suffix.lower())
        if kind is None:
            raise ReferenceError(f"{path.name}: only PNG, JPG and PDF files can be opened.")
        if not path.is_file():
            raise ReferenceError(f"{path.name}: file not found.")
        if kind == "image":
            image = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                raise ReferenceError(f"{path.name}: the image could not be read (damaged, or not an image).")
            return cls(path, "image", 1, image=image)
        try:
            import pypdfium2 as pdfium
        except ImportError:
            raise ReferenceError("PDF support is not installed (pip install pypdfium2).") from None
        try:                                             # from its bytes: the file is read once, never locked
            document = pdfium.PdfDocument(path.read_bytes())
            count = len(document)
        except Exception:                                # PDFium raises its own errors for damaged / protected files
            raise ReferenceError(f"{path.name}: the PDF could not be opened (damaged or password protected).") from None
        if count < 1:
            raise ReferenceError(f"{path.name}: the PDF has no pages.")
        return cls(path, "pdf", count, document=document)

    @property
    def key(self) -> str:
        return document_key(self.path)

    def close(self) -> None:
        if self._document is not None:
            self._document.close()
            self._document = None

    # -- pages --------------------------------------------------------------------------------------------------

    @property
    def can_previous(self) -> bool:
        return self.current > 0

    @property
    def can_next(self) -> bool:
        return self.current < self.count - 1

    def previous(self) -> bool:
        if not self.can_previous:
            return False
        self.current -= 1
        self.origin = None                               # D72: the same zoom, from the top of the page
        return True

    def next(self) -> bool:
        if not self.can_next:
            return False
        self.current += 1
        self.origin = None
        return True

    def label(self) -> str:
        """For the wall and the AI panel: what is shown."""
        return f"PDF page {self.current + 1} of {self.count}" if self.kind == "pdf" else "Image"

    def page_image(self, max_side: int) -> np.ndarray:
        """The current page as a BGR image whose longer side is at most `max_side` px (an image is never enlarged
        here; a PDF page is rendered at that size)."""
        if self.kind == "image":
            h, w = self._image.shape[:2]
            scale = min(max_side / max(w, h), 1.0)
            if scale >= 1.0:
                return self._image
            return cv2.resize(self._image, (max(int(round(w * scale)), 1), max(int(round(h * scale)), 1)),
                              interpolation=cv2.INTER_AREA)
        try:
            page = self._document[self.current]
            w_pt, h_pt = page.get_size()
            bitmap = page.render(scale=max_side / max(w_pt, h_pt))
            image = np.ascontiguousarray(bitmap.to_numpy()[:, :, :3])
        except Exception:
            raise ReferenceError(f"{self.path.name}: page {self.current + 1} could not be rendered.") from None
        return image

    def _fitted(self, size: tuple[int, int], area_height: int) -> tuple[np.ndarray, int, int]:
        """The current page fitted whole into the canvas area (above the toolbar), aspect kept, with at least MARGIN
        px of white all round, and its top-left on the wall. Cached for the shown page."""
        key = (self.current, size, area_height)
        if self._fit is None or self._fit[0] != key:
            w, _ = size
            box_w, box_h = w - 2 * MARGIN, area_height - 2 * MARGIN
            page = self.page_image(max(box_w, box_h))
            ph, pw = page.shape[:2]
            scale = min(box_w / pw, box_h / ph)
            fw, fh = max(int(round(pw * scale)), 1), max(int(round(ph * scale)), 1)
            fitted = cv2.resize(page, (fw, fh), interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
            self._fit = (key, fitted, (w - fw) // 2, (area_height - fh) // 2)
        return self._fit[1:]

    def display(self, size: tuple[int, int], area_height: int) -> np.ndarray:
        """The projector image of the current page on white: fitted whole at 100 %, else (D72) the page at its zoom
        seen through the window inside the white margin. Cached for the page, zoom and place shown."""
        view = self.view(size, area_height)
        key = (self.current, size, area_height, view.scale, view.origin)
        if key not in self._display:
            w, h = size
            out = np.full((h, w, 3), 255, np.uint8)
            if view.identity:
                fitted, x0, y0 = self._fitted(size, area_height)
                fh, fw = fitted.shape[:2]
                out[y0:y0 + fh, x0:x0 + fw] = fitted
            else:
                page, (ox, oy) = self._page_at(view, size, area_height), view.origin
                wx0, wy0, wx1, wy1 = view.window
                sx0, sy0 = max(wx0 - ox, 0), max(wy0 - oy, 0)              # the part of the page in the window
                sx1, sy1 = min(wx1 - ox, page.shape[1]), min(wy1 - oy, page.shape[0])
                if sx1 > sx0 and sy1 > sy0:
                    out[oy + sy0:oy + sy1, ox + sx0:ox + sx1] = page[sy0:sy1, sx0:sx1]
            self._display = {key: out}                       # only the shown page is kept
        return self._display[key]

    # -- zoom (D72) ---------------------------------------------------------------------------------------------

    def view(self, size: tuple[int, int], area_height: int) -> PageView:
        """Where the current page lies on the wall at its zoom (see PageView)."""
        fitted, x0, y0 = self._fitted(size, area_height)
        fh, fw = fitted.shape[:2]
        page_size = (max(int(round(fw * self.zoom)), 1), max(int(round(fh * self.zoom)), 1))
        window = (MARGIN, MARGIN, size[0] - MARGIN, area_height - MARGIN)
        return PageView(self.zoom, (x0, y0), self._clamp(self.origin, page_size, window), page_size, window)

    @staticmethod
    def _clamp(origin, page_size, window) -> tuple[int, int]:
        """The page's top-left on the wall: centred where the page is smaller than the window; where it is larger,
        kept so it still covers the window (None: centred across, from the top)."""
        out = []
        for k in (0, 1):
            lo, hi, n = window[k], window[k + 2], page_size[k]
            centred = lo + (hi - lo - n) // 2
            if n <= hi - lo:
                out.append(centred)
            else:
                v = origin[k] if origin is not None else (centred if k == 0 else lo)
                out.append(int(min(max(v, hi - n), lo)))
        return out[0], out[1]

    def _page_at(self, view: PageView, size: tuple[int, int], area_height: int) -> np.ndarray:
        """The current page drawn at the zoom (cached for the page and zoom shown): a PDF page rendered at least that
        large, an image enlarged."""
        key = (self.current, size, area_height, view.scale)
        if self._zoomed is None or self._zoomed[0] != key:
            zw, zh = view.size
            source = self.page_image(max(size[0] - 2 * MARGIN, area_height - 2 * MARGIN, zw, zh))
            interpolation = cv2.INTER_AREA if zw < source.shape[1] else cv2.INTER_LINEAR
            self._zoomed = (key, cv2.resize(source, (zw, zh), interpolation=interpolation))
        return self._zoomed[1]

    @property
    def can_zoom_in(self) -> bool:
        return self.zoom < ZOOMS[-1]

    @property
    def can_zoom_out(self) -> bool:
        return self.zoom > ZOOMS[0]

    def set_zoom(self, zoom: float, size: tuple[int, int], area_height: int) -> bool:
        """Zoom to `zoom` (1.0: the page whole) keeping the window's centre on the same place of the page."""
        if zoom == self.zoom:
            return False
        before = self.view(size, area_height)
        wx0, wy0, wx1, wy1 = before.window
        cx, cy = (wx0 + wx1) / 2, (wy0 + wy1) / 2
        px, py = before.to_page((cx, cy))
        self.zoom = zoom
        if zoom == 1.0:
            self.origin = None
        else:
            self.origin = (int(round(cx - (px - before.page[0]) * zoom)), int(round(cy - (py - before.page[1]) * zoom)))
            self.origin = self.view(size, area_height).origin
        return True

    def zoom_in(self, size: tuple[int, int], area_height: int) -> bool:
        larger = [z for z in ZOOMS if z > self.zoom]
        return bool(larger) and self.set_zoom(larger[0], size, area_height)

    def zoom_out(self, size: tuple[int, int], area_height: int) -> bool:
        smaller = [z for z in ZOOMS if z < self.zoom]
        return bool(smaller) and self.set_zoom(smaller[-1], size, area_height)

    def place(self, origin, size: tuple[int, int], area_height: int) -> bool:
        """Put the zoomed page's top-left at `origin` on the wall (as far as the page still covers the window)."""
        view = self.view(size, area_height)
        placed = self._clamp((int(round(origin[0])), int(round(origin[1]))), view.size, view.window)
        if placed == view.origin:
            return False
        self.origin = placed
        return True

    def ai_png(self) -> bytes:
        """The current page for the AI (D61): PNG, longer side at most AI_MAX_SIDE px."""
        ok, buf = cv2.imencode(".png", self.page_image(AI_MAX_SIDE))
        if not ok:
            raise ReferenceError(f"{self.path.name}: the page could not be prepared for the AI.")
        return buf.tobytes()

    # -- annotations --------------------------------------------------------------------------------------------

    def annotation(self, size: tuple[int, int]) -> Page:
        """The current page's annotation layer (its own canvas and undo history)."""
        if self.current not in self.annotations:
            self.annotations[self.current] = Page(Canvas(size))
        return self.annotations[self.current]

    def to_dict(self) -> dict:
        return {"path": str(self.path), "page": self.current, "annotations": annotations_dict(self.annotations),
                "zoom": self.zoom, "origin": None if self.origin is None else list(self.origin)}     # D72

    @classmethod
    def from_dict(cls, d: dict) -> Reference:
        ref = cls.open(d["path"])
        ref.current = min(max(int(d.get("page", 0)), 0), ref.count - 1)
        ref.annotations = annotations_from(d.get("annotations", {}), ref.count)
        zoom, origin = d.get("zoom", 1.0), d.get("origin")            # D72 (a board saved before it: 100 %)
        if zoom in ZOOMS and zoom != 1.0:
            ref.zoom = float(zoom)
            ref.origin = (int(origin[0]), int(origin[1])) if isinstance(origin, list) and len(origin) == 2 else None
        return ref
