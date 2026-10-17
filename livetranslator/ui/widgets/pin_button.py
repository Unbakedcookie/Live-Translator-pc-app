"""PureRef-style pin toggle: outlined pin = normal window, filled accent pin = always on top
(T022; spec §5.1)."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from livetranslator.theme.tokens import Palette
from livetranslator.ui.widgets.icon_button import IconButton


class PinButton(IconButton):
    def __init__(self, palette: Palette, parent: QWidget | None = None) -> None:
        super().__init__(
            "push-pin",
            "Pin on top",
            palette,
            checked_icon="push-pin-fill",
            checked_role="accent",
            checked_tooltip="Pinned on top (click to unpin)",
            parent=parent,
        )
