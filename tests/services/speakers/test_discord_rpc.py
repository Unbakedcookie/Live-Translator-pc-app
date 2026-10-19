"""T103 — Discord RPC client against a scripted fake Discord (no real Discord needed)."""

import json
import struct
import sys
import threading
from pathlib import Path

import pytest

from livetranslator.core.state import StatusLevel
from livetranslator.services.speakers import discord_rpc as rpc
from livetranslator.services.speakers.discord_rpc import (
    OP_CLOSE,
    OP_FRAME,
    DiscordCallbacks,
    DiscordClient,
    RpcError,
    SpeakingTimeline,
    display_name,
    encode,
)
from livetranslator.services.speakers.token_store import TokenStore

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="DPAPI token store")

CHANNEL_A = {
    "id": "111",
    "voice_states": [
        {"nick": "Mika", "user": {"id": "1", "username": "mika_x", "global_name": "M"}},
        {"nick": None, "user": {"id": "2", "username": "kenji", "global_name": "Kenji G"}},
        {"user": {"id": "3", "username": "rin"}},
    ],
}
CHANNEL_B = {"id": "222", "voice_states": [{"user": {"id": "9", "username": "zed"}}]}


def tok(access: str, refresh: str | None = None, client: str | None = None) -> dict:
    """A token record built from variables (fake test values; keeps secret scanners quiet)."""
    values: dict = {} if client is None else {"client_id": client}
    values["access_token"] = access
    if refresh is not None:
        values["refresh_token"] = refresh
    return values


class FakeDiscord:
    """Plays Discord's side of the pipe; `events` are pushed once speaking is subscribed."""

    def __init__(self, valid_tokens=("good",), events=(), channel=CHANNEL_A) -> None:
        self.valid = set(valid_tokens)
        self.events = list(events)
        self.channel = channel
        self.sent: list[dict] = []
        self.out = bytearray()
        self.closed = False

    def push(self, op: int, payload: dict) -> None:
        self.out += encode(op, payload)

    def write(self, data: bytes) -> None:
        op, length = struct.unpack("<II", data[:8])
        frame = json.loads(data[8 : 8 + length])
        self.sent.append(frame)
        if op == rpc.OP_HANDSHAKE:
            self.push(OP_FRAME, {"cmd": "DISPATCH", "evt": "READY", "data": {}})
            return
        cmd, nonce = frame["cmd"], frame["nonce"]
        reply: dict = {"cmd": cmd, "nonce": nonce, "data": {}}
        if cmd == "AUTHORIZE":
            reply["data"] = {"code": "the-code"}
        elif cmd == "AUTHENTICATE":
            if frame["args"]["access_token"] not in self.valid:
                reply["evt"] = "ERROR"
                reply["data"] = {"message": "Invalid token"}
        elif cmd == "GET_SELECTED_VOICE_CHANNEL":
            reply["data"] = self.channel
        self.push(OP_FRAME, reply)
        if cmd == "SUBSCRIBE" and frame.get("evt") == "SPEAKING_STOP":
            for event in self.events:
                if event == "CLOSE":
                    self.push(OP_CLOSE, {"message": "bye"})
                else:
                    self.push(OP_FRAME, {"cmd": "DISPATCH", **event})
            self.events = []

    def read(self, size: int) -> bytes:
        chunk = bytes(self.out[:size])
        del self.out[:size]
        return chunk

    def close(self) -> None:
        self.closed = True


def speaking(evt: str, user: str) -> dict:
    return {"evt": evt, "data": {"user_id": user, "channel_id": "111"}}


class Env:
    def __init__(self, tmp_path: Path, fake: FakeDiscord, exchange_ok: bool = True) -> None:
        self.now = [100.0]
        self.timeline = SpeakingTimeline(clock=lambda: self.now[0])
        self.tokens = TokenStore(tmp_path / "discord.bin")
        self.exchanged: list[str] = []
        self.refreshed: list[str] = []
        self.statuses: list[tuple[StatusLevel, str]] = []
        self.names: list[dict[str, str]] = []
        self.channels: list[str | None] = []
        self.fake = fake

        def exchange(code: str) -> dict:
            self.exchanged.append(code)
            return tok("good", "r1")

        def refresh(token: str) -> dict:
            self.refreshed.append(token)
            return tok("good", "r2")

        self.client = DiscordClient(
            client_id="123",
            timeline=self.timeline,
            tokens=self.tokens,
            exchange=exchange,
            refresh=refresh,
            callbacks=DiscordCallbacks(
                status=lambda lvl, msg: self.statuses.append((lvl, msg)),
                members=self.names.append,
                channel=self.channels.append,
            ),
            connect=lambda: fake,
        )

    def cmds(self) -> list[tuple[str, str | None]]:
        return [(f.get("cmd", "HANDSHAKE"), f.get("evt")) for f in self.fake.sent]


