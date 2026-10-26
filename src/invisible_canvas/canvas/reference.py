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
"""

from __future__ import annotations

import os
from pathlib import Path

import cv2
import numpy as np

from .board import Page
from .model import Canvas

SUPPORTED = {".png": "image", ".jpg": "image", ".jpeg": "image", ".pdf": "pdf"}
MARGIN = 12            # projector px of white around the page (the setup watch sees the canvas edge, D58)
AI_MAX_SIDE = 1600     # px: the longer side of the page image the AI reads (D61)
POINTS_PER_INCH = 72.0


class ReferenceError(Exception):
    """A reference that cannot be opened or shown; the message is for the wall."""


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
        self.annotations: dict[int, Page] = {}

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
        return True

    def next(self) -> bool:
        if not self.can_next:
            return False
        self.current += 1
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

    def display(self, size: tuple[int, int], area_height: int) -> np.ndarray:
        """The projector image of the current page: fitted into the canvas area (above the toolbar), aspect kept,
        centred on white with at least MARGIN px of white all round. Cached per page."""
        key = (self.current, size, area_height)
        if key not in self._display:
            w, h = size
            box_w, box_h = w - 2 * MARGIN, area_height - 2 * MARGIN
            page = self.page_image(max(box_w, box_h))
            ph, pw = page.shape[:2]
            scale = min(box_w / pw, box_h / ph)
            fw, fh = max(int(round(pw * scale)), 1), max(int(round(ph * scale)), 1)
            fitted = cv2.resize(page, (fw, fh), interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
            out = np.full((h, w, 3), 255, np.uint8)
            x0, y0 = (w - fw) // 2, (area_height - fh) // 2
            out[y0:y0 + fh, x0:x0 + fw] = fitted
            self._display = {key: out}                       # only the shown page is kept
        return self._display[key]

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
        return {"path": str(self.path), "page": self.current, "annotations": annotations_dict(self.annotations)}

    @classmethod
    def from_dict(cls, d: dict) -> Reference:
        ref = cls.open(d["path"])
        ref.current = min(max(int(d.get("page", 0)), 0), ref.count - 1)
        ref.annotations = annotations_from(d.get("annotations", {}), ref.count)
        return ref
