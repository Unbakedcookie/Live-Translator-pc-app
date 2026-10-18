"""Settings → Hotkeys (T072): every action the app can do gets a remappable shortcut.

Two kinds of problems are shown under the action's name:
- in-app: the combination is invalid or used by another action (refused, nothing saved);
- Windows: another program owns the combination (saved, but the store's `hotkey.<action>`
  warning says it doesn't work — the user can pick another).
"""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget

from livetranslator.app.settings_controller import HOTKEY_TITLES
from livetranslator.core.state import StatusLevel
from livetranslator.services.hotkeys import valid_hotkey
from livetranslator.theme.tokens import SPACE
from livetranslator.ui.settings.context import SettingsContext
from livetranslator.ui.settings.hotkey_box import HotkeyBox
from livetranslator.ui.settings.rows import SettingRow, SettingsPage
from livetranslator.ui.widgets.icon_button import IconButton


class HotkeyControl(QWidget):
    """Recorder box + a small "remove shortcut" button."""

    def __init__(self, ctx: SettingsContext, action: str, keys: str | None) -> None:
        super().__init__()
        self.box = HotkeyBox(keys, self)
        self.clear = IconButton("x", "Remove this shortcut", ctx.palette, parent=self)
        keep = self.clear.sizePolicy()
        keep.setRetainSizeWhenHidden(True)  # boxes stay aligned when a row has no shortcut
        self.clear.setSizePolicy(keep)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACE.xs)
        layout.addWidget(self.box)
        layout.addWidget(self.clear)
        self.box.recording.connect(ctx.settings.suspend_hotkeys)
        self.clear.clicked.connect(lambda: ctx.settings.clear_hotkey(action))


class HotkeysPage(SettingsPage):
    title_text = "Hotkeys"
    icon_name = "keyboard"

    def __init__(self, ctx: SettingsContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self.intro(
            "Click a box, then press the keys you want. Shortcuts work everywhere, even while "
            "a game has focus. Esc cancels."
        )
        section = self.section("Shortcuts")
        self.rows: dict[str, SettingRow] = {}
        self.controls: dict[str, HotkeyControl] = {}
        self.errors: dict[str, str] = {}
        hotkeys = ctx.settings.store.state.config.hotkeys
        self._seen = dict(hotkeys)
        for action, title in HOTKEY_TITLES.items():
            if action not in ctx.hotkey_actions:
                continue  # not in this build yet (e.g. screen translation): no dead rows
            control = HotkeyControl(ctx, action, hotkeys.get(action))
            control.box.captured.connect(lambda keys, a=action: self._on_captured(a, keys))
            self.controls[action] = control
            self.rows[action] = section.row(title, "", control)
        reset = QPushButton("Restore default shortcuts")
        reset.clicked.connect(self._on_reset)
        self.section().row("Start over", "Puts every shortcut back to how it came.", reset)
        self.finish()
        self.refresh()

    def _on_captured(self, action: str, keys: str) -> None:
        result = self._ctx.settings.set_hotkey(action, keys)
        if result.error:
            self.errors[action] = result.error  # refused: nothing changed in the store
        self.refresh()

    def _on_reset(self) -> None:
        self._ctx.settings.reset_hotkeys()

    def refresh(self) -> None:
        state = self._ctx.settings.store.state
        if state.config.hotkeys != self._seen:
            self._seen = dict(state.config.hotkeys)
            self.errors.clear()  # any change (here, tray, reset) makes old refusals stale
        for action, control in self.controls.items():
            control.box.set_keys(state.config.hotkeys.get(action))
            control.clear.setVisible(action in state.config.hotkeys)
            status = state.runtime.statuses.get(f"hotkey.{action}")
            problem = self.errors.get(action, "")
            keys = state.config.hotkeys.get(action)
            if not problem and keys is not None and not valid_hotkey(keys):
                problem = "This saved shortcut isn't valid. Click the box to set it again."
            elif not problem and status is not None and status.level is not StatusLevel.OK:
                problem = (
                    "Another program already uses this shortcut, so it won't work. Pick another."
                )
            row = self.rows[action]
            row.set_description(problem)
            row.description.setObjectName("SettingsError" if problem else "SettingsRowDescription")
            row.description.style().unpolish(row.description)
            row.description.style().polish(row.description)
