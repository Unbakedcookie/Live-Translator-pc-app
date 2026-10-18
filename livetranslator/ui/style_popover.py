"""Per-window style popover (T024; spec §5.1). Opens from the palette icon in the chrome.

Every control calls the WindowController; the popover redraws itself from the store, so it
always shows the true state (including changes made by hotkeys while it is open).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPaintEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from livetranslator.app.window_controller import WindowController
from livetranslator.core.state import DisplayMode, Source, WindowConfig
from livetranslator.theme.palette_gen import palette_for
from livetranslator.theme.qss import window_qss
from livetranslator.theme.tokens import (
    DEFAULT_CUSTOM_SEED,
    FONTS,
    OVERLAY,
    RADIUS,
    SPACE,
    WINDOW,
    Palette,
    default_outline_width,
)
from livetranslator.ui.widgets.colour_seed_picker import ColourSeedPicker
from livetranslator.ui.widgets.font_picker import FontPicker
from livetranslator.ui.widgets.slider import LabeledSlider
from livetranslator.ui.widgets.swatch import SwatchRow

SOURCE_LABELS = ((Source.ME, "Me"), (Source.OTHERS, "Others"), (Source.SCREEN, "Screen"))


class StylePopover(QFrame):
    """Child of its FloatingWindow (deleted with it) but shown as a separate popup window."""

    def __init__(self, controller: WindowController, window_id: str, parent: QWidget) -> None:
        super().__init__(
            parent,
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,  # never behind a pinned overlay
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._controller = controller
        self._window_id = window_id
        self._palette: Palette | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(SPACE.md, SPACE.md, SPACE.md, SPACE.md)
        root.setSpacing(SPACE.sm)

        root.addWidget(self._heading("Theme"))
        theme_row = QHBoxLayout()
        self.swatches = SwatchRow("", self)
        self.swatches.palette_selected.connect(
            lambda pid: controller.set_builtin_palette(window_id, pid)
        )
        theme_row.addWidget(self.swatches)
        self.seed = ColourSeedPicker(DEFAULT_CUSTOM_SEED, True, self)
        self.seed.seed_chosen.connect(self._on_seed)
        theme_row.addWidget(self.seed)
        self.light = QCheckBox("Light", self)
        self.light.setToolTip("Light version of the one-colour theme")
        self.light.toggled.connect(self._on_light)
        theme_row.addWidget(self.light)
        root.addLayout(theme_row)

        self.bg_opacity = LabeledSlider("Background", 0.0, 1.0, WINDOW.bg_opacity_default, self)
        self.bg_opacity.value_changed.connect(
            lambda v: controller.set_style(window_id, bg_opacity=v)
        )
        root.addWidget(self.bg_opacity)
        self.window_opacity = LabeledSlider(
            "Whole window", WINDOW.window_opacity_min, 1.0, WINDOW.window_opacity_default, self
        )
        self.window_opacity.value_changed.connect(
            lambda v: controller.set_style(window_id, window_opacity=v)
        )
        root.addWidget(self.window_opacity)

        root.addWidget(self._heading("Text"))
        text_grid = QGridLayout()
        text_grid.setHorizontalSpacing(SPACE.sm)
        self.font_box = FontPicker(FONTS.overlay_family, parent=self)
        self.font_box.font_changed.connect(self._on_font)
        self.font_size = QSpinBox(self)
        self.font_size.setRange(FONTS.overlay_size_min, FONTS.overlay_size_max)
        self.font_size.setSuffix(" pt")
        self.font_size.valueChanged.connect(lambda v: controller.set_style(window_id, font_size=v))
        text_grid.addWidget(self.font_box, 0, 0)
        text_grid.addWidget(self.font_size, 0, 1)
        self.outline = QCheckBox("Outline", self)
        self.outline.toggled.connect(lambda on: controller.set_style(window_id, outline=on))
        self.outline_width = QSpinBox(self)
        self.outline_width.setRange(1, OVERLAY.outline_width_max)
        self.outline_width.setSuffix(" px")
        self.outline_width.valueChanged.connect(
            lambda v: controller.set_style(window_id, outline_width=v)
        )
        text_grid.addWidget(self.outline, 1, 0)
        text_grid.addWidget(self.outline_width, 1, 1)
        self.shadow = QCheckBox("Shadow", self)
        self.shadow.toggled.connect(lambda on: controller.set_style(window_id, shadow=on))
        text_grid.addWidget(self.shadow, 2, 0)
        self.both = QCheckBox("Show original text too", self)
        self.both.toggled.connect(
            lambda on: controller.set_display(
                window_id, DisplayMode.BOTH if on else DisplayMode.TRANSLATION
            )
        )
        text_grid.addWidget(self.both, 3, 0, 1, 2)
        self.languages = QCheckBox("Show languages (e.g. ZH→EN)", self)
        self.languages.toggled.connect(
            lambda on: controller.set_style(window_id, show_languages=on)
        )
        text_grid.addWidget(self.languages, 4, 0, 1, 2)
        root.addLayout(text_grid)

        root.addWidget(self._heading("Show lines from"))
        sources_row = QHBoxLayout()
        self.sources: dict[Source, QCheckBox] = {}
        for source, label in SOURCE_LABELS:
            box = QCheckBox(label, self)
            box.toggled.connect(self._on_sources)
            sources_row.addWidget(box)
            self.sources[source] = box
        sources_row.addStretch(1)
        root.addLayout(sources_row)

        root.addWidget(self._heading("Window"))
        self.locked = QCheckBox("Lock position and size", self)
        self.locked.toggled.connect(lambda on: controller.set_locked(window_id, on))
        root.addWidget(self.locked)
        self.click_through = QCheckBox("Click-through", self)
        self.click_through.toggled.connect(self._on_click_through)
        root.addWidget(self.click_through)

        controller.store.window_changed.connect(self._on_window_changed)
        self.refresh()

    def _heading(self, text: str) -> QLabel:
        label = QLabel(text, self)
        font = label.font()
        font.setWeight(QFont.Weight.DemiBold)
        label.setFont(font)
        return label

    # ------------------------------------------------------------ store -> controls

    def _config(self) -> WindowConfig | None:
        return self._controller.store.state.config.window(self._window_id)

    def _on_window_changed(self, window_id: str) -> None:
        if window_id == self._window_id:
            self.refresh()

    def refresh(self) -> None:
        cfg = self._config()
        if cfg is None:
            self.close()
            return
        style = cfg.style
        palette = palette_for(style.palette_id, style.custom_seed, style.custom_dark)
        if palette != self._palette:
            self._palette = palette
            self.setStyleSheet(window_qss(palette))
            self.swatches.set_ring_color(palette.accent)
            self.font_box.apply_palette(palette)
            self.update()
        widgets = (
            self.light,
            self.font_box,
            self.font_size,
            self.outline,
            self.outline_width,
            self.shadow,
            self.both,
            self.languages,
            self.locked,
            self.click_through,
            *self.sources.values(),
        )
        for w in widgets:
            w.blockSignals(True)
        self.swatches.set_current(palette.id if style.custom_seed is None else "")
        if style.custom_seed:
            self.seed.set_seed(style.custom_seed, style.custom_dark)
        self.light.setChecked(not style.custom_dark)
        self.light.setEnabled(style.custom_seed is not None)
        self.bg_opacity.set_value(style.bg_opacity)
        self.window_opacity.set_value(style.window_opacity)
        self.font_box.set_family(style.font_family or FONTS.overlay_family)
        self.font_size.setValue(style.font_size)
        self.outline.setChecked(style.outline)
        self.outline_width.setValue(style.outline_width or default_outline_width(palette))
        self.outline_width.setEnabled(style.outline)
        self.shadow.setChecked(style.shadow)
        self.both.setChecked(cfg.display is DisplayMode.BOTH)
        self.languages.setChecked(style.show_languages)
        for source, box in self.sources.items():
            box.setChecked(source in cfg.sources)
        self.locked.setChecked(cfg.locked)
        combo = self._controller.store.state.config.hotkeys.get("click_through_all")
        self.click_through.setText(
            f"Click-through ({combo} turns it off)" if combo else "Click-through (no shortcut set)"
        )
        self.click_through.setChecked(cfg.click_through)
        for w in widgets:
            w.blockSignals(False)

    # ------------------------------------------------------------ controls -> controller

    def _on_seed(self, seed: str) -> None:
        self._controller.set_custom_palette(self._window_id, seed, not self.light.isChecked())

    def _on_light(self, light: bool) -> None:
        cfg = self._config()
        if cfg is not None and cfg.style.custom_seed:
            self._controller.set_custom_palette(self._window_id, cfg.style.custom_seed, not light)

    def _on_font(self, family: str) -> None:
        self._controller.set_style(
            self._window_id, font_family=None if family == FONTS.overlay_family else family
        )

    def _on_sources(self, _checked: bool) -> None:
        chosen = [s for s, box in self.sources.items() if box.isChecked()]
        if not chosen:  # a window must show something; undo the last untick
            self.refresh()
            return
        self._controller.set_sources(self._window_id, chosen)

    def _on_click_through(self, on: bool) -> None:
        self._controller.set_click_through(self._window_id, on)
        if on:
            self.close()  # the window is about to stop receiving the mouse

    def paintEvent(self, event: QPaintEvent) -> None:
        p = self._palette
        if p is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor(p.border))
        painter.setBrush(QColor(p.surface))
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), RADIUS.md, RADIUS.md)
        painter.end()
