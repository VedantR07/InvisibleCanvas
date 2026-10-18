"""Focus control from `[camera] focus_mode` / `focus_value` (brain.md D42).

Same mechanism as exposure (camera/exposure.py): the request goes through DirectShow's
IAMCameraControl and counts as applied only when the camera reports the requested state;
`FocusKeeper` keeps it applied while streaming.

Why: measured on the Kreo Owl 4K Pro (2026-10-19), autofocus is on by default and moved
while the camera was idle (395 -> 404). A refocus changes the image scale slightly and
moves image features, under a calibration that assumed a fixed camera.
Values are the camera's own units (Kreo: 0..1023).
"""

from __future__ import annotations

from dataclasses import dataclass

from .directshow import FLAG_AUTO, FLAG_MANUAL, FOCUS, CameraControl

MODES = ("manual", "auto", "unchanged")


@dataclass(frozen=True)
class FocusState:
    """The configured request and what the camera reports (None = not readable)."""
    requested: str              # "manual 400", "auto" or "unchanged"
    ok: bool                    # the camera reports the requested state ("unchanged": nothing requested)
    value: int | None = None
    auto: bool | None = None
    error: str = ""

    def effective(self) -> str:
        if self.auto is None:
            return "not readable"
        return f"auto (now at {self.value})" if self.auto else f"manual {self.value}"

    def describe(self) -> str:
        if not self.ok:
            return f"NOT APPLIED (requested {self.requested}): {self.error}; camera reports {self.effective()}"
        if self.requested == "unchanged":
            return f"unchanged by config; camera reports {self.effective()}"
        return f"{self.effective()}, confirmed by read-back"


def _requested(mode: str, value: int) -> str:
    if mode not in MODES:
        raise ValueError(f"focus mode must be one of {MODES}, got {mode!r}")
    return f"manual {value}" if mode == "manual" else mode


def _holds(current: tuple[int, int] | None, mode: str, value: int) -> bool:
    """Whether a (value, flags) read-back is the requested state."""
    if current is None:
        return False
    auto = bool(current[1] & FLAG_AUTO)
    return auto if mode == "auto" else (not auto and current[0] == value)


def read_state(control, mode: str = "unchanged", value: int = 0, error: str = "") -> FocusState:
    """What `control` (a `CameraControl`) reports now, judged against the request."""
    requested = _requested(mode, value)
    current = control.get(FOCUS)
    if not error and mode != "unchanged":
        if current is None:
            error = "the camera does not report focus, so the setting is not confirmed"
        elif not _holds(current, mode, value):
            error = "the camera is not in autofocus" if mode == "auto" else f"the camera does not hold manual {value}"
    return FocusState(
        requested=requested,
        ok=not error,
        value=current[0] if current else None,
        auto=bool(current[1] & FLAG_AUTO) if current else None,
        error=error,
    )


def apply_focus(control, mode: str, value: int) -> FocusState:
    """Request `mode` on `control`, read it back and report.
    Camera-side failures are returned in the state, never raised."""
    _requested(mode, value)
    error = ""
    if mode != "unchanged":
        try:
            limits = control.range(FOCUS)
            needed = FLAG_MANUAL if mode == "manual" else FLAG_AUTO
            if limits is None:
                error = "the camera has no focus control"
            elif not limits.caps & needed:
                error = f"the camera does not offer {mode} focus"
            elif mode == "manual" and not limits.min <= value <= limits.max:
                error = f"focus_value {value} is outside the camera's range {limits.min}..{limits.max}"
            elif mode == "manual":
                control.set(FOCUS, value, FLAG_MANUAL)
            else:
                control.set(FOCUS, limits.default, FLAG_AUTO)
        except OSError as e:
            error = str(e)
    return read_state(control, mode, value, error)


class FocusKeeper:
    """Applies the configured focus to DirectShow device `index` and keeps it applied
    (the camera stack may restore stored settings after a stream starts, as it did with the
    Brio's exposure, R21). Call `check()` periodically while streaming. Use on one thread (COM)."""

    def __init__(self, index: int, mode: str, value: int, *, control_factory=CameraControl):
        self.requested = _requested(mode, value)
        self.index, self.mode, self.value = index, mode, value
        self.reapplied = 0
        self._control_factory = control_factory
        self._control = None

    def open(self) -> FocusState:
        try:
            self._control = self._control_factory(self.index).__enter__()
        except OSError as e:
            return FocusState(self.requested, ok=self.mode == "unchanged", error=f"no camera control: {e}")
        return apply_focus(self._control, self.mode, self.value)

    def check(self) -> FocusState | None:
        """Re-apply if the camera no longer holds the setting. The new state, or None if it held."""
        if self._control is None or self.mode == "unchanged":
            return None
        if _holds(self._control.get(FOCUS), self.mode, self.value):
            return None
        self.reapplied += 1
        return apply_focus(self._control, self.mode, self.value)

    def read(self) -> FocusState | None:
        """The current state, without changing anything (None once closed)."""
        return None if self._control is None else read_state(self._control, self.mode, self.value)

    def close(self) -> None:
        if self._control is not None:
            self._control.__exit__(None, None, None)
            self._control = None


def read_focus(index: int) -> FocusState:
    """Read DirectShow device `index`'s focus without changing it."""
    keeper = FocusKeeper(index, "unchanged", 0)
    try:
        return keeper.open()
    finally:
        keeper.close()
