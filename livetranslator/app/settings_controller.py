"""Settings intents -> store actions (T072; spec §5.8).

The Settings pages call these methods; they never build actions themselves (same pattern as
WindowController). Hotkey checks are pure so they can be tested without Qt.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass

from livetranslator.core import actions as a
from livetranslator.core.state import (
    DEFAULT_HOTKEYS,
    HOTKEY_ACTION_NAMES,
    DeviceRef,
    EchoFilterConfig,
    PerformanceConfig,
    SpeakerMode,
    VadConfig,
)
from livetranslator.core.store import Store
from livetranslator.services.hotkeys import HotkeyError, format_hotkey, parse_hotkey

# Order and wording of the Hotkeys page and of "shortcut taken" warnings.
HOTKEY_TITLES: dict[str, str] = {
    "show_hide_all": "Show or hide all windows",
    "click_through_all": "Click-through on all windows",
    "pin_all": "Keep all windows on top",
    "lock_all": "Lock all windows in place",
    "new_window": "Open a new window",
    "mute_me": "Mute Me (microphone)",
    "mute_others": "Mute Others (what you hear)",
    "game_mode": "Game mode",
    "open_settings": "Open Settings",
    "ocr_region": "Translate a screen region",
    "ocr_recapture": "Translate the last region again",
}
if set(HOTKEY_TITLES) != set(HOTKEY_ACTION_NAMES):
    raise RuntimeError("every hotkey action needs a title on the Hotkeys page")


@dataclass(frozen=True)
class HotkeyCheck:
    keys: str | None  # normalised combination ("Ctrl+Alt+H") when accepted
    error: str = ""


def check_hotkey(
    hotkeys: Mapping[str, str],
    action: str,
    text: str,
    active: Collection[str] | None = None,
) -> HotkeyCheck:
    """Validate a new combination for `action` against the syntax and the other actions.
    Only `active` actions (those this build can perform) count as clashes, so a default
    kept for a feature that isn't built yet never blocks a combination."""
    try:
        keys = format_hotkey(parse_hotkey(text))
    except HotkeyError:
        return HotkeyCheck(None, "Use Ctrl, Alt, Shift or Win with a key (F1 to F24 work alone).")
    for other, combo in hotkeys.items():
        if other == action or (active is not None and other not in active):
            continue
        try:
            same = format_hotkey(parse_hotkey(combo)) == keys
        except HotkeyError:
            continue
        if same:
            title = HOTKEY_TITLES.get(other, other)
            return HotkeyCheck(None, f"{keys} is already used for “{title}”.")
    return HotkeyCheck(keys)


class SettingsController:
    def __init__(
        self,
        store: Store,
        suspend_hotkeys: Callable[[bool], None] | None = None,
        active_hotkeys: Collection[str] | None = None,
    ) -> None:
        self._store = store
        self._suspend = suspend_hotkeys
        self._active = active_hotkeys  # None = every known action

    @property
    def store(self) -> Store:
        return self._store

    # ------------------------------------------------------------ general / audio

    def set_my_language(self, code: str) -> None:
        self._store.dispatch(a.SetMyLanguage(code))

    def set_mic_device(self, device: DeviceRef | None) -> None:
        self._store.dispatch(a.UpdateConfigSection("audio", {"mic_device": device}))

    def set_output_device(self, device: DeviceRef | None) -> None:
        self._store.dispatch(a.UpdateConfigSection("audio", {"output_device": device}))

    def set_stream_enabled(self, mic: bool | None = None, others: bool | None = None) -> None:
        fields: dict[str, object] = {}
        if mic is not None:
            fields["mic_enabled"] = mic
        if others is not None:
            fields["others_enabled"] = others
        if fields:
            self._store.dispatch(a.UpdateConfigSection("audio", fields))

    # ------------------------------------------------------------ speakers

    def set_speaker_mode(self, mode: SpeakerMode) -> None:
        self._store.dispatch(a.UpdateConfigSection("speakers", {"mode": mode}))

    def set_max_speakers(self, count: int) -> None:
        self._store.dispatch(a.UpdateConfigSection("speakers", {"max_speakers": count}))

    def set_me_label(self, text: str) -> None:
        label = text.strip()
        if label:
            self._store.dispatch(a.UpdateConfigSection("speakers", {"me_label": label}))

    # ------------------------------------------------------------ windows

    def set_all_locked(self, locked: bool) -> None:
        self._store.dispatch(a.UpdateAllWindows({"locked": locked}))

    # ------------------------------------------------------------ hotkeys

    def set_hotkey(self, action: str, text: str) -> HotkeyCheck:
        result = check_hotkey(self._store.state.config.hotkeys, action, text, self._active)
        if result.keys is not None:
            self._store.dispatch(a.SetHotkey(action, result.keys))
        return result

    def clear_hotkey(self, action: str) -> None:
        self._store.dispatch(a.SetHotkey(action, None))

    def reset_hotkeys(self) -> None:
        self._store.dispatch(
            a.Batch(
                tuple(a.SetHotkey(name, DEFAULT_HOTKEYS.get(name)) for name in HOTKEY_ACTION_NAMES)
            )
        )

    def suspend_hotkeys(self, suspended: bool) -> None:
        """While a shortcut is being recorded, the global hotkeys must not fire (or swallow
        the keys being pressed)."""
        if self._suspend is not None:
            self._suspend(suspended)

    # ------------------------------------------------------------ performance / advanced

    def set_show_readout(self, on: bool) -> None:
        self._store.dispatch(a.UpdateConfigSection("performance", {"show_readout": on}))

    def set_game_mode(self, on: bool) -> None:
        self._store.dispatch(a.UpdateConfigSection("performance", {"game_mode": on}))

    def set_asr_interval(self, seconds: float) -> None:
        self._store.dispatch(
            a.UpdateConfigSection("performance", {"asr_update_interval_s": round(seconds, 2)})
        )

    def set_echo_filter(self, **fields: object) -> None:
        self._store.dispatch(a.UpdateConfigSection("echo_filter", fields))

    def set_vad(self, **fields: object) -> None:
        self._store.dispatch(a.UpdateConfigSection("vad", fields))

    def reset_advanced(self) -> None:
        self._store.dispatch(
            a.Batch(
                (
                    a.UpdateConfigSection("echo_filter", EchoFilterConfig().model_dump()),
                    a.UpdateConfigSection("vad", VadConfig().model_dump()),
                    a.UpdateConfigSection(
                        "performance",
                        {"asr_update_interval_s": PerformanceConfig().asr_update_interval_s},
                    ),
                )
            )
        )
