"""App identity: the icon file and the per-user notification name (user report 2026-10-18)."""

import sys
from pathlib import Path

import pytest
from PySide6.QtGui import QImage

from livetranslator.platform.app_identity import (
    AUMID_KEY,
    ICON_FILE,
    register_app_identity,
    write_icon,
)
from livetranslator.theme.icons import icon
from livetranslator.theme.tokens import DEFAULT_PALETTE_ID, PALETTES


def test_icon_is_written_as_ico(qtbot, tmp_path: Path):
    path = write_icon(icon("translate", PALETTES[DEFAULT_PALETTE_ID], "accent"), tmp_path / "d")
    assert path == tmp_path / "d" / ICON_FILE
    image = QImage(str(path))
    assert not image.isNull() and image.width() == 256


@pytest.mark.skipif(sys.platform != "win32", reason="Windows registry")
def test_registers_a_display_name_under_the_users_classes(tmp_path: Path):
    import winreg

    app_id = "LiveTranslator.TestOnly"
    try:
        assert register_app_identity(app_id, "Live Translator", tmp_path / "app.ico")
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, f"{AUMID_KEY}\\{app_id}") as key:
            assert winreg.QueryValueEx(key, "DisplayName")[0] == "Live Translator"
            assert winreg.QueryValueEx(key, "IconUri")[0] == str(tmp_path / "app.ico")
    finally:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, f"{AUMID_KEY}\\{app_id}")
