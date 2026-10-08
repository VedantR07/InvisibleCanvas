"""Camera Manager: low-latency capture on a background thread (brain.md D9).

- Only the latest frame is kept; stale frames are dropped, never queued.
- Every VideoCapture call, including open and release, runs on the capture thread.
  Other threads use `call()`, which queues work to that thread.
- The negotiated mode is verified from real frames, not from driver-reported values.
"""

from __future__ import annotations

import collections
import logging
import queue
import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass

import cv2
import numpy as np

from ..config import CameraConfig
from .directshow import list_capture_devices
from .probe import BACKENDS, configure, decode_fourcc, read_properties

log = logging.getLogger(__name__)


class CameraError(RuntimeError):
    """The camera cannot be found, opened, or does not deliver the requested mode."""


@dataclass(frozen=True)
class Frame:
    image: np.ndarray
    seq: int            # 1, 2, 3, ... in arrival order
    timestamp: float    # time.perf_counter() when read() returned


@dataclass(frozen=True)
class CameraInfo:
    index: int
    name: str
    backend: str
    width: int                 # measured from the first frame
    height: int
    reported_fourcc: str       # driver-reported; not reliable under DirectShow (brain.md R17)
    reported_fps: float
    requested: str
    open_seconds: float

    @property
    def size(self) -> tuple[int, int]:
        return self.width, self.height


@dataclass(frozen=True)
class CaptureStats:
    frames: int
    duration: float
    mean_fps: float
    recent_fps: float
    max_interval: float        # longest gap between consecutive frames, seconds
    read_failures: int


def resolve_camera(config: CameraConfig) -> tuple[int, str]:
    """Camera index and name from the name match (or the configured index)."""
    if not config.match:
        return config.index, f"camera index {config.index}"
    devices = list_capture_devices()
    hits = [d for d in devices if config.match.casefold() in d.name.casefold()]
    if len(hits) == 1:
        return hits[0].index, hits[0].name
    listing = "\n".join(f"  [{d.index}] {d.name} ({d.usb_id})" for d in devices) or "  (none)"
    problem = "no camera" if not hits else f"{len(hits)} cameras"
    raise CameraError(
        f"{problem} named like {config.match!r}. Connect it, or set [camera] match / pass --camera.\n"
        f"DirectShow cameras:\n{listing}"
    )


