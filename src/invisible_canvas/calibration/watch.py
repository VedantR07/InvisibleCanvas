"""In-session setup watch (brain.md D58): did the projector or the camera move during a session? Pure: no I/O.

The setup check (D28, D39) runs only when a tool starts. On 2026-10-27 the projection moved ~85 camera px about
15 s into a `draw` session (the user walking in; the camera did not move) and the cursor sat ~96 projector px
(~10 cm) right of the fingertip for the rest of the session. The projected canvas is in every camera frame, so
about once a second its four corners are found and compared with where the calibration puts them:

- the canvas is the largest bright region of a `WIDTH`-px-wide copy (Otsu threshold); its corners are the convex
  hull's extreme points towards the four diagonals (top-left, top-right, bottom-right, bottom-left);
- a person in front of the projection hides or cuts corners, and moves while doing so: a check counts as "moved"
  only when at least 3 corners moved by `MOVE_PX` or more in agreement (displacements within `AGREE_PX`, or
  `AGREE_REL` of their size: a small rotation spreads them), and a move is reported only after `CONFIRM`
  consecutive checks that agree.

A report is a reason to run the setup check again, which decides: the watch never changes the calibration itself.
Offline on the saved camera frames of 26 recorded `draw` sessions (2026-10-22 ... 10-27, 4,090 frames; people in
front of the projection in most): the 25 without a move gave no report (a single unconfirmed "moved" check in all
of them); the 2026-10-27 00:25 session reported (+88, -2) camera px 2 s after its move. Static agreement with the
calibration: median 3-4 camera px (one session 7).
"""

from __future__ import annotations

import time

import cv2
import numpy as np

WIDTH = 960            # px: the copy the canvas is found in (2 camera px per px at 1920)
EVERY_S = 1.0          # s between checks
MOVE_PX = 8.0          # camera px (~10 projector px, ~1 cm on the 2026-10 wall); static agreement 3-4 px, max 7
AGREE_PX = 10.0        # camera px between the displacements of corners that moved together
AGREE_REL = 0.4        # ... or this fraction of the displacement (a rotation of the projection spreads them)
CONFIRM = 2            # consecutive agreeing checks
MIN_AREA = 0.03        # the canvas region must cover at least this fraction of the frame
MIN_CONTRAST = 25.0    # grey levels between the canvas region and the rest (projected white on the wall: ~60-150)
# Diagonal directions whose extreme hull points are the corners, in the calibration's order: TL, TR, BR, BL.
_DIRECTIONS = np.array([[1, 1], [-1, 1], [-1, -1], [1, -1]], dtype=np.float64)


def canvas_corners(size: tuple[int, int]) -> np.ndarray:
    """The projector canvas's corner pixels, TL, TR, BR, BL."""
    w, h = size
    return np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], dtype=np.float64)


def expected_corners(mapper, size: tuple[int, int]) -> np.ndarray:
    """Where the calibration puts the canvas corners in the camera image (camera px)."""
    return np.asarray(mapper.projector_to_camera(canvas_corners(size)), dtype=np.float64)


def canvas_quad(image: np.ndarray, width: int = WIDTH) -> np.ndarray | None:
    """The projected canvas's corners in a camera frame (camera px, TL, TR, BR, BL), or None when there is no
    bright region that is large enough, clearly brighter than the rest and clear of the image border (the setup
    keeps a margin around the projection, A4; a region touching the border is noise or a cut-off projection)."""
    gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    scale = width / gray.shape[1]
    small = cv2.resize(gray, (width, max(int(round(gray.shape[0] * scale)), 1)), interpolation=cv2.INTER_AREA)
    small = cv2.GaussianBlur(small, (5, 5), 0)
    _, bright = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(bright)
    if count < 2:
        return None
    k = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    x, y, w, h, area = stats[k]
    if area < MIN_AREA * small.size or x == 0 or y == 0 or x + w == small.shape[1] or y + h == small.shape[0]:
        return None
    region = (labels == k).astype(np.uint8)
    inside, everything = cv2.mean(small, mask=region)[0], cv2.mean(small)[0]
    outside = (everything * small.size - inside * area) / (small.size - area)
    if inside - outside < MIN_CONTRAST:
        return None
    contours, _ = cv2.findContours(region, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    hull = cv2.convexHull(max(contours, key=cv2.contourArea)).reshape(-1, 2).astype(np.float64)
    quad = np.array([hull[np.argmin(hull @ d)] for d in _DIRECTIONS])
    return (quad + 0.5) / scale - 0.5                    # pixel centres at integers (brain.md §3.3)


def _agree(a: np.ndarray, b: np.ndarray, agree_px: float, rel: float) -> bool:
    return float(np.linalg.norm(a - b)) <= max(agree_px, rel * float(np.linalg.norm(a)))


def moved_by(expected: np.ndarray, corners: np.ndarray, move_px: float = MOVE_PX, agree_px: float = AGREE_PX,
             rel: float = AGREE_REL) -> np.ndarray | None:
    """The displacement (camera px, median of the agreeing corners) when at least 3 corners moved by `move_px` or
    more in agreement; else None (unmoved, or corners hidden or cut by someone in front)."""
    d = np.asarray(corners, dtype=np.float64) - np.asarray(expected, dtype=np.float64)
    big = [i for i in range(len(d)) if np.linalg.norm(d[i]) >= move_px]
    best: list[int] = []
    for i in big:
        group = [j for j in big if _agree(d[i], d[j], agree_px, rel)]
        if len(group) > len(best):
            best = group
    return np.median(d[best], axis=0) if len(best) >= 3 else None


class SetupWatch:
    """`update(t, frame)` once per camera frame; it checks every `every_s` and returns the confirmed displacement
    (camera px) when the setup moved, else None. `reset(expected)` after a recalibration."""

    def __init__(self, expected: np.ndarray, every_s: float = EVERY_S, confirm: int = CONFIRM):
        self.every_s, self.confirm = every_s, confirm
        self.checks, self.no_canvas, self.moved_checks = 0, 0, 0
        self.check_ms_total, self.check_ms_max = 0.0, 0.0
        self.reset(expected)

    def reset(self, expected: np.ndarray) -> None:
        self.expected = np.asarray(expected, dtype=np.float64)
        self._last: float | None = None
        self._run: list[np.ndarray] = []

    def update(self, t: float, frame: np.ndarray) -> np.ndarray | None:
        if self._last is not None and t - self._last < self.every_s:
            return None
        self._last = t
        start = time.perf_counter()
        corners = canvas_quad(frame)
        d = None if corners is None else moved_by(self.expected, corners)
        ms = (time.perf_counter() - start) * 1000
        self.checks += 1
        self.check_ms_total += ms
        self.check_ms_max = max(self.check_ms_max, ms)
        self.no_canvas += corners is None
        if d is None:
            self._run = []
            return None
        self.moved_checks += 1
        if self._run and not _agree(d, self._run[-1], AGREE_PX, AGREE_REL):
            self._run = []
        self._run.append(d)
        if len(self._run) < self.confirm:
            return None
        found, self._run = np.median(np.array(self._run), axis=0), []
        return found

    def summary(self) -> dict:
        return {"checks": self.checks, "no_canvas": self.no_canvas, "moved_checks": self.moved_checks,
                "check_ms_mean": round(self.check_ms_total / self.checks, 2) if self.checks else None,
                "check_ms_max": round(self.check_ms_max, 2)}
