"""Fingertip shadow: where the projector ray through the fingertip meets the surface (brain.md D35).

The calibration H is exact only for points ON the surface. A hovering fingertip F is not: the
camera ray through F meets the surface at Wc (H maps the fingertip image to Wc's projector pixel),
the projector ray through F meets it at Wp, and Wp is where F's shadow falls. Wp is on the surface,
so H maps its camera image exactly: H(shadow tip) is the projector pixel whose light lands on the
fingertip, whatever the hover distance. The camera vector fingertip -> shadow tip is the parallax:
it grows with the hover distance and the camera-projector baseline and is zero at contact.

Finding it: the hand's shadow is (nearly) the hand's outline shifted by that vector. In a dark
room the shadowed surface sits at the camera's black level, well below lit skin, so a dark-pixel
map is matched against finger outlines drawn from the landmarks: all fingers together first (the
whole-hand shift), then the index finger alone near it. Pixels on the hand or outside the projected
canvas are ignored, and a ring around the template must be lit, so a broad dark area cannot match.
This is a measurement for diagnostics; the cursor itself still uses H(fingertip).
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

# Outlines start at the middle knuckle: towards the palm the ring would fall into the palm's own shadow.
FINGER_CHAINS = ((2, 3, 4), (6, 7, 8), (10, 11, 12), (14, 15, 16), (18, 19, 20))
INDEX_CHAIN = ((6, 7, 8),)
ALL_BONES = ((1, 2, 3, 4), (5, 6, 7, 8), (9, 10, 11, 12), (13, 14, 15, 16), (17, 18, 19, 20))
PALM = (0, 1, 5, 9, 13, 17)
INDEX_TIP = 8


@dataclass(frozen=True)
class Shadow:
    offset: tuple[float, float]      # camera px, fingertip -> its shadow tip
    tip: tuple[float, float]         # camera px, the shadow tip (on the surface)
    score: float                     # dark fraction inside the outline minus in the ring around it (-1..1)
    coverage: float                  # fraction of the outline on visible canvas (not on the hand, not outside)
    hand_offset: tuple[float, float]  # the whole-hand shift found first


def finger_width(landmarks: np.ndarray) -> float:
    """Finger width estimate: the spacing of the knuckles (index-middle-ring-little), which does not depend
    on the pose. (The first version used 0.085 x wrist->middle fingertip, which shrinks to ~6 px in the
    pointing pose with the middle finger curled; 2026-10-10.)"""
    k = landmarks[[5, 9, 13, 17]]
    return max(6.0, float(np.mean(np.linalg.norm(np.diff(k, axis=0), axis=1))))


def outline_mask(shape: tuple[int, int], landmarks: np.ndarray, chains, width: float) -> np.ndarray:
    """Fingers as thick polylines; each chain's tip is extended by half a width (the fingertip pad)."""
    mask = np.zeros(shape, np.uint8)
    t = max(1, int(round(width)))
    for chain in chains:
        pts = landmarks[list(chain)].astype(np.float64)
        d = pts[-1] - pts[-2]
        n = np.linalg.norm(d)
        if n > 0:
            pts = np.vstack([pts, pts[-1] + d / n * width * 0.5])
        cv2.polylines(mask, [np.round(pts).astype(np.int32)], False, 1, t, cv2.LINE_8)
    return mask


def _palm_and_forearm(shape: tuple[int, int], landmarks: np.ndarray) -> np.ndarray:
    """Palm polygon plus the forearm (not in the landmarks): from the wrist, away from the middle
    knuckle, 1.5 hand lengths long and as wide as the palm."""
    mask = np.zeros(shape, np.uint8)
    cv2.fillPoly(mask, [np.round(landmarks[list(PALM)]).astype(np.int32)], 1)
    d = landmarks[0] - landmarks[9]
    n = np.linalg.norm(d)
    if n > 0:
        d /= n
        side = np.array([-d[1], d[0]]) * 0.55 * float(np.linalg.norm(landmarks[5] - landmarks[17]))
        far = landmarks[0] + d * 1.5 * float(np.linalg.norm(landmarks[12] - landmarks[0]))
        arm = np.array([landmarks[0] + side, far + side, far - side, landmarks[0] - side])
        cv2.fillPoly(mask, [np.round(arm).astype(np.int32)], 1)
    return mask


