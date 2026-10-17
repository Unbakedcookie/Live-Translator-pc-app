"""'Pick one colour' button: choose a seed colour and preview the palette made from it (T022;
spec §6.5)."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QColorDialog, QWidget

from livetranslator.theme.palette_gen import generate_palette
from livetranslator.theme.tokens import Palette
from livetranslator.ui.widgets.swatch import PaletteSwatch


class ColourSeedPicker(PaletteSwatch):
    """Shows the generated palette for the current seed; click to choose another colour."""

    seed_chosen = Signal(str)  # '#RRGGBB'

    def __init__(self, seed: str, dark: bool, parent: QWidget | None = None) -> None:
        self._seed = seed.upper()
        self._dark = dark
        super().__init__(generate_palette(self._seed, dark=dark), parent)
        self.setToolTip("Make a theme from one colour")
        self.clicked.connect(self._choose)

    @property
    def seed(self) -> str:
        return self._seed

    def set_seed(self, seed: str, dark: bool) -> None:
        self._seed, self._dark = seed.upper(), dark
        palette: Palette = generate_palette(self._seed, dark=dark)
        self.set_palette(palette)
        self.setToolTip("Make a theme from one colour")

    def _choose(self) -> None:
        color = QColorDialog.getColor(QColor(self._seed), self.window(), "Pick a theme colour")
        if color.isValid():
            seed = color.name().upper()
            self.set_seed(seed, self._dark)
            self.seed_chosen.emit(seed)
