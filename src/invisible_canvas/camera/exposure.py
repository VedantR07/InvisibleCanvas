"""Exposure control from `[camera] exposure_mode` / `exposure_value` (brain.md D24).

The request goes through DirectShow's IAMCameraControl and is then read back: it counts
as applied only when the camera reports the requested state. OpenCV's CAP_PROP_EXPOSURE
is not used because under CAP_DSHOW it cannot read back whether exposure is auto or manual.

Values are DirectShow units: exposure time = 2**value seconds (-5 = 31.25 ms). Measured on
the Brio 100: auto exposure in dim light lowers the frame rate to ~15 fps; manual -5 or
shorter holds 30 fps.
"""

from __future__ import annotations

from dataclasses import dataclass

from .directshow import AUTO_EXPOSURE_PRIORITY, EXPOSURE, FLAG_AUTO, FLAG_MANUAL, CameraControl

MODES = ("manual", "auto", "unchanged")


def exposure_ms(value: int) -> float:
    return 1000.0 * 2.0 ** value


@dataclass(frozen=True)
class ExposureState:
    """The configured request and what the camera reports (None = not readable)."""
    requested: str              # "manual -5", "auto" or "unchanged"
    ok: bool                    # the camera reports the requested state ("unchanged": nothing requested)
    value: int | None = None
    auto: bool | None = None
    priority: int | None = None  # AutoExposurePriority; 1 lets auto exposure lower the frame rate
    error: str = ""

    def effective(self) -> str:
        if self.auto is None:
            return "not readable"
        if self.auto:
            text = "auto"
            if self.priority == 1:
                text += " (AE priority 1: the camera may lower the frame rate in dim light)"
            return text
        return f"manual {self.value} ({exposure_ms(self.value):.1f} ms)"

    def describe(self) -> str:
        if not self.ok:
            return f"NOT APPLIED (requested {self.requested}): {self.error}; camera reports {self.effective()}"
        if self.requested == "unchanged":
            return f"unchanged by config; camera reports {self.effective()}"
        return f"{self.effective()}, confirmed by read-back"


def _requested(mode: str, value: int) -> str:
    if mode not in MODES:
        raise ValueError(f"exposure mode must be one of {MODES}, got {mode!r}")
    return f"manual {value}" if mode == "manual" else mode


def _holds(current: tuple[int, int] | None, mode: str, value: int) -> bool:
    """Whether a (value, flags) read-back is the requested state."""
    if current is None:
        return False
    auto = bool(current[1] & FLAG_AUTO)
    return auto if mode == "auto" else (not auto and current[0] == value)


def read_state(control, mode: str = "unchanged", value: int = 0, error: str = "") -> ExposureState:
    """What `control` (a `CameraControl`) reports now, judged against the request."""
    requested = _requested(mode, value)
    current = control.get(EXPOSURE)
    priority = control.get(AUTO_EXPOSURE_PRIORITY)
    if not error and mode != "unchanged":
        if current is None:
            error = "the camera does not report exposure, so the setting is not confirmed"
        elif not _holds(current, mode, value):
            error = "the camera is not in auto exposure" if mode == "auto" else f"the camera does not hold manual {value}"
    return ExposureState(
        requested=requested,
        ok=not error,
        value=current[0] if current else None,
        auto=bool(current[1] & FLAG_AUTO) if current else None,
        priority=priority[0] if priority else None,
        error=error,
    )


def apply_exposure(control, mode: str, value: int) -> ExposureState:
    """Request `mode` on `control`, read it back and report.
    Camera-side failures are returned in the state, never raised."""
    _requested(mode, value)
    error = ""
    if mode != "unchanged":
        try:
            limits = control.range(EXPOSURE)
            needed = FLAG_MANUAL if mode == "manual" else FLAG_AUTO
            if limits is None:
                error = "the camera has no exposure control"
            elif not limits.caps & needed:
                error = f"the camera does not offer {mode} exposure"
            elif mode == "manual" and not limits.min <= value <= limits.max:
                error = f"exposure_value {value} is outside the camera's range {limits.min}..{limits.max}"
            elif mode == "manual":
                control.set(EXPOSURE, value, FLAG_MANUAL)
            else:
                control.set(EXPOSURE, limits.default, FLAG_AUTO)
        except OSError as e:
            error = str(e)
    return read_state(control, mode, value, error)


class ExposureKeeper:
    """Applies the configured exposure to DirectShow device `index` and keeps it applied.

    Measured on the Brio 100 (Windows 11): about 1 s and again about 3 s after a stream
    starts, the camera stack resets exposure to its stored value (-4, auto), so a single
    set at open does not last. Call `check()` periodically while streaming; it re-applies
    the setting and counts how often that was needed. Use on one thread (COM).
    """

    def __init__(self, index: int, mode: str, value: int, *, control_factory=CameraControl):
        self.requested = _requested(mode, value)
        self.index, self.mode, self.value = index, mode, value
        self.reapplied = 0
        self._control_factory = control_factory
        self._control = None

    def open(self) -> ExposureState:
        try:
            self._control = self._control_factory(self.index).__enter__()
        except OSError as e:
            return ExposureState(self.requested, ok=self.mode == "unchanged", error=f"no camera control: {e}")
        return apply_exposure(self._control, self.mode, self.value)

    def check(self) -> ExposureState | None:
        """Re-apply if the camera no longer holds the setting. The new state, or None if it held."""
        if self._control is None or self.mode == "unchanged":
            return None
        if _holds(self._control.get(EXPOSURE), self.mode, self.value):
            return None
        self.reapplied += 1
        return apply_exposure(self._control, self.mode, self.value)

    def read(self) -> ExposureState | None:
        """The current state, without changing anything (None once closed)."""
        return None if self._control is None else read_state(self._control, self.mode, self.value)

    def close(self) -> None:
        if self._control is not None:
            self._control.__exit__(None, None, None)
            self._control = None


def read_exposure(index: int) -> ExposureState:
    """Read DirectShow device `index`'s exposure without changing it."""
    keeper = ExposureKeeper(index, "unchanged", 0)
    try:
        return keeper.open()
    finally:
        keeper.close()
