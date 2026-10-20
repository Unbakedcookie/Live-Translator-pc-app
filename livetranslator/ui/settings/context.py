"""What the Settings pages are given (T072). The app layer fills this in; pages only read it
and call the controllers, so they stay presentational and testable with fakes."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from livetranslator.app.discord_controller import DiscordController
from livetranslator.app.language_controller import LanguageController
from livetranslator.app.settings_controller import SettingsController
from livetranslator.app.window_controller import WindowController
from livetranslator.core.state import Source
from livetranslator.services.audio.devices import DeviceList
from livetranslator.theme.tokens import DEFAULT_PALETTE_ID, PALETTES, Palette


@dataclass(frozen=True)
class EngineRow:
    role: str  # "Speech recognition"
    engine: str  # "Whisper large-v3-turbo"
    where: str  # "Graphics card", "Processor", "Starting…", "Off"


@dataclass(frozen=True)
class EngineSummary:
    rows: tuple[EngineRow, ...] = ()
    pairs: tuple[tuple[str, str], ...] = ()  # installed direct translation pairs


@dataclass
class SettingsContext:
    settings: SettingsController
    windows: WindowController
    models_dir: Path
    log_dir: Path
    open_folder: Callable[[Path], None]
    palette: Palette = field(default_factory=lambda: PALETTES[DEFAULT_PALETTE_ID])
    devices: Callable[[], DeviceList] | None = None  # None = speech is off this session
    level_db: Callable[[Source], float | None] | None = None
    engines: Callable[[], EngineSummary] | None = None
    hotkey_actions: tuple[str, ...] = ()  # actions this build can perform (no dead rows)
    smart_translation: bool = False  # the Qwen files are installed (Translation page switch)
    discord: DiscordController | None = None  # Speakers page: Discord names setup (T104)
    languages: LanguageController | None = None  # Languages page (T074)
    run_setup: Callable[[], None] | None = None  # Advanced: the setup wizard again (T073)