def hand_mask(shape: tuple[int, int], landmarks: np.ndarray, width: float) -> np.ndarray:
    """The hand and forearm as the camera sees them (skin, not surface), with a few px of margin."""
    mask = outline_mask(shape, landmarks, ALL_BONES, width * 1.2) | _palm_and_forearm(shape, landmarks)
    return cv2.dilate(mask, np.ones((5, 5), np.uint8))


def dark_level(black: float, background: float, fraction: float = 0.15) -> float:
    """Luma below which a canvas pixel counts as shadow: 15 % of the way from black to the lit canvas.
    (Measured 2026-10-10 at grey 128: shadow ~21 = black level, lit skin 63-120 with its dark side ~45,
    lit canvas 135-175.)"""
    return black + fraction * (background - black)


def _match(dark: np.ndarray, valid: np.ndarray, inside: np.ndarray, ring: np.ndarray, base: tuple[int, int],
           centre: tuple[float, float], radius: float, min_coverage: float):
    """Best shift of the (inside, ring) template within `radius` of `centre`. Template bbox origin = base."""
    th, tw = inside.shape
    bx, by = base
    H, W = dark.shape
    cx, cy = int(round(centre[0])), int(round(centre[1]))
    r = int(np.ceil(radius))
    x0, y0 = max(bx + cx - r, 0), max(by + cy - r, 0)
    x1, y1 = min(bx + cx + r + tw, W), min(by + cy + r + th, H)
    if x1 - x0 < tw or y1 - y0 < th:
        return None
    dv = (dark * valid)[y0:y1, x0:x1]
    vv = valid[y0:y1, x0:x1]
    fi, fr = inside.astype(np.float32), ring.astype(np.float32)
    in_num = cv2.matchTemplate(dv, fi, cv2.TM_CCORR)
    in_den = cv2.matchTemplate(vv, fi, cv2.TM_CCORR)
    ring_num = cv2.matchTemplate(dv, fr, cv2.TM_CCORR)
    ring_den = cv2.matchTemplate(vv, fr, cv2.TM_CCORR)
    n_in, n_ring = float(fi.sum()), float(fr.sum())
    ok = (in_den >= min_coverage * n_in) & (ring_den >= min_coverage * n_ring)
    ys, xs = np.mgrid[0:in_num.shape[0], 0:in_num.shape[1]]
    ox, oy = xs + x0 - bx, ys + y0 - by                       # shift for each result position
    ok &= (ox - centre[0]) ** 2 + (oy - centre[1]) ** 2 <= radius ** 2
    if not ok.any():
        return None
    with np.errstate(invalid="ignore", divide="ignore"):
        score = np.where(ok, in_num / np.maximum(in_den, 1e-6) - ring_num / np.maximum(ring_den, 1e-6), -2.0)
    j, i = np.unravel_index(int(np.argmax(score)), score.shape)
    best = float(score[j, i])
    # sub-pixel: parabola through the neighbours (when they are valid)
    sx = sy = 0.0
    if 0 < i < score.shape[1] - 1 and score[j, i - 1] > -2 and score[j, i + 1] > -2:
        den = score[j, i - 1] - 2 * best + score[j, i + 1]
        sx = 0.5 * (score[j, i - 1] - score[j, i + 1]) / den if den < 0 else 0.0
    if 0 < j < score.shape[0] - 1 and score[j - 1, i] > -2 and score[j + 1, i] > -2:
        den = score[j - 1, i] - 2 * best + score[j + 1, i]
        sy = 0.5 * (score[j - 1, i] - score[j + 1, i]) / den if den < 0 else 0.0
    coverage = float(in_den[j, i]) / n_in
    return float(ox[j, i] + np.clip(sx, -0.5, 0.5)), float(oy[j, i] + np.clip(sy, -0.5, 0.5)), best, coverage


def _template(shape, landmarks, chains, width):
    """Finger outline (should be dark when shifted onto the shadow) and a ring around it (should be lit),
    leaving out the ring where the shadow of the palm and the lower fingers lies."""
    inside = outline_mask(shape, landmarks, chains, width)
    k = max(3, int(round(width * 0.8)) | 1)
    ring = cv2.dilate(inside, np.ones((k, k), np.uint8)) - inside
    base = outline_mask(shape, landmarks, ((5, 6), (9, 10), (13, 14), (17, 18), (1, 2)), width) |         _palm_and_forearm(shape, landmarks)
    ring[cv2.dilate(base, np.ones((k, k), np.uint8)) > 0] = 0
    ys, xs = np.nonzero(ring | inside)
    x0, y0, x1, y1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
    return inside[y0:y1, x0:x1], ring[y0:y1, x0:x1], (int(x0), int(y0))