class CameraManager:
    def __init__(self, config: CameraConfig, *, allow_mode_mismatch: bool = False):
        self.config = config
        self.allow_mode_mismatch = allow_mode_mismatch
        self.info: CameraInfo | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._open_error: BaseException | None = None
        self._commands: queue.SimpleQueue = queue.SimpleQueue()
        self._cond = threading.Condition()
        self._frame: Frame | None = None
        self._stamps: collections.deque[float] = collections.deque(maxlen=100_000)
        self._max_interval = 0.0
        self._failures = 0
        self.error: str | None = None

    # -- lifecycle ----------------------------------------------------------

    def open(self, timeout: float = 15.0) -> CameraInfo:
        index, name = resolve_camera(self.config)
        self._thread = threading.Thread(target=self._run, args=(index, name), name="camera", daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout):
            self._stop.set()
            raise CameraError(f"camera {name!r} did not open within {timeout:.0f} s")
        if self._open_error is not None:
            raise self._open_error
        return self.info

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None

    def __enter__(self) -> CameraManager:
        self.open()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- capture thread -----------------------------------------------------

    def _open_capture(self, index: int, name: str) -> cv2.VideoCapture:
        c = self.config
        t0 = time.perf_counter()
        cap = cv2.VideoCapture(index, BACKENDS[c.backend])
        if not cap.isOpened():
            raise CameraError(f"could not open camera [{index}] {name!r} with backend {c.backend}")
        configure(cap, c.fourcc, c.width, c.height, c.fps)
        frame = None
        for _ in range(10):
            ok, frame = cap.read()
            if ok and frame is not None:
                break
        else:
            cap.release()
            raise CameraError(f"camera [{index}] {name!r} opened but delivered no frames")
        height, width = frame.shape[:2]
        requested = f"{c.fourcc} {c.width}x{c.height}@{c.fps}"
        self.info = CameraInfo(
            index=index, name=name, backend=c.backend, width=width, height=height,
            reported_fourcc=decode_fourcc(cap.get(cv2.CAP_PROP_FOURCC)),
            reported_fps=float(cap.get(cv2.CAP_PROP_FPS)),
            requested=requested, open_seconds=time.perf_counter() - t0,
        )
        if (width, height) != (c.width, c.height):
            message = f"camera delivers {width}x{height}, requested {requested}"
            if not self.allow_mode_mismatch:
                cap.release()
                raise CameraError(message + ". Check `devices` for the modes this camera supports.")
            log.warning(message)
        return cap

    def _run(self, index: int, name: str) -> None:
        try:
            cap = self._open_capture(index, name)
        except BaseException as e:  # reported to open()
            self._open_error = e
            self._ready.set()
            return
        self._ready.set()
        last = None
        try:
            while not self._stop.is_set():
                self._run_commands(cap)
                ok, image = cap.read()
                now = time.perf_counter()
                if not ok or image is None:
                    self._failures += 1
                    if self._failures % 30 == 0:
                        self.error = f"camera stopped delivering frames ({self._failures} failed reads)"
                        log.error(self.error)
                    continue
                if last is not None:
                    self._max_interval = max(self._max_interval, now - last)
                last = now
                with self._cond:
                    seq = self._frame.seq + 1 if self._frame else 1
                    self._frame = Frame(image, seq, now)
                    self._stamps.append(now)
                    self._cond.notify_all()
        finally:
            self._run_commands(cap)
            cap.release()

    def _run_commands(self, cap: cv2.VideoCapture) -> None:
        while True:
            try:
                fn, future = self._commands.get_nowait()
            except queue.Empty:
                return
            try:
                future.set_result(fn(cap))
            except BaseException as e:
                future.set_exception(e)

    # -- consumer API -------------------------------------------------------

    def latest(self) -> Frame | None:
        with self._cond:
            return self._frame

    def wait_frame(self, after_seq: int = 0, timeout: float = 1.0) -> Frame | None:
        """The first frame with seq > after_seq, or None on timeout."""
        deadline = time.perf_counter() + timeout
        with self._cond:
            while self._frame is None or self._frame.seq <= after_seq:
                remaining = deadline - time.perf_counter()
                if remaining <= 0:
                    return None
                self._cond.wait(remaining)
            return self._frame

    def call(self, fn, timeout: float = 5.0):
        """Run fn(cap) on the capture thread and return its result."""
        future: Future = Future()
        self._commands.put((fn, future))
        return future.result(timeout)

    def open_settings_dialog(self) -> None:
        """The driver's own property dialog (DirectShow): exposure, focus, white balance."""
        self.call(lambda cap: cap.set(cv2.CAP_PROP_SETTINGS, 1))

    def read_properties(self) -> dict[str, float]:
        return self.call(read_properties)

    def reset_stats(self) -> None:
        with self._cond:
            self._stamps.clear()
        self._max_interval = 0.0
        self._failures = 0

    def timestamps(self) -> np.ndarray:
        with self._cond:
            return np.array(self._stamps)

    def stats(self) -> CaptureStats:
        stamps = self.timestamps()
        n = len(stamps)
        duration = float(stamps[-1] - stamps[0]) if n >= 2 else 0.0
        recent = stamps[-31:]
        recent_fps = (len(recent) - 1) / (recent[-1] - recent[0]) if len(recent) >= 2 and recent[-1] > recent[0] else 0.0
        return CaptureStats(
            frames=n,
            duration=duration,
            mean_fps=(n - 1) / duration if duration > 0 else 0.0,
            recent_fps=float(recent_fps),
            max_interval=self._max_interval,
            read_failures=self._failures,
        )


def per_second_fps(stamps: np.ndarray) -> np.ndarray:
    """Frames in each consecutive full 1-second window (for the 'sustained fps' test)."""
    stamps = np.asarray(stamps, dtype=np.float64)
    if len(stamps) < 2:
        return np.array([])
    seconds = int((stamps[-1] - stamps[0]) // 1.0)
    edges = stamps[0] + np.arange(seconds + 1)
    counts, _ = np.histogram(stamps, bins=edges)
    return counts.astype(np.float64)
