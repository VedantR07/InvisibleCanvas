"""`detect` (Phase 1B diagnostic, brain.md D29): automatic cross detection on real camera frames.

Read-only: never writes a calibration; `calibrate` and `validate` stay manual.

For each of the 24 targets (4 calibration corners, 20 validation points), rendered as in
`calibrate`/`validate` but without the label text, the projector shows black (background)
and then the target; the detector runs on the averaged frame and on every single frame.
Negative controls: blank screens, and two crosses inside one search window.

The detections are compared with:
- each other over the single frames (stability),
- the projector geometry (H from the 4 detected corners, applied to the 20 detected grid
  centres: a click-free validation),
- the manual centres (the current calibration's corner clicks and the clicks of the latest
  validation made with it), if the setup still matches that calibration (D28 metric).
Writes data/reports/detection-<stamp>.json and a .png contact sheet of every target.
"""

from __future__ import annotations

import dataclasses
import json
from collections import Counter

import cv2
import numpy as np

from ..calibration.detect import CrossDetection, CrossParams, detect_cross
from ..calibration.metrics import accuracy_stats, setup_check
from ..calibration.store import CalibrationError, check_compatible, load_calibration
from ..calibration.targets import corner_targets, grid_targets
from ..config import Config
from ..display import patterns
from ..geometry.homography import GeometryError, apply_homography, estimate_homography
from .common import BACKGROUND_FRAMES, SINGLE_FRAMES, add_device_args, capture_frames, now_iso, open_session, save_report

SEARCH_RADIUS = 80        # camera px around the position the calibration predicts
TILE = 81                 # contact sheet: camera px per tile side, drawn 4x


def add_parser(subparsers) -> None:
    p = subparsers.add_parser("detect", help="Phase 1B diagnostic: automatic cross detection on real frames (read-only)")
    add_device_args(p)
    p.add_argument("--frames", type=int, default=SINGLE_FRAMES, help="single frames per target (default 10)")
    p.add_argument("--calibration-windows", action="store_true",
                   help="search only near where the current calibration predicts each target "
                        "(default: whole frame; a moved setup makes the windows wrong)")
    p.set_defaults(func=run)


_capture = capture_frames


def _two_crosses(size, centre, gap: int) -> np.ndarray:
    """Two crosses (arms and thickness as the targets, no ring) `gap` projector px apart."""
    img = patterns.blank(size)
    for dx in (-gap / 2, gap / 2):
        x, y = int(round(centre[0] + dx)), int(round(centre[1]))
        cv2.line(img, (x - 26, y), (x + 26, y), patterns.WHITE, 3, cv2.LINE_8)
        cv2.line(img, (x, y - 26), (x, y + 26), patterns.WHITE, 3, cv2.LINE_8)
    return img


# -- analysis helpers ----------------------------------------------------------------------------

def _detection_dict(d: CrossDetection) -> dict:
    out = dataclasses.asdict(d)
    out["rejected"] = list(d.rejected)[:5]
    return out


def _stats(values) -> dict | None:
    values = np.asarray(values, dtype=float)
    if len(values) == 0:
        return None
    s = accuracy_stats(values)
    return {"count": s.count, "mean": s.mean, "median": s.median, "p95": s.p95, "max": s.max}


def _is_manual(report: dict) -> bool:
    """Manual validation reports: `mode` "manual", or (before Phase 1C) no mode and a manual method."""
    return report.get("mode", "manual") == "manual" and str(report.get("method", "")).startswith("manual")


def _latest_validation_clicks(config: Config, calibration) -> tuple[np.ndarray, np.ndarray, str] | None:
    """Targets and clicked camera points of the newest MANUAL validation made with this calibration.
    Automatic validations (validate --auto) are detections, never a manual reference."""
    for path in sorted(config.reports_dir.glob("validation-*.json"), reverse=True):
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not _is_manual(report):
            continue
        if report.get("calibration_created_at") == calibration.created_at and report.get("points"):
            targets = np.array([p["target"] for p in report["points"]], dtype=float)
            clicks = np.array([p["camera"] for p in report["points"]], dtype=float)
            return targets, clicks, path.name
    return None


