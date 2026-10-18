"""T024 — the composed app starts, makes a default window, saves, and reloads (pytest-qt)."""

import json
import sys
from pathlib import Path

import pytest

from livetranslator.app.application import ALL_HOTKEY_ACTIONS, LiveTranslatorApp
from livetranslator.app.paths import app_paths
from livetranslator.app.window_controller import HOTKEY_ACTIONS

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="real desktop windows + hotkeys")


def start(home: Path) -> tuple[LiveTranslatorApp, list[int]]:
    quits: list[int] = []
    return LiveTranslatorApp(app_paths(home), lambda: quits.append(1)), quits


def test_first_start_creates_one_window_and_saves(qtbot, tmp_path: Path):
    live, _ = start(tmp_path)
    try:
        windows = live.store.state.config.windows
        assert len(windows) == 1
        assert windows[0].target_lang == "en"
        assert live.windows.windows[windows[0].id].isVisible()
        registered = set(live.hotkeys.registered)
        warned = {k.removeprefix("hotkey.") for k in live.store.state.runtime.statuses}
        bound = {x for x in ALL_HOTKEY_ACTIONS if x in live.store.state.config.hotkeys}
        assert bound == set(HOTKEY_ACTIONS) - {"new_window", "lock_all"}  # T072: start unbound
        assert registered | warned == bound  # each one bound, or reported
    finally:
        live.shutdown()
    saved = json.loads((tmp_path / "config" / "settings.json").read_text(encoding="utf-8"))
    assert [w["id"] for w in saved["windows"]] == [windows[0].id]
    assert saved["windows"][0]["geometry"] is not None


def test_second_start_restores_the_same_window(qtbot, tmp_path: Path):
    first, _ = start(tmp_path)
    window_id = first.store.state.config.windows[0].id
    first.controller.set_style(window_id, palette_id="neon", bg_opacity=0.4)
    first.shutdown()

    second, _ = start(tmp_path)
    try:
        windows = second.store.state.config.windows
        assert [w.id for w in windows] == [window_id]
        assert (windows[0].style.palette_id, windows[0].style.bg_opacity) == ("neon", 0.4)
    finally:
        second.shutdown()


def test_damaged_settings_show_a_notice(qtbot, tmp_path: Path):
    settings = tmp_path / "config" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text("{oops", encoding="utf-8")
    live, _ = start(tmp_path)
    try:
        status = live.store.state.runtime.statuses["settings.load"]
        assert "damaged" in status.message
        assert len(list(settings.parent.glob("settings.corrupt-*.json"))) == 1
    finally:
        live.shutdown()


def test_partial_translation_follows_game_mode():
    from livetranslator.app.application import partials_allowed
    from livetranslator.core.state import AppConfig, PerformanceConfig

    assert partials_allowed(AppConfig())
    assert not partials_allowed(AppConfig(performance=PerformanceConfig(game_mode=True)))


def test_closing_the_last_window_keeps_the_app_in_the_tray(qtbot, tmp_path: Path, monkeypatch):
    live, quits = start(tmp_path)
    try:
        assert live.tray is not None and live.tray.icon.isVisible()
        notes: list[str] = []
        monkeypatch.setattr(live.tray, "notify", notes.append)
        live.controller.remove_window(live.store.state.config.windows[0].id)
        assert quits == [] and len(notes) == 1
        live.tray.actions["new_window"].trigger()
        assert len(live.windows.windows) == 1
    finally:
        live.shutdown()
    assert not live.tray.icon.isVisible()


def test_settings_change_persists_after_restart(qtbot, tmp_path: Path):
    first, _ = start(tmp_path)
    try:
        first.open_settings("Performance")
        window = first.settings_window
        assert window is not None and window.isVisible()
        assert window.stack.currentWidget() is window.pages["Performance"]
        window.pages["General"].language.language_changed.emit("ko")  # type: ignore[attr-defined]
        window.hide()
        first._on_hotkey("open_settings")
        assert window.isVisible()
        assert first.tray is not None and "settings" in first.tray.actions
    finally:
        first.shutdown()
    second, _ = start(tmp_path)
    try:
        assert second.store.state.config.my_language == "ko"
    finally:
        second.shutdown()


def test_every_quit_path_asks_about_a_non_empty_conversation(qtbot, tmp_path: Path, monkeypatch):
    from livetranslator.core import actions as a
    from livetranslator.core.state import Source, Utterance
    from livetranslator.ui.dialogs import QuitChoice

    live, quits = start(tmp_path)
    try:
        answers = [QuitChoice.CANCEL, QuitChoice.DISCARD]
        asked: list[int] = []

        def ask(_parent: object) -> QuitChoice:
            asked.append(1)
            return answers.pop(0)

        monkeypatch.setattr(live.quit_flow, "_ask_quit", ask)
        assert live.tray is not None
        live.tray.actions["quit"].trigger()  # empty log: quits at once, no question
        assert quits == [1] and asked == []
        live.store.dispatch(
            a.AddUtterance(
                Utterance(id="u1", source=Source.ME, speaker_id="me", start=0.0, committed="hi")
            )
        )
        live.tray.actions["quit"].trigger()  # Cancel
        assert quits == [1] and asked == [1]
        window = next(iter(live.windows.windows.values()))
        window.quit_requested.emit()  # overlay menu "Quit": Close without saving
        assert quits == [1, 1] and asked == [1, 1]
        assert "transcript" in live.tray.actions
    finally:
        live.shutdown()


def test_quit_hides_settings_and_transcript_first(qtbot, tmp_path: Path):
    """Tier B found Quit doing nothing while the transcript was open: Qt 6 cancels a quit
    when a visible window refuses to close, and these two only hide."""
    seen: list[tuple[bool, bool]] = []
    live = LiveTranslatorApp(app_paths(tmp_path), lambda: None)
    live._quit_app = lambda: seen.append(
        (live.settings_window.isVisible(), live.transcript_window.isVisible())  # type: ignore[union-attr]
    )
    try:
        live.open_settings()
        live.open_transcript()
        assert live.request_quit()  # empty conversation: straight to quit
        assert seen == [(False, False)]
    finally:
        live.shutdown()
