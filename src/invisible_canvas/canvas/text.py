"""Typeset text for the projector (brain.md D64): installed Windows TrueType fonts (Segoe UI) through Pillow, which
draws any Unicode text, unlike OpenCV's Hershey fonts (ASCII only). Used where text is read on the wall (Smart Lines
notes and their review bar); drawing happens only when that content changes (the result is cached by the caller).

A font is looked up in the Windows font folder unless an absolute path is given; a missing font falls back to
Pillow's built-in one, so the wall still shows the text.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONT_DIR = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"


def font_path(name: str) -> Path:
    return Path(name) if Path(name).is_absolute() else FONT_DIR / name


@lru_cache(maxsize=32)
def font(name: str, size: int):
    try:
        return ImageFont.truetype(str(font_path(name)), int(size))
    except OSError:
        return ImageFont.load_default(int(size))


def available(name: str) -> bool:
    return font_path(name).is_file()


def width(text: str, f) -> float:
    return f.getlength(text)


def _longest(n: int, fits) -> int:
    """The largest k in 0..n with fits(k) (fits is monotonic: true up to some k), by bisection."""
    lo, hi = 0, n
    while lo < hi:
        mid = (lo + hi + 1) // 2
        lo, hi = (mid, hi) if fits(mid) else (lo, mid - 1)
    return lo


def fit(text: str, f, max_width: float) -> str:
    """`text`, shortened with '...' so that it is at most `max_width` px wide in `f`."""
    if width(text, f) <= max_width:
        return text
    k = _longest(len(text), lambda k: width(text[:k] + "...", f) <= max_width)
    return text[:k].rstrip() + "..."


def fit_end(text: str, f, max_width: float) -> str:
    """`text`, shortened at its start with '...' so that its end stays in view (text being typed)."""
    if width(text, f) <= max_width:
        return text
    k = _longest(len(text), lambda k: width("..." + text[len(text) - k:], f) <= max_width)
    return "..." + text[len(text) - k:]


def _rgb(bgr):
    return None if bgr is None else (int(bgr[2]), int(bgr[1]), int(bgr[0]))


def _bounds(op) -> tuple[float, float, float, float]:
    if op[0] == "text":
        _, (x, y), text, f, _, anchor = op
        left, top, right, bottom = f.getbbox(text, anchor=anchor) if text else (0, 0, 0, 0)
        return x + left, y + top, x + right, y + bottom
    if op[0] == "rrect":
        return op[1]
    xs, ys = [p[0] for p in op[1]], [p[1] for p in op[1]]
    return min(xs), min(ys), max(xs), max(ys)


def draw(img: np.ndarray, ops) -> None:
    """Draw on a BGR image in place, in order. ops:
    ("text", (x, y), text, font, bgr, anchor)          anchor as Pillow's ("la" top left, "lm" left middle, ...)
    ("rrect", (x0, y0, x1, y1), radius, fill_bgr | None, outline_bgr | None[, outline_px])   (default 1 px)
    ("poly", [(x, y), ...], fill_bgr)
    Each one goes through Pillow on its own small region only: a whole 1280 x 720 frame there and back costs
    ~7 ms, a line of text ~0.1 ms."""
    h, w = img.shape[:2]
    for op in ops:
        x0, y0, x1, y1 = _bounds(op)
        x0, y0 = max(int(x0) - 2, 0), max(int(y0) - 2, 0)
        x1, y1 = min(int(x1) + 3, w), min(int(y1) + 3, h)
        if x0 >= x1 or y0 >= y1:
            continue
        region = img[y0:y1, x0:x1]
        pil = Image.fromarray(np.ascontiguousarray(region[:, :, ::-1]))
        d = ImageDraw.Draw(pil)
        if op[0] == "text":
            _, (x, y), text, f, bgr, anchor = op
            d.text((x - x0, y - y0), text, font=f, fill=_rgb(bgr), anchor=anchor)
        elif op[0] == "rrect":
            (rx0, ry0, rx1, ry1), radius, fill, outline = op[1:5]
            d.rounded_rectangle((rx0 - x0, ry0 - y0, rx1 - x0, ry1 - y0), radius=radius, fill=_rgb(fill),
                                outline=_rgb(outline), width=op[5] if len(op) > 5 else 1)
        else:
            _, points, fill = op
            d.polygon([(px - x0, py - y0) for px, py in points], fill=_rgb(fill))
        region[:] = np.asarray(pil)[:, :, ::-1]
