"""DirectShow video-capture devices (Windows, ctypes COM, no extra deps).

Devices are listed in the order of ICreateDevEnum over CLSID_VideoInputDeviceCategory,
which is the order OpenCV's CAP_DSHOW backend uses for its indices.
`CameraControl` reads and sets a device's IAMCameraControl values (exposure).
"""

from __future__ import annotations

import contextlib
import ctypes
import re
from ctypes import wintypes
from dataclasses import dataclass


@dataclass(frozen=True)
class CaptureDevice:
    index: int           # OpenCV CAP_DSHOW index
    name: str            # DirectShow FriendlyName
    path: str            # DevicePath ("" for virtual cameras)
    vid: str | None      # USB vendor id, lower-case hex
    pid: str | None      # USB product id

    @property
    def usb_id(self) -> str:
        return f"{self.vid}:{self.pid}" if self.vid and self.pid else "-"


_VID_PID = re.compile(r"vid_([0-9a-f]{4})&pid_([0-9a-f]{4})", re.IGNORECASE)


def parse_vid_pid(device_path: str) -> tuple[str | None, str | None]:
    m = _VID_PID.search(device_path or "")
    if not m:
        return None, None
    return m.group(1).lower(), m.group(2).lower()


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class VARIANT(ctypes.Structure):
    # vt + 3 reserved WORDs, then the 8/16-byte value union. Only BSTR is read here.
    _fields_ = [
        ("vt", ctypes.c_ushort),
        ("reserved1", ctypes.c_ushort),
        ("reserved2", ctypes.c_ushort),
        ("reserved3", ctypes.c_ushort),
        ("value", ctypes.c_void_p),
        ("extra", ctypes.c_void_p),
    ]


_CLSID_SystemDeviceEnum = "{62BE5D10-60EB-11D0-BD3B-00A0C911CE86}"
_IID_ICreateDevEnum = "{29840822-5B84-11D0-BD3B-00A0C911CE86}"
_CLSID_VideoInputDeviceCategory = "{860BB310-5D01-11D0-BD3B-00A0C911CE86}"
_IID_IPropertyBag = "{55272A00-42CB-11CE-8135-00AA004BB851}"
_IID_IBaseFilter = "{56A86895-0AD4-11CE-B03A-0020AF0BA770}"
_IID_IAMCameraControl = "{C6E13370-30AC-11D0-A18C-00A0C9118956}"
_CLSCTX_INPROC_SERVER = 0x1
_COINIT_APARTMENTTHREADED = 0x2
_RPC_E_CHANGED_MODE = -2147417850  # 0x80010106: COM already initialised in another mode
_VT_BSTR = 8

_ole32 = ctypes.WinDLL("ole32")
_oleaut32 = ctypes.WinDLL("oleaut32")
_ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
_ole32.CoInitializeEx.restype = ctypes.c_long
_ole32.CoUninitialize.restype = None
_ole32.CLSIDFromString.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(GUID)]
_ole32.CLSIDFromString.restype = ctypes.c_long
_ole32.CoCreateInstance.argtypes = [
    ctypes.POINTER(GUID), ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)
]
_ole32.CoCreateInstance.restype = ctypes.c_long
_oleaut32.VariantInit.argtypes = [ctypes.POINTER(VARIANT)]
_oleaut32.VariantInit.restype = None
_oleaut32.VariantClear.argtypes = [ctypes.POINTER(VARIANT)]
_oleaut32.VariantClear.restype = ctypes.c_long


def _guid(text: str) -> GUID:
    g = GUID()
    hr = _ole32.CLSIDFromString(text, ctypes.byref(g))
    if hr != 0:
        raise OSError(f"CLSIDFromString({text}) failed: 0x{hr & 0xFFFFFFFF:08X}")
    return g


def _method(obj: ctypes.c_void_p, index: int, *argtypes, restype=ctypes.c_long):
    """Bind COM vtable entry `index` of interface pointer `obj`."""
    vtable = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    prototype = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)
    function = prototype(vtable[index])
    return lambda *args: function(obj, *args)


def _release(obj: ctypes.c_void_p) -> None:
    if obj and obj.value:
        _method(obj, 2, restype=ctypes.c_ulong)()  # IUnknown::Release


def _check(hr: int, what: str) -> None:
    if hr < 0:
        raise OSError(f"{what} failed: 0x{hr & 0xFFFFFFFF:08X}")


def _read_string(bag: ctypes.c_void_p, name: str) -> str:
    var = VARIANT()
    _oleaut32.VariantInit(ctypes.byref(var))
    read = _method(bag, 3, wintypes.LPCWSTR, ctypes.POINTER(VARIANT), ctypes.c_void_p)  # IPropertyBag::Read
    try:
        if read(name, ctypes.byref(var), None) != 0 or var.vt != _VT_BSTR or not var.value:
            return ""
        return ctypes.wstring_at(var.value)
    finally:
        _oleaut32.VariantClear(ctypes.byref(var))


@contextlib.contextmanager
def _com():
    """COM initialised on this thread for the duration (tolerates another apartment mode)."""
    hr = _ole32.CoInitializeEx(None, _COINIT_APARTMENTTHREADED)
    if hr < 0 and hr != _RPC_E_CHANGED_MODE:
        _check(hr, "CoInitializeEx")
    try:
        yield
    finally:
        if hr >= 0:
            _ole32.CoUninitialize()