def find_shadow(grey: np.ndarray, landmarks: np.ndarray, canvas: np.ndarray, black: float, background: float,
                *, radius: float = 160.0, refine: float = 14.0, min_score: float = 0.5,
                min_coverage: float = 0.15) -> Shadow | None:
    """The index fingertip's shadow in a camera frame, or None when it is not visible / not found.

    grey: camera luma; landmarks: 21x2 camera px; canvas: bool mask of the projected canvas in the camera
    image; black / background: luma of unlit surface and of the lit canvas (measured before tracking).
    """
    landmarks = np.asarray(landmarks, dtype=np.float64)
    width = finger_width(landmarks)
    dark = ((grey < dark_level(black, background)) & canvas).astype(np.float32)
    valid = (canvas & (hand_mask(grey.shape, landmarks, width) == 0)).astype(np.float32)
    # Coarse: all fingers together. (A wide search with the index finger alone was tried on the
    # 2026-10-10 frames and matched other fingers' shadows: one finger outline is not distinctive.)
    inside, ring, base = _template(grey.shape, landmarks, FINGER_CHAINS, width)
    coarse = _match(dark, valid, inside, ring, base, (0.0, 0.0), radius, min_coverage)
    if coarse is None or coarse[2] < min_score:
        return None
    fine = _match(dark, valid, *_template(grey.shape, landmarks, INDEX_CHAIN, width), coarse[:2], refine,
                  min_coverage)
    if fine is None or fine[2] < min_score:
        return None
    dx, dy, score, coverage = fine
    tip = landmarks[INDEX_TIP]
    return Shadow((dx, dy), (float(tip[0] + dx), float(tip[1] + dy)), score, coverage, (coarse[0], coarse[1]))


# -- the shadow centre at a known place (D36) ----------------------------------------------------------
#
# The accuracy test asks the operator to put the fingertip's shadow on the target centre, so the
# shadow is looked for only there: along the finger direction (from the landmarks) the finger's
# shadow is a dark strip about one finger wide; its END is where the dark run stops. The reference
# point ("shadow centre") is on the strip's centre line, half a strip width back from the end: the
# centre of the fingertip's shadow. It is reported only when it is established reliably: a strip
# behind the end, a visible lit surface beyond it (not hidden by the hand or outside the canvas),
# a plausible width and enough contrast. Otherwise the reason is returned.


@dataclass(frozen=True)
class ShadowTip:
    found: bool
    reason: str                                  # "ok" or why the shadow centre is not established
    centre: tuple[float, float] | None = None    # camera px, centre of the fingertip's shadow
    end: tuple[float, float] | None = None       # camera px, where the shadow strip ends
    width: float | None = None                   # strip width, camera px
    contrast: float | None = None                # (lit - shadow) / (background - black)