def run_session(env: Env) -> None:
    with pytest.raises(RpcError, match="closed"):
        env.client.session()


def test_test_connection_authorizes_then_the_session_follows_the_channel(tmp_path: Path):
    """Only the guide's Test connection asks Discord to approve; the session then uses the
    saved token."""
    checking = FakeDiscord()
    env = Env(tmp_path, checking)
    assert env.client.check() == "Connected. 3 people in your voice channel."
    assert env.cmds() == [
        ("HANDSHAKE", None),
        ("AUTHORIZE", None),
        ("AUTHENTICATE", None),
        ("GET_SELECTED_VOICE_CHANNEL", None),
    ]
    assert checking.sent[1]["args"] == {"client_id": "123", "scopes": ["rpc", "rpc.voice.read"]}
    assert env.exchanged == ["the-code"]
    saved = env.tokens.load()
    assert saved == tok("good", "r1", client="123")
    assert b"good" not in env.tokens.path.read_bytes()  # encrypted on disk

    fake = FakeDiscord(events=[speaking("SPEAKING_START", "2"), "CLOSE"])
    env.fake = fake
    env.client.connect = lambda: fake
    run_session(env)
    assert env.cmds() == [
        ("HANDSHAKE", None),
        ("AUTHENTICATE", None),
        ("SUBSCRIBE", "VOICE_CHANNEL_SELECT"),
        ("GET_SELECTED_VOICE_CHANNEL", None),
        ("SUBSCRIBE", "SPEAKING_START"),
        ("SUBSCRIBE", "SPEAKING_STOP"),
    ]
    assert env.names == [{"1": "Mika", "2": "Kenji G", "3": "rin"}]  # nick > global > user
    assert env.channels == ["111"]
    assert (StatusLevel.OK, "Discord connected.") in env.statuses


def test_background_never_prompts_and_stops_without_a_sign_in(tmp_path: Path, monkeypatch):
    """User report 2026-10-18: Discord's approve window popped up again and again because
    the background session re-asked every 5 s."""
    monkeypatch.setattr(rpc, "RETRY_S", 0.01)
    attempts: list[FakeDiscord] = []

    def connect() -> FakeDiscord:
        fake = FakeDiscord()
        attempts.append(fake)
        return fake

    env = Env(tmp_path, FakeDiscord())
    env.client.connect = connect
    env.client.start()
    assert env.client._thread is not None
    env.client._thread.join(5)
    assert not env.client._thread.is_alive()  # gave up instead of retrying
    assert len(attempts) == 1
    assert all(f.get("cmd") != "AUTHORIZE" for f in attempts[0].sent)
    level, message = env.statuses[-1]
    assert level is StatusLevel.WARNING and "Test connection" in message


def test_refused_approval_and_token_errors_say_what_to_do(tmp_path: Path):
    class Refusing(FakeDiscord):
        def write(self, data: bytes) -> None:
            _op, length = struct.unpack("<II", data[:8])
            frame = json.loads(data[8 : 8 + length])
            if frame.get("cmd") == "AUTHORIZE":
                self.sent.append(frame)
                self.push(
                    OP_FRAME,
                    {
                        "cmd": "AUTHORIZE",
                        "nonce": frame["nonce"],
                        "evt": "ERROR",
                        "data": {"code": 5000, "message": "OAuth2 Error: invalid_scope"},
                    },
                )
                return
            super().write(data)

    env = Env(tmp_path, Refusing())
    with pytest.raises(RpcError, match="App Testers"):
        env.client.check()
    assert env.exchanged == []
    assert "step 5" in rpc.token_error_advice("invalid_grant")
    assert "step 6" in rpc.token_error_advice("invalid_client")
    assert "(weird)" in rpc.token_error_advice("weird")
    assert "Authorize" in rpc.authorize_error_advice("User cancelled the request")


def test_stored_token_skips_the_prompt_and_a_stale_one_is_refreshed(tmp_path: Path):
    fake = FakeDiscord(events=["CLOSE"])
    env = Env(tmp_path, fake)
    env.tokens.save(tok("good", "r0", client="123"))
    run_session(env)
    assert ("AUTHORIZE", None) not in env.cmds() and env.exchanged == []
    stale = FakeDiscord(events=["CLOSE"])
    env2 = Env(tmp_path, stale)
    env2.tokens.save(tok("expired", "r0", client="123"))
    run_session(env2)
    assert env2.refreshed == ["r0"] and ("AUTHORIZE", None) not in env2.cmds()
    saved = env2.tokens.load()
    assert saved is not None and saved["refresh_token"] == "r2"


