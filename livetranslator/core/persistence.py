"""Settings persistence: versioned JSON, atomic, debounced (T015; spec §5.8).

Only `AppState.config` is ever written. The session (chat log) and runtime state never reach
disk, by construction: `save_config` takes an AppConfig, not the whole state.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import cast

from loguru import logger
from pydantic import ValidationError
from PySide6.QtCore import QObject, QTimer, Signal

from livetranslator.core.actions import ClearStatus, SetStatus
from livetranslator.core.migrations import MigrationError, NewerSchemaError, RawConfig, migrate
from livetranslator.core.state import AppConfig, StatusLevel
from livetranslator.core.store import Store

DEBOUNCE_MS = 500
STATUS_KEY = "settings"


@dataclass(frozen=True)
class LoadResult:
    config: AppConfig
    notice: str | None = None  # plain-language message for the user, if something went wrong


def _set_aside(path: Path, label: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = path.with_name(f"{path.stem}.{label}-{stamp}{path.suffix}")
    counter = 1
    while target.exists():
        target = path.with_name(f"{path.stem}.{label}-{stamp}-{counter}{path.suffix}")
        counter += 1
    path.replace(target)
    return target


def load_config(path: Path) -> LoadResult:
    """Load settings. A missing file gives defaults; a damaged one is kept aside, not lost."""
    if not path.exists():
        return LoadResult(AppConfig())
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise MigrationError("settings root is not an object")
        return LoadResult(AppConfig.model_validate(migrate(cast(RawConfig, raw))))
    except NewerSchemaError:
        kept = _set_aside(path, "newer-version")
        logger.warning("settings from a newer app version set aside as {}", kept.name)
        return LoadResult(
            AppConfig(),
            f"Your settings were saved by a newer version of Live Translator, so defaults "
            f"are in use. The file was kept as {kept.name}.",
        )
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        MigrationError,
        ValidationError,
    ) as exc:
        kept = _set_aside(path, "corrupt")
        logger.warning("settings unreadable ({}); set aside as {}", type(exc).__name__, kept.name)
        return LoadResult(
            AppConfig(),
            f"Your settings file was damaged, so defaults are in use. The old file was kept "
            f"as {kept.name}.",
        )


def save_config(path: Path, config: AppConfig) -> None:
    """Write atomically: temp file + fsync + os.replace, so a crash never leaves half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(config.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"
    tmp = path.with_name(path.name + ".tmp")
    try:
        with tmp.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


class Persistence(QObject):
    """Saves the config DEBOUNCE_MS after the last change; `flush()` saves pending changes now."""

    saved = Signal()

    def __init__(
        self,
        store: Store,
        path: Path,
        debounce_ms: int = DEBOUNCE_MS,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._store = store
        self._path = path
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(debounce_ms)
        self._timer.timeout.connect(self.save)
        store.config_changed.connect(self._schedule)

    @property
    def pending(self) -> bool:
        return self._timer.isActive()

    def _schedule(self, _section: str) -> None:
        self._timer.start()  # restarting the timer is the debounce

    def flush(self) -> None:
        if self._timer.isActive():
            self._timer.stop()
            self.save()

    def save(self) -> None:
        try:
            save_config(self._path, self._store.state.config)
        except OSError as exc:
            logger.error("settings save failed: {}", type(exc).__name__)
            self._store.dispatch(
                SetStatus(
                    STATUS_KEY,
                    StatusLevel.WARNING,
                    "Couldn't save your settings. Check that the settings folder is writable.",
                )
            )
            return
        if STATUS_KEY in self._store.state.runtime.statuses:
            self._store.dispatch(ClearStatus(STATUS_KEY))
        self.saved.emit()