def _contact_sheet(tiles: list[tuple[str, np.ndarray, tuple | None, tuple | None, tuple]]) -> np.ndarray:
    """Each tile: label, averaged grey frame, detected centre, manual centre, tile centre."""
    z, half, cols = 4, TILE // 2, 6
    rows = (len(tiles) + cols - 1) // cols
    sheet = np.full((rows * (TILE * z + 24), cols * TILE * z, 3), 24, np.uint8)
    for k, (label, image, detected, manual, centre) in enumerate(tiles):
        cx, cy = int(round(centre[0])), int(round(centre[1]))
        patch = np.zeros((TILE, TILE), np.float32)
        h, w = image.shape
        x0, y0 = cx - half, cy - half
        sx0, sy0, sx1, sy1 = max(x0, 0), max(y0, 0), min(x0 + TILE, w), min(y0 + TILE, h)
        patch[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0] = image[sy0:sy1, sx0:sx1]
        lo, hi = np.percentile(patch, 1), np.percentile(patch, 99.5)
        patch = np.clip((patch - lo) / max(hi - lo, 1.0) * 255, 0, 255).astype(np.uint8)
        big = cv2.cvtColor(cv2.resize(patch, (TILE * z, TILE * z), interpolation=cv2.INTER_NEAREST), cv2.COLOR_GRAY2BGR)

        def to_tile(p):
            return int(round((p[0] - x0 + 0.5) * z - 0.5)), int(round((p[1] - y0 + 0.5) * z - 0.5))

        if manual is not None:
            mx, my = to_tile(manual)
            cv2.drawMarker(big, (mx, my), patterns.ORANGE, cv2.MARKER_TILTED_CROSS, 18, 1)
        if detected is not None:
            dx, dy = to_tile(detected)
            cv2.drawMarker(big, (dx, dy), patterns.GREEN, cv2.MARKER_CROSS, 22, 1)
        r, c = divmod(k, cols)
        oy, ox = r * (TILE * z + 24), c * TILE * z
        sheet[oy + 24:oy + 24 + TILE * z, ox:ox + TILE * z] = big
        patterns.text(sheet, label, (ox + 6, oy + 17), patterns.WHITE if detected else patterns.RED, 0.5)
    return sheet


# -- main --------------------------------------------------------------------------------------