def test_token_for_another_app_id_is_not_used(tmp_path: Path):
    env = Env(tmp_path, FakeDiscord(events=["CLOSE"]))
    env.tokens.save(tok("good", client="999"))
    with pytest.raises(rpc.NeedsApproval):
        env.client.session()  # needs Test connection; never prompts by itself
    assert ("AUTHENTICATE", None) not in env.cmds() and ("AUTHORIZE", None) not in env.cmds()


def test_speaking_events_build_the_timeline(tmp_path: Path):
    env = Env(tmp_path, FakeDiscord(events=[]))
    timeline = env.timeline
    timeline.start("2")
    env.now[0] = 102.0
    timeline.stop("2")
    timeline.start("1")
    env.now[0] = 103.0
    got = timeline.intervals(101.0, 103.0)
    assert [(i.user_id, i.start, i.end) for i in got] == [("2", 100.0, 102.0), ("1", 102.0, 103.0)]
    timeline.lag = 0.5  # Discord reports 0.5 s before our audio has it
    assert [(i.start, i.end) for i in timeline.intervals(102.4, 103.0)] == [
        (100.5, 102.5),
        (102.5, 103.5),
    ]
    assert timeline.starts == [100.0, 102.0]


def test_dispatch_routes_speaking_and_channel_changes(tmp_path: Path):
    fake = FakeDiscord(events=["CLOSE"])
    env = Env(tmp_path, fake)
    env.tokens.save(tok("good", client="123"))
    run_session(env)  # now following channel 111
    fake.channel = CHANNEL_B
    fake.out.clear()
    env.client._transport = fake
    env.client._dispatch(speaking("SPEAKING_START", "1"))
    env.client._dispatch(
        {"cmd": "DISPATCH", "evt": "VOICE_CHANNEL_SELECT", "data": {"channel_id": "222"}}
    )
    assert env.cmds()[-5:] == [  # read the new channel, then move the subscriptions
        ("GET_SELECTED_VOICE_CHANNEL", None),
        ("UNSUBSCRIBE", "SPEAKING_START"),
        ("UNSUBSCRIBE", "SPEAKING_STOP"),
        ("SUBSCRIBE", "SPEAKING_START"),
        ("SUBSCRIBE", "SPEAKING_STOP"),
    ]
    assert env.names[-1] == {"9": "zed"} and env.channels[-1] == "222"
    assert env.timeline.intervals(0, 1e9) == []  # cleared on channel change
    env.client._dispatch(
        {"cmd": "DISPATCH", "evt": "VOICE_CHANNEL_SELECT", "data": {"channel_id": None}}
    )
    assert env.channels[-1] is None  # left voice


def test_reconnects_when_discord_comes_back(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(rpc, "RETRY_S", 0.01)
    attempts: list[int] = []
    second = FakeDiscord(events=["CLOSE"])
    done = threading.Event()

    def connect():
        attempts.append(1)
        if len(attempts) == 1:
            raise RpcError("Discord isn't running")
        if len(attempts) == 2:
            return second
        done.set()
        raise RpcError("Discord isn't running")

    env = Env(tmp_path, second)
    env.client.connect = connect
    env.tokens.save(tok("good", client="123"))
    env.client.start()
    assert done.wait(5)
    env.client.stop()
    assert len(attempts) >= 3 and second.closed
    messages = [m for _, m in env.statuses]
    assert "Discord: Discord isn't running. Retrying…" in messages
    assert "Discord connected." in messages


def test_wrong_app_id_is_reported(tmp_path: Path):
    class Refusing(FakeDiscord):
        def write(self, data: bytes) -> None:
            self.push(OP_CLOSE, {"code": 4000, "message": "Invalid Client ID"})

    env = Env(tmp_path, Refusing())
    with pytest.raises(RpcError, match="Invalid Client ID"):
        env.client.session()


def test_display_name_and_token_store(tmp_path: Path):
    assert display_name({"nick": "", "user": {"username": "u"}}) == "u"
    store = TokenStore(tmp_path / "t.bin")
    assert store.load() is None
    store.save({"a": 1})
    assert store.load() == {"a": 1}
    store.path.write_bytes(b"not dpapi")
    assert store.load() is None  # unreadable: treated as signed out
    store.delete()
    assert not store.path.exists()


def test_token_requests_name_the_app(monkeypatch):
    """Discord's firewall blocks Python's default agent with 403 "error code: 1010"."""
    import io
    import urllib.request

    seen: list[urllib.request.Request] = []

    def fake_urlopen(request: urllib.request.Request, timeout: float) -> io.BytesIO:
        seen.append(request)
        return io.BytesIO(b'{"access_token": "a"}')

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert rpc.exchange_code("1" * 18, "s", "c") == tok("a")
    agent = seen[0].get_header("User-agent")
    assert agent is not None and agent.startswith("LiveTranslator (") and "urllib" not in agent
