"""Display discovery on Windows via ctypes (no extra dependencies).

Call `enable_dpi_awareness()` before creating windows or listing displays, so all
coordinates are physical pixels (the laptop runs at 150 % scaling).

Sources combined per display:
- EnumDisplayMonitors / GetMonitorInfoW: desktop bounds, primary flag, GDI name
- EnumDisplaySettingsW: current mode, refresh rate, available modes
- QueryDisplayConfig / DisplayConfigGetDeviceInfo: EDID name and id, output technology
- GetDpiForMonitor: Windows scaling
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Data model and pure logic (unit-tested without hardware)
# ---------------------------------------------------------------------------

OUTPUT_TECHNOLOGIES = {
    0xFFFFFFFF: "other",
    0: "vga",
    1: "s-video",
    2: "composite",
    3: "component",
    4: "dvi",
    5: "hdmi",
    6: "lvds",
    8: "d-jpn",
    9: "sdi",
    10: "displayport",
    11: "displayport-embedded",
    12: "udi",
    13: "udi-embedded",
    14: "sdtv-dongle",
    15: "miracast",
    16: "indirect-wired",
    17: "indirect-virtual",
    18: "displayport-usb-tunnel",
    0x80000000: "internal",
}

# Connectors a physical projector can be attached to.
EXTERNAL_PHYSICAL_OUTPUTS = frozenset(
    {"vga", "s-video", "composite", "component", "dvi", "hdmi", "displayport", "udi",
     "displayport-usb-tunnel"}
)


@dataclass(frozen=True)
class DisplayMode:
    width: int
    height: int
    refresh_hz: int

    def __str__(self) -> str:
        return f"{self.width}x{self.height}@{self.refresh_hz}"


@dataclass(frozen=True)
class Display:
    gdi_name: str          # e.g. \\.\DISPLAY2
    friendly_name: str     # EDID monitor name, "" if unavailable
    edid_id: str           # manufacturer + product code, e.g. "TMA2076"
    output: str            # see OUTPUT_TECHNOLOGIES
    primary: bool
    x: int                 # desktop bounds in physical pixels
    y: int
    width: int
    height: int
    refresh_hz: float
    bits_per_pixel: int
    scale_percent: int     # Windows display scaling
    modes: tuple[DisplayMode, ...] = ()

    @property
    def is_external_physical(self) -> bool:
        return self.output in EXTERNAL_PHYSICAL_OUTPUTS

    @property
    def label(self) -> str:
        name = self.friendly_name or "(no EDID name)"
        return f"{self.gdi_name} {name} [{self.edid_id or '?'}]"

    def supports(self, width: int, height: int) -> bool:
        return any(m.width == width and m.height == height for m in self.modes)


class ProjectorNotFound(RuntimeError):
    """No display, or more than one, matches the projector selection rule."""


def decode_edid_manufacturer(raw: int) -> str:
    """Decode the 3-letter PNP id from DISPLAYCONFIG_TARGET_DEVICE_NAME.edidManufactureId.

    The EDID stores it big-endian (bytes 8-9); Windows hands it over as a little-endian
    UINT16, so the bytes are swapped first. Each letter is 5 bits, 1 = 'A'.
    """
    value = ((raw & 0xFF) << 8) | ((raw >> 8) & 0xFF)
    codes = ((value >> 10) & 0x1F, (value >> 5) & 0x1F, value & 0x1F)
    if not all(1 <= c <= 26 for c in codes):
        return ""
    return "".join(chr(ord("A") + c - 1) for c in codes)


def _matches(display: Display, needle: str) -> bool:
    n = needle.casefold()
    gdi = display.gdi_name.casefold()
    return (
        n == gdi
        or n == gdi.removeprefix("\\\\.\\")
        or (bool(display.friendly_name) and n in display.friendly_name.casefold())
        or (bool(display.edid_id) and n in display.edid_id.casefold())
    )


def select_projector(displays: list[Display], match: str = "") -> tuple[Display, str]:
    """Pick the projector explicitly; never by index.

    With `match`: the single display whose GDI name equals it, or whose EDID name/id
    contains it. Without: the single non-primary display on a physical external
    connector (virtual/indirect displays such as the Meta virtual monitor are excluded).
    Returns (display, human-readable rule). Raises ProjectorNotFound when zero or
    several displays qualify.
    """
    if match:
        hits = [d for d in displays if _matches(d, match)]
        rule = f"matches {match!r}"
    else:
        hits = [d for d in displays if not d.primary and d.is_external_physical]
        rule = "only non-primary display on a physical external connector"
    if len(hits) == 1:
        return hits[0], rule
    listing = "\n".join(
        f"  {d.label} output={d.output} primary={d.primary} {d.width}x{d.height}"
        for d in displays
    ) or "  (no displays)"
    problem = "no display" if not hits else f"{len(hits)} displays"
    raise ProjectorNotFound(
        f"projector not identified: {problem} matched (rule: {rule}). "
        f"Connect the projector, or set [projector] match in the config / pass --display.\n"
        f"Displays:\n{listing}"
    )


# ---------------------------------------------------------------------------
# Win32 structures
# ---------------------------------------------------------------------------


class LUID(ctypes.Structure):
    _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", wintypes.LONG)]


class DISPLAYCONFIG_RATIONAL(ctypes.Structure):
    _fields_ = [("Numerator", ctypes.c_uint32), ("Denominator", ctypes.c_uint32)]


class DISPLAYCONFIG_PATH_SOURCE_INFO(ctypes.Structure):
    _fields_ = [
        ("adapterId", LUID),
        ("id", ctypes.c_uint32),
        ("modeInfoIdx", ctypes.c_uint32),
        ("statusFlags", ctypes.c_uint32),
    ]


class DISPLAYCONFIG_PATH_TARGET_INFO(ctypes.Structure):
    _fields_ = [
        ("adapterId", LUID),
        ("id", ctypes.c_uint32),
        ("modeInfoIdx", ctypes.c_uint32),
        ("outputTechnology", ctypes.c_uint32),
        ("rotation", ctypes.c_uint32),
        ("scaling", ctypes.c_uint32),
        ("refreshRate", DISPLAYCONFIG_RATIONAL),
        ("scanLineOrdering", ctypes.c_uint32),
        ("targetAvailable", wintypes.BOOL),
        ("statusFlags", ctypes.c_uint32),
    ]


class DISPLAYCONFIG_PATH_INFO(ctypes.Structure):
    _fields_ = [
        ("sourceInfo", DISPLAYCONFIG_PATH_SOURCE_INFO),
        ("targetInfo", DISPLAYCONFIG_PATH_TARGET_INFO),
        ("flags", ctypes.c_uint32),
    ]


class _DISPLAYCONFIG_MODE_UNION(ctypes.Union):
    _fields_ = [("raw", ctypes.c_ubyte * 48), ("_align", ctypes.c_uint64)]


class DISPLAYCONFIG_MODE_INFO(ctypes.Structure):
    _fields_ = [
        ("infoType", ctypes.c_uint32),
        ("id", ctypes.c_uint32),
        ("adapterId", LUID),
        ("info", _DISPLAYCONFIG_MODE_UNION),
    ]


class DISPLAYCONFIG_DEVICE_INFO_HEADER(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_uint32),
        ("size", ctypes.c_uint32),
        ("adapterId", LUID),
        ("id", ctypes.c_uint32),
    ]


class DISPLAYCONFIG_SOURCE_DEVICE_NAME(ctypes.Structure):
    _fields_ = [
        ("header", DISPLAYCONFIG_DEVICE_INFO_HEADER),
        ("viewGdiDeviceName", ctypes.c_wchar * 32),
    ]


class DISPLAYCONFIG_TARGET_DEVICE_NAME(ctypes.Structure):
    _fields_ = [
        ("header", DISPLAYCONFIG_DEVICE_INFO_HEADER),
        ("flags", ctypes.c_uint32),
        ("outputTechnology", ctypes.c_uint32),
        ("edidManufactureId", ctypes.c_uint16),
        ("edidProductCodeId", ctypes.c_uint16),
        ("connectorInstance", ctypes.c_uint32),
        ("monitorFriendlyDeviceName", ctypes.c_wchar * 64),
        ("monitorDevicePath", ctypes.c_wchar * 128),
    ]


class _DEVMODE_DISPLAY_FIELDS(ctypes.Structure):
    _fields_ = [
        ("dmPosition", wintypes.POINTL),
        ("dmDisplayOrientation", wintypes.DWORD),
        ("dmDisplayFixedOutput", wintypes.DWORD),
    ]


class DEVMODEW(ctypes.Structure):
    _fields_ = [
        ("dmDeviceName", ctypes.c_wchar * 32),
        ("dmSpecVersion", wintypes.WORD),
        ("dmDriverVersion", wintypes.WORD),
        ("dmSize", wintypes.WORD),
        ("dmDriverExtra", wintypes.WORD),
        ("dmFields", wintypes.DWORD),
        ("display", _DEVMODE_DISPLAY_FIELDS),  # union with the printer fields, same size
        ("dmColor", ctypes.c_short),
        ("dmDuplex", ctypes.c_short),
        ("dmYResolution", ctypes.c_short),
        ("dmTTOption", ctypes.c_short),
        ("dmCollate", ctypes.c_short),
        ("dmFormName", ctypes.c_wchar * 32),
        ("dmLogPixels", wintypes.WORD),
        ("dmBitsPerPel", wintypes.DWORD),
        ("dmPelsWidth", wintypes.DWORD),
        ("dmPelsHeight", wintypes.DWORD),
        ("dmDisplayFlags", wintypes.DWORD),
        ("dmDisplayFrequency", wintypes.DWORD),
        ("dmICMMethod", wintypes.DWORD),
        ("dmICMIntent", wintypes.DWORD),
        ("dmMediaType", wintypes.DWORD),
        ("dmDitherType", wintypes.DWORD),
        ("dmReserved1", wintypes.DWORD),
        ("dmReserved2", wintypes.DWORD),
        ("dmPanningWidth", wintypes.DWORD),
        ("dmPanningHeight", wintypes.DWORD),
    ]


class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
        ("szDevice", ctypes.c_wchar * 32),
    ]


_QDC_ONLY_ACTIVE_PATHS = 0x2
_DEVICE_INFO_GET_SOURCE_NAME = 1
_DEVICE_INFO_GET_TARGET_NAME = 2
_ERROR_INSUFFICIENT_BUFFER = 122
_ENUM_CURRENT_SETTINGS = 0xFFFFFFFF
_MONITORINFOF_PRIMARY = 0x1
_MDT_EFFECTIVE_DPI = 0
_DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_shcore = ctypes.WinDLL("shcore")

_MONITORENUMPROC = ctypes.WINFUNCTYPE(
    wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM
)

_user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
_user32.SetProcessDpiAwarenessContext.restype = wintypes.BOOL
_user32.GetThreadDpiAwarenessContext.restype = ctypes.c_void_p
_user32.GetAwarenessFromDpiAwarenessContext.argtypes = [ctypes.c_void_p]
_user32.GetAwarenessFromDpiAwarenessContext.restype = ctypes.c_int
_user32.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.RECT), _MONITORENUMPROC, wintypes.LPARAM]
_user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFOEXW)]
_user32.EnumDisplaySettingsW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(DEVMODEW)]
_user32.GetDisplayConfigBufferSizes.argtypes = [ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint32)]
_user32.GetDisplayConfigBufferSizes.restype = ctypes.c_long
_user32.QueryDisplayConfig.argtypes = [
    ctypes.c_uint32,
    ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(DISPLAYCONFIG_PATH_INFO),
    ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(DISPLAYCONFIG_MODE_INFO),
    ctypes.c_void_p,
]
_user32.QueryDisplayConfig.restype = ctypes.c_long
_user32.DisplayConfigGetDeviceInfo.argtypes = [ctypes.POINTER(DISPLAYCONFIG_DEVICE_INFO_HEADER)]
_user32.DisplayConfigGetDeviceInfo.restype = ctypes.c_long
_shcore.GetDpiForMonitor.argtypes = [wintypes.HMONITOR, ctypes.c_int, ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_uint)]
_shcore.GetDpiForMonitor.restype = ctypes.c_long


# ---------------------------------------------------------------------------
# Win32 queries
# ---------------------------------------------------------------------------


def enable_dpi_awareness() -> str:
    """Make the process per-monitor DPI aware (v2). Returns the resulting awareness."""
    _user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(_DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2))
    return dpi_awareness()


def dpi_awareness() -> str:
    awareness = _user32.GetAwarenessFromDpiAwarenessContext(_user32.GetThreadDpiAwarenessContext())
    return {0: "unaware", 1: "system", 2: "per-monitor"}.get(awareness, f"unknown({awareness})")


def _display_config() -> dict[str, dict]:
    """GDI name -> {friendly_name, edid_id, output, refresh_hz} for active paths."""
    for _ in range(5):
        n_paths, n_modes = ctypes.c_uint32(), ctypes.c_uint32()
        rc = _user32.GetDisplayConfigBufferSizes(_QDC_ONLY_ACTIVE_PATHS, ctypes.byref(n_paths), ctypes.byref(n_modes))
        if rc != 0:
            raise OSError(f"GetDisplayConfigBufferSizes failed: {rc}")
        paths = (DISPLAYCONFIG_PATH_INFO * n_paths.value)()
        modes = (DISPLAYCONFIG_MODE_INFO * n_modes.value)()
        rc = _user32.QueryDisplayConfig(
            _QDC_ONLY_ACTIVE_PATHS, ctypes.byref(n_paths), paths, ctypes.byref(n_modes), modes, None
        )
        if rc == _ERROR_INSUFFICIENT_BUFFER:
            continue  # display configuration changed between the two calls
        if rc != 0:
            raise OSError(f"QueryDisplayConfig failed: {rc}")
        break
    else:
        raise OSError("QueryDisplayConfig kept changing")

    result: dict[str, dict] = {}
    for path in paths[: n_paths.value]:
        source = DISPLAYCONFIG_SOURCE_DEVICE_NAME()
        source.header.type = _DEVICE_INFO_GET_SOURCE_NAME
        source.header.size = ctypes.sizeof(source)
        source.header.adapterId = path.sourceInfo.adapterId
        source.header.id = path.sourceInfo.id
        if _user32.DisplayConfigGetDeviceInfo(ctypes.byref(source.header)) != 0:
            continue
        target = DISPLAYCONFIG_TARGET_DEVICE_NAME()
        target.header.type = _DEVICE_INFO_GET_TARGET_NAME
        target.header.size = ctypes.sizeof(target)
        target.header.adapterId = path.targetInfo.adapterId
        target.header.id = path.targetInfo.id
        if _user32.DisplayConfigGetDeviceInfo(ctypes.byref(target.header)) != 0:
            continue
        edid_valid = bool(target.flags & 0x4)
        edid_id = (
            f"{decode_edid_manufacturer(target.edidManufactureId)}{target.edidProductCodeId:04X}"
            if edid_valid else ""
        )
        rate = path.targetInfo.refreshRate
        result[source.viewGdiDeviceName] = {
            "friendly_name": target.monitorFriendlyDeviceName,
            "edid_id": edid_id,
            "output": OUTPUT_TECHNOLOGIES.get(target.outputTechnology, f"unknown({target.outputTechnology})"),
            "refresh_hz": rate.Numerator / rate.Denominator if rate.Denominator else 0.0,
        }
    return result


def _current_mode(gdi_name: str) -> DEVMODEW | None:
    mode = DEVMODEW()
    mode.dmSize = ctypes.sizeof(DEVMODEW)
    if not _user32.EnumDisplaySettingsW(gdi_name, _ENUM_CURRENT_SETTINGS, ctypes.byref(mode)):
        return None
    return mode


def _available_modes(gdi_name: str) -> tuple[DisplayMode, ...]:
    modes = set()
    mode = DEVMODEW()
    mode.dmSize = ctypes.sizeof(DEVMODEW)
    i = 0
    while _user32.EnumDisplaySettingsW(gdi_name, i, ctypes.byref(mode)):
        if mode.dmBitsPerPel >= 24:
            modes.add(DisplayMode(mode.dmPelsWidth, mode.dmPelsHeight, mode.dmDisplayFrequency))
        i += 1
    return tuple(sorted(modes, key=lambda m: (m.width * m.height, m.width, m.refresh_hz), reverse=True))


def _scale_percent(hmonitor) -> int:
    dpi_x, dpi_y = ctypes.c_uint(), ctypes.c_uint()
    if _shcore.GetDpiForMonitor(hmonitor, _MDT_EFFECTIVE_DPI, ctypes.byref(dpi_x), ctypes.byref(dpi_y)) != 0:
        return 0
    return round(dpi_x.value * 100 / 96)


def list_displays(*, with_modes: bool = True) -> list[Display]:
    """All active displays, primary first. Coordinates are physical pixels if the
    process is DPI aware (see enable_dpi_awareness)."""
    monitors = []

    def callback(hmonitor, _hdc, _rect, _lparam):
        info = MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(MONITORINFOEXW)
        if _user32.GetMonitorInfoW(hmonitor, ctypes.byref(info)):
            monitors.append((hmonitor, info.szDevice, info.rcMonitor, bool(info.dwFlags & _MONITORINFOF_PRIMARY)))
        return True

    _user32.EnumDisplayMonitors(None, None, _MONITORENUMPROC(callback), 0)

    try:
        config = _display_config()
    except OSError:
        config = {}

    displays = []
    for hmonitor, gdi_name, rect, primary in monitors:
        extra = config.get(gdi_name, {})
        mode = _current_mode(gdi_name)
        refresh = extra.get("refresh_hz") or (mode.dmDisplayFrequency if mode else 0.0)
        displays.append(
            Display(
                gdi_name=gdi_name,
                friendly_name=extra.get("friendly_name", ""),
                edid_id=extra.get("edid_id", ""),
                output=extra.get("output", "unknown"),
                primary=primary,
                x=rect.left,
                y=rect.top,
                width=rect.right - rect.left,
                height=rect.bottom - rect.top,
                refresh_hz=round(float(refresh), 3),
                bits_per_pixel=mode.dmBitsPerPel if mode else 0,
                scale_percent=_scale_percent(hmonitor),
                modes=_available_modes(gdi_name) if with_modes else (),
            )
        )
    displays.sort(key=lambda d: (not d.primary, d.gdi_name))
    return displays
