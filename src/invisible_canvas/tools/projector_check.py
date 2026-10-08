"""`projector`: projector output check (brain.md A2).

Shows an alignment pattern, white, black and the dark canvas fullscreen on the
identified projector, and reports whether the window really covers the display.
"""

from __future__ import annotations

import time

import cv2

from ..config import Config
from ..display import patterns
from ..display.projector import ProjectorWindow
from .common import add_device_args, resolve_projector


def add_parser(subparsers) -> None:
    p = subparsers.add_parser("projector", help="show the alignment pattern on the projector (A2)")
    add_device_args(p, camera=False)
    p.add_argument("--seconds", type=float, default=0.0, help="close automatically after N seconds")
    p.set_defaults(func=run)


def run(config: Config, args) -> int:
    display, size, description = resolve_projector(config, args.windowed)
    print(f"projector: {description}")
    screens = [
        ("alignment pattern", patterns.alignment_pattern(size)),
        ("white (check camera saturation)", patterns.blank(size, 255)),
        ("black (check ambient light)", patterns.blank(size, 0)),
        ("dark canvas", patterns.dark_canvas(size)),
    ]
    window = ProjectorWindow(display, size, windowed=args.windowed)
    window.open()
    print(f"window geometry: {'OK' if window.geometry_ok else 'NOT OK'}: {window.geometry_report}")
    print("SPACE: next screen | ESC/q: quit")
    index = 0
    window.show(screens[0][1])
    print(f"showing: {screens[0][0]}")
    start = time.perf_counter()
    try:
        while True:
            key = cv2.waitKey(30)
            if key in (27, ord("q")):
                break
            if key == 32:
                index = (index + 1) % len(screens)
                window.show(screens[index][1])
                print(f"showing: {screens[index][0]}")
            if args.seconds and time.perf_counter() - start > args.seconds:
                break
    finally:
        window.close()
        cv2.destroyAllWindows()
    return 0 if window.geometry_ok else 1
