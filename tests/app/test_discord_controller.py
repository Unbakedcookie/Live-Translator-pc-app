"""T103/T104 — Discord names in the app: when it runs, names, renames, lag, disconnect."""

import sys
from pathlib import Path

import pytest

from livetranslator.app.discord_controller import DiscordController
from livetranslator.core import actions as a
from livetranslator.core.state import AppState, Source, SpeakerMode, Utterance
from livetranslator.core.store import Store
from livetranslator.services.speakers.discord_rpc import RpcError, SpeakingTimeline

FAKE = "t"
FAKE_ID = "1" * 18  # a made-up Discord application ID

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="DPAPI")


class FakeClient:
    def __init__(self, app_id: str, secret: str, fail: str = "") -> None:
        self.app_id, self.secret, self.fail = app_id, secret, fail
        self.running = False

    def start(self) -> None:
        self.running = True

    def stop(self) -> None:
        self.running = False

    def check(self) -> str:
        if self.fail:
            raise RpcError(self.fail)
        return "Connected. 3 people in your voice channel."


def make(qtbot, tmp_path: Path, fail: str = ""):
    store = Store(AppState())
    made: list[FakeClient] = []

    def factory(app_id: str, secret: str) -> FakeClient:
        made.append(FakeClient(app_id, secret, fail))
        return made[-1]

    now = [0.0]
    timeline = SpeakingTimeline(clock=lambda: now[0])
    ctl = DiscordController(store, tmp_path, timeline, factory)  # type: ignore[arg-type]
    return store, ctl, made, now


def test_runs_only_when_set_up_and_the_mode_allows(qtbot, tmp_path: Path):
    store, ctl, made, _ = make(qtbot, tmp_path)
    ctl.apply()
    assert made == []  # not set up
    ctl.save_setup(f" {FAKE_ID} ", " s3cret ")  # config change → apply()
    started = [(c.app_id, c.secret, c.running) for c in made]
    assert started == [(FAKE_ID, "s3cret", True)]
    store.dispatch(a.UpdateConfigSection("speakers", {"mode": SpeakerMode.VOICE}))
    assert not made[0].running  # voice-only: Discord off
    store.dispatch(a.UpdateConfigSection("speakers", {"mode": SpeakerMode.AUTO}))
    assert made[-1].running and len(made) == 2
    assert b"s3cret" not in (tmp_path / "discord-secret.bin").read_bytes()


def test_member_names_label_speakers_but_never_override_a_user_rename(qtbot, tmp_path: Path):
    store, ctl, _, _ = make(qtbot, tmp_path)
    ctl.on_members({"1": "Mika", "2": "Kenji"})
    names = store.state.session.speaker_names
    assert names == {"discord:1": "Mika", "discord:2": "Kenji"}
    store.dispatch(a.RenameSpeaker("discord:2", "Ken (tank)"))  # the user's own name
    ctl.on_members({"1": "Mika!", "2": "Kenji"})
    names = store.state.session.speaker_names
    assert names == {"discord:1": "Mika!", "discord:2": "Ken (tank)"}


def test_lag_calibration_from_speaking_starts_and_line_starts(qtbot, tmp_path: Path):
    store, ctl, _, now = make(qtbot, tmp_path)
    for t, uid in ((10.0, "u1"), (20.0, "u2"), (30.0, "u3")):
        now[0] = t
        ctl.timeline.start("1")
        ctl.timeline.stop("1")
        store.dispatch(
            a.AddUtterance(
                Utterance(id=uid, source=Source.OTHERS, speaker_id="others", start=t + 0.3)
            )
        )
    ctl.calibrate()
    assert ctl.timeline.lag == pytest.approx(0.3)


def test_disconnect_deletes_everything(qtbot, tmp_path: Path):
    store, ctl, made, _ = make(qtbot, tmp_path)
    ctl.save_setup(FAKE_ID, "s")
    ctl.tokens.save(dict(access_token=FAKE))
    ctl.disconnect()
    assert not made[0].running
    assert store.state.config.speakers.discord_app_id is None
    assert ctl.secret() == "" and ctl.tokens.load() is None
    assert not (tmp_path / "discord-token.bin").exists()


def test_check_reports_on_a_background_thread(qtbot, tmp_path: Path):
    _, ctl, _, _ = make(qtbot, tmp_path)
    got: list[tuple[bool, str]] = []
    ctl.check(FAKE_ID, "s", lambda ok, msg: got.append((ok, msg)))
    qtbot.waitUntil(lambda: bool(got), timeout=2000)
    assert got == [(True, "Connected. 3 people in your voice channel.")]
    _, bad, _, _ = make(qtbot, tmp_path, fail="Discord isn't running")
    got.clear()
    bad.check(FAKE_ID, "s", lambda ok, msg: got.append((ok, msg)))
    qtbot.waitUntil(lambda: bool(got), timeout=2000)
    assert got == [(False, "Discord isn't running")]
