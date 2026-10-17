"""Automatic detection of a projected calibration cross in a camera image (Phase 1B, D29).

Pure (numpy + OpenCV image ops), no I/O. Coordinates are camera pixels with pixel centres
at integer coordinates, the same convention as clicks, H and every other space (brain.md 3).

Method (cross geometry, not the ring):
1. Signal = image - background (a frame of the black projection), then a white top-hat, which
   keeps thin bright structures (the 3-px arms) and removes smooth brightness changes.
2. Threshold relative to the peak, never below a noise floor estimated from the image.
3. Connected components; a candidate must be solid at its centre. The ring, a clipped ring
   arc and label text are hollow or not cross-shaped, so they are never used: the target
   ring may be clipped by the canvas edge (4 % validation inset) without affecting the result.
4. The candidate's pixels are split into two arms by angle, a weighted line is fitted to each
   arm, and the centre is the intersection of the two lines. A projective map sends lines to
   lines, so the intersection is the image of the cross centre under any perspective; a
   centroid is not (it shifts ~0.13 px for the target ring at our perspective).
5. Anything doubtful is rejected with a reason instead of returning a centre: low contrast,
   no cross, several crosses, cross truncated by the image or search window, a missing or
   short half-arm, arms that are not straight lines, arms far from perpendicular.

Programming errors (bad arrays, mismatched shapes) raise DetectionError.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np


class DetectionError(ValueError):
    """Invalid input to the detector (not a detection failure)."""


@dataclass(frozen=True)
class CrossParams:
    """Fixed from the target geometry (3-px arms, 26-px half-arms, ring radius 36, projector
    px) and the camera scale (~1.0-1.3 camera px per projector px). Not tuned on hardware."""
    max_arm_width_px: int = 12          # top-hat kernel = 2 * this + 1
    rel_threshold: float = 0.4          # of the peak signal
    noise_k: float = 6.0                # threshold never below this many noise sigmas
    min_peak: float = 10.0              # grey levels; a weaker peak is not a projected target
    min_contrast: float = 8.0           # peak / noise sigma
    min_area_px: int = 25
    max_line_residual_px: float = 3.5   # rms distance of arm pixels from their fitted line
                                        # (a uniform arm of width W has rms W/sqrt(12): 3.5 px at W = 12)
    min_elongation: float = 5.0         # half-arm length / line residual
    min_half_arm_balance: float = 0.6   # shortest / longest of the four half-arms
    min_half_arm_px: float = 12.0       # the 26-px half-arm at >= 0.46 camera px per projector px;
                                        # label glyphs (~5 px strokes) stay below it
    min_arm_angle_deg: float = 60.0     # acute angle between the arm lines (90 = perpendicular)


@dataclass(frozen=True)
class CrossDetection:
    ok: bool
    center: tuple[float, float] | None   # camera px; None when rejected
    reason: str = ""                     # empty when ok, else why it was rejected
    fit_sigma_px: float | None = None    # statistical 1-sigma of the line intersection (not accuracy)
    peak: float = 0.0                    # signal peak, grey levels
    contrast: float = 0.0                # peak / noise sigma
    candidates: int = 0                  # components that passed the cross test in the search area
    arm_angle_deg: float | None = None   # acute angle between the arm lines

    line_residual_px: float | None = None
    half_arm_balance: float | None = None
    rejected: tuple[str, ...] = field(default_factory=tuple)   # why other components were not crosses

    @classmethod
    def fail(cls, reason: str, **kw) -> CrossDetection:
        return cls(ok=False, center=None, reason=reason, **kw)


def _as_gray(image, name: str) -> np.ndarray:
    if image is None:
        raise DetectionError(f"{name} is None")
    arr = np.asarray(image)
    if arr.ndim == 3 and arr.shape[2] == 3:
        if arr.dtype != np.uint8:
            raise DetectionError(f"{name}: colour images must be uint8, got {arr.dtype}")
        arr = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
    elif arr.ndim != 2:
        raise DetectionError(f"{name} must be HxW or HxWx3, got shape {arr.shape}")
    if arr.size == 0:
        raise DetectionError(f"{name} is empty")
    if not np.issubdtype(arr.dtype, np.number) or arr.dtype == np.bool_:
        raise DetectionError(f"{name} must be numeric, got {arr.dtype}")
    out = arr.astype(np.float32)
    if not np.all(np.isfinite(out)):
        raise DetectionError(f"{name} contains NaN or infinity")
    return out


def _weighted_line(p: np.ndarray, wt: np.ndarray):
    """Weighted total-least-squares line: (point, direction, normal, rms distance, points, weights).
    One robust pass: pixels farther than 2.5 rms from the line (stray glyph or noise pixels
    touching an arm) are dropped and the line refitted."""
    for attempt in range(2):
        mean = (p * wt[:, None]).sum(axis=0) / wt.sum()
        q = p - mean
        cov = (q * wt[:, None]).T @ q / wt.sum()
        evals, evecs = np.linalg.eigh(cov)
        direction, normal = evecs[:, 1], evecs[:, 0]
        rms = float(np.sqrt(max(evals[0], 0.0)))
        if attempt == 1:
            break
        keep = np.abs(q @ normal) <= max(2.5 * rms, 2.0)
        if keep.all() or keep.sum() < 4:
            break
        p, wt = p[keep], wt[keep]
    return mean, direction, normal, rms, p, wt


@dataclass
class _Fit:
    center: np.ndarray
    angle_deg: float
    residual: float
    balance: float
    elongation: float
    sigma: float
    shortest_half_arm: float


def _fit_cross(xs: np.ndarray, ys: np.ndarray, w: np.ndarray, start: np.ndarray) -> _Fit | str:
    """Two-line fit around `start`. Returns the fit, or a reason string."""
    c = start.astype(np.float64)
    pts = np.column_stack([xs, ys]).astype(np.float64)
    dirs = []
    for _ in range(8):
        d = pts - c
        r = np.hypot(d[:, 0], d[:, 1])
        r_min = max(2.0, 0.12 * float(np.percentile(r, 95)))   # skip the central square
        far = r > r_min
        if far.sum() < 8:
            return "too few arm pixels"
        theta = np.arctan2(d[far, 1], d[far, 0])
        ww = w[far]
        phi = np.angle(np.sum(ww * np.exp(4j * theta))) / 4.0   # plus orientation (mod 90 deg)
        # Arm A: directions phi and phi + 180 deg (within +-45 deg); arm B: the other two.
        arm = np.abs(np.mod(theta - phi + np.pi / 4, np.pi) - np.pi / 4) <= np.pi / 4
        p_far = pts[far]
        lines = []
        for sel in (arm, ~arm):
            if sel.sum() < 4:
                return "a cross arm is missing"
            mean, direction, normal, rms, p, wt = _weighted_line(p_far[sel], ww[sel])
            lines.append((mean, direction, normal, p, wt, rms))
        (m1, d1, n1, *_), (m2, d2, n2, *_) = lines
        # Intersection of m1 + s d1 and m2 + t d2.
        a = np.column_stack([d1, -d2])
        if abs(np.linalg.det(a)) < 1e-6:
            return "cross arms are parallel"
        s, _t = np.linalg.solve(a, m2 - m1)
        new = m1 + s * d1
        moved = float(np.linalg.norm(new - c))
        c = new
        dirs = lines
        if moved < 1e-4:
            break

    (m1, d1, n1, p1, w1, res1), (m2, d2, n2, p2, w2, res2) = dirs
    angle = float(np.degrees(np.arccos(np.clip(abs(float(d1 @ d2)), 0.0, 1.0))))   # acute angle between the lines
    halves = []
    for p, d in ((p1, d1), (p2, d2)):
        t = (p - c) @ d
        if not np.any(t > 0) or not np.any(t < 0):
            return "a half-arm is missing"
        halves += [float(np.percentile(t[t > 0], 98)), float(-np.percentile(t[t < 0], 2))]
    residual = float(np.sqrt((res1 ** 2 * w1.sum() + res2 ** 2 * w2.sum()) / (w1.sum() + w2.sum())))
    balance = min(halves) / max(halves)
    elongation = min(halves) / max(residual, 1e-6)
    # Standard error of each line's offset, combined into the intersection (indicative only).
    se1 = res1 / np.sqrt(max(len(p1), 1))
    se2 = res2 / np.sqrt(max(len(p2), 1))
    sin_a = max(abs(np.sin(np.radians(angle))), 1e-3)
    sigma = float(np.hypot(se1, se2) / sin_a)
    return _Fit(center=c, angle_deg=angle, residual=residual, balance=balance, elongation=elongation, sigma=sigma,
                shortest_half_arm=min(halves))


def detect_cross(image, *, background=None, expected: tuple[float, float] | None = None,
                 search_radius: float | None = None, params: CrossParams = CrossParams()) -> CrossDetection:
    """Find the single projected cross in `image` (or in the square of half-size `search_radius`
    around `expected`, camera px). `background`: the same view with the target off (optional
    but recommended on real frames). Returns a CrossDetection; never a guess."""
    gray = _as_gray(image, "image")
    if background is not None:
        bg = _as_gray(background, "background")
        if bg.shape != gray.shape:
            raise DetectionError(f"background shape {bg.shape} differs from image shape {gray.shape}")
        gray = gray - bg
    h, w = gray.shape
    x0, y0, x1, y1 = 0, 0, w, h
    if expected is not None or search_radius is not None:
        if expected is None or search_radius is None:
            raise DetectionError("expected and search_radius must be given together")
        ex, ey = (float(v) for v in expected)
        if not (np.isfinite(ex) and np.isfinite(ey)):
            raise DetectionError("expected position is not finite")
        if not (0 <= ex <= w - 1 and 0 <= ey <= h - 1):
            raise DetectionError(f"expected position ({ex:.1f}, {ey:.1f}) is outside the {w}x{h} image")
        if not np.isfinite(search_radius) or search_radius <= 0:
            raise DetectionError("search_radius must be a positive number")
        r = int(np.ceil(search_radius))
        x0, y0 = max(int(round(ex)) - r, 0), max(int(round(ey)) - r, 0)
        x1, y1 = min(int(round(ex)) + r + 1, w), min(int(round(ey)) + r + 1, h)

    # Top-hat on a margin around the window, so the opening is not distorted at the window edge.
    k = 2 * params.max_arm_width_px + 1
    mx0, my0, mx1, my1 = max(x0 - k, 0), max(y0 - k, 0), min(x1 + k, w), min(y1 + k, h)
    region = gray[my0:my1, mx0:mx1]
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k, k))
    tophat = cv2.morphologyEx(region, cv2.MORPH_TOPHAT, kernel)
    signal = tophat[y0 - my0:y1 - my0, x0 - mx0:x1 - mx0]

    med = float(np.median(signal))
    noise = float(1.4826 * np.median(np.abs(signal - med)))
    peak = float(cv2.GaussianBlur(signal, (3, 3), 0).max() - med)   # blur: a hot pixel is not a peak
    contrast = peak / max(noise, 0.5)
    if peak < params.min_peak or contrast < params.min_contrast:
        return CrossDetection.fail(f"no projected target: peak {peak:.1f} grey levels, contrast {contrast:.1f} "
                                   f"(need >= {params.min_peak:g} and >= {params.min_contrast:g})",
                                   peak=peak, contrast=contrast)
    threshold = med + max(params.rel_threshold * peak, params.noise_k * noise)
    mask = (signal > threshold).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)

    crosses, rejected, hollow = [], [], []   # `rejected`: solid candidates, reported first
    win_h, win_w = signal.shape
    for i in range(1, count):
        bx, by, bw, bh, area = stats[i]
        if area < params.min_area_px:
            continue
        ys, xs = np.nonzero(labels[by:by + bh, bx:bx + bw] == i)    # within the bounding box only
        ys, xs = ys + by, xs + bx
        wts = signal[ys, xs] - med
        centroid = np.array([(xs * wts).sum() / wts.sum(), (ys * wts).sum() / wts.sum()])
        where = f"({centroid[0] + x0:.0f}, {centroid[1] + y0:.0f})"
        # Solid at the centre: rings, arcs and most text are hollow there.
        cx, cy = int(round(centroid[0])), int(round(centroid[1]))
        near = labels[max(cy - 1, 0):cy + 2, max(cx - 1, 0):cx + 2] == i
        if not near.any():
            hollow.append(f"component at {where} is hollow (ring/arc/text)")
            continue
        # A pattern cut by the frame or the window cannot be checked for completeness.
        if bx + x0 == 0 or by + y0 == 0 or bx + bw + x0 >= w or by + bh + y0 >= h:
            rejected.append(f"component at {where}: the cross is cut off by the image border")
            continue
        if bx == 0 or by == 0 or bx + bw >= win_w or by + bh >= win_h:
            rejected.append(f"component at {where}: the cross extends beyond the search window")
            continue
        # Use the component plus a 1-px rim, so blurred arm edges count symmetrically.
        # (The bounding box grown by the 1-px rim; identical to dilating the whole label image.)
        ex0, ey0 = max(bx - 1, 0), max(by - 1, 0)
        ex1, ey1 = min(bx + bw + 1, win_w), min(by + bh + 1, win_h)
        comp = cv2.dilate((labels[ey0:ey1, ex0:ex1] == i).astype(np.uint8), np.ones((3, 3), np.uint8))
        ys, xs = np.nonzero(comp)
        ys, xs = ys + ey0, xs + ex0
        wts = np.clip(signal[ys, xs] - med, 0.0, None)
        fit = _fit_cross(xs.astype(np.float64), ys.astype(np.float64), wts.astype(np.float64), centroid)
        if isinstance(fit, str):
            rejected.append(f"component at {where}: {fit}")
            continue
        problems = []
        if fit.shortest_half_arm < params.min_half_arm_px:
            problems.append(f"too small for a target (shortest half-arm {fit.shortest_half_arm:.1f} px)")
        if fit.residual > params.max_line_residual_px:
            problems.append(f"arms not straight (line residual {fit.residual:.2f} px)")
        if fit.elongation < params.min_elongation:
            problems.append(f"arms too short for their width (elongation {fit.elongation:.1f})")
        if fit.balance < params.min_half_arm_balance:
            problems.append(f"half-arms unequal (balance {fit.balance:.2f})")
        if fit.angle_deg < params.min_arm_angle_deg:
            problems.append(f"arms {fit.angle_deg:.1f} deg apart (need >= {params.min_arm_angle_deg:g})")
        fx, fy = int(round(fit.center[0])), int(round(fit.center[1]))
        if not (0 <= fx < win_w and 0 <= fy < win_h) or signal[fy, fx] <= threshold:
            problems.append("the arm lines do not cross on the bright pattern")
        if problems:
            rejected.append(f"component at {where} is not a clean cross: " + "; ".join(problems))
            continue
        crosses.append(fit)

    rejected += hollow
    common = dict(peak=peak, contrast=contrast, candidates=len(crosses), rejected=tuple(rejected))
    if not crosses:
        return CrossDetection.fail("no cross found" + (f" ({rejected[0]})" if rejected else ""), **common)
    if len(crosses) > 1:
        where = ", ".join(f"({f.center[0] + x0:.0f}, {f.center[1] + y0:.0f})" for f in crosses)
        return CrossDetection.fail(f"{len(crosses)} crosses in the search area: {where}", **common)
    fit = crosses[0]
    return CrossDetection(
        ok=True, center=(float(fit.center[0] + x0), float(fit.center[1] + y0)),
        arm_angle_deg=fit.angle_deg, line_residual_px=fit.residual, half_arm_balance=fit.balance,
        fit_sigma_px=fit.sigma, **common,
    )
