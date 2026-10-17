import pytest

from invisible_canvas.camera.directshow import (
    AUTO_EXPOSURE_PRIORITY,
    EXPOSURE,
    FLAG_AUTO,
    FLAG_MANUAL,
    ControlRange,
)
from invisible_canvas.camera.exposure import ExposureKeeper, apply_exposure, exposure_ms


class FakeControl:
    """Stands in for directshow.CameraControl; values as read from the Brio 100."""

    def __init__(self, *, limits=ControlRange(-11, -2, 1, -6, FLAG_AUTO | FLAG_MANUAL),
                 state=(-4, FLAG_AUTO), priority=(1, 0), takes_setting=True, set_error=None):
        self.limits = limits
        self.values = {EXPOSURE: state, AUTO_EXPOSURE_PRIORITY: priority}
        self.takes_setting = takes_setting
        self.set_error = set_error
        self.sets = []
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.closed = True

    def reset_by_camera_stack(self):
        """What Windows does to the Brio ~1 s and ~3 s after each stream start."""
        self.values[EXPOSURE] = (-4, FLAG_AUTO)

    def range(self, prop):
        return self.limits if prop == EXPOSURE else None

    def get(self, prop):
        return self.values.get(prop)

    def set(self, prop, value, flags):
        self.sets.append((prop, value, flags))
        if self.set_error:
            raise OSError(self.set_error)
        if self.takes_setting:
            self.values[prop] = (value, flags)


def test_manual_exposure_is_applied_and_confirmed():
    control = FakeControl()
    state = apply_exposure(control, "manual", -5)
    assert control.sets == [(EXPOSURE, -5, FLAG_MANUAL)]
    assert state.ok and state.error == ""
    assert (state.value, state.auto, state.priority) == (-5, False, 1)
    assert state.describe() == "manual -5 (31.2 ms), confirmed by read-back"


def test_auto_exposure_is_applied_and_confirmed():
    control = FakeControl(state=(-5, FLAG_MANUAL))
    state = apply_exposure(control, "auto", -5)
    assert control.sets == [(EXPOSURE, -6, FLAG_AUTO)]  # the device default, in auto mode
    assert state.ok and state.auto is True
    assert "AE priority 1" in state.describe()


def test_unchanged_only_reads():
    control = FakeControl()
    state = apply_exposure(control, "unchanged", -5)
    assert control.sets == []
    assert state.ok
    assert state.describe() == (
        "unchanged by config; camera reports auto (AE priority 1: the camera may lower the frame rate in dim light)"
    )


def test_camera_that_ignores_the_setting_is_not_reported_as_applied():
    state = apply_exposure(FakeControl(takes_setting=False), "manual", -5)
    assert not state.ok
    assert state.auto is True and state.value == -4
    assert state.describe().startswith("NOT APPLIED (requested manual -5): the camera does not hold manual -5")


def test_value_outside_the_camera_range_is_not_sent():
    control = FakeControl()
    state = apply_exposure(control, "manual", -20)
    assert control.sets == []
    assert not state.ok
    assert "outside the camera's range -11..-2" in state.error


def test_camera_without_exposure_control():
    state = apply_exposure(FakeControl(limits=None, state=None, priority=None), "manual", -5)
    assert not state.ok
    assert "no exposure control" in state.error
    assert state.effective() == "not readable"


def test_camera_without_manual_exposure():
    state = apply_exposure(FakeControl(limits=ControlRange(-11, -2, 1, -6, FLAG_AUTO)), "manual", -5)
    assert not state.ok
    assert "does not offer manual exposure" in state.error


def test_failed_set_is_reported():
    state = apply_exposure(FakeControl(set_error="IAMCameraControl::Set failed: 0x80070490"), "manual", -5)
    assert not state.ok
    assert "0x80070490" in state.error


def test_unreadable_exposure_is_not_confirmed():
    class WriteOnly(FakeControl):
        def get(self, prop):
            return None

    state = apply_exposure(WriteOnly(), "manual", -5)
    assert not state.ok
    assert "not confirmed" in state.error


def test_unknown_mode_is_a_programming_error():
    with pytest.raises(ValueError):
        apply_exposure(FakeControl(), "aperture", -5)


def test_keeper_reapplies_after_the_camera_resets_exposure():
    control = FakeControl()
    keeper = ExposureKeeper(0, "manual", -5, control_factory=lambda index: control)
    assert keeper.open().ok
    assert keeper.check() is None                 # still held: nothing sent
    assert len(control.sets) == 1

    control.reset_by_camera_stack()
    assert keeper.read().ok is False              # the reset is visible, not hidden
    state = keeper.check()
    assert state.ok and (state.value, state.auto) == (-5, False)
    assert keeper.reapplied == 1
    assert control.sets[-1] == (EXPOSURE, -5, FLAG_MANUAL)

    keeper.close()
    assert control.closed and keeper.read() is None and keeper.check() is None


def test_keeper_reports_a_failed_reapply():
    control = FakeControl()
    keeper = ExposureKeeper(0, "manual", -5, control_factory=lambda index: control)
    keeper.open()
    control.reset_by_camera_stack()
    control.takes_setting = False
    state = keeper.check()
    assert not state.ok and state.auto is True


def test_unchanged_keeper_never_sets():
    control = FakeControl()
    keeper = ExposureKeeper(0, "unchanged", -5, control_factory=lambda index: control)
    assert keeper.open().ok
    control.reset_by_camera_stack()
    assert keeper.check() is None
    assert control.sets == []


def test_keeper_without_camera_control():
    def no_control(index):
        raise OSError("QueryInterface(IAMCameraControl) failed: 0x80004002")

    manual = ExposureKeeper(2, "manual", -5, control_factory=no_control).open()
    assert not manual.ok and "0x80004002" in manual.error
    assert ExposureKeeper(2, "unchanged", -5, control_factory=no_control).open().ok


def test_exposure_ms():
    assert exposure_ms(-5) == 31.25
    assert exposure_ms(-6) == 15.625
