"""Projector output: a borderless fullscreen OpenCV window on the identified display.

After going fullscreen, the real window geometry is read back through Win32 and
compared with the display's rectangle. If HighGUI did not cover the display
exactly, the window is forced into place; the result is reported, never assumed.
"""

from __future__ import annotations

import ctypes
import logging
from ctypes import wintypes

import cv2
import numpy as np

from . import patterns
from .monitors import Display

log = logging.getLogger(__name__)

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
_user32.FindWindowW.restype = wintypes.HWND
_user32.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
_user32.FindWindowExW.restype = wintypes.HWND
_user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
_user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
_user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
_user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
_user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]

_GWL_STYLE = -16
_WS_POPUP = 0x80000000
_WS_VISIBLE = 0x10000000
_SWP_FRAMECHANGED = 0x0020
_SWP_SHOWWINDOW = 0x0040


def _rect(hwnd, client: bool = False) -> tuple[int, int, int, int] | None:
    if not hwnd:
        return None
    r = wintypes.RECT()
    ok = _user32.GetClientRect(hwnd, ctypes.byref(r)) if client else _user32.GetWindowRect(hwnd, ctypes.byref(r))
    return (r.left, r.top, r.right, r.bottom) if ok else None


class ProjectorWindow:
    NAME = "Invisible Canvas - Projector"

    def __init__(self, display: Display | None, size: tuple[int, int], *, windowed: bool = False):
        if display is None and not windowed:
            raise ValueError("a display is required unless windowed")
        self.display = display
        self.size = (int(size[0]), int(size[1]))
        self.windowed = windowed
        self.geometry_ok = False
        self.geometry_report = "not opened"

    def open(self) -> None:
        if self.windowed:
            cv2.namedWindow(self.NAME, cv2.WINDOW_AUTOSIZE)
            cv2.moveWindow(self.NAME, 80, 80)
            self.show(patterns.blank(self.size))
            cv2.waitKey(1)
            self.geometry_ok = True
            self.geometry_report = f"windowed dev mode, {self.size[0]}x{self.size[1]} on the laptop screen"
            return
        d = self.display
        cv2.namedWindow(self.NAME, cv2.WINDOW_NORMAL)
        cv2.moveWindow(self.NAME, d.x, d.y)
        cv2.setWindowProperty(self.NAME, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        self.show(patterns.blank(self.size))
        cv2.waitKey(1)
        if not self._verify():
            log.warning("HighGUI fullscreen did not cover the display exactly; forcing window geometry")
            self._force_geometry()
            cv2.waitKey(1)
            self._verify()

    def _handles(self):
        frame = _user32.FindWindowW(None, self.NAME)
        child = _user32.FindWindowExW(frame, None, None, None) if frame else None
        return frame, child

    def _verify(self) -> bool:
        d = self.display
        frame, child = self._handles()
        window = _rect(frame)
        client = _rect(child, client=True) if child else _rect(frame, client=True)
        target = (d.x, d.y, d.x + d.width, d.y + d.height)
        client_size = (client[2] - client[0], client[3] - client[1]) if client else None
        self.geometry_ok = window == target and client_size == self.size
        self.geometry_report = (
            f"window rect {window} vs display rect {target}; image area {client_size} vs canvas {self.size}"
        )
        return self.geometry_ok

    def _force_geometry(self) -> None:
        d = self.display
        frame, _ = self._handles()
        if not frame:
            return
        _user32.SetWindowLongPtrW(frame, _GWL_STYLE, _WS_POPUP | _WS_VISIBLE)
        _user32.SetWindowPos(frame, None, d.x, d.y, d.width, d.height, _SWP_FRAMECHANGED | _SWP_SHOWWINDOW)

    def show(self, image: np.ndarray) -> None:
        w, h = self.size
        if image.shape[:2] != (h, w):
            raise ValueError(f"projector image must be {w}x{h}, got {image.shape[1]}x{image.shape[0]}")
        cv2.imshow(self.NAME, image)

    def close(self) -> None:
        try:
            cv2.destroyWindow(self.NAME)
        except cv2.error:
            pass
