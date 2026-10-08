import ctypes

import pytest

from invisible_canvas.display import monitors
from invisible_canvas.display.monitors import (
    Display,
    DisplayMode,
    ProjectorNotFound,
    decode_edid_manufacturer,
    select_projector,
)


def make(gdi, name="", edid="", output="hdmi", primary=False, w=1280, h=720, modes=()):
    return Display(gdi, name, edid, output, primary, 0, 0, w, h, 60.0, 32, 100, modes)


LAPTOP = make(r"\\.\DISPLAY1", "TL160ADMP37", "TMA2076", "internal", primary=True, w=2560, h=1600)
PROJECTOR = make(r"\\.\DISPLAY2", "WZATCO", "WZT0001", "hdmi")
VIRTUAL = make(r"\\.\DISPLAY3", "Meta Virtual Monitor", "", "indirect-virtual")


def test_auto_selects_the_single_external_display():
    display, rule = select_projector([LAPTOP, VIRTUAL, PROJECTOR])
    assert display is PROJECTOR
    assert "external" in rule


def test_auto_never_picks_primary_or_virtual_displays():
    with pytest.raises(ProjectorNotFound):
        select_projector([LAPTOP, VIRTUAL])


def test_auto_refuses_to_guess_between_two_external_displays():
    monitor = make(r"\\.\DISPLAY4", "Office Monitor", "DEL1234", "displayport")
    with pytest.raises(ProjectorNotFound, match="2 displays"):
        select_projector([LAPTOP, PROJECTOR, monitor])


def test_match_by_edid_name_is_case_insensitive():
    display, rule = select_projector([LAPTOP, PROJECTOR], "wzatco")
    assert display is PROJECTOR
    assert "wzatco" in rule


def test_match_by_edid_id():
    assert select_projector([LAPTOP, PROJECTOR], "TMA2076")[0] is LAPTOP


@pytest.mark.parametrize("needle", [r"\\.\DISPLAY2", "DISPLAY2", "display2"])
def test_match_by_gdi_name_with_or_without_prefix(needle):
    assert select_projector([LAPTOP, PROJECTOR], needle)[0] is PROJECTOR


def test_gdi_name_match_is_exact():
    tenth = make(r"\\.\DISPLAY10", "Other", "", "hdmi")
    assert select_projector([LAPTOP, tenth], "DISPLAY1")[0] is LAPTOP


def test_no_match_lists_all_displays():
    with pytest.raises(ProjectorNotFound) as info:
        select_projector([LAPTOP, VIRTUAL], "wzatco")
    assert "TL160ADMP37" in str(info.value)
    assert "Meta Virtual Monitor" in str(info.value)


def test_decode_edid_manufacturer():
    # "TMA" packed big-endian is 0x51A1; Windows hands it over byte-swapped.
    # Verified on this laptop: its panel decodes to TMA2076, matching WMI.
    assert decode_edid_manufacturer(0xA151) == "TMA"


def test_decode_edid_manufacturer_rejects_invalid_codes():
    assert decode_edid_manufacturer(0) == ""
    assert decode_edid_manufacturer(0xFFFF) == ""


def test_display_supports_mode():
    display = make(r"\\.\DISPLAY2", modes=(DisplayMode(1920, 1080, 60), DisplayMode(1280, 720, 60)))
    assert display.supports(1280, 720)
    assert not display.supports(1024, 768)


def test_win32_struct_sizes_match_windows_sdk():
    assert ctypes.sizeof(monitors.DISPLAYCONFIG_PATH_INFO) == 72
    assert ctypes.sizeof(monitors.DISPLAYCONFIG_MODE_INFO) == 64
    assert ctypes.sizeof(monitors.DEVMODEW) == 220
    assert ctypes.sizeof(monitors.DISPLAYCONFIG_TARGET_DEVICE_NAME) == 420
    assert ctypes.sizeof(monitors.DISPLAYCONFIG_SOURCE_DEVICE_NAME) == 84
    assert ctypes.sizeof(monitors.MONITORINFOEXW) == 104
