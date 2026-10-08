"""Command-line entry point: python -m invisible_canvas <command>."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .config import ConfigError, load_config, with_overrides
from .display import monitors
from .tools import devices

TOOLS = (devices,)


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

    try:
        config = load_config(args.config)
        config = with_overrides(
            config, display=getattr(args, "display", None), camera=getattr(args, "camera", None)
        )
    except ConfigError as e:
        print(f"config error: {e}", file=sys.stderr)
        return 2
    return args.func(config, args)


if __name__ == "__main__":
    sys.exit(main())
