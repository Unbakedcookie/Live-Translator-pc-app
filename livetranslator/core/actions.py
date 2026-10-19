"""Actions: every state change is one of these, dispatched to the store (T013; spec §6.3).

Generic `fields` updates are validated by the reducer against the target model, so a bad
value (e.g. opacity 1.5) is rejected instead of corrupting state.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from livetranslator.core.state import AppConfig, Away, StatusLevel, Utterance, WindowConfig

ConfigSection = Literal["audio", "speakers", "engines", "performance", "echo_filter", "vad"]

# ---------------------------------------------------------------- config


@dataclass(frozen=True)
class ReplaceConfig:
    """Swap in a whole config (startup load, restore defaults)."""

    config: AppConfig


@dataclass(frozen=True)
class SetMyLanguage:
    language: str


@dataclass(frozen=True)
class UpdateConfigSection:
    section: ConfigSection
    fields: Mapping[str, object]


@dataclass(frozen=True)
class SetHotkey:
    action: str
    keys: str | None  # None = unbound


@dataclass(frozen=True)
class SetLockLayout:
    locked: bool


@dataclass(frozen=True)
class SetModelsDir:
    path: str | None


@dataclass(frozen=True)
class SetWizardCompleted:
    completed: bool = True


@dataclass(frozen=True)
class AddWindow:
    window: WindowConfig


@dataclass(frozen=True)
class RemoveWindow:
    window_id: str


@dataclass(frozen=True)
class UpdateWindow:
    """Top-level window fields (title, target_lang, sources, display, geometry, pinned, ...)."""

    window_id: str
    fields: Mapping[str, object]


@dataclass(frozen=True)
class UpdateWindowStyle:
    window_id: str
    fields: Mapping[str, object]


@dataclass(frozen=True)
class UpdateAllWindows:
    """Same top-level change on every window (hotkeys: pin all, click-through all)."""

    fields: Mapping[str, object]


# ---------------------------------------------------------------- session


@dataclass(frozen=True)
class AddUtterance:
    utterance: Utterance


@dataclass(frozen=True)
class UpdateUtterance:
    utterance_id: str
    fields: Mapping[str, object]


@dataclass(frozen=True)
class SetTranslation:
    utterance_id: str
    language: str
    text: str
    source_text: str = ""  # the original text that was translated (T062)


@dataclass(frozen=True)
class RemoveUtterance:
    utterance_id: str


@dataclass(frozen=True)
class ClearSession:
    pass


@dataclass(frozen=True)
class RenameSpeaker:
    speaker_id: str
    name: str | None  # None = back to the automatic label


# ---------------------------------------------------------------- runtime


@dataclass(frozen=True)
class SetStatus:
    key: str
    level: StatusLevel
    message: str


@dataclass(frozen=True)
class ClearStatus:
    key: str


@dataclass(frozen=True)
class SetMetric:
    name: str
    value: float


@dataclass(frozen=True)
class SetAllHidden:
    """True hides every overlay; False shows every overlay, including ones hidden or minimized
    one at a time."""

    hidden: bool


@dataclass(frozen=True)
class SetWindowAway:
    """Put one overlay away (`Away.HIDDEN` / `Away.MINIMIZED`) or bring it back (None)."""

    window_id: str
    away: Away | None


@dataclass(frozen=True)
class RestoreMinimized:
    """The taskbar button was clicked: every minimized overlay comes back."""


@dataclass(frozen=True)
class Batch:
    """Several actions applied as one step (one set of change notifications)."""

    actions: tuple[Action, ...] = field(default_factory=tuple)


Action = (
    ReplaceConfig
    | SetMyLanguage
    | UpdateConfigSection
    | SetHotkey
    | SetLockLayout
    | SetModelsDir
    | SetWizardCompleted
    | AddWindow
    | RemoveWindow
    | UpdateWindow
    | UpdateWindowStyle
    | UpdateAllWindows
    | AddUtterance
    | UpdateUtterance
    | SetTranslation
    | RemoveUtterance
    | ClearSession
    | RenameSpeaker
    | SetStatus
    | ClearStatus
    | SetMetric
    | SetAllHidden
    | SetWindowAway
    | RestoreMinimized
    | Batch
)
