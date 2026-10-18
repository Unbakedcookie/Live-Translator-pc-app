"""Shortcut recorder (T072; the user asked that any function can be remapped by anyone).

Click the box, press the new combination, done. Esc, clicking anywhere else in the window,
switching page or leaving the window cancels.
While recording, the app's global hotkeys are paused (the `recording` signal), otherwise
pressing an existing shortcut would trigger it instead of being recorded.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFocusEvent, QHideEvent, QKeyEvent
from PySide6.QtWidgets import QPushButton, QWidget

from livetranslator.services.hotkeys import combo_text
from livetranslator.theme.tokens import SETTINGS

NOT_SET = "Not set"
PROMPT = "Press keys…"
UNUSABLE = "That key can't be used — try another"

# A modifier key's own flag isn't always in its press event's modifiers (Qt/platform detail),
# so it is added (press) or removed (release) explicitly for the live feedback.
_MODIFIER_KEYS = {
    Qt.Key.Key_Control: Qt.KeyboardModifier.ControlModifier,
    Qt.Key.Key_Alt: Qt.KeyboardModifier.AltModifier,
    Qt.Key.Key_Shift: Qt.KeyboardModifier.ShiftModifier,
    Qt.Key.Key_Meta: Qt.KeyboardModifier.MetaModifier,
    Qt.Key.Key_AltGr: Qt.KeyboardModifier.AltModifier,
}


def held_modifiers(event: QKeyEvent, pressed: bool) -> Qt.KeyboardModifier:
    """Modifiers held after this event, counting the event's own modifier key."""
    mods = event.modifiers()
    own = _MODIFIER_KEYS.get(Qt.Key(event.key()))
    if own is None:
        return mods
    return mods | own if pressed else mods & ~own


def modifier_prefix(modifiers: Qt.KeyboardModifier) -> str:
    """'Ctrl+Alt+' while only modifiers are held (live feedback while recording)."""
    names = [
        label
        for flag, label in (
            (Qt.KeyboardModifier.ControlModifier, "Ctrl"),
            (Qt.KeyboardModifier.AltModifier, "Alt"),
            (Qt.KeyboardModifier.ShiftModifier, "Shift"),
            (Qt.KeyboardModifier.MetaModifier, "Win"),
        )
        if modifiers & flag
    ]
    return "".join(f"{n}+" for n in names)


def event_combo(event: QKeyEvent) -> str | None:
    """The combination a key press stands for, or None for a lone modifier / unknown key.
    Uses the Windows virtual-key code, so Shift+1 is "Shift+1" (not "!")."""
    if Qt.Key(event.key()) in _MODIFIER_KEYS:
        return None
    mods = event.modifiers()
    return combo_text(
        event.nativeVirtualKey(),
        ctrl=bool(mods & Qt.KeyboardModifier.ControlModifier),
        alt=bool(mods & Qt.KeyboardModifier.AltModifier),
        shift=bool(mods & Qt.KeyboardModifier.ShiftModifier),
        win=bool(mods & Qt.KeyboardModifier.MetaModifier),
    )


class HotkeyBox(QPushButton):
    captured = Signal(str)  # e.g. "Ctrl+Alt+H"
    recording = Signal(bool)

    def __init__(self, keys: str | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("HotkeyBox")
        self.setCheckable(True)
        self.setFixedWidth(SETTINGS.control_width)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._keys = keys
        self.clicked.connect(self._on_clicked)
        self._show_keys()

    @property
    def is_recording(self) -> bool:
        return self.isChecked()

    def set_keys(self, keys: str | None) -> None:
        self._keys = keys
        if not self.is_recording:
            self._show_keys()

    def _show_keys(self) -> None:
        self.setText(self._keys or NOT_SET)

    def _on_clicked(self, checked: bool) -> None:
        if checked:
            self.setText(PROMPT)
            self.setFocus()
            self.grabKeyboard()
            self.recording.emit(True)
        else:
            self.stop()

    def stop(self) -> None:
        if not self.is_recording:
            return
        self.releaseKeyboard()
        self.setChecked(False)
        self._show_keys()
        self.recording.emit(False)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if not self.is_recording:
            super().keyPressEvent(event)
            return
        if event.key() == Qt.Key.Key_Escape and event.modifiers() == Qt.KeyboardModifier.NoModifier:
            self.stop()
            return
        combo = event_combo(event)
        if combo is None:
            if Qt.Key(event.key()) in _MODIFIER_KEYS:
                self.setText(modifier_prefix(held_modifiers(event, pressed=True)) or PROMPT)
            else:
                self.setText(UNUSABLE)  # e.g. Tab or a numpad key: keep listening
            return
        self.stop()
        self.captured.emit(combo)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        if self.is_recording:
            self.setText(modifier_prefix(held_modifiers(event, pressed=False)) or PROMPT)
            return
        super().keyReleaseEvent(event)

    def focusOutEvent(self, event: QFocusEvent) -> None:
        self.stop()
        super().focusOutEvent(event)

    def hideEvent(self, event: QHideEvent) -> None:  # page switched or window closed
        self.stop()
        super().hideEvent(event)
