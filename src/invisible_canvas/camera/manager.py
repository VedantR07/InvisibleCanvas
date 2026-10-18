"""Camera Manager: low-latency capture on a background thread (brain.md D9).

- Only the latest frame is kept; stale frames are dropped, never queued.
- Every VideoCapture call, including open and release, runs on the capture thread.
  Other threads use `call()`, which queues work to that thread.
- The negotiated mode is verified from real frames, not from driver-reported values.
- The configured exposure (D24), focus (D42) and gain (D43) are applied on every open,
  verified by read-back and kept applied while streaming.
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
from .exposure import ExposureKeeper, ExposureState
from .locks import FOCUS_SETTING, GAIN_SETTING, LockKeeper, LockState
from .probe import BACKENDS, configure, decode_fourcc, read_properties

log = logging.getLogger(__name__)

# How often the capture thread checks that the camera still holds the configured exposure,
# focus and gain.
# The Brio's exposure is reset ~1 s and ~3 s after each stream start (brain.md D24).
EXPOSURE_CHECK_SECONDS = 0.25


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
    reported_fourcc: str       # driver-reported; matched the measured behaviour on the Brio 100 (brain.md R17)
    reported_fps: float        # driver-reported; not a measurement (60 is reported when 15 are delivered)
    requested: str
    open_seconds: float
    exposure: ExposureState | None = None   # at open; None: not read (backend is not dshow)
    focus: LockState | None = None          # at open; None: not read (backend is not dshow)
    gain: LockState | None = None           # at open; None: not read (backend is not dshow)

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
    exposure_reapplied: int = 0  # times the camera lost the configured exposure and it was re-applied
    focus_reapplied: int = 0     # the same for focus
    gain_reapplied: int = 0      # the same for gain


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
    """`allow_mode_mismatch`: warn instead of failing when the camera does not deliver the
    requested size or does not confirm the requested exposure, focus or gain (diagnostic tools)."""

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
        self._exposure: ExposureKeeper | None = None   # capture thread only
        self._locks: dict[str, LockKeeper] = {}         # focus, gain; capture thread only
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
        exposure = None
        locks: dict[str, LockState] = {}
        if c.backend == "dshow":
            # Applied while streaming, through DirectShow (the CAP_DSHOW index is the same
            # device), then kept applied by the capture loop.
            self._exposure = ExposureKeeper(index, c.exposure_mode, c.exposure_value)
            exposure = self._exposure.open()
            if not exposure.ok:
                self._exposure.close()   # nothing to keep
            for setting, mode, value in ((FOCUS_SETTING, c.focus_mode, c.focus_value),
                                         (GAIN_SETTING, c.gain_mode, c.gain_value)):
                keeper = LockKeeper(setting, index, mode, value)
                locks[setting.name] = keeper.open()
                if not locks[setting.name].ok:
                    keeper.close()       # nothing to keep
                self._locks[setting.name] = keeper
        self.info = CameraInfo(
            index=index, name=name, backend=c.backend, width=width, height=height,
            reported_fourcc=decode_fourcc(cap.get(cv2.CAP_PROP_FOURCC)),
            reported_fps=float(cap.get(cv2.CAP_PROP_FPS)),
            requested=requested, open_seconds=time.perf_counter() - t0, exposure=exposure,
            focus=locks.get("focus"), gain=locks.get("gain"),
        )
        problems = []
        if (width, height) != (c.width, c.height):
            problems.append((f"camera delivers {width}x{height}, requested {requested}",
                             "Check `devices` for the modes this camera supports."))
        if exposure is not None and not exposure.ok:
            problems.append((f"exposure {exposure.describe()}",
                             'Fix [camera] exposure_mode/exposure_value, or use exposure_mode = "unchanged".'))
        for name, state in locks.items():
            if not state.ok:
                problems.append((f"{name} {state.describe()}",
                                 f'Fix [camera] {name}_mode/{name}_value, or use {name}_mode = "unchanged".'))
        for message, advice in problems:
            if not self.allow_mode_mismatch:
                cap.release()
                raise CameraError(f"{message}. {advice}")
            log.warning(message)
        return cap

    def _keep_exposure(self) -> None:
        state = self._exposure.check()
        if state is None:
            return
        if state.ok:
            log.info("camera reset its exposure; re-applied %s (%d so far)",
                     state.requested, self._exposure.reapplied)
        else:
            self.error = f"exposure {state.describe()}"
            log.error(self.error)
            self._exposure.close()   # stop retrying; the error stays visible

    def _keep_locks(self) -> None:
        for name, keeper in self._locks.items():
            state = keeper.check()
            if state is None:
                continue
            if state.ok:
                log.info("camera reset its %s; re-applied %s (%d so far)", name, state.requested, keeper.reapplied)
            else:
                self.error = f"{name} {state.describe()}"
                log.error(self.error)
                keeper.close()   # stop retrying; the error stays visible

    def _close_controls(self) -> None:
        for keeper in (self._exposure, *self._locks.values()):
            if keeper is not None:
                keeper.close()

    def _run(self, index: int, name: str) -> None:
        try:
            cap = self._open_capture(index, name)
        except BaseException as e:  # reported to open()
            self._close_controls()
            self._open_error = e
            self._ready.set()
            return
        self._ready.set()
        last = None
        next_exposure_check = 0.0
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
                # After publishing the frame, so the check never delays one.
                if now >= next_exposure_check:
                    next_exposure_check = now + EXPOSURE_CHECK_SECONDS
                    if self._exposure is not None:
                        self._keep_exposure()
                    self._keep_locks()
        finally:
            self._run_commands(cap)
            cap.release()
            self._close_controls()

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

    def read_exposure(self) -> ExposureState | None:
        """Exposure as the camera reports it now (None: not dshow, or not kept)."""
        return self.call(lambda cap: self._exposure.read() if self._exposure is not None else None)

    def read_focus(self) -> LockState | None:
        """Focus as the camera reports it now (None: not dshow, or not kept)."""
        return self._read_lock("focus")

    def read_gain(self) -> LockState | None:
        """Gain as the camera reports it now (None: not dshow, or not kept)."""
        return self._read_lock("gain")

    def _read_lock(self, name: str) -> LockState | None:
        return self.call(lambda cap: self._locks[name].read() if name in self._locks else None)

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
            exposure_reapplied=self._exposure.reapplied if self._exposure is not None else 0,
            focus_reapplied=self._locks["focus"].reapplied if "focus" in self._locks else 0,
            gain_reapplied=self._locks["gain"].reapplied if "gain" in self._locks else 0,
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
