"""Custom colours (user request 2026-10-19): labelled slots + a picker, on top of a theme."""

import sys

import pytest
from pydantic import ValidationError
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from livetranslator.app.window_controller import WindowController
from livetranslator.core.state import AppConfig, AppState, Geometry, WindowConfig, WindowStyle
from livetranslator.core.store import Store
from livetranslator.theme.contrast import hard_to_read
from livetranslator.theme.palette_gen import palette_for, with_colors
from livetranslator.theme.tokens import MIDNIGHT, PAPER, color_names, color_tokens
from livetranslator.ui.custom_colours import SLOT_LABELS
from livetranslator.ui.floating_window import FloatingWindow

START = Geometry(x=2000, y=600, width=520, height=220, screen="Odyssey G95C")


def test_every_colour_has_a_labelled_slot():
    names = color_names()
    assert len(names) == 13 + 8  # 13 single colours + 8 people
    assert set(SLOT_LABELS) == set(names) == set(color_tokens(MIDNIGHT))


def test_colours_go_on_top_of_the_theme():
    assert with_colors(MIDNIGHT, ()) is MIDNIGHT
    edited = with_colors(MIDNIGHT, (("bg", "#FFFFFF"), ("speaker_others_3", "#123456")))
    assert edited.bg == "#FFFFFF" and not edited.is_dark  # white background: a light theme
    assert edited.speaker_others[2] == "#123456"
    assert edited.speaker_others[0] == MIDNIGHT.speaker_others[0]
    assert edited.text_primary == MIDNIGHT.text_primary
    assert edited.id == "midnight_edited"
    darker = with_colors(PAPER, (("bg", "#101010"),))
    assert darker.is_dark
    assert palette_for("paper", None, True, (("accent", "#FF0000"),)).accent == "#FF0000"


def test_saved_colours_are_checked():
    style = WindowStyle(custom_colors=(("speaker_me", "#abcdef"), ("bg", "#000000")))
    assert style.custom_colors == (("bg", "#000000"), ("speaker_me", "#ABCDEF"))  # slot order
    for bad in ((("nope", "#000000"),), (("bg", "red"),), (("bg", "#000000"), ("bg", "#111111"))):
        with pytest.raises(ValidationError):
            WindowStyle(custom_colors=bad)


def test_hard_to_read_names_the_colours():
    assert hard_to_read(MIDNIGHT) == []
    same = with_colors(MIDNIGHT, (("text_primary", MIDNIGHT.bg),))
    assert hard_to_read(same) == ["text_primary"]


def test_controller_merges_and_clears():
    store = Store(AppState(config=AppConfig(windows=(WindowConfig(id="w1"),))))
    controller = WindowController(store)

    def colors():
        found = store.state.config.window("w1")
        assert found is not None
        return found.style.custom_colors

    controller.set_custom_color("w1", "accent", "#ff0000")
    controller.set_custom_color("w1", "bg", "#000000")
    controller.set_custom_color("w1", "accent", "#00ff00")
    assert colors() == (("bg", "#000000"), ("accent", "#00FF00"))
    controller.reset_custom_colors("w1")
    assert colors() == ()
    controller.set_custom_color("w1", "bg", "#000000")
    controller.set_builtin_palette("w1", "paper")  # a new theme starts clean
    assert colors() == ()
    controller.set_custom_color("w1", "bg", "#000000")
    controller.set_custom_palette("w1", "#3B82F6", True)
    assert colors() == ()


@pytest.mark.skipif(sys.platform != "win32", reason="native window flags")
def test_editor_slots_and_picker_change_the_window(qtbot):
    store = Store(AppState(config=AppConfig(windows=(WindowConfig(id="w1", geometry=START),))))
    controller = WindowController(store)
    window = FloatingWindow(controller, "w1", lambda _wid: [])
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)

    window.open_style_popover()
    popover = window.popover
    assert popover is not None
    qtbot.mouseClick(popover.custom, Qt.MouseButton.LeftButton)
    editor = window.colour_editor
    assert editor is not None and editor.isVisible() and not popover.isVisible()
    assert editor.selected == "bg"
    assert editor.picker.currentColor().name().upper() == MIDNIGHT.bg

    qtbot.mouseClick(editor.slots["text_primary"], Qt.MouseButton.LeftButton)
    assert editor.selected == "text_primary"
    assert editor.picker.currentColor().name().upper() == MIDNIGHT.text_primary
    editor.picker.setCurrentColor(QColor("#FFD0D0"))
    qtbot.waitUntil(lambda: window.palette_value.text_primary == "#FFD0D0", timeout=2000)
    assert editor.slots["text_primary"].color == "#FFD0D0"
    assert editor.undo.isEnabled() and not editor.warning.isVisible()
    assert popover.swatches.swatches["midnight"].isChecked() is False  # customised

    # Picking the background's own colour for the text: warned, by slot name.
    editor.picker.setCurrentColor(QColor(MIDNIGHT.bg))
    qtbot.waitUntil(lambda: editor.warning.isVisible(), timeout=2000)
    assert "Text" in editor.warning.text()

    editor.undo.click()
    assert window.palette_value == MIDNIGHT and not editor.undo.isEnabled()

    editor.theme.choice_changed.emit("paper")
    assert window.palette_value == PAPER

    editor.picker.setCurrentColor(QColor("#22AA55"))
    editor.whole.click()
    found = store.state.config.window("w1")
    assert found is not None and found.style.custom_seed == "#22AA55"
    assert found.style.custom_colors == ()
    editor.close()
    assert not editor.isVisible()