def run(config: Config, args) -> int:
    v = config.validation
    try:
        calibration = load_calibration(config.calibration_dir)
    except CalibrationError as e:
        calibration = None
        print(f"no usable calibration ({e}): searching whole frames, no manual comparison")

    with open_session(config, args) as s:
        w, h = s.canvas_size
        if calibration is not None:
            try:
                check_compatible(calibration, s.camera_info.size, s.canvas_size)
            except CalibrationError as e:
                print(f"calibration not usable for this session ({e}): searching whole frames")
                calibration = None
        corners = corner_targets(w, h, config.calibration.target_inset)
        grid = grid_targets(w, h, v.grid_cols, v.grid_rows, v.grid_inset)
        h_inv = np.linalg.inv(calibration.homography) if calibration is not None else None
        use_windows = args.calibration_windows and h_inv is not None
        edge = np.zeros(len(grid), bool)
        rows, cols = np.divmod(np.arange(len(grid)), v.grid_cols)
        edge[(rows == 0) | (rows == v.grid_rows - 1) | (cols == 0) | (cols == v.grid_cols - 1)] = True

        jobs = [("corner", i, t, patterns.target_screen(s.canvas_size, corners, i, None, show_others=True))
                for i, t in enumerate(corners)]
        jobs += [("grid-edge" if edge[i] else "grid-interior", i, t,
                  patterns.target_screen(s.canvas_size, grid, i, None, show_others=False))
                 for i, t in enumerate(grid)]

        black = patterns.blank(s.canvas_size)
        results, tiles = [], []
        started = now_iso()
        for n, (group, i, target, screen) in enumerate(jobs):
            expected = apply_homography(h_inv, [target])[0] if h_inv is not None else None
            window = dict(expected=tuple(expected), search_radius=SEARCH_RADIUS) if use_windows else {}
            s.projector.show(black)
            background, _ = _capture(s, BACKGROUND_FRAMES)
            s.projector.show(screen)
            average, singles = _capture(s, args.frames)
            avg = detect_cross(average, background=background, **window)
            single = [detect_cross(f, background=background, **window) for f in singles]
            centres = np.array([d.center for d in single if d.ok])
            entry = {
                "group": group, "index": i, "projector": target.tolist(),
                "expected_camera": None if expected is None else expected.tolist(),
                "average": _detection_dict(avg),
                "singles": {
                    "frames": len(single), "accepted": int(len(centres)),
                    "rejections": dict(Counter(d.reason.split(" (")[0] for d in single if not d.ok)),
                    "mean": centres.mean(axis=0).tolist() if len(centres) else None,
                    "sd": centres.std(axis=0, ddof=1).tolist() if len(centres) > 1 else None,
                    "max_from_mean": float(np.linalg.norm(centres - centres.mean(axis=0), axis=1).max())
                    if len(centres) else None,
                },
            }
            results.append(entry)
            tile_centre = avg.center or (tuple(expected) if expected is not None else (w / 2, h / 2))
            tiles.append([f"{group[:6]} {i + 1} {'' if avg.ok else 'REJECTED'}", average, avg.center, None, tile_centre])
            view = cv2.cvtColor(np.clip(average, 0, 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)
            if avg.ok:
                patterns.draw_crosshair(view, avg.center, patterns.GREEN, gap=6, arm=30, thickness=1)
            s.operator.show(view, lines=["CROSS DETECTION (Phase 1B diagnostic, read-only)", f"{n + 1} / {len(jobs)}: {group} {i + 1}",
                                         f"average: {'OK ' + f'({avg.center[0]:.2f}, {avg.center[1]:.2f})' if avg.ok else avg.reason[:60]}",
                                         f"singles accepted {len(centres)} / {len(single)}"])

        # Negative controls.
        negatives = []
        s.projector.show(black)
        background, _ = _capture(s, BACKGROUND_FRAMES)
        blank, _ = _capture(s, BACKGROUND_FRAMES)
        for i, t in enumerate(corners):
            window = (dict(expected=tuple(apply_homography(h_inv, [t])[0]), search_radius=SEARCH_RADIUS)
                      if use_windows else {})
            d = detect_cross(blank, background=background, **window)
            negatives.append({"case": f"blank screen at corner {i + 1}", "rejected": not d.ok, "reason": d.reason})
        for centre in ([640, 360], [345, 470]):
            s.projector.show(_two_crosses(s.canvas_size, centre, 70))
            image, _ = _capture(s, BACKGROUND_FRAMES)
            window = (dict(expected=tuple(apply_homography(h_inv, [centre])[0]), search_radius=SEARCH_RADIUS)
                      if use_windows else {})
            d = detect_cross(image, background=background, **window)
            negatives.append({"case": f"two crosses 70 px apart around {centre}", "rejected": not d.ok,
                              "reason": d.reason, "candidates": d.candidates})
        s.projector.show(black)
        exposure_end = s.camera.read_exposure()
        stats_end = s.camera.stats()

    # -- evaluation ------------------------------------------------------------------------------
    avg_ok = [r["average"]["ok"] for r in results]
    det = [np.array(r["average"]["center"]) if r["average"]["ok"] else None for r in results]
    singles_total = sum(r["singles"]["frames"] for r in results)
    singles_ok = sum(r["singles"]["accepted"] for r in results)
    sd_max = max((max(r["singles"]["sd"]) for r in results if r["singles"]["sd"]), default=None)
    dev_max = max((r["singles"]["max_from_mean"] for r in results if r["singles"]["max_from_mean"] is not None),
                  default=None)
    corners_det = det[:4]
    grid_det = det[4:]

    click_free = None
    if all(c is not None for c in corners_det) and all(g is not None for g in grid_det):
        try:
            h_det = estimate_homography(np.array(corners_det), corners)
            err = np.linalg.norm(apply_homography(h_det, np.array(grid_det)) - grid, axis=1)
            click_free = {"all": _stats(err), "edge": _stats(err[edge]), "interior": _stats(err[~edge]),
                          "errors_px": err.tolist()}
        except GeometryError as e:
            click_free = {"error": str(e)}

    manual = None
    setup = None
    if calibration is not None and all(c is not None for c in corners_det):
        setup = setup_check(calibration.camera_points, np.array(corners_det), v.repeatability_mean_px)
        ref = _latest_validation_clicks(config, calibration)
        if setup.consistent:
            d_corner = [float(np.linalg.norm(det[k] - calibration.camera_points[k])) for k in range(4)]
            manual = {"corners_vs_calibration_clicks": _stats(d_corner), "corner_diffs_px": d_corner}
            for k in range(4):
                tiles[k][3] = tuple(calibration.camera_points[k])
            if ref is not None and np.array_equal(ref[0], grid):
                diffs = [float(np.linalg.norm(det[4 + k] - ref[1][k])) if det[4 + k] is not None else None
                         for k in range(len(grid))]
                vec = np.array([det[4 + k] - ref[1][k] for k in range(len(grid)) if det[4 + k] is not None])
                ok_d = np.array([d for d in diffs if d is not None])
                manual.update({
                    "grid_reference": ref[2],
                    "grid_vs_validation_clicks": _stats(ok_d),
                    "grid_edge": _stats([d for d, e in zip(diffs, edge) if d is not None and e]),
                    "grid_interior": _stats([d for d, e in zip(diffs, edge) if d is not None and not e]),
                    "grid_mean_vector_px": vec.mean(axis=0).tolist() if len(vec) else None,
                    "grid_diffs_px": diffs,
                })
                for k in range(len(grid)):
                    tiles[4 + k][3] = tuple(ref[1][k])
            all_d = np.array(d_corner + [d for d in manual.get("grid_diffs_px", []) if d is not None])
            manual["all"] = _stats(all_d)

    def verdict(ok):
        return "PASS" if ok else "FAIL"

    criteria = {
        "B1 detection": all(avg_ok) and singles_ok >= 0.95 * singles_total,
        "B2 no false detection": all(n["rejected"] for n in negatives),
        "B3 stability": sd_max is not None and sd_max <= 0.3 and dev_max <= 1.0,
        "B4 click-free consistency": bool(click_free and "all" in click_free
                                          and click_free["all"]["mean"] <= v.required_mean_px
                                          and click_free["all"]["max"] <= v.required_max_px),
        "B5 agreement with manual centres": (None if manual is None or "all" not in manual else
                                             manual["all"]["mean"] <= 2.0 and manual["all"]["max"] <= 4.0),
    }
    stretch = bool(click_free and "all" in click_free and click_free["all"]["mean"] <= v.stretch_mean_px
                   and click_free["all"]["max"] <= v.stretch_max_px)

    report = {
        "created_at": now_iso(), "started_at": started, "mode": "diagnostic (read-only)",
        "calibration_created_at": calibration.created_at if calibration is not None else None,
        "params": dataclasses.asdict(CrossParams()),
        "search": f"calibration windows, radius {SEARCH_RADIUS} px" if use_windows else "whole frame",
        "frames_per_target": args.frames, "background_frames": BACKGROUND_FRAMES,
        "rendering": "as calibrate/validate, without label text",
        "targets": results, "negatives": negatives,
        "single_frames": {"accepted": singles_ok, "total": singles_total, "max_sd_px": sd_max,
                          "max_from_mean_px": dev_max},
        "setup_check": None if setup is None else {**dataclasses.asdict(setup), "consistent": setup.consistent},
        "manual_comparison": manual, "click_free": click_free, "click_free_stretch": stretch,
        "criteria": criteria,
        "camera": {"fps": stats_end.mean_fps, "read_failures": stats_end.read_failures,
                   "exposure_end": None if exposure_end is None else exposure_end.describe()},
    }
    path = save_report(config, "detection", report)
    cv2.imwrite(str(path.with_suffix(".png")), _contact_sheet([tuple(t) for t in tiles]))

    # -- console summary -------------------------------------------------------------------------
    print(f"targets detected (averaged frame): {sum(avg_ok)} / {len(results)}; "
          f"single frames accepted {singles_ok} / {singles_total}")
    for r in results:
        a = r["average"]
        if not a["ok"]:
            print(f"  REJECTED {r['group']} {r['index'] + 1}: {a['reason']}")
        if r["singles"]["rejections"]:
            print(f"  {r['group']} {r['index'] + 1} single-frame rejections: {r['singles']['rejections']}")
    print(f"stability: max single-frame sd {sd_max if sd_max is None else round(sd_max, 3)} px, "
          f"max distance from mean {dev_max if dev_max is None else round(dev_max, 3)} px")
    for n in negatives:
        print(f"  negative control, {n['case']}: {'rejected' if n['rejected'] else 'FALSE DETECTION'} ({n['reason'][:70]})")
    if setup is not None:
        print(f"setup vs calibration {calibration.created_at}: variation {setup.variation:.2f} px "
              f"({'unchanged' if setup.consistent else 'CHANGED: manual comparison not evaluable'})")
    if manual:
        for key in ("corners_vs_calibration_clicks", "grid_vs_validation_clicks", "grid_edge", "grid_interior", "all"):
            if manual.get(key):
                print(f"  detected - manual, {key}: mean {manual[key]['mean']:.2f}, max {manual[key]['max']:.2f} camera px")
    if click_free and "all" in click_free:
        for key in ("all", "edge", "interior"):
            st = click_free[key]
            print(f"click-free (detected corners -> H -> detected grid), {key}: mean {st['mean']:.2f}, "
                  f"max {st['max']:.2f} projector px")
    for name, ok in criteria.items():
        print(f"{name}: {'not evaluable' if ok is None else verdict(ok)}")
    print(f"camera: {stats_end.mean_fps:.1f} fps, failed reads {stats_end.read_failures}; exposure at end: "
          f"{report['camera']['exposure_end']}")
    print(f"report: {path} (+ .png contact sheet: green + detected, orange x manual)")
    return 0 if all(ok is not False for ok in criteria.values()) else 1
