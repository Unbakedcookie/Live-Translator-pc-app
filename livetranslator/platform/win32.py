"""Win32 window helpers via ctypes (T021; spec §5.1).

Pin and click-through are set directly on the native window instead of through Qt window
flags: changing Qt flags re-creates the native window (visible flicker, lost position).
The bit arithmetic lives in pure functions so it can be tested without a window.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x00000008
WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000

HWND_TOPMOST = -1
HWND_NOTOPMOST = -2

SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
_SWP_KEEP = SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE


# ---------------------------------------------------------------- pure flag math


def click_through_style(ex_style: int, enabled: bool) -> int:
    """Extended style with click-through on/off.

    Click-through needs WS_EX_TRANSPARENT (mouse falls through) on a layered window. Turning it
    off removes only WS_EX_TRANSPARENT; WS_EX_LAYERED stays because Qt uses it for opacity.
    """
    if enabled:
        return ex_style | WS_EX_TRANSPARENT | WS_EX_LAYERED
    return ex_style & ~WS_EX_TRANSPARENT


def has_click_through(ex_style: int) -> bool:
    return bool(ex_style & WS_EX_TRANSPARENT)


def has_topmost(ex_style: int) -> bool:
    return bool(ex_style & WS_EX_TOPMOST)


# ---------------------------------------------------------------- native calls

if sys.platform == "win32":
    _user32 = ctypes.WinDLL("user32", use_last_error=True)

    _get_long = _user32.GetWindowLongPtrW
    _get_long.argtypes = [wintypes.HWND, ctypes.c_int]
    _get_long.restype = ctypes.c_ssize_t

    _set_long = _user32.SetWindowLongPtrW
    _set_long.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    _set_long.restype = ctypes.c_ssize_t

    _set_pos = _user32.SetWindowPos
    _set_pos.argtypes = [
        wintypes.HWND,
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    ]
    _set_pos.restype = wintypes.BOOL


def _require_windows() -> None:
    if sys.platform != "win32":
        raise OSError("Win32 window helpers are only available on Windows")


def get_ex_style(hwnd: int) -> int:
    _require_windows()
    return int(_get_long(hwnd, GWL_EXSTYLE))


def _set_ex_style(hwnd: int, ex_style: int) -> None:
    ctypes.set_last_error(0)
    previous = _set_long(hwnd, GWL_EXSTYLE, ex_style)
    if previous == 0 and ctypes.get_last_error() != 0:
        raise ctypes.WinError(ctypes.get_last_error())
    # Make Windows re-read the style without moving, sizing or activating the window.
    _set_pos(hwnd, None, 0, 0, 0, 0, _SWP_KEEP | SWP_FRAMECHANGED)


def set_topmost(hwnd: int, enabled: bool) -> None:
    _require_windows()
    after = HWND_TOPMOST if enabled else HWND_NOTOPMOST
    if not _set_pos(hwnd, after, 0, 0, 0, 0, _SWP_KEEP):
        raise ctypes.WinError(ctypes.get_last_error())


def is_topmost(hwnd: int) -> bool:
    return has_topmost(get_ex_style(hwnd))


def set_click_through(hwnd: int, enabled: bool) -> None:
    _set_ex_style(hwnd, click_through_style(get_ex_style(hwnd), enabled))


def is_click_through(hwnd: int) -> bool:
    return has_click_through(get_ex_style(hwnd))
