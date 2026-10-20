"""Custom colours for one window (user request 2026-10-19; replaces the one-colour picker in
the style popover, which opened behind pinned overlays).

Every colour of the window's theme is a labelled slot. Click a slot, then pick a colour on
the right: the window changes as you go. Colours are saved on top of the theme they were set
on (WindowStyle.custom_colors), so "Undo my changes" goes back to it. "Make a whole theme"
still builds every colour from the picked one, as before.

A stay-on-top tool window beside the overlay, so neither hides the other.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QColor, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QColorDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from livetranslator.app.window_controller import WindowController
from livetranslator.theme.contrast import hard_to_read
from livetranslator.theme.palette_gen import palette_for
from livetranslator.theme.qss import settings_qss, window_qss
from livetranslator.theme.tokens import (
    DEFAULT_PALETTE_ID,
    MOTION,
    PALETTES,
    RADIUS,
    SETTINGS,
    SPACE,
    WINDOW,
    Palette,
    color_tokens,
)
from livetranslator.ui.screens import place_beside
from livetranslator.ui.settings.rows import note
from livetranslator.ui.widgets.choice_combo import ChoiceCombo
from livetranslator.ui.widgets.swatch import SWATCH

PEOPLE = 8  # tokens.SPEAKER_RAMP_SIZE, spelled out for the labels below
SLOT_GROUPS: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    (
        "Window",
        (
            ("bg", "Background"),
            ("surface", "Title bar and menus"),
            ("surface_alt", "Hover"),
            ("border", "Border"),
        ),
    ),
    (
        "Text",
        (
            ("text_primary", "Text"),
            ("text_secondary", "Text still being heard"),
            ("outline", "Text outline"),
        ),
    ),
    (
        "Buttons and status",
        (
            ("accent", "Highlight"),
            ("on_accent", "Text on highlight"),
            ("danger", "Warning"),
            ("ok", "OK"),
        ),
    ),
    (
        "Names",
        (
            ("speaker_me", "Me"),
            ("speaker_screen", "Screen"),
            *((f"speaker_others_{i}", f"Person {i}") for i in range(1, PEOPLE + 1)),
        ),
    ),
)
SLOT_LABELS = {name: label for _group, slots in SLOT_GROUPS for name, label in slots}
LEFT_GROUPS = 3  # Window, Text, Buttons in the first column; Names in the second


def theme_items() -> list[tuple[str, object]]:
    return [(p.name, p.id) for p in PALETTES.values()]


class ColourSlot(QAbstractButton):
    """A colour chip and its name; checked = the slot the picker colours."""

    def __init__(self, name: str, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.name = name
        self.setText(label)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(QSize(SETTINGS.colour_slot_width, SWATCH + SPACE.xs))
        self._ui: Palette = PALETTES[DEFAULT_PALETTE_ID]
        self.color = self._ui.bg  # until set_color

    def set_color(self, color: str, ui: Palette) -> None:
        self.color, self._ui = color, ui
        self.setToolTip(f"{self.text()}: {color}")
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        ui = self._ui
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        box = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if self.isChecked() or self.underMouse():
            painter.setPen(QPen(QColor(ui.accent), WINDOW.border_width * 2))
            painter.setBrush(QColor(ui.surface_alt))
            painter.drawRoundedRect(box, RADIUS.sm, RADIUS.sm)
        chip = SWATCH - SPACE.sm
        top = (self.height() - chip) / 2
        # text_secondary, not border: dark chips must stay visible on the dark editor
        painter.setPen(QPen(QColor(ui.text_secondary), WINDOW.border_width))
        painter.setBrush(QColor(self.color))
        painter.drawRoundedRect(QRectF(SPACE.xs, top, chip, chip), RADIUS.sm, RADIUS.sm)
        painter.setPen(QColor(ui.text_primary))
        text = QRectF(SPACE.xs + chip + SPACE.sm, 0, self.width(), self.height())
        painter.drawText(
            text, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.text()
        )
        painter.end()


class CustomColoursEditor(QWidget):
    """One per overlay window; FloatingWindow opens and owns it."""

    closed = Signal()

    def __init__(
        self,
        controller: WindowController,
        window_id: str,
        parent: QWidget,
        ui: Palette | None = None,
    ) -> None:
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self._controller = controller
        self._window_id = window_id
        self._ui = ui or PALETTES[DEFAULT_PALETTE_ID]
        self._palette: Palette | None = None
        self._pending: str | None = None
        self.setWindowTitle("Custom colours")
        self.setObjectName("SettingsRoot")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setStyleSheet(window_qss(self._ui) + settings_qss(self._ui))

        root = QVBoxLayout(self)
        root.setContentsMargins(SPACE.lg, SPACE.lg, SPACE.lg, SPACE.lg)
        root.setSpacing(SPACE.md)
        root.addWidget(
            note(
                "Click a colour on the left, then pick its new colour. "
                "Your window changes as you go."
            )
        )

        body = QHBoxLayout()
        body.setSpacing(SPACE.lg)
        columns = (QVBoxLayout(), QVBoxLayout())
        self.slots: dict[str, ColourSlot] = {}
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for index, (title, slots) in enumerate(SLOT_GROUPS):
            column = columns[0 if index < LEFT_GROUPS else 1]
            heading = QLabel(title)
            heading.setObjectName("SettingsSectionTitle")
            column.addWidget(heading)
            grid = QGridLayout()
            grid.setSpacing(SPACE.xs // 2)
            for row, (name, label) in enumerate(slots):
                slot = ColourSlot(name, label)
                slot.clicked.connect(lambda _c=False, n=name: self.select(n))
                self._group.addButton(slot)
                grid.addWidget(slot, row, 0)
                self.slots[name] = slot
            column.addLayout(grid)
        for column in columns:
            column.addStretch(1)
            body.addLayout(column)

        self.picker = QColorDialog(self)
        self.picker.setWindowFlags(Qt.WindowType.Widget)
        self.picker.setOptions(
            QColorDialog.ColorDialogOption.NoButtons
            | QColorDialog.ColorDialogOption.DontUseNativeDialog
        )
        self.picker.currentColorChanged.connect(self._on_picked)
        body.addWidget(self.picker, 1)
        root.addLayout(body)

        self.warning = note("")
        self.warning.setObjectName("SettingsWarning")
        root.addWidget(self.warning)

        actions = QHBoxLayout()
        actions.setSpacing(SPACE.sm)
        actions.addWidget(QLabel("Start again from"))
        self.theme = ChoiceCombo(theme_items())
        self.theme.apply_palette(self._ui)
        self.theme.setToolTip("Puts every colour back to this theme")
        self.theme.choice_changed.connect(
            lambda pid: controller.set_builtin_palette(window_id, str(pid))
        )
        actions.addWidget(self.theme)
        self.whole = QPushButton("Make a whole theme from the picked colour")
        self.whole.setToolTip("Every colour is worked out from the one you picked")
        self.whole.clicked.connect(self._make_theme)
        actions.addWidget(self.whole)
        actions.addStretch(1)
        self.undo = QPushButton("Undo my changes")
        self.undo.clicked.connect(lambda: controller.reset_custom_colors(window_id))
        actions.addWidget(self.undo)
        done = QPushButton("Done")
        done.setDefault(True)
        done.clicked.connect(self.close)
        actions.addWidget(done)
        root.addLayout(actions)

        self._apply_timer = QTimer(self)
        self._apply_timer.setSingleShot(True)
        self._apply_timer.setInterval(MOTION.colour_apply_ms)
        self._apply_timer.timeout.connect(self._apply_pending)

        controller.store.window_changed.connect(self._on_window_changed)
        self.refresh()
        self.select("bg")

    # ------------------------------------------------------------ store -> editor

    @property
    def selected(self) -> str:
        checked = self._group.checkedButton()
        return checked.name if isinstance(checked, ColourSlot) else "bg"

    def _on_window_changed(self, window_id: str) -> None:
        if window_id == self._window_id:
            self.refresh()

    def refresh(self) -> None:
        cfg = self._controller.store.state.config.window(self._window_id)
        if cfg is None:
            self.close()
            return
        style = cfg.style
        palette = palette_for(
            style.palette_id, style.custom_seed, style.custom_dark, style.custom_colors
        )
        self._palette = palette
        colors = color_tokens(palette)
        for name, slot in self.slots.items():
            slot.set_color(colors[name], self._ui)
        self.theme.set_choice(style.palette_id if style.palette_id in PALETTES else None)
        self.undo.setEnabled(bool(style.custom_colors))
        unreadable = [SLOT_LABELS[n] for n in hard_to_read(palette) if n in SLOT_LABELS]
        self.warning.setText(
            "Hard to read on its background: " + ", ".join(unreadable) if unreadable else ""
        )
        self.warning.setVisible(bool(unreadable))
        current = colors.get(self.selected)
        if current is not None and self._pending is None:
            self._show_in_picker(current)

    def select(self, name: str) -> None:
        self._apply_pending()  # a colour still being dragged belongs to the old slot
        self.slots[name].setChecked(True)
        self._show_in_picker(self.slots[name].color)

    def _show_in_picker(self, color: str) -> None:
        if self.picker.currentColor().name().upper() == color.upper():
            return
        self.picker.blockSignals(True)
        self.picker.setCurrentColor(QColor(color))
        self.picker.blockSignals(False)

    # ------------------------------------------------------------ editor -> controller

    def _on_picked(self, color: QColor) -> None:
        if not color.isValid():
            return
        self._pending = color.name().upper()
        self._apply_timer.start()

    def _apply_pending(self) -> None:
        self._apply_timer.stop()
        color, self._pending = self._pending, None
        if color is None:
            return
        name = self.selected
        if self.slots[name].color.upper() != color:
            self._controller.set_custom_color(self._window_id, name, color)

    def _make_theme(self) -> None:
        self._apply_timer.stop()
        self._pending = None
        dark = self._palette.is_dark if self._palette is not None else True
        seed = self.picker.currentColor().name().upper()
        self._controller.set_custom_palette(self._window_id, seed, dark)

    # ------------------------------------------------------------ window

    def open_beside(self, anchor: QWidget) -> None:
        self.adjustSize()
        if not self.isVisible():
            place_beside(self, anchor)
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event: QCloseEvent) -> None:
        self._apply_pending()
        super().closeEvent(event)
        self.closed.emit()
