"""Camera settings locked from `[camera]`: focus (`focus_mode`/`focus_value`) and gain
(`gain_mode`/`gain_value`) (brain.md D42, D43).

Same mechanism as exposure (camera/exposure.py): the request goes through DirectShow, counts as
applied only when the camera reports the requested state, and `LockKeeper` keeps it applied while
streaming. Focus is an IAMCameraControl property, gain an IAMVideoProcAmp property.

Why, measured on the Kreo Owl 4K Pro (2026-10-19):
- focus: autofocus hunted (719 -> 64 -> 499) and settled on a value 4x blurrier than the sharpest;
  a refocus also moves image features under a calibration;
- gain: manual-only 0..15 and left at 0 under manual exposure, which makes the 60-fps image too
  dark (white 69.8 at gain 0, 145.6 at gain 15).
Values are the camera's own units.
"""

from __future__ import annotations

from dataclasses import dataclass

from .directshow import FLAG_AUTO, FLAG_MANUAL, FOCUS, GAIN, CameraControl

MODES = ("manual", "auto", "unchanged")


@dataclass(frozen=True)
class Setting:
    name: str        # used in messages and config keys: "<name>_mode", "<name>_value"
    interface: str   # CameraControl interface: "camera" or "procamp"
    prop: int


FOCUS_SETTING = Setting("focus", "camera", FOCUS)
GAIN_SETTING = Setting("gain", "procamp", GAIN)


@dataclass(frozen=True)
class LockState:
    """The configured request and what the camera reports (None = not readable)."""
    setting: str                # "focus" or "gain"
    requested: str              # "manual 410", "auto" or "unchanged"
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


def _requested(setting: Setting, mode: str, value: int) -> str:
    if mode not in MODES:
        raise ValueError(f"{setting.name} mode must be one of {MODES}, got {mode!r}")
    return f"manual {value}" if mode == "manual" else mode


def _holds(current: tuple[int, int] | None, mode: str, value: int) -> bool:
    """Whether a (value, flags) read-back is the requested state."""
    if current is None:
        return False
    auto = bool(current[1] & FLAG_AUTO)
    return auto if mode == "auto" else (not auto and current[0] == value)


def read_state(setting: Setting, control, mode: str = "unchanged", value: int = 0, error: str = "") -> LockState:
    """What `control` (a `CameraControl` on `setting.interface`) reports now, judged against the request."""
    requested = _requested(setting, mode, value)
    current = control.get(setting.prop)
    if not error and mode != "unchanged":
        if current is None:
            error = f"the camera does not report {setting.name}, so the setting is not confirmed"
        elif not _holds(current, mode, value):
            error = (f"the camera is not in auto {setting.name}" if mode == "auto"
                     else f"the camera does not hold manual {value}")
    return LockState(
        setting=setting.name,
        requested=requested,
        ok=not error,
        value=current[0] if current else None,
        auto=bool(current[1] & FLAG_AUTO) if current else None,
        error=error,
    )


def apply_setting(setting: Setting, control, mode: str, value: int) -> LockState:
    """Request `mode` on `control`, read it back and report.
    Camera-side failures are returned in the state, never raised."""
    _requested(setting, mode, value)
    error = ""
    if mode != "unchanged":
        try:
            limits = control.range(setting.prop)
            needed = FLAG_MANUAL if mode == "manual" else FLAG_AUTO
            if limits is None:
                error = f"the camera has no {setting.name} control"
            elif not limits.caps & needed:
                error = f"the camera does not offer {mode} {setting.name}"
            elif mode == "manual" and not limits.min <= value <= limits.max:
                error = f"{setting.name}_value {value} is outside the camera's range {limits.min}..{limits.max}"
            elif mode == "manual":
                control.set(setting.prop, value, FLAG_MANUAL)
            else:
                control.set(setting.prop, limits.default, FLAG_AUTO)
        except OSError as e:
            error = str(e)
    return read_state(setting, control, mode, value, error)


class LockKeeper:
    """Applies a configured setting to DirectShow device `index` and keeps it applied (the camera
    stack may restore stored settings after a stream starts, as it did with the Brio's exposure,
    R21). Call `check()` periodically while streaming. Use on one thread (COM).
    `control_factory(index, interface)` opens the control (tests pass a fake)."""

    def __init__(self, setting: Setting, index: int, mode: str, value: int, *, control_factory=CameraControl):
        self.setting = setting
        self.requested = _requested(setting, mode, value)
        self.index, self.mode, self.value = index, mode, value
        self.reapplied = 0
        self._control_factory = control_factory
        self._control = None

    def open(self) -> LockState:
        try:
            self._control = self._control_factory(self.index, self.setting.interface).__enter__()
        except OSError as e:
            return LockState(self.setting.name, self.requested, ok=self.mode == "unchanged",
                             error=f"no camera control: {e}")
        return apply_setting(self.setting, self._control, self.mode, self.value)

    def check(self) -> LockState | None:
        """Re-apply if the camera no longer holds the setting. The new state, or None if it held."""
        if self._control is None or self.mode == "unchanged":
            return None
        if _holds(self._control.get(self.setting.prop), self.mode, self.value):
            return None
        self.reapplied += 1
        return apply_setting(self.setting, self._control, self.mode, self.value)

    def read(self) -> LockState | None:
        """The current state, without changing anything (None once closed)."""
        return None if self._control is None else read_state(self.setting, self._control, self.mode, self.value)

    def close(self) -> None:
        if self._control is not None:
            self._control.__exit__(None, None, None)
            self._control = None


def read_setting(setting: Setting, index: int) -> LockState:
    """Read DirectShow device `index`'s setting without changing it."""
    keeper = LockKeeper(setting, index, "unchanged", 0)
    try:
        return keeper.open()
    finally:
        keeper.close()
