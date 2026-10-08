"""Command-line entry point: python -m invisible_canvas <command>."""

from __future__ import annotations

import argparse
import ctypes
import logging
import sys
from pathlib import Path

from .calibration.store import CalibrationError
from .camera.manager import CameraError
from .config import ConfigError, load_config, with_overrides
from .display import monitors
from .tools import calibrate, camera_check, devices, latency, map_demo, projector_check, validate

# Order = the order of the Phase 1A runbook (brain.md section 9.5).
TOOLS = (devices, projector_check, camera_check, latency, calibrate, validate, map_demo)

# Expected, user-fixable failures: print the message, no traceback.
USER_ERRORS = (CameraError, CalibrationError, monitors.ProjectorNotFound)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m invisible_canvas",
        description="Invisible Canvas: Phase 1A foundation tools (see brain.md).",
    )
    parser.add_argument("--config", type=Path, help="config file (default: config/default.toml)")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")
    for tool in TOOLS:
        tool.add_parser(subparsers)
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    # Must happen before any window is created or any display is queried:
    # the laptop runs at 150 % scaling.
    monitors.enable_dpi_awareness()
    # 1 ms timer resolution: otherwise every cv2.waitKey(1) sleeps a full ~15.6 ms
    # Windows tick, which adds that much latency to the GUI loop.
    ctypes.WinDLL("winmm").timeBeginPeriod(1)

    try:
        config = load_config(args.config)
        config = with_overrides(
            config, display=getattr(args, "display", None), camera=getattr(args, "camera", None)
        )
    except ConfigError as e:
        print(f"config error: {e}", file=sys.stderr)
        return 2
    try:
        return args.func(config, args)
    except USER_ERRORS as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
