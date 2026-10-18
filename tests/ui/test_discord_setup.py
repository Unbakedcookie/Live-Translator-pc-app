"""T104 — the Discord setup guide window."""

import sys
from pathlib import Path

import pytest

from livetranslator.app.discord_controller import DiscordController
from livetranslator.core.state import AppState
from livetranslator.core.store import Store
from livetranslator.services.speakers.discord_rpc import REDIRECT_URI, SpeakingTimeline
from livetranslator.theme.tokens import DEFAULT_PALETTE_ID, PALETTES
from livetranslator.ui.discord_setup import STEPS, DiscordSetup

FAKE_ID = "1" * 18  # made-up Discord application IDs
OTHER_ID = "4" * 18

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="DPAPI")


class OkClient:
    def __init__(self, app_id: str, secret: str) -> None:
        self.app_id = app_id

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def check(self) -> str:
        return f"Connected as app {self.app_id}."


@pytest.fixture
def env(qtbot, tmp_path: Path):
    store = Store(AppState())
    ctl = DiscordController(store, tmp_path, SpeakingTimeline(), OkClient)  # type: ignore[arg-type]
    window = DiscordSetup(ctl, PALETTES[DEFAULT_PALETTE_ID])
    qtbot.addWidget(window)
    return store, ctl, window


def test_steps_mention_the_redirect_and_the_tester_fallback():
    assert len(STEPS) == 7
    assert any(REDIRECT_URI in s for s in STEPS)
    assert "App Testers" in STEPS[-1]


def test_buttons_need_a_numeric_id_and_a_secret(env):
    _, _, window = env
    assert not window.test.isEnabled() and not window.save.isEnabled()
    window.app_id.setText("not a number")
    window.secret.setText("s")
    assert not window.save.isEnabled()
    window.app_id.setText("1234567890")  # too short for a Discord ID
    assert not window.save.isEnabled()
    window.app_id.setText(FAKE_ID)
    assert window.save.isEnabled() and window.test.isEnabled()


def test_test_save_and_disconnect(env, qtbot):
    store, ctl, window = env
    window.app_id.setText(FAKE_ID)
    window.secret.setText("secret")
    window.test.click()
    qtbot.waitUntil(lambda: window.result.text().startswith("Connected"), timeout=2000)
    assert window.result.text() == f"Connected as app {FAKE_ID}."
    window.save.click()
    assert store.state.config.speakers.discord_app_id == FAKE_ID
    assert ctl.secret() == "secret" and window.remove.isEnabled()
    window.remove.click()
    assert store.state.config.speakers.discord_app_id is None and ctl.secret() == ""
    assert window.app_id.text() == "" and "deleted" in window.result.text()


def test_reopening_shows_the_saved_setup(env, qtbot):
    _, ctl, _ = env
    ctl.save_setup(OTHER_ID, "abc")
    again = DiscordSetup(ctl, PALETTES[DEFAULT_PALETTE_ID])
    qtbot.addWidget(again)
    assert again.app_id.text() == OTHER_ID and again.secret.text() == "abc"
