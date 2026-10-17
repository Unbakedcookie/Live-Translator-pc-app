"""T011 — app folder resolution (Tier A). Expected paths are written out by hand."""

import os
import sys
from pathlib import Path

import pytest

from livetranslator.app.paths import HOME_ENV, app_paths


def test_explicit_home(tmp_path: Path):
    p = app_paths(tmp_path)
    assert p.config_dir == tmp_path / "config"
    assert p.data_dir == tmp_path / "data"
    assert p.log_dir == tmp_path / "logs"
    assert p.settings_file == tmp_path / "config" / "settings.json"
    assert p.default_models_dir == tmp_path / "data" / "models"


def test_env_home(isolated_home: Path):
    assert app_paths().settings_file == isolated_home / "config" / "settings.json"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows folder layout")
def test_platformdirs_defaults_on_windows(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(HOME_ENV)
    roaming = Path(os.environ["APPDATA"])
    local = Path(os.environ["LOCALAPPDATA"])
    p = app_paths()
    assert p.config_dir == roaming / "LiveTranslator"
    assert p.settings_file == roaming / "LiveTranslator" / "settings.json"
    assert p.data_dir == local / "LiveTranslator"
    assert p.log_dir == local / "LiveTranslator" / "Logs"
    assert p.default_models_dir == local / "LiveTranslator" / "models"


def test_ensure_creates_app_folders_only(tmp_path: Path):
    p = app_paths(tmp_path)
    p.ensure()
    assert p.config_dir.is_dir()
    assert p.data_dir.is_dir()
    assert p.log_dir.is_dir()
    assert not p.default_models_dir.exists()  # models folder is user-configurable (§5.8)