def _video_input_monikers():
    """Yield (CAP_DSHOW index, IMoniker) per video input device. Needs `_com()`.
    Each moniker is released when the caller moves on; close the generator when stopping early."""
    devenum = ctypes.c_void_p()
    enum_moniker = ctypes.c_void_p()
    try:
        _check(
            _ole32.CoCreateInstance(
                ctypes.byref(_guid(_CLSID_SystemDeviceEnum)), None, _CLSCTX_INPROC_SERVER,
                ctypes.byref(_guid(_IID_ICreateDevEnum)), ctypes.byref(devenum),
            ),
            "CoCreateInstance(SystemDeviceEnum)",
        )
        create_class_enumerator = _method(
            devenum, 3, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p), wintypes.DWORD
        )
        hr = create_class_enumerator(ctypes.byref(_guid(_CLSID_VideoInputDeviceCategory)), ctypes.byref(enum_moniker), 0)
        _check(hr, "CreateClassEnumerator")
        if hr != 0 or not enum_moniker.value:
            return  # S_FALSE: the category is empty

        next_moniker = _method(enum_moniker, 3, wintypes.ULONG, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.ULONG))
        index = 0
        while True:
            moniker = ctypes.c_void_p()
            fetched = wintypes.ULONG()
            if next_moniker(1, ctypes.byref(moniker), ctypes.byref(fetched)) != 0 or fetched.value != 1:
                break
            try:
                yield index, moniker
            finally:
                _release(moniker)
            index += 1
    finally:
        _release(enum_moniker)
        _release(devenum)


def _device_strings(moniker: ctypes.c_void_p) -> tuple[str, str]:
    """(FriendlyName, DevicePath) of a device moniker; empty strings if unavailable."""
    bag = ctypes.c_void_p()
    try:
        bind_to_storage = _method(
            moniker, 9, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)
        )  # IMoniker::BindToStorage
        if bind_to_storage(None, None, ctypes.byref(_guid(_IID_IPropertyBag)), ctypes.byref(bag)) != 0:
            return "", ""
        return _read_string(bag, "FriendlyName"), _read_string(bag, "DevicePath")
    finally:
        _release(bag)


def list_capture_devices() -> list[CaptureDevice]:
    """DirectShow video input devices in OpenCV CAP_DSHOW index order."""
    devices: list[CaptureDevice] = []
    with _com(), contextlib.closing(_video_input_monikers()) as monikers:
        for index, moniker in monikers:
            name, path = _device_strings(moniker)
            vid, pid = parse_vid_pid(path)
            devices.append(CaptureDevice(index, name, path, vid, pid))
    return devices


# IAMCameraControl properties (KSPROPERTY_CAMERACONTROL_*) and flags (CameraControl_Flags_*).
EXPOSURE = 4                 # DirectShow units: exposure time = 2**value seconds
AUTO_EXPOSURE_PRIORITY = 19  # 1 = in auto exposure the camera may lower the frame rate
FLAG_AUTO = 0x1
FLAG_MANUAL = 0x2


@dataclass(frozen=True)
class ControlRange:
    min: int
    max: int
    step: int
    default: int
    caps: int                # FLAG_AUTO / FLAG_MANUAL supported


class CameraControl:
    """IAMCameraControl of the DirectShow device at `index` (CAP_DSHOW order).

    Use as a context manager, on one thread. Values are set on the device itself, so
    they outlive this object, any VideoCapture, and the process.
    """

    def __init__(self, index: int):
        self.index = index
        self.name = ""
        self._ctl = ctypes.c_void_p()
        self._stack = contextlib.ExitStack()

    def __enter__(self) -> CameraControl:
        with contextlib.ExitStack() as stack:
            stack.enter_context(_com())
            device = ctypes.c_void_p()
            try:
                with contextlib.closing(_video_input_monikers()) as monikers:
                    for index, moniker in monikers:
                        if index == self.index:
                            self.name = _device_strings(moniker)[0]
                            bind_to_object = _method(
                                moniker, 8, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(GUID),
                                ctypes.POINTER(ctypes.c_void_p),
                            )  # IMoniker::BindToObject
                            _check(bind_to_object(None, None, ctypes.byref(_guid(_IID_IBaseFilter)),
                                                  ctypes.byref(device)), "BindToObject(IBaseFilter)")
                            break
                    else:
                        raise OSError(f"no DirectShow video device with index {self.index}")
                query_interface = _method(device, 0, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))
                _check(query_interface(ctypes.byref(_guid(_IID_IAMCameraControl)), ctypes.byref(self._ctl)),
                       "QueryInterface(IAMCameraControl)")
            finally:
                _release(device)
            self._stack = stack.pop_all()
        return self

    def __exit__(self, *exc) -> None:
        _release(self._ctl)
        self._ctl = ctypes.c_void_p()
        self._stack.close()

    def range(self, prop: int) -> ControlRange | None:
        """The device's range for `prop`, or None if it does not support it."""
        values = [ctypes.c_long() for _ in range(5)]
        get_range = _method(self._ctl, 3, ctypes.c_long, *([ctypes.POINTER(ctypes.c_long)] * 5))
        if get_range(prop, *(ctypes.byref(v) for v in values)) < 0:
            return None
        return ControlRange(*(v.value for v in values))

    def get(self, prop: int) -> tuple[int, int] | None:
        """(value, flags) as the device reports them, or None if not readable."""
        value, flags = ctypes.c_long(), ctypes.c_long()
        get = _method(self._ctl, 5, ctypes.c_long, ctypes.POINTER(ctypes.c_long), ctypes.POINTER(ctypes.c_long))
        if get(prop, ctypes.byref(value), ctypes.byref(flags)) < 0:
            return None
        return value.value, flags.value

    def set(self, prop: int, value: int, flags: int) -> None:
        set_ = _method(self._ctl, 4, ctypes.c_long, ctypes.c_long, ctypes.c_long)
        _check(set_(prop, value, flags), f"IAMCameraControl::Set({prop}, {value}, flags {flags})")
