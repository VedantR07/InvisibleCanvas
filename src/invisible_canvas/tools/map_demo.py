"""`mapdemo`: live camera -> canvas mapping check (brain.md A8).

Hover over any spot of the surface in the camera view: the projector draws a
crosshair at the mapped canvas position, which should land on that physical spot.
Click to pin points (e.g. on stickers) and measure the offsets with a ruler.
"""

from __future__ import annotations

import cv2

from ..calibration.collect import draw_point
from ..calibration.store import check_compatible, load_calibration
from ..config import Config
from ..display import patterns
from ..mapping.mapper import CoordinateMapper
from .calibrate import draw_canvas_outline
from .common import add_device_args, now_iso, open_session, save_report


def add_parser(subparsers) -> None:
    p = subparsers.add_parser("mapdemo", help="hover in the camera view, crosshair projected there (A8)")
    add_device_args(p)
    p.set_defaults(func=run)


def run(config: Config, args) -> int:
    calibration = load_calibration(config.calibration_dir)
    pins: list[dict] = []
    with open_session(config, args) as s:
        check_compatible(calibration, s.camera_info.size, s.canvas_size)
        mapper = CoordinateMapper.from_calibration(calibration)
        state = {"hover": None}

        def on_mouse(kind: str, x: float, y: float) -> None:
            if kind == "move":
                state["hover"] = (x, y)
            elif kind == "click":
                px, py = mapper.map_point(x, y)
                pins.append({"camera": [x, y], "projector": [px, py]})
                print(f"pin {len(pins)}: camera ({x:.2f}, {y:.2f}) -> canvas ({px:.2f}, {py:.2f})")
            elif kind == "rclick" and pins:
                pins.pop()

        s.operator.on_mouse = on_mouse
        while True:
            frame = s.camera.wait_frame(0, 2.0)
            if frame is None:
                break
            view = frame.image.copy()
            draw_canvas_outline(view, mapper, patterns.DIM)
            projected = patterns.dark_canvas(s.canvas_size)
            for k, pin in enumerate(pins):
                patterns.draw_crosshair(projected, pin["projector"], patterns.YELLOW)
                patterns.text(projected, str(k + 1), (pin["projector"][0] + 14, pin["projector"][1] - 14),
                              patterns.YELLOW)
                draw_point(view, pin["camera"], patterns.YELLOW, str(k + 1))
            lines = [
                "MAP DEMO",
                "Hover over the surface in the camera view: the crosshair is projected at the mapped point.",
                "Click: pin (numbered) | right-click: remove last | c: clear | ESC: quit",
                "",
            ]
            hover = state["hover"]
            if hover is not None:
                px, py = mapper.map_point(*hover)
                inside = bool(mapper.inside_canvas([[px, py]])[0])
                if inside:
                    patterns.draw_crosshair(projected, (px, py))
                lines.append(f"camera ({hover[0]:.1f}, {hover[1]:.1f}) -> canvas ({px:.1f}, {py:.1f})"
                             + ("" if inside else " outside canvas"))
            lines.append(f"pins: {len(pins)}")
            s.projector.show(projected)
            s.operator.show(view, raw=frame.image, loupe_center=hover, lines=lines)
            key = cv2.waitKey(1)
            if key == 27:
                break
            if key == ord("c"):
                pins.clear()
        s.operator.on_mouse = None

    if pins:
        report = {"created_at": now_iso(), "calibration_created_at": calibration.created_at, "pins": pins,
                  "note": "record the measured physical offset of each pin in brain.md (A8)"}
        print(f"report: {save_report(config, 'mapdemo', report)}")
    return 0
