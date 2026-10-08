"""Camera capability probing for diagnostics.

Measures what the driver really delivers: for each requested mode the camera is
reopened, configured, and the actual frame size and delivered frame rate are
measured from real frames. Reported values from the driver are recorded alongside,
but never trusted on their own.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import cv2

BACKENDS = {"dshow": cv2.CAP_DSHOW, "msmf": cv2.CAP_MSMF, "any": cv2.CAP_ANY}

DEFAULT_MODES: tuple[tuple[str, int, int, int], ...] = (
    ("MJPG", 1920, 1080, 30),
    ("MJPG", 1920, 1080, 60),
    ("MJPG", 1280, 720, 30),
    ("MJPG", 1280, 720, 60),
    ("MJPG", 640, 480, 30),
    ("MJPG", 640, 480, 60),
    ("YUY2", 1920, 1080, 30),
    ("YUY2", 1280, 720, 30),
    ("YUY2", 640, 480, 30),
)

PROPERTY_NAMES = (
    "BRIGHTNESS", "CONTRAST", "SATURATION", "SHARPNESS", "GAMMA", "GAIN",
    "EXPOSURE", "AUTO_EXPOSURE", "AUTOFOCUS", "FOCUS", "AUTO_WB", "WB_TEMPERATURE",
    "BACKLIGHT", "ZOOM", "PAN", "TILT",
)


def decode_fourcc(value: float) -> str:
    code = int(value)
    if code <= 0:
        return ""
    text = "".join(chr((code >> (8 * i)) & 0xFF) for i in range(4))
    return text if text.isprintable() else f"0x{code:08X}"


@dataclass(frozen=True)
class ModeResult:
    requested: str          # e.g. "MJPG 1920x1080@30", or "default"
    opened: bool
    frame_width: int
    frame_height: int
    reported_fourcc: str
    reported_fps: float
    measured_fps: float
    frames: int
    open_seconds: float
    error: str = ""

    @property
    def delivered(self) -> str:
        if not self.frames:
            return "no frames"
        return f"{self.frame_width}x{self.frame_height} {self.reported_fourcc or '?'} {self.measured_fps:.1f} fps"


def configure(cap: cv2.VideoCapture, fourcc: str, width: int, height: int, fps: int) -> None:
    """Request a mode. Order matters for some DirectShow drivers: FOURCC first."""
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, fps)


def measure(cap: cv2.VideoCapture, seconds: float, warmup: float) -> tuple[int, float, tuple[int, int]]:
    """Read frames for `warmup` + `seconds`; return (frames, measured fps, frame size)."""
    end_warmup = time.perf_counter() + warmup
    while time.perf_counter() < end_warmup:
        cap.read()
    stamps = []
    size = (0, 0)
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        ok, frame = cap.read()
        if ok and frame is not None:
            stamps.append(time.perf_counter())
            size = (frame.shape[1], frame.shape[0])
    fps = (len(stamps) - 1) / (stamps[-1] - stamps[0]) if len(stamps) >= 2 else 0.0
    return len(stamps), fps, size


def read_properties(cap: cv2.VideoCapture) -> dict[str, float]:
    """Driver-reported property values. Read-only: nothing is changed on the camera."""
    return {name: float(cap.get(getattr(cv2, f"CAP_PROP_{name}"))) for name in PROPERTY_NAMES}


def probe_mode(
    index: int,
    backend: str,
    mode: tuple[str, int, int, int] | None,
    *,
    seconds: float = 2.0,
    warmup: float = 0.5,
    with_properties: bool = False,
) -> tuple[ModeResult, dict[str, float]]:
    """Open the camera, request `mode` (None = driver default) and measure it."""
    label = "default" if mode is None else f"{mode[0]} {mode[1]}x{mode[2]}@{mode[3]}"
    t0 = time.perf_counter()
    cap = cv2.VideoCapture(index, BACKENDS[backend])
    try:
        if not cap.isOpened():
            return ModeResult(label, False, 0, 0, "", 0.0, 0.0, 0, time.perf_counter() - t0, "could not open"), {}
        if mode is not None:
            configure(cap, *mode)
        ok, _ = cap.read()
        open_seconds = time.perf_counter() - t0
        if not ok:
            return ModeResult(label, True, 0, 0, "", 0.0, 0.0, 0, open_seconds, "no frame after open"), {}
        frames, fps, (w, h) = measure(cap, seconds, warmup)
        result = ModeResult(
            requested=label,
            opened=True,
            frame_width=w,
            frame_height=h,
            reported_fourcc=decode_fourcc(cap.get(cv2.CAP_PROP_FOURCC)),
            reported_fps=float(cap.get(cv2.CAP_PROP_FPS)),
            measured_fps=round(fps, 2),
            frames=frames,
            open_seconds=round(open_seconds, 2),
        )
        properties = read_properties(cap) if with_properties else {}
        return result, properties
    finally:
        cap.release()
