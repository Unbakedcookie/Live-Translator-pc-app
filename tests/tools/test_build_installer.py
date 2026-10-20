"""Setup .exe build (packaging; spec §11)."""

import re
from pathlib import Path

from livetranslator import __version__
from livetranslator.platform.win32 import APP_USER_MODEL_ID
from tools.build_installer import (
    ISCC_ENV,
    SCRIPT,
    find_iscc,
    iscc_command,
    setup_path,
)


def test_iscc_is_found_from_the_env_first(tmp_path: Path):
    iscc = tmp_path / "ISCC.exe"
    iscc.write_bytes(b"")
    assert find_iscc({ISCC_ENV: str(iscc)}) == iscc
    pf = tmp_path / "pf"
    (pf / "Inno Setup 6").mkdir(parents=True)
    (pf / "Inno Setup 6" / "ISCC.exe").write_bytes(b"")
    found = find_iscc({"ProgramFiles": str(pf)})
    assert found is not None  # the repo's local copy, or Program Files


def test_the_command_passes_version_and_folders():
    cmd = iscc_command(Path("ISCC.exe"), "1.2.3")
    assert cmd[0] == "ISCC.exe" and cmd[-1] == str(SCRIPT)
    assert "/DAppVersion=1.2.3" in cmd
    assert any(arg.startswith("/DSourceDir=") and arg.endswith("LiveTranslator") for arg in cmd)
    assert setup_path("1.2.3").name == "LiveTranslator-Setup-1.2.3.exe"
    assert setup_path().name == f"LiveTranslator-Setup-{__version__}.exe"


def test_shortcuts_are_offered_but_not_ticked():
    """User request 2026-10-19: show what we'd make, leave the boxes empty."""
    text = SCRIPT.read_text(encoding="utf-8")
    tasks = re.findall(r"^Name: \"(\w+)\";.*$", text.split("[Tasks]")[1].split("[")[0], re.M)
    assert tasks == ["startmenu", "desktopicon"]
    for line in text.split("[Tasks]")[1].split("[")[0].strip().splitlines():
        assert line.endswith("Flags: unchecked"), line
    icons = text.split("[Icons]")[1].split("[")[0].strip().splitlines()
    assert all("Tasks: " in line for line in icons)  # no shortcut without its box ticked


def test_the_taskbar_identity_matches_the_app():
    text = SCRIPT.read_text(encoding="utf-8")
    assert f'#define AppUserModelId "{APP_USER_MODEL_ID}"' in text
    assert "PrivilegesRequired=lowest" in text  # no admin prompt by default
