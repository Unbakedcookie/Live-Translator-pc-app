"""Build the Windows setup .exe from the app folder with Inno Setup (packaging; spec §11).

    python -m tools.build_app          # first: build/dist/LiveTranslator/
    python -m tools.build_installer    # -> build/installer/LiveTranslator-Setup-<version>.exe

Inno Setup (free, its own licence; a build tool, nothing of it ships except the small setup
stub it writes) is looked up in LT_ISCC, then local/tools/InnoSetup, then Program Files.
"""

from __future__ import annotations

import os
import subprocess  # nosec B404 - runs the Inno Setup compiler (build tool)
import sys
from pathlib import Path

from livetranslator import __version__
from tools.build_app import APP, BUILD, ROOT

SCRIPT = ROOT / "tools" / "installer" / "LiveTranslator.iss"
OUTPUT = BUILD / "installer"
ICON = BUILD / "icon" / "app.ico"
ISCC_ENV = "LT_ISCC"


def find_iscc(env: dict[str, str] | None = None) -> Path | None:
    env = dict(os.environ) if env is None else env
    candidates = [
        Path(env[ISCC_ENV]) if env.get(ISCC_ENV) else None,
        ROOT / "local" / "tools" / "InnoSetup" / "ISCC.exe",
        *(
            Path(env[var]) / "Inno Setup 6" / "ISCC.exe"
            for var in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA")
            if env.get(var)
        ),
    ]
    return next((p for p in candidates if p is not None and p.is_file()), None)


def iscc_command(iscc: Path, version: str = __version__) -> list[str]:
    return [
        str(iscc),
        "/Q",
        f"/DAppVersion={version}",
        f"/DSourceDir={APP}",
        f"/DOutputDir={OUTPUT}",
        f"/DIconFile={ICON}",
        str(SCRIPT),
    ]


def setup_path(version: str = __version__) -> Path:
    return OUTPUT / f"LiveTranslator-Setup-{version}.exe"


def main() -> int:
    if not (APP / "LiveTranslator.exe").is_file() or not ICON.is_file():
        print("build the app first: python -m tools.build_app")
        return 1
    iscc = find_iscc()
    if iscc is None:
        print(f"Inno Setup not found (set {ISCC_ENV} to ISCC.exe)")
        return 1
    OUTPUT.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(iscc_command(iscc), check=False)  # nosec B603 - fixed args
    if result.returncode:
        return result.returncode
    setup = setup_path()
    print(f"{setup}: {setup.stat().st_size >> 20} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
