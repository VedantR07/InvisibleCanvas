"""Images shown on the projector (projector pixels; BGR uint8).

Pixel centres are at integer coordinates. Targets are drawn with odd line widths
so they are symmetric about the target pixel.
"""

from __future__ import annotations

import cv2
import numpy as np

WHITE = (255, 255, 255)
GREY = (140, 140, 140)
DIM = (70, 70, 70)
FAINT = (35, 35, 35)
GREEN = (0, 220, 0)
YELLOW = (0, 230, 255)
RED = (0, 0, 255)
ORANGE = (0, 140, 255)
CYAN = (255, 230, 0)
FONT = cv2.FONT_HERSHEY_SIMPLEX


def blank(size: tuple[int, int], value: int = 0) -> np.ndarray:
    w, h = size
    return np.full((h, w, 3), value, dtype=np.uint8)


def text(img: np.ndarray, message: str, org: tuple[int, int], color=GREY, scale: float = 0.6, thickness: int = 1) -> None:
    cv2.putText(img, message, (int(org[0]), int(org[1])), FONT, scale, color, thickness, cv2.LINE_AA)


def centered_text(img: np.ndarray, message: str, y: int, color=GREY, scale: float = 0.7, *, box: bool = False) -> None:
    """Horizontally centred text; `box` puts a black background behind it for legibility."""
    (tw, th), baseline = cv2.getTextSize(message, FONT, scale, 1)
    x = (img.shape[1] - tw) // 2
    if box:
        cv2.rectangle(img, (x - 8, y - th - 8), (x + tw + 8, y + baseline + 6), (0, 0, 0), -1)
    text(img, message, (x, y), color, scale)


def _line_pairs(img: np.ndarray, x0: int, y0: int, size: int = 48) -> None:
    """Alternating 1-px stripes. They look sharp only if the image reaches the panel 1:1."""
    img[y0:y0 + 2 * size + 8, x0:x0 + size] = 0                    # clear (no grid lines through it)
    img[y0:y0 + size, x0:x0 + size:2] = WHITE                      # vertical stripes
    img[y0 + size + 8:y0 + 2 * size + 8:2, x0:x0 + size] = WHITE  # horizontal stripes


def alignment_pattern(size: tuple[int, int]) -> np.ndarray:
    """Checks fullscreen placement, overscan and 1:1 pixel mapping."""
    w, h = size
    img = blank(size)
    img[:, ::80] = FAINT
    img[::80, :] = FAINT
    cx, cy = (w - 1) // 2, (h - 1) // 2
    for x0, y0 in ((24, 24), (w - 72, 24), (24, h - 128), (w - 72, h - 128), (cx - 160, cy - 52), (cx + 112, cy - 52)):
        _line_pairs(img, x0, y0)
    cv2.line(img, (cx - 40, cy), (cx + 40, cy), GREY, 1)
    cv2.line(img, (cx, cy - 40), (cx, cy + 40), GREY, 1)
    # 1-px border on the outermost pixels: all four sides must be visible on the wall.
    img[0, :] = img[-1, :] = WHITE
    img[:, 0] = img[:, -1] = WHITE
    text(img, "(0,0)", (90, 40))
    text(img, f"({w - 1},0)", (w - 200, 40))
    text(img, f"(0,{h - 1})", (90, h - 20))
    text(img, f"({w - 1},{h - 1})", (w - 230, h - 20))
    centered_text(img, f"{w} x {h}", cy - 70, WHITE, 1.0)
    centered_text(img, "The 1-px white border must be visible on all four sides.", cy + 150)
    centered_text(img, "Striped squares must look like fine stripes, not grey or moire.", cy + 180)
    centered_text(img, "SPACE: next screen   ESC: quit", cy + 220, DIM, 0.55)
    return img


