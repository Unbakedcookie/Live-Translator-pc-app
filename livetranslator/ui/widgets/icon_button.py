"""Icon-only tool button with palette-driven Phosphor icons (T022)."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QToolButton, QWidget

from livetranslator.theme.icons import IconRole, icon
from livetranslator.theme.tokens import WINDOW, Palette


class IconButton(QToolButton):
    """A flat icon button. With `checked_icon` it becomes a toggle whose icon and colour show
    the state (e.g. outline pin vs. filled accent pin)."""

    def __init__(
        self,
        icon_name: str,
        tooltip: str,
        palette: Palette,
        *,
        role: IconRole = "text_secondary",
        checked_icon: str | None = None,
        checked_role: IconRole = "accent",
        checked_tooltip: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._icon_name = icon_name
        self._role: IconRole = role
        self._checked_icon = checked_icon
        self._checked_role: IconRole = checked_role
        self._tooltip = tooltip
        self._checked_tooltip = checked_tooltip or tooltip
        self._palette = palette
        self.setAutoRaise(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setIconSize(QSize(WINDOW.icon_size, WINDOW.icon_size))
        if checked_icon is not None:
            self.setCheckable(True)
            self.toggled.connect(lambda _checked: self._refresh())
        self._refresh()

    def apply_palette(self, palette: Palette) -> None:
        self._palette = palette
        self._refresh()

    def _refresh(self) -> None:
        on = self.isChecked() and self._checked_icon is not None
        name = self._checked_icon if on and self._checked_icon else self._icon_name
        role: IconRole = self._checked_role if on else self._role
        self.setIcon(
            icon(name, self._palette, role, active_role="text_primary" if not on else role)
        )
        self.setToolTip(self._checked_tooltip if on else self._tooltip)
