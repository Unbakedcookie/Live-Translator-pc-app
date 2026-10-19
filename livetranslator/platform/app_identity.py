"""The app's Windows identity: taskbar name/icon and the name on its notifications.

`set_app_user_model_id` (platform.win32) gives the process its own taskbar identity. Windows
then labels notifications with that raw id ("LiveTranslator.App") unless the id is registered
with a display name and icon under HKCU\\Software\\Classes\\AppUserModelId (user report
2026-10-18; seen on this PC). This registers it per user, no admin rights. The installer
(T113) removes the key on uninstall.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon

ICON_FILE = "app.ico"
ICON_SIZES = (16, 24, 32, 48, 64, 256)
AUMID_KEY = r"Software\Classes\AppUserModelId"


def write_icon(window_icon: QIcon, folder: Path) -> Path | None:
    """Save the app icon as a multi-size .ico (for the registry entry and shortcuts)."""
    path = folder / ICON_FILE
    folder.mkdir(parents=True, exist_ok=True)
    # Qt writes one image per file; the largest wins and Windows scales it down cleanly.
    pixmap = window_icon.pixmap(max(ICON_SIZES), max(ICON_SIZES))
    if pixmap.isNull() or not pixmap.save(str(path), "ICO"):
        return None
    return path


def register_app_identity(app_id: str, display_name: str, icon_path: Path | None) -> bool:
    """Name (and icon) Windows shows for `app_id` on notifications. False if not on Windows or
    the registry refused."""
    if sys.platform != "win32":
        return False
    import winreg

    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, f"{AUMID_KEY}\\{app_id}") as key:
            winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, display_name)
            if icon_path is not None:
                winreg.SetValueEx(key, "IconUri", 0, winreg.REG_SZ, str(icon_path))
    except OSError:
        return False
    return True
