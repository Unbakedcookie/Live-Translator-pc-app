"""Filesystem locations (T011; spec §5.8). Every path comes from here, never hand-built.

Defaults come from platformdirs:
  config  %APPDATA%\\LiveTranslator             (settings.json; small, roams)
  data    %LOCALAPPDATA%\\LiveTranslator        (models by default)
  logs    %LOCALAPPDATA%\\LiveTranslator\\Logs

Setting LIVETRANSLATOR_HOME=<dir> puts everything under that one folder. Tests use it so they
never touch the real profile, and it gives a clean "fresh install" profile for first-run checks.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from platformdirs import PlatformDirs

from livetranslator import APP_NAME

HOME_ENV = "LIVETRANSLATOR_HOME"
SETTINGS_FILE = "settings.json"


@dataclass(frozen=True)
class AppPaths:
    config_dir: Path
    data_dir: Path
    log_dir: Path

    @property
    def settings_file(self) -> Path:
        return self.config_dir / SETTINGS_FILE

    @property
    def default_models_dir(self) -> Path:
        return self.data_dir / "models"

    def ensure(self) -> None:
        """Create the app's own folders (not the models folder, which is user-configurable)."""
        for directory in (self.config_dir, self.data_dir, self.log_dir):
            directory.mkdir(parents=True, exist_ok=True)


def app_paths(home: Path | None = None) -> AppPaths:
    """Resolve the app folders. `home` (or LIVETRANSLATOR_HOME) overrides platformdirs."""
    if home is None and (env_home := os.environ.get(HOME_ENV)):
        home = Path(env_home)
    if home is not None:
        return AppPaths(
            config_dir=home / "config",
            data_dir=home / "data",
            log_dir=home / "logs",
        )
    roaming = PlatformDirs(APP_NAME, appauthor=False, roaming=True)
    local = PlatformDirs(APP_NAME, appauthor=False)
    return AppPaths(
        config_dir=Path(roaming.user_config_dir),
        data_dir=Path(local.user_data_dir),
        log_dir=Path(local.user_log_dir),
    )