def shadow_tip_near(grey: np.ndarray, point, direction, width: float, black: float, background: float,
                    hand: np.ndarray, canvas: np.ndarray, *, reach: float = 3.0) -> ShadowTip:
    """The fingertip's shadow near `point` (camera px). direction: the finger's pointing direction in the
    camera image (e.g. landmark 8 - landmark 6); width: finger width (camera px); hand / canvas: masks of
    pixels on the hand (as the camera sees it) and of the projected canvas."""
    u = np.asarray(direction, dtype=np.float64)
    if not np.linalg.norm(u) > 0 or background - black < 10:
        return ShadowTip(False, "no direction" if not np.linalg.norm(u) > 0 else "no contrast between lit and unlit")
    u /= np.linalg.norm(u)
    n = np.array([-u[1], u[0]])
    w = float(width)
    A, B = int(np.ceil(reach * w + w)), int(np.ceil(2.5 * w))
    a = np.arange(-A, A + 1, dtype=np.float32)
    b = np.arange(-B, B + 1, dtype=np.float32)
    bb, aa = np.meshgrid(b, a)                                    # rows: along the finger, columns: across
    mx = (point[0] + aa * u[0] + bb * n[0]).astype(np.float32)
    my = (point[1] + aa * u[1] + bb * n[1]).astype(np.float32)
    g = cv2.remap(grey.astype(np.float32), mx, my, cv2.INTER_LINEAR, borderValue=-1)
    ok = cv2.remap((canvas & (hand == 0)).astype(np.uint8), mx, my, cv2.INTER_NEAREST, borderValue=0) > 0
    ok &= g >= 0
    level = black + 0.5 * (background - black)                    # half-way: the edge at half intensity
    dark = (g < level) & ok
    count, labels, stats, _ = cv2.connectedComponentsWithStats(dark.astype(np.uint8), connectivity=8)
    near_axis = np.abs(bb) <= 1.5 * w
    best, best_size = 0, 0
    for k in range(1, count):
        comp = labels == k
        size = int(comp.sum())
        if size > best_size and (comp & near_axis).any():
            best, best_size = k, size
    if best == 0 or best_size < 1.5 * w * w:
        return ShadowTip(False, "no shadow strip near the target")
    comp = labels == best
    rows = comp.sum(axis=1)
    tip_rows = np.nonzero(rows >= 0.3 * w)[0]
    i_end = int(tip_rows.max())
    a_end = float(a[i_end])
    if a_end >= A - w:
        return ShadowTip(False, "strip runs out of the search area (shadow end not near the target)")
    behind = (aa >= a_end - 1.5 * w) & (aa <= a_end - 0.3 * w)
    body = comp & behind
    body_rows = [r for r in range(len(a)) if behind[r, 0]]
    if not body.any():
        return ShadowTip(False, "no strip behind the shadow end")
    b_c = float(bb[body].mean())
    strip_w = float(np.mean([rows[r] for r in body_rows]))
    if not 0.5 * w <= strip_w <= 2.2 * w:
        return ShadowTip(False, f"strip width {strip_w:.0f} px implausible for a {w:.0f}-px finger")
    beyond = (aa >= a_end + 0.2 * w) & (aa <= a_end + 1.0 * w) & (np.abs(bb - b_c) <= 0.5 * w)
    if ok[beyond].mean() < 0.7:
        return ShadowTip(False, "shadow end hidden (by the hand, or outside the canvas)")
    if dark[beyond].mean() > 0.2:
        return ShadowTip(False, "no clear end: dark beyond the strip")
    lit = g[beyond & ok]
    shade = g[body]
    contrast = float((np.median(lit) - np.median(shade)) / (background - black))
    if not 0.5 <= contrast <= 1.3:      # > 1.3: the "shadow" is darker than unlit surface (skin, an object)
        return ShadowTip(False, f"contrast {contrast:.2f} outside 0.5-1.3")
    end = np.asarray(point) + a_end * u + b_c * n
    centre = end - 0.5 * strip_w * u
    return ShadowTip(True, "ok", (float(centre[0]), float(centre[1])), (float(end[0]), float(end[1])),
                     strip_w, contrast)


@dataclass(frozen=True)
class ShadowCentre:
    """The shadow centre over the frames of one hold (D36): established only when found in enough frames
    and steady (the hold is steady, so its shadow is)."""
    established: bool
    reason: str
    centre: tuple[float, float] | None       # camera px, median over the frames
    frames: int
    found: int
    spread_px: float | None                  # largest distance of a frame's centre from the median


def steady_shadow_centre(tips: list[ShadowTip], *, min_found: int = 3, max_spread: float = 6.0) -> ShadowCentre:
    found = [t for t in tips if t.found]
    if len(found) < min_found:
        reasons = sorted({t.reason for t in tips if not t.found})
        return ShadowCentre(False, f"found in {len(found)}/{len(tips)} frames (need {min_found}): "
                            + "; ".join(reasons), None, len(tips), len(found), None)
    c = np.array([t.centre for t in found])
    med = np.median(c, axis=0)
    spread = float(np.linalg.norm(c - med, axis=1).max())
    if spread > max_spread:
        return ShadowCentre(False, f"not steady: frame centres up to {spread:.1f} px apart (max {max_spread:g})",
                            None, len(tips), len(found), spread)
    return ShadowCentre(True, "ok", (float(med[0]), float(med[1])), len(tips), len(found), spread)
