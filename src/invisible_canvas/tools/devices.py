"""`devices`: hardware diagnostics for displays and cameras (brain.md step 1A.1).

Lists every display (EDID name, connector, resolution, refresh rate, scaling, modes)
and identifies the projector explicitly. Lists every DirectShow camera and measures
the modes each physical camera really delivers. Saves a JSON report.
"""

from __future__ import annotations

import dataclasses
import platform

import cv2
import numpy as np

from ..camera.directshow import list_capture_devices
from ..camera.exposure import read_exposure
from ..camera.locks import FOCUS_SETTING, GAIN_SETTING, read_setting
from ..camera.probe import DEFAULT_MODES, probe_mode
from ..config import Config
from ..display import monitors
from .common import now_iso, save_report


def add_parser(subparsers) -> None:
    p = subparsers.add_parser("devices", help="hardware diagnostics: displays, projector, cameras")
    p.add_argument("--display", help="projector selection override (EDID name/id or GDI name)")
    p.add_argument("--camera", help="probe only cameras whose name contains this (also used for selection)")
    p.add_argument("--quick", action="store_true", help="list only; skip camera mode probing")
    p.add_argument("--all-cameras", action="store_true", help="also probe virtual cameras (no USB id)")
    p.add_argument("--seconds", type=float, default=2.0, help="fps measurement time per mode (default 2)")
    p.set_defaults(func=run)


def _display_section(config: Config, report: dict) -> bool:
    displays = monitors.list_displays()
    report["displays"] = [dataclasses.asdict(d) | {"modes": [str(m) for m in d.modes]} for d in displays]
    print(f"\nDISPLAYS ({len(displays)})")
    for d in displays:
        tag = "PRIMARY" if d.primary else ""
        print(f"  {d.label}  output={d.output}  {tag}")
        print(f"      desktop {d.width}x{d.height} at ({d.x},{d.y}) | {d.refresh_hz:g} Hz | "
              f"{d.bits_per_pixel} bpp | scaling {d.scale_percent} %")
        top = str(d.modes[0]) if d.modes else "-"
        print(f"      {len(d.modes)} modes (largest {top}) | "
              f"{config.projector.expected_width}x{config.projector.expected_height} offered: "
              f"{'yes' if d.supports(config.projector.expected_width, config.projector.expected_height) else 'no'}")

    print("\nPROJECTOR")
    try:
        projector, rule = monitors.select_projector(displays, config.projector.match)
    except monitors.ProjectorNotFound as e:
        print(f"  NOT IDENTIFIED: {e}")
        report["projector"] = {"identified": False, "reason": str(e)}
        return False
    w, h = config.projector.expected_width, config.projector.expected_height
    checks = {
        f"current mode {w}x{h}": (projector.width, projector.height) == (w, h),
        "scaling 100 %": projector.scale_percent == 100,
        f"{w}x{h} offered": projector.supports(w, h),
    }
    print(f"  identified: {projector.label} output={projector.output} ({rule})")
    for name, ok in checks.items():
        print(f"  [{'OK' if ok else 'WARN'}] {name}")
    report["projector"] = {"identified": True, "gdi_name": projector.gdi_name, "label": projector.label,
                           "rule": rule, "checks": checks}
    return True


def _camera_section(config: Config, args, report: dict) -> bool:
    devices = list_capture_devices()
    report["cameras"] = []
    print(f"\nCAMERAS ({len(devices)} DirectShow devices; index = OpenCV CAP_DSHOW index)")
    for d in devices:
        kind = f"usb {d.usb_id}" if d.vid else "virtual / no USB id"
        print(f"  [{d.index}] {d.name}  ({kind})")

    print("\nCAMERA SELECTION")
    selected_ok = False
    if config.camera.match:
        hits = [d for d in devices if config.camera.match.casefold() in d.name.casefold()]
        if len(hits) == 1:
            print(f"  identified: [{hits[0].index}] {hits[0].name} (matches {config.camera.match!r})")
            selected_ok = True
        else:
            print(f"  NOT IDENTIFIED: {len(hits)} devices match {config.camera.match!r}")
        report["camera_selection"] = {"match": config.camera.match, "hits": [d.name for d in hits]}
    else:
        print(f"  by index {config.camera.index} (no name match configured)")
        report["camera_selection"] = {"index": config.camera.index}
        selected_ok = True

    for d in devices:
        entry = {"index": d.index, "name": d.name, "path": d.path, "usb_id": d.usb_id, "modes": [], "properties": {}}
        report["cameras"].append(entry)
        if args.camera and args.camera.casefold() not in d.name.casefold():
            continue
        if not d.vid and not args.all_cameras:
            continue
        print(f"\nCAMERA MODES [{d.index}] {d.name}  (backend {config.camera.backend})")
        modes = [None] if args.quick else [None, *DEFAULT_MODES]
        for mode in modes:
            result, props = probe_mode(d.index, config.camera.backend, mode,
                                       seconds=args.seconds, with_properties=mode is None)
            entry["modes"].append(dataclasses.asdict(result))
            if props:
                entry["properties"] = props
            detail = result.error or (
                f"{result.delivered} (driver says {result.reported_fps:g} fps; open {result.open_seconds:.2f} s)"
            )
            print(f"  {result.requested:<20} -> {detail}")
        if entry["properties"]:
            props = ", ".join(f"{k}={v:g}" for k, v in entry["properties"].items())
            print(f"  properties (read-only): {props}")
        if config.camera.backend == "dshow":
            # Read only. Each probe opens a new stream, and the camera stack resets exposure
            # to its stored value at stream start, so these modes ran with the exposure read
            # here. The tools apply and keep [camera] exposure_mode (CameraManager).
            exposure = read_exposure(d.index)
            entry["exposure"] = dataclasses.asdict(exposure)
            print(f"  exposure during probing (read-only; `camera` measures the configured exposure): "
                  f"{exposure.effective()}")
            for setting in (FOCUS_SETTING, GAIN_SETTING):
                state = read_setting(setting, d.index)
                entry[setting.name] = dataclasses.asdict(state)
                print(f"  {setting.name} during probing (read-only; `camera` measures the configured "
                      f"{setting.name}): {state.effective()}")
    return selected_ok


def run(config: Config, args) -> int:
    report = {
        "created_at": now_iso(),
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "opencv": cv2.__version__,
            "os": platform.platform(),
            "dpi_awareness": monitors.dpi_awareness(),
        },
    }
    env = report["environment"]
    print(f"Invisible Canvas hardware diagnostics  {report['created_at']}")
    print(f"Python {env['python']} | numpy {env['numpy']} | OpenCV {env['opencv']} | "
          f"DPI awareness: {env['dpi_awareness']}")

    projector_ok = _display_section(config, report)
    camera_ok = _camera_section(config, args, report)

    path = save_report(config, "devices", report)
    print(f"\nprojector identified: {'yes' if projector_ok else 'NO'} | "
          f"camera identified: {'yes' if camera_ok else 'NO'}")
    print(f"report: {path}")
    return 0 if projector_ok and camera_ok else 1


if __name__ == "__main__":
    # `python -m invisible_canvas.tools.devices [options]` is the same as
    # `python -m invisible_canvas devices [options]`: go through the package CLI so
    # DPI awareness, timer resolution and config loading happen exactly as there.
    import sys

    from ..__main__ import main

    sys.exit(main(["devices", *sys.argv[1:]]))
