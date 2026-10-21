"""Tray icon + menu (T071; spec §5.12).

Presentational: every item acts through the WindowController (the same paths as the global
hotkeys), and checkmarks/icon colour are re-read from the store whenever it changes.
Items for features that don't exist yet (Language Manager, Discord) are
added by their own tasks, so the menu never shows a dead entry.

Icon colour: accent = listening, secondary = paused (both streams muted), danger = an
error status is active (its message is in the tooltip).
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from livetranslator import APP_DISPLAY_NAME
from livetranslator.app.window_controller import WindowController
from livetranslator.core.state import AppState, StatusLevel
from livetranslator.theme.icons import AppIconState, app_icon
from livetranslator.theme.qss import window_qss
from livetranslator.theme.tokens import DEFAULT_PALETTE_ID, PALETTES

ICON_NAME = "translate"


def tray_status(state: AppState) -> tuple[AppIconState, str]:
    """(icon state, tooltip) for the current state."""
    errors = [s.message for s in state.runtime.statuses.values() if s.level is StatusLevel.ERROR]
    if errors:
        return "attention", f"{APP_DISPLAY_NAME}: {errors[0]}"
    audio = state.config.audio
    if not audio.mic_enabled and not audio.others_enabled:
        return "paused", f"{APP_DISPLAY_NAME}: paused (both muted)"
    if state.runtime.anything_away:
        return "listening", f"{APP_DISPLAY_NAME}: listening, windows hidden"
    return "listening", f"{APP_DISPLAY_NAME}: listening"


class Tray(QObject):
    def __init__(
        self,
        controller: WindowController,
        quit_app: Callable[[], object],
        open_settings: Callable[[], None] | None = None,
        parent: QObject | None = None,
        open_transcript: Callable[[], None] | None = None,
        select_region: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._palette = PALETTES[DEFAULT_PALETTE_ID]
        self.icon = QSystemTrayIcon(self)
        self.icon_state: AppIconState | None = None
        self.menu = QMenu()
        self.menu.setStyleSheet(window_qss(self._palette))
        self.actions: dict[str, QAction] = {}

        def add(key: str, text: str, slot: Callable[[], object], checkable: bool = False) -> None:
            action = self.menu.addAction(text)
            action.setCheckable(checkable)
            action.triggered.connect(slot)
            self.actions[key] = action

        def hotkey(name: str) -> Callable[[], None]:
            return lambda: controller.handle_hotkey(name)

        add("show_hide_all", "Show/Hide all", hotkey("show_hide_all"))
        add("new_window", "New window", lambda: controller.add_window())
        self.menu.addSeparator()
        add("mute_me", "Mute Me", hotkey("mute_me"), checkable=True)
        add("mute_others", "Mute Others", hotkey("mute_others"), checkable=True)
        add("game_mode", "Game mode", hotkey("game_mode"), checkable=True)
        add("click_through_all", "Click-through", hotkey("click_through_all"), checkable=True)
        self.menu.addSeparator()
        # Wrapped so Qt's `checked` argument never reaches the callbacks.
        if select_region is not None:
            add("ocr_region", "Translate screen region…", lambda: select_region())
        if open_transcript is not None:
            add("transcript", "Transcript…", lambda: open_transcript())
        if open_settings is not None:
            add("settings", "Settings…", lambda: open_settings())
        add("quit", "Quit", lambda: quit_app())

        self.icon.setContextMenu(self.menu)
        self.icon.activated.connect(self._on_activated)
        store = controller.store
        store.config_changed.connect(lambda _key: self.refresh())
        store.runtime_changed.connect(lambda _key: self.refresh())
        store.window_changed.connect(lambda _key: self.refresh())
        self.refresh()

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        # One click shows everything that was put away (or hides all). People single-click
        # the icon to get a lost window back (user report 2026-10-18).
        if reason is QSystemTrayIcon.ActivationReason.Trigger:
            self._controller.handle_hotkey("show_hide_all")

    def refresh(self) -> None:
        state = self._controller.store.state
        config = state.config
        checks = {
            "mute_me": not config.audio.mic_enabled,
            "mute_others": not config.audio.others_enabled,
            "game_mode": config.performance.game_mode,
            "click_through_all": bool(config.windows)
            and all(w.click_through for w in config.windows),
        }
        for key, checked in checks.items():
            action = self.actions[key]
            action.blockSignals(True)
            action.setChecked(checked)
            action.blockSignals(False)
        status, tooltip = tray_status(state)
        if status != self.icon_state:  # redraw only on a change (it's painted, not a font)
            self.icon.setIcon(app_icon(status))
        self.icon.setToolTip(tooltip)
        self.icon_state = status

    def notify(self, message: str) -> None:
        """A Windows notification from the tray icon (e.g. "still running" after the last
        window closes)."""
        self.icon.showMessage(APP_DISPLAY_NAME, message, self.icon.icon())

    def show(self) -> None:
        self.icon.show()

    def hide(self) -> None:
        self.icon.hide()
