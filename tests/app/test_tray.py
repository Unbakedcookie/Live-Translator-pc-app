"""T071 — tray menu items act through the controller; checkmarks and icon follow the store."""

import pytest
from PySide6.QtWidgets import QSystemTrayIcon

from livetranslator.app.tray import Tray, tray_status
from livetranslator.app.window_controller import WindowController
from livetranslator.core import actions as a
from livetranslator.core.state import AppConfig, AppState, StatusLevel, WindowConfig
from livetranslator.core.store import Store


def make_state(**audio: bool) -> AppState:
    state = AppState(config=AppConfig(windows=(WindowConfig(id="a"),)))
    if audio:
        config = state.config.model_copy(
            update={"audio": state.config.audio.model_copy(update=audio)}
        )
        state = state.model_copy(update={"config": config})
    return state


def test_tray_status_roles_and_tooltips():
    assert tray_status(make_state()) == ("accent", "Live Translator: listening")
    paused = make_state(mic_enabled=False, others_enabled=False)
    assert tray_status(paused) == ("text_secondary", "Live Translator: paused (both muted)")
    one_muted = make_state(mic_enabled=False)
    assert tray_status(one_muted)[0] == "accent"


def test_tray_status_error_wins_and_hidden_is_mentioned():
    store = Store(make_state(mic_enabled=False, others_enabled=False))
    store.dispatch(a.SetStatus("asr", StatusLevel.WARNING, "slow"))
    assert tray_status(store.state)[0] == "text_secondary"  # a warning isn't an error
    store.dispatch(a.SetStatus("asr", StatusLevel.ERROR, "Speech model failed to load."))
    assert tray_status(store.state) == ("danger", "Live Translator: Speech model failed to load.")
    hidden = Store(make_state())
    hidden.dispatch(a.SetAllHidden(True))
    assert tray_status(hidden.state) == ("accent", "Live Translator: listening, windows hidden")


@pytest.fixture
def env(qtbot):
    store = Store(make_state())
    quits: list[int] = []
    settings: list[int] = []
    tray = Tray(WindowController(store), lambda: quits.append(1), lambda: settings.append(1))
    yield store, tray, quits, settings
    tray.hide()


def test_every_item_acts_on_the_store(env):
    store, tray, quits, settings = env
    tray.actions["mute_me"].trigger()
    assert not store.state.config.audio.mic_enabled
    tray.actions["mute_others"].trigger()
    assert not store.state.config.audio.others_enabled
    tray.actions["game_mode"].trigger()
    assert store.state.config.performance.game_mode
    tray.actions["click_through_all"].trigger()
    assert all(w.click_through for w in store.state.config.windows)
    tray.actions["show_hide_all"].trigger()
    assert store.state.runtime.all_hidden
    tray.actions["new_window"].trigger()
    assert len(store.state.config.windows) == 2
    tray.actions["settings"].trigger()
    tray.actions["quit"].trigger()
    assert settings == [1] and quits == [1]


def test_menu_order_matches_the_spec(env):
    _, tray, _, _ = env
    texts = [x.text() for x in tray.menu.actions() if not x.isSeparator()]
    assert texts == [
        "Show/Hide all",
        "New window",
        "Mute Me",
        "Mute Others",
        "Game mode",
        "Click-through",
        "Settings…",
        "Quit",
    ]


def test_checkmarks_follow_the_store(env):
    store, tray, _, _ = env
    assert not any(tray.actions[k].isChecked() for k in ("mute_me", "game_mode"))
    store.dispatch(a.UpdateConfigSection("audio", {"mic_enabled": False}))
    store.dispatch(a.UpdateConfigSection("performance", {"game_mode": True}))
    store.dispatch(a.UpdateAllWindows({"click_through": True}))
    assert tray.actions["mute_me"].isChecked()
    assert not tray.actions["mute_others"].isChecked()
    assert tray.actions["game_mode"].isChecked()
    assert tray.actions["click_through_all"].isChecked()


def test_icon_role_and_tooltip_follow_status(env):
    store, tray, _, _ = env
    assert tray.icon_role == "accent"
    store.dispatch(a.SetStatus("asr", StatusLevel.ERROR, "No speech model."))
    assert tray.icon_role == "danger"
    assert tray.icon.toolTip() == "Live Translator: No speech model."
    store.dispatch(a.ClearStatus("asr"))
    assert tray.icon_role == "accent"


def test_double_click_toggles_show_hide(env):
    store, tray, _, _ = env
    tray.icon.activated.emit(QSystemTrayIcon.ActivationReason.DoubleClick)
    assert store.state.runtime.all_hidden
    tray.icon.activated.emit(QSystemTrayIcon.ActivationReason.Trigger)  # single click: nothing
    assert store.state.runtime.all_hidden
    tray.icon.activated.emit(QSystemTrayIcon.ActivationReason.DoubleClick)
    assert not store.state.runtime.all_hidden


def test_no_settings_item_without_a_settings_window(qtbot):
    tray = Tray(WindowController(Store(make_state())), lambda: None)
    assert "settings" not in tray.actions
    tray.hide()
