import pytest

from invisible_canvas.camera.directshow import FLAG_AUTO, FLAG_MANUAL, FOCUS, GAIN, CameraControl, ControlRange
from invisible_canvas.camera.locks import FOCUS_SETTING, GAIN_SETTING, LockKeeper, apply_setting


class FakeControl:
    """Stands in for directshow.CameraControl; ranges and states as read from the Kreo Owl 4K Pro."""

    KREO = {
        FOCUS: (ControlRange(0, 1023, 1, 192, FLAG_AUTO | FLAG_MANUAL), (404, FLAG_AUTO)),
        GAIN: (ControlRange(0, 15, 1, 0, FLAG_MANUAL), (0, FLAG_MANUAL)),
    }

    def __init__(self, prop=FOCUS, *, limits="kreo", state="kreo", takes_setting=True, set_error=None):
        kreo_limits, kreo_state = self.KREO[prop]
        self.prop = prop
        self.limits = kreo_limits if limits == "kreo" else limits
        self.values = {prop: kreo_state if state == "kreo" else state}
        self.takes_setting = takes_setting
        self.set_error = set_error
        self.sets = []
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.closed = True

    def camera_takes_over(self, value):
        """The camera (or a stored setting restored at stream start) changes the value."""
        self.values[self.prop] = value

    def range(self, prop):
        return self.limits if prop == self.prop else None

    def get(self, prop):
        return self.values.get(prop)

    def set(self, prop, value, flags):
        self.sets.append((prop, value, flags))
        if self.set_error:
            raise OSError(self.set_error)
        if self.takes_setting:
            self.values[prop] = (value, flags)


def test_settings_use_the_right_directshow_interface():
    assert (FOCUS_SETTING.interface, FOCUS_SETTING.prop) == ("camera", FOCUS)
    assert (GAIN_SETTING.interface, GAIN_SETTING.prop) == ("procamp", GAIN)
    with pytest.raises(ValueError):
        CameraControl(0, "videoprocamp")


def test_manual_focus_is_applied_and_confirmed():
    control = FakeControl(FOCUS)
    state = apply_setting(FOCUS_SETTING, control, "manual", 410)
    assert control.sets == [(FOCUS, 410, FLAG_MANUAL)]
    assert state.ok and state.error == "" and state.setting == "focus"
    assert (state.value, state.auto) == (410, False)
    assert state.describe() == "manual 410, confirmed by read-back"


def test_manual_gain_is_applied_and_confirmed():
    control = FakeControl(GAIN)
    state = apply_setting(GAIN_SETTING, control, "manual", 15)
    assert control.sets == [(GAIN, 15, FLAG_MANUAL)]
    assert state.ok and state.setting == "gain"
    assert state.describe() == "manual 15, confirmed by read-back"


def test_auto_focus_is_applied_and_confirmed():
    control = FakeControl(FOCUS, state=(410, FLAG_MANUAL))
    state = apply_setting(FOCUS_SETTING, control, "auto", 0)
    assert control.sets == [(FOCUS, 192, FLAG_AUTO)]
    assert state.ok and state.auto


def test_kreo_gain_has_no_auto_mode():
    control = FakeControl(GAIN)
    state = apply_setting(GAIN_SETTING, control, "auto", 0)
    assert control.sets == []
    assert not state.ok and state.error == "the camera does not offer auto gain"


def test_unchanged_only_reads():
    control = FakeControl(FOCUS)
    state = apply_setting(FOCUS_SETTING, control, "unchanged", 0)
    assert control.sets == []
    assert state.ok
    assert state.describe() == "unchanged by config; camera reports auto (now at 404)"


def test_camera_that_ignores_the_setting_is_not_reported_as_applied():
    control = FakeControl(FOCUS, takes_setting=False)
    state = apply_setting(FOCUS_SETTING, control, "manual", 410)
    assert not state.ok
    assert "does not hold manual 410" in state.describe()
    assert "camera reports auto (now at 404)" in state.describe()


@pytest.mark.parametrize("setting,prop,value,message", [
    (FOCUS_SETTING, FOCUS, 2000, "focus_value 2000 is outside the camera's range 0..1023"),
    (GAIN_SETTING, GAIN, 16, "gain_value 16 is outside the camera's range 0..15"),
    (GAIN_SETTING, GAIN, -1, "gain_value -1 is outside the camera's range 0..15"),
])
def test_value_outside_the_camera_range_is_not_sent(setting, prop, value, message):
    control = FakeControl(prop)
    state = apply_setting(setting, control, "manual", value)
    assert control.sets == []
    assert not state.ok and state.error == message


def test_camera_without_the_control():
    control = FakeControl(GAIN, limits=None, state=None)
    state = apply_setting(GAIN_SETTING, control, "manual", 15)
    assert not state.ok
    assert state.error == "the camera has no gain control"
    assert state.effective() == "not readable"


def test_failed_set_is_reported():
    control = FakeControl(FOCUS, set_error="IAMCameraControl::Set failed")
    state = apply_setting(FOCUS_SETTING, control, "manual", 410)
    assert not state.ok and "Set failed" in state.error


def test_unknown_mode_is_a_programming_error():
    with pytest.raises(ValueError, match="gain mode"):
        apply_setting(GAIN_SETTING, FakeControl(GAIN), "fixed", 15)


@pytest.mark.parametrize("setting,prop,value,taken_over", [
    (FOCUS_SETTING, FOCUS, 410, (380, FLAG_AUTO)),      # autofocus takes over again
    (GAIN_SETTING, GAIN, 15, (0, FLAG_MANUAL)),         # a stored gain restored at stream start
])
def test_keeper_reapplies_when_the_camera_changes_the_setting(setting, prop, value, taken_over):
    control = FakeControl(prop)
    opened = []
    keeper = LockKeeper(setting, 0, "manual", value,
                        control_factory=lambda index, interface: opened.append(interface) or control)
    assert keeper.open().ok
    assert opened == [setting.interface]
    assert keeper.check() is None          # still held: nothing done
    control.camera_takes_over(taken_over)
    state = keeper.check()
    assert state is not None and state.ok
    assert keeper.reapplied == 1
    assert control.values[prop] == (value, FLAG_MANUAL)
    keeper.close()
    assert control.closed


def test_keeper_reports_a_failed_reapply():
    control = FakeControl(FOCUS)
    keeper = LockKeeper(FOCUS_SETTING, 0, "manual", 410, control_factory=lambda index, interface: control)
    keeper.open()
    control.takes_setting = False
    control.camera_takes_over((380, FLAG_AUTO))
    state = keeper.check()
    assert state is not None and not state.ok


def test_unchanged_keeper_never_sets():
    control = FakeControl(GAIN)
    keeper = LockKeeper(GAIN_SETTING, 0, "unchanged", 15, control_factory=lambda index, interface: control)
    assert keeper.open().ok
    control.camera_takes_over((7, FLAG_MANUAL))
    assert keeper.check() is None
    assert control.sets == []


def test_keeper_without_camera_control():
    def no_control(index, interface):
        raise OSError("no IAMVideoProcAmp")
    manual = LockKeeper(GAIN_SETTING, 2, "manual", 15, control_factory=no_control).open()
    assert not manual.ok and "no camera control" in manual.error
    assert LockKeeper(GAIN_SETTING, 2, "unchanged", 15, control_factory=no_control).open().ok
