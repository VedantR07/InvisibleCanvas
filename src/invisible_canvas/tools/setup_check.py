"""`setupcheck` (diagnostic, brain.md D32): the automatic setup check on its own, repeatedly.

Read-only: the calibration's 4 corners are detected again and compared with the current
calibration (the D28 metric), optionally with every projected image shifted by whole projector
pixels (a controlled perturbation). Each check is judged against the given limits, so a series
shows normal variation, slow drift and sensitivity to movement. Nothing is saved except the
report `data/reports/setupcheck-<stamp>.json`.
"""

from __future__ import annotations

import time

import numpy as np

from ..calibration.auto import AutoCalibrationError, auto_setup_check
from ..calibration.store import check_compatible, load_calibration
from ..calibration.targets import CORNER_NAMES
from ..config import Config
from .common import CameraMeasure, add_device_args, now_iso, open_session, save_report


def _shift_list(text: str) -> list[tuple[int, int]]:
    """'0,0 2,0 -1,0' -> [(0, 0), (2, 0), (-1, 0)] (one argument, so negative values are not options)."""
    shifts = []
    for pair in text.replace(";", " ").split():
        dx, dy = pair.split(",")
        shifts.append((int(dx), int(dy)))
    if not shifts:
        raise ValueError("no shifts")
    return shifts


def add_parser(subparsers) -> None:
    p = subparsers.add_parser("setupcheck", help="diagnostic: repeated automatic setup checks (read-only, D32)")
    add_device_args(p)
    p.add_argument("--repeat", type=int, default=1, help="checks per shift (default 1)")
    p.add_argument("--interval", type=float, default=0.0, help="seconds between the starts of repeated checks")
    p.add_argument("--shifts", type=_shift_list, default=[(0, 0)], metavar='"DX,DY ..."',
                   help='projector-pixel shifts to test in order, e.g. --shifts="0,0 2,0 -1,0 0,0" '
                        "(default 0,0 = no movement)")
    p.add_argument("--limits", nargs="+", type=float, default=[1.0, 2.0],
                   help="limits (camera px, repeatability metric) to judge each check against (default 1.0 2.0)")
    p.set_defaults(func=run)


def run(config: Config, args) -> int:
    calibration = load_calibration(config.calibration_dir)
    limits = sorted(args.limits)
    checks = []
    start = time.perf_counter()
    with open_session(config, args) as s:
        check_compatible(calibration, s.camera_info.size, s.canvas_size)
        print(f"calibration {calibration.created_at} ({calibration.method}); limits {limits} camera px")
        for shift in args.shifts:
            measure = CameraMeasure(s, title=f"SETUP CHECK diagnostic, shift {shift}", shift=shift)
            for k in range(args.repeat):
                if k and args.interval:                                      # keep the start-to-start interval
                    next_start = checks[-1]["t_s"] + args.interval
                    while time.perf_counter() - start < next_start:
                        time.sleep(0.05)
                t = time.perf_counter() - start
                entry = {"t_s": round(t, 1), "time": now_iso(), "shift_px": list(shift)}
                try:
                    result, measurements = auto_setup_check(measure, calibration, s.canvas_size, limits[-1])
                except AutoCalibrationError as e:
                    entry.update(detected=False, error=str(e), details=e.details)
                    print(f"  t={t:6.1f} s shift {shift}: corners NOT detected: {e}")
                    checks.append(entry)
                    continue
                corner = np.linalg.norm(np.array(result.shifts), axis=1)
                entry.update(
                    detected=True, variation_px=result.variation, mean_shift_px=list(result.mean_shift),
                    shifts_px=[list(v) for v in result.shifts], max_corner_shift_px=float(corner.max()),
                    worst_single_sd_px=max(m.single_sd or 0.0 for m in measurements),
                    verdicts={f"{lim:g}": result.variation <= lim for lim in limits},
                )
                checks.append(entry)
                verdicts = "  ".join(f"<= {lim:g}: {'ok' if ok else 'REFUSED'}" for lim, ok in zip(limits, entry["verdicts"].values()))
                print(f"  t={t:6.1f} s shift {str(shift):>8}: variation {result.variation:5.2f} px, mean shift "
                      f"({result.mean_shift[0]:+.2f}, {result.mean_shift[1]:+.2f}), largest corner {corner.max():.2f}  |  {verdicts}")

    by_shift = {}
    for c in checks:
        if c.get("detected"):
            by_shift.setdefault(tuple(c["shift_px"]), []).append(c["variation_px"])
    summary = {f"{dx},{dy}": {"n": len(v), "min": min(v), "max": max(v), "mean": float(np.mean(v)),
                              **{f"refused_at_{lim:g}": sum(x > lim for x in v) for lim in limits}}
               for (dx, dy), v in by_shift.items()}
    report = {"created_at": now_iso(), "mode": "diagnostic (read-only)", "calibration_created_at": calibration.created_at,
              "calibration_method": calibration.method, "limits_px": limits, "repeat": args.repeat,
              "interval_s": args.interval, "checks": checks, "summary": summary,
              "corner_names": list(CORNER_NAMES)}
    path = save_report(config, "setupcheck", report)
    print("summary (variation, camera px):")
    for key, v in summary.items():
        refused = ", ".join(f"refused at {lim:g}: {v[f'refused_at_{lim:g}']}/{v['n']}" for lim in limits)
        print(f"  shift {key:>7}: n {v['n']}, min {v['min']:.2f}, mean {v['mean']:.2f}, max {v['max']:.2f}; {refused}")
    print(f"report: {path}")
    return 0 if all(c.get("detected") for c in checks) else 1
