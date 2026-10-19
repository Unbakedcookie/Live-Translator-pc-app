"""Where the user's real models live, for the tests that run real engines (Qwen, Whisper...).

Read once at import, before the autouse fixture points LIVETRANSLATOR_HOME at a temp folder.
The models moved to D: on 2026-10-18 (user's C: drive was full), with LIVETRANSLATOR_HOME set
as a *user* environment variable; a shell started before that doesn't see it, so the
registry value is used as a fallback.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from livetranslator.app.paths import HOME_ENV, app_paths


def _user_env(name: str) -> str | None:
    if sys.platform != "win32":
        return None
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            return str(winreg.QueryValueEx(key, name)[0])
    except OSError:
        return None


def _real_models_dir() -> Path:
    home = os.environ.get(HOME_ENV) or _user_env(HOME_ENV)
    paths = app_paths(Path(home) if home else None)
    return paths.data_dir / "models"


REAL_MODELS = _real_models_dir()
