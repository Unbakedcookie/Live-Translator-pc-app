"""T022 — widget kit behaviour (pytest-qt). Visual look is reviewed via the gallery (G1)."""

from PySide6.QtCore import QPoint, QSize, Qt

from livetranslator.core.languages import DEFAULT_LANGUAGES, language
from livetranslator.theme.palette_gen import generate_palette
from livetranslator.theme.tokens import MIDNIGHT, PALETTES, PAPER
from livetranslator.ui.gallery import Gallery
from livetranslator.ui.widgets.colour_seed_picker import ColourSeedPicker
from livetranslator.ui.widgets.icon_button import IconButton
from livetranslator.ui.widgets.language_picker import LanguagePicker
from livetranslator.ui.widgets.pin_button import PinButton
from livetranslator.ui.widgets.slider import LabeledSlider
from livetranslator.ui.widgets.swatch import SwatchRow
from livetranslator.ui.widgets.toast import Toast


def centre_colour(button) -> str:
    image = button.icon().pixmap(QSize(32, 32)).toImage()
    # sample the densest pixel row through the middle: any opaque pixel's colour
    for x in range(32):
        for y in range(32):
            c = image.pixelColor(x, y)
            if c.alpha() == 255:
                return c.name().upper()
    return ""


def test_pin_button_toggles_icon_colour_and_tooltip(qtbot):
    pin = PinButton(MIDNIGHT)
    qtbot.addWidget(pin)
    seen: list[bool] = []
    pin.toggled.connect(seen.append)
    assert centre_colour(pin) == MIDNIGHT.text_secondary
    qtbot.mouseClick(pin, Qt.MouseButton.LeftButton)
    assert seen == [True]
    assert centre_colour(pin) == MIDNIGHT.accent
    assert "unpin" in pin.toolTip()


def test_icon_button_recolours_with_palette(qtbot):
    button = IconButton("gear", "Settings", MIDNIGHT)
    qtbot.addWidget(button)
    button.apply_palette(PAPER)
    assert centre_colour(button) == PAPER.text_secondary


def test_slider_emits_fraction_and_set_value_is_silent(qtbot):
    slider = LabeledSlider("Background", 0.0, 1.0, 0.7)
    qtbot.addWidget(slider)
    values: list[float] = []
    slider.value_changed.connect(values.append)
    assert slider.value() == 0.7
    assert slider._value_label.text() == "70 %"
    slider.set_value(0.25)
    assert values == []
    assert slider._value_label.text() == "25 %"
    slider._slider.setValue(40)
    assert values == [0.4]


def test_swatch_row_selects_palette(qtbot):
    row = SwatchRow("midnight")
    qtbot.addWidget(row)
    picked: list[str] = []
    row.palette_selected.connect(picked.append)
    assert list(row.swatches) == list(PALETTES)
    assert row.swatches["midnight"].isChecked()
    qtbot.mouseClick(row.swatches["neon"], Qt.MouseButton.LeftButton)
    assert picked == ["neon"]
    assert row.swatches["neon"].isChecked() and not row.swatches["midnight"].isChecked()
    row.set_current("custom_3B82F6_dark")
    assert not any(s.isChecked() for s in row.swatches.values())


def test_language_picker(qtbot):
    picker = LanguagePicker("ja")
    qtbot.addWidget(picker)
    assert picker.count() == len(DEFAULT_LANGUAGES) == 15
    assert picker.current_code() == "ja"
    assert picker.currentText() == "Japanese · 日本語"
    chosen: list[str] = []
    picker.language_changed.connect(chosen.append)
    picker.set_language("ko")
    assert chosen == []
    picker.activated.emit(picker.findData("es"))
    assert chosen == ["es"]
    picker.set_language("sw")  # not in the defaults: added on the fly
    assert picker.current_code() == "sw"
    assert language("sw").label == "SW"


def test_colour_seed_picker_shows_generated_palette(qtbot):
    picker = ColourSeedPicker("#3b82f6", dark=True)
    qtbot.addWidget(picker)
    assert picker.seed == "#3B82F6"
    assert picker.palette_value == generate_palette("#3B82F6", dark=True)
    picker.set_seed("#EF4444", dark=False)
    assert picker.palette_value.id == "custom_EF4444_light"


def test_toast_closes_itself(qtbot):
    toast = Toast("Click-through on. Press Ctrl+Alt+T to turn it off.", MIDNIGHT, duration_ms=50)
    with qtbot.waitSignal(toast.destroyed, timeout=2000):  # WA_DeleteOnClose after closing
        toast.show_at(QPoint(400, 400))
        assert toast.isVisible()


def test_gallery_builds_one_panel_per_palette(qtbot):
    gallery = Gallery()
    qtbot.addWidget(gallery)
    assert len(gallery.panels) == 5


def test_language_popup_is_wide_enough_for_long_names(qtbot):
    picker = LanguagePicker("pt")
    qtbot.addWidget(picker)
    picker.resize(120, 24)  # narrow, like in the chrome strip
    picker.show()
    picker.showPopup()
    view = picker.view()
    assert view.width() >= view.sizeHintForColumn(0)
    assert view.window().testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    picker.hidePopup()
