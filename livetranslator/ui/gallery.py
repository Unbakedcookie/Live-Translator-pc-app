"""Widget gallery for the G1 review: every widget in every palette (T022).

python -m livetranslator.ui.gallery
"""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from livetranslator.theme.fonts import bundled_font_files, register_fonts
from livetranslator.theme.qss import build_qss
from livetranslator.theme.tokens import (
    DEFAULT_CUSTOM_SEED,
    PALETTES,
    RADIUS,
    SPACE,
    WINDOW,
    Palette,
)
from livetranslator.ui.widgets.colour_seed_picker import ColourSeedPicker
from livetranslator.ui.widgets.icon_button import IconButton
from livetranslator.ui.widgets.language_picker import LanguagePicker
from livetranslator.ui.widgets.pin_button import PinButton
from livetranslator.ui.widgets.slider import LabeledSlider
from livetranslator.ui.widgets.swatch import SwatchRow


class PalettePanel(QWidget):
    """One column of the gallery, drawn in `palette`."""

    def __init__(self, palette: Palette, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._palette = palette
        self.setStyleSheet(build_qss(palette))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE.md, SPACE.md, SPACE.md, SPACE.md)
        layout.setSpacing(SPACE.sm)

        title = QLabel(palette.name, self)
        layout.addWidget(title)

        icons = QHBoxLayout()
        icons.setSpacing(SPACE.xs)
        pin = PinButton(palette, self)
        pin.setChecked(True)
        icons.addWidget(pin)
        icons.addWidget(PinButton(palette, self))
        for name, tip in (
            ("palette", "Style"),
            ("gear", "Settings"),
            ("minus", "Hide"),
            ("x", "Close"),
        ):
            icons.addWidget(IconButton(name, tip, palette, parent=self))
        icons.addStretch(1)
        layout.addLayout(icons)

        layout.addWidget(LanguagePicker("ja", parent=self))
        layout.addWidget(LabeledSlider("Background", 0.0, 1.0, WINDOW.bg_opacity_default, self))
        layout.addWidget(LabeledSlider("Window", WINDOW.window_opacity_min, 1.0, 1.0, self))
        swatches = SwatchRow(palette.id, self)
        swatches.set_ring_color(palette.accent)
        layout.addWidget(swatches)
        seed_row = QHBoxLayout()
        seed_row.addWidget(QLabel("One colour", self))
        seed_row.addWidget(ColourSeedPicker(DEFAULT_CUSTOM_SEED, palette.is_dark, self))
        seed_row.addStretch(1)
        layout.addLayout(seed_row)
        buttons = QHBoxLayout()
        buttons.addWidget(QPushButton("Button", self))
        checked = QPushButton("Checked", self)
        checked.setCheckable(True)
        checked.setChecked(True)
        buttons.addWidget(checked)
        layout.addLayout(buttons)
        layout.addStretch(1)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor(self._palette.border))
        painter.setBrush(QColor(self._palette.surface))
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), RADIUS.md, RADIUS.md)
        painter.end()


class Gallery(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Live Translator widget gallery")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACE.lg, SPACE.lg, SPACE.lg, SPACE.lg)
        layout.setSpacing(SPACE.lg)
        self.panels = [PalettePanel(p, self) for p in PALETTES.values()]
        for panel in self.panels:
            panel.setMinimumWidth(WINDOW.default_width // 2 + SPACE.xl)
            layout.addWidget(panel, 0, Qt.AlignmentFlag.AlignTop)


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    register_fonts(bundled_font_files())
    gallery = Gallery()
    gallery.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
