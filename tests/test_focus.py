import pytest

from invisible_canvas.camera.directshow import FLAG_AUTO, FLAG_MANUAL, FOCUS, ControlRange
from invisible_canvas.camera.focus import FocusKeeper, apply_focus


class FakeControl:
    """Stands in for directshow.CameraControl; range and state as read from the Kreo Owl 4K Pro."""

    def __init__(self, *, limits=ControlRange(0, 1023, 1, 192, FLAG_AUTO | FLAG_MANUAL),
                 state=(404, FLAG_AUTO), takes_setting=True, set_error=None):
        self.limits = limits
        self.values = {FOCUS: state}
        self.takes_setting = takes_setting
        self.set_error = set_error
        self.sets = []
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.closed = True

    def refocus(self, value=380):
        """Autofocus taking over again (e.g. a stored setting restored at stream start)."""
        self.values[FOCUS] = (value, FLAG_AUTO)

    def range(self, prop):
        return self.limits if prop == FOCUS else None

    def get(self, prop):
        return self.values.get(prop)

    def set(self, prop, value, flags):
        self.sets.append((prop, value, flags))
        if self.set_error:
            raise OSError(self.set_error)
        if self.takes_setting:
            self.values[prop] = (value, flags)


def test_manual_focus_is_applied_and_confirmed():
    control = FakeControl()
    state = apply_focus(control, "manual", 400)
    assert control.sets == [(FOCUS, 400, FLAG_MANUAL)]
    assert state.ok and state.error == ""
    assert (state.value, state.auto) == (400, False)
    assert state.describe() == "manual 400, confirmed by read-back"


def test_auto_focus_is_applied_and_confirmed():
    control = FakeControl(state=(400, FLAG_MANUAL))
    state = apply_focus(control, "auto", 0)
    assert control.sets == [(FOCUS, 192, FLAG_AUTO)]
    assert state.ok and state.auto


def test_unchanged_only_reads():
    control = FakeControl()
    state = apply_focus(control, "unchanged", 0)
    assert control.sets == []
    assert state.ok
    assert state.describe() == "unchanged by config; camera reports auto (now at 404)"


def test_camera_that_ignores_the_setting_is_not_reported_as_applied():
    control = FakeControl(takes_setting=False)
    state = apply_focus(control, "manual", 400)
    assert not state.ok
    assert "does not hold manual 400" in state.describe()
    assert "camera reports auto (now at 404)" in state.describe()


def test_value_outside_the_camera_range_is_not_sent():
    control = FakeControl()
    state = apply_focus(control, "manual", 2000)
    assert control.sets == []
    assert not state.ok
    assert "outside the camera's range 0..1023" in state.error


def test_camera_without_focus_control():
    control = FakeControl(limits=None, state=None)
    state = apply_focus(control, "manual", 400)
    assert not state.ok
    assert state.error == "the camera has no focus control"
    assert state.effective() == "not readable"


def test_camera_without_manual_focus():
    control = FakeControl(limits=ControlRange(0, 1023, 1, 192, FLAG_AUTO))
    state = apply_focus(control, "manual", 400)
    assert not state.ok and "does not offer manual focus" in state.error


def test_failed_set_is_reported():
    control = FakeControl(set_error="IAMCameraControl::Set failed")
    state = apply_focus(control, "manual", 400)
    assert not state.ok and "Set failed" in state.error


def test_unknown_mode_is_a_programming_error():
    with pytest.raises(ValueError):
        apply_focus(FakeControl(), "fixed", 400)


def test_keeper_reapplies_after_autofocus_takes_over():
    control = FakeControl()
    keeper = FocusKeeper(0, "manual", 400, control_factory=lambda index: control)
    assert keeper.open().ok
    assert keeper.check() is None          # still held: nothing done
    control.refocus()
    state = keeper.check()
    assert state is not None and state.ok
    assert keeper.reapplied == 1
    assert control.values[FOCUS] == (400, FLAG_MANUAL)
    keeper.close()
    assert control.closed


def test_keeper_reports_a_failed_reapply():
    control = FakeControl()
    keeper = FocusKeeper(0, "manual", 400, control_factory=lambda index: control)
    keeper.open()
    control.takes_setting = False
    control.refocus()
    state = keeper.check()
    assert state is not None and not state.ok


def test_unchanged_keeper_never_sets():
    control = FakeControl()
    keeper = FocusKeeper(0, "unchanged", 400, control_factory=lambda index: control)
    assert keeper.open().ok
    control.refocus()
    assert keeper.check() is None
    assert control.sets == []


def test_keeper_without_camera_control():
    def no_control(index):
        raise OSError("no IAMCameraControl")
    manual = FocusKeeper(2, "manual", 400, control_factory=no_control).open()
    assert not manual.ok and "no camera control" in manual.error
    assert FocusKeeper(2, "unchanged", 400, control_factory=no_control).open().ok
