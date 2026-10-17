"""Synthetic camera for tests: the real projector rendering seen through a known homography.

Not a test module. It stands in for `CameraMeasure` (tools/common.py): given a projector screen it
returns a TargetMeasurement from synthetic background and single frames. Algorithm tests only;
real-camera performance is measured on the hardware (brain.md D29, D30).
"""

from __future__ import annotations

from types import SimpleNamespace

import cv2
import numpy as np

from invisible_canvas.calibration.auto import measurement_from_frames
from invisible_canvas.display import patterns
from invisible_canvas.geometry.homography import apply_homography
from invisible_canvas.tools.common import shifted

CANVAS = (1280, 720)
CAMERA = (1920, 1080)
# Camera -> projector, like the real setup (mild perspective, ~3 deg roll).
H_REAL = np.array([
    [0.9193, -0.01734, -241.15],
    [0.05485, 0.8773, -187.47],
    [5.837e-05, 2.885e-05, 1.0],
])


def moved(h: np.ndarray, dx: float, dy: float) -> np.ndarray:
    """The scene after the projection moved by (dx, dy) camera px in the camera image."""
    return h @ np.array([[1, 0, -dx], [0, 1, -dy], [0, 0, 1]], dtype=float)


def truth(h: np.ndarray, projector_points) -> np.ndarray:
    """Exact camera positions of projector points."""
    return apply_homography(np.linalg.inv(h), projector_points)


def warp(screen: np.ndarray, h: np.ndarray) -> np.ndarray:
    cam = cv2.warpPerspective(screen, h, CAMERA, flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP)
    return cv2.GaussianBlur(cv2.cvtColor(cam, cv2.COLOR_BGR2GRAY).astype(np.float32), (0, 0), 0.8)


class SyntheticScene:
    """`measure(screen)` with a synthetic camera. Options make it misbehave on purpose:
    fail_calls: call indexes (0-based) on which the target is not shown (blank screen);
    extra_cross_calls: call indexes on which a second cross is shown (ambiguous);
    jitter: per-frame random image shift in camera px (unstable target);
    shift: whole-projector-pixel shift of every screen (as `validate --simulate-shift`)."""

    def __init__(self, h=H_REAL, *, frames=3, noise=1.5, gain=0.8, ambient=10.0, jitter=0.0, seed=0,
                 fail_calls=(), extra_cross_calls=(), shift=(0, 0)):
        self.h, self.frames, self.noise, self.gain, self.ambient = h, frames, noise, gain, ambient
        self.jitter, self.fail_calls, self.extra_cross_calls, self.shift = jitter, set(fail_calls), set(extra_cross_calls), shift
        self.rng = np.random.default_rng(seed)
        self.calls = 0
        self.screens = []
        # A pool of independent noise fields, drawn once (full-frame normal noise is the slow part).
        self._pool = [self.rng.normal(0.0, noise, (CAMERA[1], CAMERA[0])).astype(np.float32) for _ in range(frames + 3)]
        self._next = 0

    def _noisy(self, image):
        noise = self._pool[self._next % len(self._pool)]
        self._next += 1
        out = image * self.gain + self.ambient + noise
        return np.clip(np.round(out), 0, 255).astype(np.uint8)

    def __call__(self, screen):
        call = self.calls
        self.calls += 1
        screen = shifted(screen, *self.shift)
        if call in self.fail_calls:
            screen = np.zeros_like(screen)
        if call in self.extra_cross_calls:
            screen = screen.copy()
            patterns.draw_target(screen, (640, 360), active=True)
        self.screens.append(screen)
        background = self._noisy(warp(np.zeros_like(screen), self.h))
        base = warp(screen, self.h)
        frames = []
        for _ in range(self.frames):
            if self.jitter:
                dx, dy = self.rng.uniform(-self.jitter, self.jitter, 2)
                frames.append(self._noisy(warp(screen, moved(self.h, dx, dy))))
            else:
                frames.append(self._noisy(base))
        return measurement_from_frames(background, frames)


class FakeSession:
    """Stands in for tools.common.Session: no camera, no windows."""
    canvas_size = CANVAS

    def __init__(self):
        self.camera_info = SimpleNamespace(name="Brio 100", size=CAMERA)
        self.display = SimpleNamespace(label="TEST PROJECTOR")
        self.projector = SimpleNamespace(show=lambda image: None)
        self.operator = SimpleNamespace(show=lambda *a, **k: None, on_mouse=None)
        frame = SimpleNamespace(image=np.zeros((CAMERA[1], CAMERA[0], 3), np.uint8), seq=1)
        self.camera = SimpleNamespace(latest=lambda: frame, wait_frame=lambda *a, **k: frame)