def _symmetric_ring(img: np.ndarray, x: int, y: int, radius: int, color, thickness: int) -> None:
    """A circle mirrored in both axes: cv2.circle alone is rasterised slightly off-centre,
    which would bias the target's centroid (matters for Phase 1B detection)."""
    half = radius + thickness
    n = 2 * half + 1
    mask = np.zeros((n, n), dtype=np.uint8)
    cv2.circle(mask, (half, half), radius, 255, thickness, cv2.LINE_8)
    mask |= mask[::-1, :]
    mask |= mask[:, ::-1]
    h, w = img.shape[:2]
    x0, y0 = x - half, y - half
    sx0, sy0, sx1, sy1 = max(x0, 0), max(y0, 0), min(x0 + n, w), min(y0 + n, h)
    if sx0 >= sx1 or sy0 >= sy1:
        return
    region = mask[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0] > 0
    img[sy0:sy1, sx0:sx1][region] = color


def draw_target(img: np.ndarray, center, *, active: bool, label: str | None = None) -> None:
    """Calibration/validation target: a cross (3-px arms) centred on an integer pixel."""
    x, y = int(round(center[0])), int(round(center[1]))
    color = WHITE if active else DIM
    arm = 26 if active else 14
    cv2.line(img, (x - arm, y), (x + arm, y), color, 3, cv2.LINE_8)
    cv2.line(img, (x, y - arm), (x, y + arm), color, 3, cv2.LINE_8)
    if active:
        _symmetric_ring(img, x, y, 36, color, 3)  # fits inside the canvas at the default 6 % inset
    if label:
        w = img.shape[1]
        tx = x + 46 if x < w - 260 else x - 244
        text(img, label, (tx, y - 10 if y > 40 else y + 30), color, 0.6)


def draw_crosshair(img: np.ndarray, center, color=CYAN, *, gap: int = 5, arm: int = 26, thickness: int = 3) -> None:
    """Pointer crosshair with an open centre and a 1-px dot on the exact point."""
    x, y = int(round(center[0])), int(round(center[1]))
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        cv2.line(img, (x + dx * gap, y + dy * gap), (x + dx * arm, y + dy * arm), color, thickness, cv2.LINE_8)
    if 0 <= y < img.shape[0] and 0 <= x < img.shape[1]:
        img[y, x] = color


def dark_canvas(size: tuple[int, int], step: int = 160) -> np.ndarray:
    img = blank(size)
    img[:, ::step] = FAINT
    img[::step, :] = FAINT
    img[0, :] = img[-1, :] = DIM
    img[:, 0] = img[:, -1] = DIM
    return img


def target_screen(size, targets, active: int, labels=None, *, show_others: bool = True, title: str = "") -> np.ndarray:
    """One active target (bright) and, optionally, the other targets (dim)."""
    img = blank(size)
    for i, t in enumerate(targets):
        if i == active:
            continue
        if show_others:
            draw_target(img, t, active=False)
    draw_target(img, targets[active], active=True, label=labels[active] if labels else None)
    if title:
        centered_text(img, title, img.shape[0] // 2, DIM, 0.6)
    return img


def error_map(size, truth: np.ndarray, measured: np.ndarray, errors: np.ndarray, *,
              scale: float = 10.0, limits: tuple[float, float] = (5.0, 12.0), caption: str = "") -> np.ndarray:
    """Truth points with error vectors magnified `scale` times, colored by size."""
    img = dark_canvas(size)
    mean_limit, max_limit = limits
    for (tx, ty), (mx, my), e in zip(truth, measured, errors):
        color = GREEN if e <= mean_limit else (ORANGE if e <= max_limit else RED)
        start = (int(round(tx)), int(round(ty)))
        if np.all(np.isfinite([mx, my])):
            end = (int(round(tx + scale * (mx - tx))), int(round(ty + scale * (my - ty))))
            cv2.arrowedLine(img, start, end, color, 2, cv2.LINE_AA, tipLength=0.2)
        cv2.circle(img, start, 4, WHITE, -1)
        text(img, f"{e:.1f}", (start[0] + 8, start[1] - 8), color, 0.5)
    if caption:
        centered_text(img, caption, int(size[1] * 0.8), WHITE, 0.6, box=True)
    centered_text(img, f"error vectors magnified x{scale:g}; green <= {mean_limit:g} px, "
                       f"orange <= {max_limit:g} px, red above", int(size[1] * 0.2), GREY, 0.55, box=True)
    return img
