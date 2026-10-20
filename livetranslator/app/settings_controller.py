"""Settings intents -> store actions (T072; spec §5.8).

The Settings pages call these methods; they never build actions themselves (same pattern as
WindowController). Hotkey checks are pure so they can be tested without Qt.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass

from livetranslator.core import actions as a
from livetranslator.core.state import (
    DEFAULT_HOTKEYS,
    HOTKEY_ACTION_NAMES,
    MAX_MIC_LANGUAGES,
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

    def set_mic_languages(self, first: str, also: Sequence[str] = ()) -> None:
        """Settings "I speak" + "I also speak". `first`: "same" (the language you translate
        into), "auto" (detect any) or a language code; `also`: more codes ("" = none)."""
        chosen = mic_languages_for(first, also, self._store.state.config.my_language)
        self._store.dispatch(a.UpdateConfigSection("audio", {"mic_languages": chosen}))

    def set_chinese_script(self, script: str) -> None:
        """'simplified' or 'traditional': how recognised Mandarin is written."""
        self._store.dispatch(a.UpdateConfigSection("engines", {"chinese_script": script}))

    def set_smart_language(self, code: str, on: bool) -> None:
        """Use (or stop using) the Qwen translator for lines from or into `code`."""
        current = self._store.state.config.engines.smart_languages
        wanted = tuple(sorted({*current, code} if on else set(current) - {code}))
        self._store.dispatch(a.UpdateConfigSection("engines", {"smart_languages": wanted}))

    def set_smart_fallback(self, on: bool) -> None:
        """Use Qwen for languages no installed translation model covers."""
        self._store.dispatch(a.UpdateConfigSection("engines", {"smart_fallback": on}))

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


def mic_choice(mic_languages: tuple[str, ...]) -> tuple[str, tuple[str, ...]]:
    """The ("I speak", "I also speak" list) choices that show a saved `mic_languages`."""
    if not mic_languages:
        return "same", ()
    if mic_languages == ("auto",):
        return "auto", ()
    return mic_languages[0], mic_languages[1:]


def mic_languages_for(first: str, also: Sequence[str], my_language: str) -> tuple[str, ...]:
    """The saved `mic_languages` for the ("I speak", "I also speak" list) choices. Blanks,
    repeats and the first language are dropped; at most MAX_MIC_LANGUAGES in all."""
    if first == "auto":
        return ("auto",)
    base = my_language if first == "same" else first
    chosen = [base]
    for code in also:
        if code and code not in chosen:
            chosen.append(code)
    chosen = chosen[:MAX_MIC_LANGUAGES]
    if len(chosen) > 1:
        return tuple(chosen)
    return () if first == "same" else (base,)
