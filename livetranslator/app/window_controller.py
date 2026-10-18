"""Window intents -> store actions (T024; spec §5.1, §5.7, §6.1).

Widgets call these methods; they never build actions themselves. Hotkey actions are handled
here too, so the same toggle logic serves the hotkeys now and the tray menu later (T071).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from livetranslator.core import actions as a
from livetranslator.core.state import DisplayMode, Geometry, Source, WindowConfig
from livetranslator.core.store import Store
from livetranslator.ui.geometry import Rect

# Hotkey actions this controller implements. OCR hotkeys are added with OCR (T083).
HOTKEY_ACTIONS = (
    "show_hide_all",
    "click_through_all",
    "pin_all",
    "mute_me",
    "mute_others",
    "game_mode",
    "new_window",
    "lock_all",
)


def new_window_id() -> str:
    return f"w-{uuid.uuid4().hex[:8]}"


class WindowController:
    def __init__(self, store: Store) -> None:
        self._store = store

    @property
    def store(self) -> Store:
        return self._store

    # ------------------------------------------------------------ one window

    def add_window(self, target_lang: str | None = None) -> str:
        config = self._store.state.config
        window_id = new_window_id()
        self._store.dispatch(
            a.AddWindow(WindowConfig(id=window_id, target_lang=target_lang or config.my_language))
        )
        return window_id

    def remove_window(self, window_id: str) -> None:
        self._store.dispatch(a.RemoveWindow(window_id))

    def set_pinned(self, window_id: str, pinned: bool) -> None:
        self._store.dispatch(a.UpdateWindow(window_id, {"pinned": pinned}))

    def set_click_through(self, window_id: str, enabled: bool) -> None:
        self._store.dispatch(a.UpdateWindow(window_id, {"click_through": enabled}))

    def set_locked(self, window_id: str, locked: bool) -> None:
        self._store.dispatch(a.UpdateWindow(window_id, {"locked": locked}))

    def set_target_lang(self, window_id: str, code: str) -> None:
        self._store.dispatch(a.UpdateWindow(window_id, {"target_lang": code}))

    def set_display(self, window_id: str, mode: DisplayMode) -> None:
        self._store.dispatch(a.UpdateWindow(window_id, {"display": mode}))

    def set_sources(self, window_id: str, sources: Iterable[Source]) -> None:
        self._store.dispatch(a.UpdateWindow(window_id, {"sources": tuple(sources)}))

    def set_geometry(self, window_id: str, rect: Rect, screen: str) -> None:
        geometry = Geometry(x=rect.x, y=rect.y, width=rect.width, height=rect.height, screen=screen)
        self._store.dispatch(a.UpdateWindow(window_id, {"geometry": geometry}))

    def rename_speaker(self, speaker_id: str, name: str) -> None:
        """T104: session-only rename; "" goes back to the automatic label."""
        self._store.dispatch(a.RenameSpeaker(speaker_id, name.strip() or None))

    def set_style(self, window_id: str, **fields: object) -> None:
        self._store.dispatch(a.UpdateWindowStyle(window_id, fields))

    def set_builtin_palette(self, window_id: str, palette_id: str) -> None:
        self.set_style(window_id, palette_id=palette_id, custom_seed=None)

    def set_custom_palette(self, window_id: str, seed: str, dark: bool) -> None:
        self.set_style(window_id, custom_seed=seed, custom_dark=dark)

    # ------------------------------------------------------------ all windows / hotkeys

    def handle_hotkey(self, action: str) -> None:
        state = self._store.state
        windows = state.config.windows
        match action:
            case "show_hide_all":
                self._store.dispatch(a.SetAllHidden(not state.runtime.all_hidden))
            case "click_through_all":
                enable = not all(w.click_through for w in windows)
                self._store.dispatch(a.UpdateAllWindows({"click_through": enable}))
            case "pin_all":
                pin = not all(w.pinned for w in windows)
                self._store.dispatch(a.UpdateAllWindows({"pinned": pin}))
            case "mute_me":
                audio = state.config.audio
                self._store.dispatch(
                    a.UpdateConfigSection("audio", {"mic_enabled": not audio.mic_enabled})
                )
            case "mute_others":
                audio = state.config.audio
                self._store.dispatch(
                    a.UpdateConfigSection("audio", {"others_enabled": not audio.others_enabled})
                )
            case "game_mode":
                perf = state.config.performance
                self._store.dispatch(
                    a.UpdateConfigSection("performance", {"game_mode": not perf.game_mode})
                )
            case "new_window":
                self.add_window()
            case "lock_all":
                lock = not all(w.locked for w in windows)
                self._store.dispatch(a.UpdateAllWindows({"locked": lock}))
            case _:
                raise ValueError(f"unknown hotkey action {action!r}")
