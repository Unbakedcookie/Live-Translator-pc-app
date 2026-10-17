"""Shared test fixtures (T011)."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from loguru import logger

from livetranslator.app.paths import HOME_ENV


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point every test at a throwaway profile so the real %APPDATA% is never touched."""
    home = tmp_path / "lt-home"
    monkeypatch.setenv(HOME_ENV, str(home))
    yield home
    logger.remove()  # release log files so Windows can delete tmp_path
