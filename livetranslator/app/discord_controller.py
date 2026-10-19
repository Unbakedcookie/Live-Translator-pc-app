"""Discord names for speaker labels (T103/T104; spec §5.13; D-013, D-030).

Runs the RPC client when the user has set up their own Discord app (Application ID in the
settings, client secret DPAPI-encrypted next to them) and the speaker mode allows Discord.

- Channel members' display names become the labels of "discord:<id>" speakers (as session
  renames) — unless the user renamed that speaker themselves.
- Every few seconds the Discord-vs-audio lag is re-estimated from SPEAKING_START times and the
  starts of "Others" lines (calibration.py, D-025) so fusion lines them up.
- Disconnect stops the client and deletes the token and the secret.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from livetranslator.core import actions as a
from livetranslator.core.state import Source, SpeakerMode, StatusLevel
from livetranslator.core.store import Store
from livetranslator.services.speakers.calibration import calibrate_lag
from livetranslator.services.speakers.discord_rpc import (
    DiscordCallbacks,
    DiscordClient,
    RpcError,
    SpeakingTimeline,
    exchange_code,
    refresh_token,
)
from livetranslator.services.speakers.token_store import TokenStore

STATUS_KEY = "discord"
CALIBRATE_MS = 5000
TOKEN_FILE = "discord-token.bin"  # nosec B105 - a file name, not a secret
SECRET_FILE = "discord-secret.bin"  # nosec B105 - a file name, not a secret

ClientFactory = Callable[[str, str], DiscordClient]  # (app id, secret) -> client


class DiscordController(QObject):
    _check_passed = Signal()  # from the test thread; restarts the background client

    def __init__(
        self,
        store: Store,
        config_dir: Path,
        timeline: SpeakingTimeline | None = None,
        make_client: ClientFactory | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._store = store
        self.timeline = timeline or SpeakingTimeline()
        self.tokens = TokenStore(config_dir / TOKEN_FILE)
        self.secrets = TokenStore(config_dir / SECRET_FILE)
        self._make_client = make_client or self._default_client
        self.client: DiscordClient | None = None
        self._running_for: tuple[str, str] | None = None
        self._our_names: dict[str, str] = {}  # speaker id -> the Discord name we set
        self._timer = QTimer(self)
        self._timer.setInterval(CALIBRATE_MS)
        self._timer.timeout.connect(self.calibrate)
        store.config_changed.connect(
            lambda section: self.apply() if section in ("speakers", "all") else None
        )
        self._check_passed.connect(self.restart)

    # ------------------------------------------------------------ setup (Settings / guide)

    @property
    def app_id(self) -> str | None:
        return self._store.state.config.speakers.discord_app_id

    def secret(self) -> str:
        values = self.secrets.load() or {}
        return str(values.get("secret") or "")

    def save_setup(self, app_id: str, secret: str) -> None:
        self.secrets.save({"secret": secret.strip()})
        self._store.dispatch(
            a.UpdateConfigSection("speakers", {"discord_app_id": app_id.strip() or None})
        )

    def disconnect(self) -> None:
        self._stop()
        self.tokens.delete()
        self.secrets.delete()
        self._store.dispatch(a.UpdateConfigSection("speakers", {"discord_app_id": None}))
        self._store.dispatch(a.ClearStatus(STATUS_KEY))

    def check(self, app_id: str, secret: str, done: Callable[[bool, str], None]) -> None:
        """ "Test connection" on a background thread; `done(ok, message)` from that thread."""

        def run() -> None:
            try:
                message = self._make_client(app_id.strip(), secret.strip()).check()
            except RpcError as exc:
                done(False, str(exc))
            except Exception as exc:  # report, never crash the guide
                done(False, f"Couldn't connect ({type(exc).__name__}).")
            else:
                done(True, message)
                self._check_passed.emit()  # signed in now: the background client can run

        threading.Thread(target=run, name="discord-check", daemon=True).start()

    # ------------------------------------------------------------ running

    def wanted(self) -> tuple[str, str] | None:
        speakers = self._store.state.config.speakers
        if speakers.mode in (SpeakerMode.OFF, SpeakerMode.VOICE) or not speakers.discord_app_id:
            return None
        secret = self.secret()
        return (speakers.discord_app_id, secret) if secret else None

    def apply(self) -> None:
        wanted = self.wanted()
        if wanted == self._running_for:
            return
        self._stop()
        if wanted is None:
            return
        self.client = self._make_client(*wanted)
        self.client.start()
        self._running_for = wanted
        self._timer.start()

    def restart(self) -> None:
        """Start again from scratch (e.g. after Test connection signed in, or after the
        background client gave up because it had no sign-in)."""
        self._stop()
        self.apply()

    def _stop(self) -> None:
        self._timer.stop()
        if self.client is not None:
            self.client.stop()
            self.client = None
        self._running_for = None
        self.timeline.clear()

    def stop(self) -> None:
        self._stop()

    def _default_client(self, app_id: str, secret: str) -> DiscordClient:
        return DiscordClient(
            client_id=app_id,
            timeline=self.timeline,
            tokens=self.tokens,
            exchange=lambda code: exchange_code(app_id, secret, code),
            refresh=lambda token: refresh_token(app_id, secret, token),
            callbacks=DiscordCallbacks(status=self._status, members=self.on_members),
        )

    # ------------------------------------------------------------ callbacks (any thread)

    def _status(self, level: StatusLevel, message: str) -> None:
        self._store.dispatch(a.SetStatus(STATUS_KEY, level, message))

    def on_members(self, names: dict[str, str]) -> None:
        current = self._store.state.session.speaker_names
        for user_id, name in names.items():
            speaker = f"discord:{user_id}"
            ours = self._our_names.get(speaker)
            if speaker in current and current[speaker] != ours:
                continue  # the user renamed this speaker: keep their name
            self._our_names[speaker] = name
            self._store.dispatch(a.RenameSpeaker(speaker, name))

    def calibrate(self) -> None:
        onsets = [
            u.start for u in self._store.state.session.utterances if u.source is Source.OTHERS
        ]
        lag = calibrate_lag(list(self.timeline.starts), onsets)
        if lag is not None:
            self.timeline.lag = lag
