"""Settings file schema migrations (T015; spec §5.8).

Each entry upgrades raw JSON data from version N to N+1. Version 0 means "no
schema_version field": the layout is identical to version 1, so its migration only stamps
the version. Future format changes add a function here and bump state.SCHEMA_VERSION.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from livetranslator.core.state import SCHEMA_VERSION

RawConfig = dict[str, Any]


class MigrationError(ValueError):
    pass


class NewerSchemaError(MigrationError):
    """The file was written by a newer version of the app."""


def _v0_to_v1(data: RawConfig) -> RawConfig:
    return {**data, "schema_version": 1}


def _v1_to_v2(data: RawConfig) -> RawConfig:
    """v2 drops the per-window "mica" style option: Mica can't render on the
    overlay's layered (per-pixel alpha) window (G1 feedback, 2026-10-17)."""
    raw_windows: Any = data.get("windows")
    if not isinstance(raw_windows, list):
        # Leave malformed data alone so validation still rejects it (the file is then set
        # aside as damaged) instead of being silently "repaired" here.
        return {**data, "schema_version": 2}
    windows: list[Any] = []
    for window in cast(list[Any], raw_windows):
        if isinstance(window, dict):
            entry = cast(dict[str, Any], window)
            style: Any = entry.get("style")
            if isinstance(style, dict):
                kept = {k: v for k, v in cast(dict[str, Any], style).items() if k != "mica"}
                entry = {**entry, "style": kept}
            windows.append(entry)
        else:
            windows.append(window)
    return {**data, "windows": windows, "schema_version": 2}


MIGRATIONS: dict[int, Callable[[RawConfig], RawConfig]] = {0: _v0_to_v1, 1: _v1_to_v2}


def migrate(data: RawConfig, target: int = SCHEMA_VERSION) -> RawConfig:
    version = data.get("schema_version", 0)
    if not isinstance(version, int) or version < 0:
        raise MigrationError(f"invalid schema_version {version!r}")
    if version > target:
        raise NewerSchemaError(f"settings schema {version} is newer than supported {target}")
    while version < target:
        step = MIGRATIONS.get(version)
        if step is None:
            raise MigrationError(f"no migration from schema {version}")
        data = step(data)
        version += 1
        if data.get("schema_version") != version:
            raise MigrationError(f"migration to {version} did not stamp the version")
    return data
