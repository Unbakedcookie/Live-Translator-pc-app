"""Application state models (T013; spec §5.8, §6.3).

AppState = config (persisted) + session (chat log, memory only) + runtime (status, metrics).
All models are frozen and validated; reducers build new instances instead of mutating.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from livetranslator.theme.tokens import DEFAULT_PALETTE_ID, FONTS, OVERLAY, WINDOW

SCHEMA_VERSION = 2
LANGUAGE_CODE = re.compile(r"^[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", validate_default=True)


def _check_language(value: str) -> str:
    if not LANGUAGE_CODE.match(value):
        raise ValueError(f"not a language code: {value!r}")
    return value


# ---------------------------------------------------------------- enums


class Source(StrEnum):
    ME = "me"
    OTHERS = "others"
    SCREEN = "screen"


class DisplayMode(StrEnum):
    TRANSLATION = "translation"  # translation only
    BOTH = "both"  # original + translation


class SpeakerMode(StrEnum):
    AUTO = "auto"  # Discord names when connected, voice labels otherwise
    VOICE = "voice"
    DISCORD = "discord"
    OFF = "off"  # a single "Others" label


class StatusLevel(StrEnum):
    OK = "ok"
    BUSY = "busy"
    WARNING = "warning"
    ERROR = "error"


# ---------------------------------------------------------------- config (persisted)

Opacity = Annotated[float, Field(ge=0.0, le=1.0)]
WindowOpacity = Annotated[float, Field(ge=WINDOW.window_opacity_min, le=1.0)]
FontSize = Annotated[int, Field(ge=FONTS.overlay_size_min, le=FONTS.overlay_size_max)]


class Geometry(Frozen):
    """Window rectangle in Qt device-independent pixels (virtual desktop), plus the monitor it
    was on (spec §5.1). Qt handles per-monitor DPI scaling."""

    x: int
    y: int
    width: Annotated[int, Field(ge=WINDOW.min_width)]
    height: Annotated[int, Field(ge=WINDOW.min_height)]
    screen: str = ""  # QScreen.name(), e.g. "Odyssey G95C"; "" = unknown


class WindowStyle(Frozen):
    palette_id: str = DEFAULT_PALETTE_ID
    custom_seed: str | None = None  # '#RRGGBB' -> generated palette instead of palette_id
    custom_dark: bool = True
    bg_opacity: Opacity = WINDOW.bg_opacity_default
    window_opacity: WindowOpacity = WINDOW.window_opacity_default
    font_family: str | None = None  # None = Inter
    font_size: FontSize = FONTS.overlay_size_default
    outline: bool = True
    outline_width: Annotated[int, Field(ge=1, le=OVERLAY.outline_width_max)] | None = None
    shadow: bool = False
    show_languages: bool = True  # "ZH→EN" tag after the speaker on translated lines

    @field_validator("custom_seed")
    @classmethod
    def _seed_is_hex(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(r"#[0-9A-Fa-f]{6}", value):
            raise ValueError(f"custom_seed must be '#RRGGBB', got {value!r}")
        return value.upper() if value else value


class WindowConfig(Frozen):
    id: str = Field(min_length=1)
    title: str = ""
    target_lang: str = "en"
    sources: tuple[Source, ...] = (Source.ME, Source.OTHERS)
    display: DisplayMode = DisplayMode.TRANSLATION
    style: WindowStyle = WindowStyle()
    geometry: Geometry | None = None  # None = default placement (spec §5.1)
    pinned: bool = True
    click_through: bool = False
    locked: bool = False

    @field_validator("target_lang")
    @classmethod
    def _target_lang(cls, value: str) -> str:
        return _check_language(value)

    @field_validator("sources")
    @classmethod
    def _sources_unique_sorted(cls, value: tuple[Source, ...]) -> tuple[Source, ...]:
        order = list(Source)
        return tuple(sorted(set(value), key=order.index))


class DeviceRef(Frozen):
    """Audio device saved by name + host API, never by index (spec §5.3)."""

    name: str = Field(min_length=1)
    host_api: str = "Windows WASAPI"


class AudioConfig(Frozen):
    mic_device: DeviceRef | None = None  # None = Windows default
    output_device: DeviceRef | None = None
    mic_enabled: bool = True
    others_enabled: bool = True


MAX_SPEAKERS_LIMIT = 12


class SpeakerConfig(Frozen):
    mode: SpeakerMode = SpeakerMode.AUTO
    max_speakers: Annotated[int, Field(ge=1, le=MAX_SPEAKERS_LIMIT)] = 6
    me_label: str = Field(default="Me", min_length=1)
    use_discord_name_for_me: bool = False
    discord_app_id: str | None = None  # own-app mode (spec §5.13)

    @field_validator("discord_app_id")
    @classmethod
    def _snowflake(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(r"\d{15,21}", value):
            raise ValueError("a Discord application ID is 15-21 digits")
        return value


class EngineConfig(Frozen):
    """None = use the recommended default chosen from the M03 benchmarks (gate G4)."""

    asr_model: str | None = None
    mt_engine: str | None = None
    diarization_engine: str | None = None
    # Lines from or into these languages use the smarter Qwen translator when it's installed
    # (Mandarin follow-up 2026-10-18: Opus-MT garbles Chinese chat slang). Empty = off.
    smart_languages: tuple[str, ...] = ()


class PerformanceConfig(Frozen):
    game_mode: bool = False
    show_readout: bool = False
    asr_update_interval_s: Annotated[float, Field(ge=0.2, le=3.0)] = 0.5


class EchoFilterConfig(Frozen):
    """Drop a 'Me' line that repeats recent 'Others' speech (spec §5.2, D-010)."""

    window_s: Annotated[float, Field(ge=0.0, le=30.0)] = 4.0
    min_ratio: Annotated[float, Field(ge=0.0, le=100.0)] = 80.0


class VadConfig(Frozen):
    """Utterance segmentation (spec §5.4; Advanced settings)."""

    threshold: Annotated[float, Field(gt=0.0, lt=1.0)] = 0.5  # speech probability to open
    end_silence_ms: Annotated[int, Field(ge=100, le=3000)] = 500
    max_utterance_s: Annotated[float, Field(ge=3.0, le=30.0)] = 15.0


DEFAULT_HOTKEYS: dict[str, str] = {
    "show_hide_all": "Ctrl+Alt+H",
    "click_through_all": "Ctrl+Alt+T",
    "pin_all": "Ctrl+Alt+P",
    "ocr_region": "Ctrl+Alt+O",
    "ocr_recapture": "Ctrl+Alt+R",
    "mute_me": "Ctrl+Alt+M",
    "mute_others": "Ctrl+Alt+N",
    "game_mode": "Ctrl+Alt+G",
}
# T072: any function can get a shortcut; these start without one.
UNBOUND_HOTKEY_ACTIONS: tuple[str, ...] = ("new_window", "lock_all", "open_settings")
HOTKEY_ACTION_NAMES: tuple[str, ...] = (*DEFAULT_HOTKEYS, *UNBOUND_HOTKEY_ACTIONS)


class AppConfig(Frozen):
    schema_version: int = SCHEMA_VERSION
    my_language: str = "en"
    audio: AudioConfig = AudioConfig()
    speakers: SpeakerConfig = SpeakerConfig()
    engines: EngineConfig = EngineConfig()
    performance: PerformanceConfig = PerformanceConfig()
    echo_filter: EchoFilterConfig = EchoFilterConfig()
    vad: VadConfig = VadConfig()
    hotkeys: dict[str, str] = Field(default_factory=lambda: dict(DEFAULT_HOTKEYS))
    windows: tuple[WindowConfig, ...] = ()
    lock_layout: bool = False
    models_dir: str | None = None  # None = platformdirs default (app.paths)
    wizard_completed: bool = False

    @field_validator("my_language")
    @classmethod
    def _my_language(cls, value: str) -> str:
        return _check_language(value)

    @model_validator(mode="after")
    def _unique_window_ids(self) -> Self:
        ids = [w.id for w in self.windows]
        if len(ids) != len(set(ids)):
            raise ValueError(f"duplicate window ids: {ids}")
        return self

    def window(self, window_id: str) -> WindowConfig | None:
        return next((w for w in self.windows if w.id == window_id), None)


# ---------------------------------------------------------------- session (memory only)


class Utterance(Frozen):
    """One chat-log line. Partial while `is_final` is False (spec §5.2)."""

    id: str = Field(min_length=1)
    source: Source
    speaker_id: str  # "me", "screen", "others", "discord:<user id>", "voice:<n>"
    start: float  # seconds on the app's monotonic clock
    end: float | None = None
    committed: str = ""  # stable text (primary colour)
    tentative: str = ""  # may still change (secondary colour)
    language: str | None = None
    is_final: bool = False
    translations: dict[str, str] = Field(default_factory=dict[str, str])
    # lang -> the original text each translation was made from (T062): a translation is
    # current only while this equals `text`; otherwise it is shown as still changing.
    translated_from: dict[str, str] = Field(default_factory=dict[str, str])

    @property
    def text(self) -> str:
        if self.committed and self.tentative:
            return f"{self.committed} {self.tentative}"
        return self.committed or self.tentative


class SessionState(Frozen):
    utterances: tuple[Utterance, ...] = ()
    speaker_names: dict[str, str] = Field(default_factory=dict[str, str])  # session renames

    def utterance(self, utterance_id: str) -> Utterance | None:
        return next((u for u in reversed(self.utterances) if u.id == utterance_id), None)


# ---------------------------------------------------------------- runtime (memory only)


class RuntimeStatus(Frozen):
    level: StatusLevel
    message: str  # plain language, shown to the user (spec §9)


class RuntimeState(Frozen):
    statuses: dict[str, RuntimeStatus] = Field(default_factory=dict[str, RuntimeStatus])
    metrics: dict[str, float] = Field(default_factory=dict[str, float])
    all_hidden: bool = False


class AppState(Frozen):
    config: AppConfig = AppConfig()
    session: SessionState = SessionState()
    runtime: RuntimeState = RuntimeState()
