"""T024 — window intents and hotkey toggles -> store (Tier A)."""

import pytest

from livetranslator.app.window_controller import HOTKEY_ACTIONS, WindowController
from livetranslator.core.state import AppConfig, AppState, Geometry, WindowConfig, WindowStyle
from livetranslator.core.store import Store
from livetranslator.ui.geometry import Rect


@pytest.fixture
def controller(qapp) -> WindowController:
    config = AppConfig(
        my_language="es",
        windows=(WindowConfig(id="a"), WindowConfig(id="b", pinned=False, click_through=True)),
    )
    return WindowController(Store(AppState(config=config)))


def windows(c: WindowController) -> tuple[WindowConfig, ...]:
    return c.store.state.config.windows


def test_add_window_uses_my_language(controller: WindowController):
    new_id = controller.add_window()
    assert new_id.startswith("w-") and len(new_id) == 10
    assert windows(controller)[-1] == WindowConfig(id=new_id, target_lang="es")


def test_set_geometry_and_palettes(controller: WindowController):
    controller.set_geometry("a", Rect(10, 20, 600, 240), "Odyssey G95C")
    assert windows(controller)[0].geometry == Geometry(
        x=10, y=20, width=600, height=240, screen="Odyssey G95C"
    )
    controller.set_custom_palette("a", "#EF4444", False)
    assert windows(controller)[0].style == WindowStyle(custom_seed="#EF4444", custom_dark=False)
    controller.set_builtin_palette("a", "neon")
    style = windows(controller)[0].style
    assert (style.palette_id, style.custom_seed) == ("neon", None)


def test_click_through_all_toggles(controller: WindowController):
    # mixed (b on, a off) -> all on; all on -> all off
    controller.handle_hotkey("click_through_all")
    assert [w.click_through for w in windows(controller)] == [True, True]
    controller.handle_hotkey("click_through_all")
    assert [w.click_through for w in windows(controller)] == [False, False]


def test_pin_all_toggles(controller: WindowController):
    controller.handle_hotkey("pin_all")  # mixed -> all pinned
    assert [w.pinned for w in windows(controller)] == [True, True]
    controller.handle_hotkey("pin_all")
    assert [w.pinned for w in windows(controller)] == [False, False]


def test_show_hide_mute_game_mode(controller: WindowController):
    state = controller.store.state
    controller.handle_hotkey("show_hide_all")
    assert controller.store.state.runtime.all_hidden is True
    controller.handle_hotkey("mute_me")
    controller.handle_hotkey("mute_others")
    controller.handle_hotkey("game_mode")
    config = controller.store.state.config
    assert (config.audio.mic_enabled, config.audio.others_enabled) == (False, False)
    assert config.performance.game_mode is True
    assert state.runtime.all_hidden is False  # old state untouched


def test_every_registered_hotkey_action_is_handled(controller: WindowController):
    for action in HOTKEY_ACTIONS:
        controller.handle_hotkey(action)
    with pytest.raises(ValueError, match="unknown hotkey action"):
        controller.handle_hotkey("ocr_region")  # registered only once OCR exists (T083)
