"""Optional Windows 11 Mica "frosted glass" backdrop via win32mica (T012; spec §5.1, §6.5).

Off by default. On Windows builds without Mica (anything before Windows 11, build 22000) it is
a no-op and the window keeps its plain translucent painting.
"""

from __future__ import annotations

import importlib
import sys
from typing import Any

MICA_MIN_BUILD = 22000  # first Windows 11 build


def windows_build() -> int:
    if sys.platform != "win32":
        return 0
    return sys.getwindowsversion().build


def mica_supported(build: int) -> bool:
    return build >= MICA_MIN_BUILD


def apply_mica(hwnd: int, *, dark: bool, build: int | None = None) -> bool:
    """Apply Mica to a top-level window. Returns True only if Windows accepted it."""
    if not mica_supported(windows_build() if build is None else build):
        return False
    mica: Any = importlib.import_module("win32mica")  # untyped package
    theme = mica.MicaTheme.DARK if dark else mica.MicaTheme.LIGHT
    result = mica.ApplyMica(hwnd, theme, mica.MicaStyle.DEFAULT)
    return result == 0
