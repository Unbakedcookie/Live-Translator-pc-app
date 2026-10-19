"""Discord local RPC: who is speaking in my voice channel (T103; spec §5.13; D-013, D-030).

Talks to the Discord desktop client over its named pipe (`\\\\.\\pipe\\discord-ipc-N`):
frames are `<op:uint32 LE><length:uint32 LE><JSON>`. Flow:

1. HANDSHAKE with the user's own Application ID → READY.
2. AUTHENTICATE with a stored token, or AUTHORIZE (Discord shows its own prompt) → code →
   token exchange over HTTPS (needs the app's client secret: D-030 Plan A) → AUTHENTICATE.
   Only the guide's "Test connection" may AUTHORIZE. The background session never does: it
   retried every 5 s and Discord's approve window popped up again and again (user report
   2026-10-18). Without a usable token it stops and says to run the test.
3. GET_SELECTED_VOICE_CHANNEL → members' display names; SUBSCRIBE VOICE_CHANNEL_SELECT,
   and SPEAKING_START / SPEAKING_STOP for the current channel (moved along on channel change).
4. Speaking events go into a `SpeakingTimeline` the speaker worker reads (fusion, T101).

If Discord isn't running or closes, the client keeps retrying in the background (no
prompts). Nothing is written to disk except the DPAPI-encrypted token (TokenStore). Names
never reach the logs.
"""

from __future__ import annotations

import contextlib
import json
import struct
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from loguru import logger

from livetranslator import __version__
from livetranslator.core.state import StatusLevel
from livetranslator.services.speakers.fusion import SpeakingInterval
from livetranslator.services.speakers.token_store import TokenStore

OP_HANDSHAKE, OP_FRAME, OP_CLOSE = 0, 1, 2
SCOPES = ("rpc", "rpc.voice.read")
REDIRECT_URI = "http://127.0.0.1"  # the user registers exactly this in the portal (guide)
PROJECT_URL = "https://github.com/Unbakedcookie/Live-Translator-pc-app"
TOKEN_URL = "https://discord.com/api/oauth2/token"  # nosec B105 - Discord's public endpoint
RETRY_S = 5.0
# Discord's firewall answers Python's default "Python-urllib/x.y" with 403 "error code: 1010"
# (user's sign-in failed 2026-10-18; reproduced with dummy values: default agent 403,
# named agent 400 invalid_client). Any real request must name the app.
USER_AGENT = f"LiveTranslator ({PROJECT_URL}, {__version__})"
KEEP_S = 120.0  # speaking history kept for fusion
PIPES = 10


class RpcError(RuntimeError):
    pass


# ---------------------------------------------------------------- framing


def encode(op: int, payload: dict[str, Any]) -> bytes:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return struct.pack("<II", op, len(body)) + body


class Transport(Protocol):
    def write(self, data: bytes) -> None: ...

    def read(self, size: int) -> bytes: ...

    def close(self) -> None: ...


def read_frame(transport: Transport) -> tuple[int, dict[str, Any]]:
    header = _read_exact(transport, 8)
    op, length = struct.unpack("<II", header)
    payload = json.loads(_read_exact(transport, length).decode("utf-8")) if length else {}
    return op, payload


def _read_exact(transport: Transport, size: int) -> bytes:
    data = b""
    while len(data) < size:
        chunk = transport.read(size - len(data))
        if not chunk:
            raise RpcError("Discord closed the connection")
        data += chunk
    return data


class PipeTransport:
    """The first Discord pipe that opens (several Discord builds may be running)."""

    def __init__(self) -> None:
        self._file: Any = None
        for n in range(PIPES):
            try:
                self._file = open(rf"\\.\pipe\discord-ipc-{n}", "r+b", buffering=0)  # noqa: SIM115
                return
            except OSError:
                continue
        raise RpcError("Discord isn't running")

    def write(self, data: bytes) -> None:
        self._file.write(data)

    def read(self, size: int) -> bytes:
        return bytes(self._file.read(size) or b"")

    def close(self) -> None:
        with contextlib.suppress(OSError):
            self._file.close()


# ---------------------------------------------------------------- speaking timeline


class SpeakingTimeline:
    """Who spoke when, on the app's monotonic clock, shifted by the calibrated lag."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._open: dict[str, float] = {}
        self._closed: list[SpeakingInterval] = []
        self.starts: list[float] = []  # SPEAKING_START times, for lag calibration
        self.lag = 0.0  # seconds Discord's events arrive before our audio (D-025)
        self._lock = threading.Lock()

    def start(self, user_id: str) -> None:
        now = self._clock()
        with self._lock:
            self._open.setdefault(user_id, now)
            self.starts.append(now)
            self._prune(now)

    def stop(self, user_id: str) -> None:
        now = self._clock()
        with self._lock:
            began = self._open.pop(user_id, None)
            if began is not None:
                self._closed.append(SpeakingInterval(user_id, began, now))

    def clear(self) -> None:
        with self._lock:
            self._open.clear()
            self._closed.clear()
            self.starts.clear()

    def intervals(self, start: float, end: float) -> list[SpeakingInterval]:
        """Speaking intervals overlapping [start, end] of our audio clock."""
        now = self._clock()
        with self._lock:
            all_intervals = [
                *self._closed,
                *(SpeakingInterval(u, s, now) for u, s in self._open.items()),
            ]
            lag = self.lag
        shifted = [SpeakingInterval(i.user_id, i.start + lag, i.end + lag) for i in all_intervals]
        return [i for i in shifted if i.end > start and i.start < end]

    def _prune(self, now: float) -> None:
        self._closed = [i for i in self._closed if now - i.end <= KEEP_S]
        self.starts = [t for t in self.starts if now - t <= KEEP_S]


# ---------------------------------------------------------------- token exchange


def exchange_code(client_id: str, secret: str, code: str) -> dict[str, Any]:
    """OAuth2 authorization-code exchange (D-030 Plan A: the user's own app secret)."""
    return _token_request(
        {
            "client_id": client_id,
            "client_secret": secret,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
        }
    )


def refresh_token(client_id: str, secret: str, token: str) -> dict[str, Any]:
    return _token_request(
        {
            "client_id": client_id,
            "client_secret": secret,
            "grant_type": "refresh_token",
            "refresh_token": token,
        }
    )


def _token_request(form: dict[str, str]) -> dict[str, Any]:
    request = urllib.request.Request(
        TOKEN_URL,
        data=urllib.parse.urlencode(form).encode("ascii"),
        headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:  # nosec B310 - fixed https URL
            return dict(json.load(response))
    except urllib.error.HTTPError as exc:
        error = _oauth_error(exc)
        logger.warning("Discord token request refused (HTTP {}, {})", exc.code, error or "?")
        raise RpcError(token_error_advice(error)) from exc
    except OSError as exc:
        logger.warning("Discord token request failed ({})", type(exc).__name__)
        raise RpcError("Couldn't reach Discord to finish signing in. Check the internet.") from exc


def _oauth_error(exc: urllib.error.HTTPError) -> str:
    """The OAuth2 error code from Discord's reply body (e.g. "invalid_grant"), or ""."""
    try:
        body = json.loads(exc.read().decode("utf-8", "replace"))
    except (OSError, ValueError):
        return ""
    return str(body.get("error") or "") if isinstance(body, dict) else ""


def token_error_advice(error: str) -> str:
    """Plain advice for a refused token request (the guide shows it)."""
    if error == "invalid_client":
        return (
            "Discord didn't accept the client secret. Do step 6 again (Reset Secret), paste "
            "the new secret and test again."
        )
    if error == "invalid_grant":
        return (
            "Discord refused the sign-in code. Check step 5: the redirect must be exactly "
            f"{REDIRECT_URI} and saved with Save Changes. Then test again."
        )
    if error == "invalid_scope":
        return (
            "Discord doesn't allow this app to read voice channels for your account yet "
            "(step 8: App Testers)."
        )
    detail = f" ({error})" if error else ""
    return f"Discord refused the sign-in{detail}. Check the Application ID and secret."


def authorize_error_advice(message: str) -> str:
    """Plain advice for a failed AUTHORIZE (Discord's approve window)."""
    lowered = message.lower()
    if "cancel" in lowered or "denied" in lowered or "closed" in lowered:
        return "The request was closed in Discord. Click Test connection and choose Authorize."
    if "scope" in lowered or "not allowed" in lowered or "whitelist" in lowered:
        return (
            f"Discord said: {message}. Your account may need to be on the app's App Testers "
            "list (step 8)."
        )
    return f"Discord said: {message}."


# ---------------------------------------------------------------- client


Exchange = Callable[[str], dict[str, Any]]  # code -> token response
Refresh = Callable[[str], dict[str, Any]]  # refresh token -> token response


@dataclass
class DiscordCallbacks:
    status: Callable[[StatusLevel, str], None] = lambda level, message: None
    members: Callable[[dict[str, str]], None] = lambda names: None  # user id -> display name
    channel: Callable[[str | None], None] = lambda channel_id: None


def display_name(state: dict[str, Any]) -> str:
    """A voice state's best name: server nickname, then global name, then username."""
    user = state.get("user") or {}
    return str(state.get("nick") or user.get("global_name") or user.get("username") or "?")


class NeedsApproval(RpcError):
    """No usable sign-in: only the setup guide's Test connection may ask Discord again."""


@dataclass
class DiscordClient:
    client_id: str
    timeline: SpeakingTimeline
    tokens: TokenStore
    exchange: Exchange
    refresh: Refresh
    callbacks: DiscordCallbacks = field(default_factory=DiscordCallbacks)
    connect: Callable[[], Transport] = PipeTransport
    _transport: Transport | None = None
    _channel: str | None = None
    _stop: threading.Event = field(default_factory=threading.Event)
    _thread: threading.Thread | None = None

    # ------------------------------------------------------------ lifecycle

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="discord-rpc", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._transport is not None:
            self._transport.close()
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.session()
            except NeedsApproval:
                self.callbacks.status(
                    StatusLevel.WARNING,
                    "Discord isn't signed in. Open Settings, Speakers, Set up… and click "
                    "Test connection.",
                )
                return  # never prompt from the background; the guide restarts us
            except RpcError as exc:
                self.callbacks.status(StatusLevel.WARNING, f"Discord: {exc}. Retrying…")
            except Exception as exc:  # never let the thread die
                logger.warning("Discord RPC error ({})", type(exc).__name__)
                self.callbacks.status(StatusLevel.WARNING, "Discord connection lost. Retrying…")
            finally:
                if self._transport is not None:
                    self._transport.close()
                    self._transport = None
                self.timeline.clear()
            self._stop.wait(RETRY_S)

    # ------------------------------------------------------------ one connection

    def check(self) -> str:
        """One attempt for the setup guide's "Test connection": connect, sign in (Discord
        may show its approve prompt), read the voice channel, disconnect. Returns a plain
        message; raises RpcError with what went wrong."""
        try:
            self._transport = self.connect()
            self._send(OP_HANDSHAKE, {"v": 1, "client_id": self.client_id})
            op, ready = read_frame(self._transport)
            if op == OP_CLOSE or ready.get("evt") != "READY":
                raise RpcError(
                    str(ready.get("message") or "Discord didn't accept the Application ID")
                )
            self._sign_in(allow_prompt=True)
            channel = self._selected_channel()
        finally:
            if self._transport is not None:
                self._transport.close()
                self._transport = None
        if channel is None:
            return "Connected. Join a voice channel and the names will appear."
        count = len(channel.get("voice_states") or ())
        return f"Connected. {count} people in your voice channel."

    def session(self) -> None:
        """Connect, sign in, follow the voice channel, then read events until it closes."""
        self._transport = self.connect()
        self._send(OP_HANDSHAKE, {"v": 1, "client_id": self.client_id})
        op, ready = read_frame(self._transport)
        if op == OP_CLOSE or ready.get("evt") != "READY":
            raise RpcError(str(ready.get("message") or "Discord didn't accept the Application ID"))
        self._sign_in(allow_prompt=False)
        self.callbacks.status(StatusLevel.OK, "Discord connected.")
        self._call("SUBSCRIBE", {}, evt="VOICE_CHANNEL_SELECT")
        self._follow(self._selected_channel())
        while not self._stop.is_set():
            op, frame = read_frame(self._transport)
            if op == OP_CLOSE:
                raise RpcError("Discord closed the connection")
            self._dispatch(frame)

    def _sign_in(self, allow_prompt: bool) -> None:
        saved = self.tokens.load() or {}
        token = saved.get("access_token")
        if token and saved.get("client_id") == self.client_id:
            if self._authenticate(str(token)):
                return
            refresh = saved.get("refresh_token")
            if refresh:
                try:
                    if self._authenticate(self._store(self.refresh(str(refresh)))):
                        return
                except RpcError:
                    pass
        if not allow_prompt:
            raise NeedsApproval("not signed in")
        self.callbacks.status(StatusLevel.BUSY, "Discord: approve the request in Discord…")
        reply = self._call(
            "AUTHORIZE", {"client_id": self.client_id, "scopes": list(SCOPES)}, check=False
        )
        if reply.get("evt") == "ERROR":
            data = reply.get("data") or {}
            message = str(data.get("message") or "error")
            logger.warning("Discord AUTHORIZE refused (code {})", data.get("code", "?"))
            raise RpcError(authorize_error_advice(message))
        code = (reply.get("data") or {}).get("code")
        if not code:
            raise RpcError("Discord didn't approve the request")
        if not self._authenticate(self._store(self.exchange(str(code)))):
            raise RpcError("Discord rejected the sign-in")

    def _store(self, tokens: dict[str, Any]) -> str:
        access = tokens.get("access_token")
        if not access:
            raise RpcError("Discord didn't return a token")
        self.tokens.save(
            {
                "client_id": self.client_id,
                "access_token": access,
                "refresh_token": tokens.get("refresh_token"),
            }
        )
        return str(access)

    def _authenticate(self, token: str) -> bool:
        reply = self._call("AUTHENTICATE", {"access_token": token}, check=False)
        return reply.get("evt") != "ERROR"

    def _selected_channel(self) -> dict[str, Any] | None:
        reply = self._call("GET_SELECTED_VOICE_CHANNEL", {})
        data = reply.get("data")
        return data if isinstance(data, dict) else None

    def _follow(self, channel: dict[str, Any] | None) -> None:
        new_id = str(channel["id"]) if channel and channel.get("id") else None
        if self._channel and self._channel != new_id:
            for evt in ("SPEAKING_START", "SPEAKING_STOP"):
                self._call("UNSUBSCRIBE", {"channel_id": self._channel}, evt=evt, check=False)
            self.timeline.clear()
        self._channel = new_id
        self.callbacks.channel(new_id)
        if channel is None or new_id is None:
            return
        names = {
            str((s.get("user") or {}).get("id")): display_name(s)
            for s in channel.get("voice_states") or ()
            if (s.get("user") or {}).get("id")
        }
        self.callbacks.members(names)
        for evt in ("SPEAKING_START", "SPEAKING_STOP"):
            self._call("SUBSCRIBE", {"channel_id": new_id}, evt=evt)

    # ------------------------------------------------------------ messages

    def _send(self, op: int, payload: dict[str, Any]) -> None:
        if self._transport is None:
            raise RpcError("not connected")
        self._transport.write(encode(op, payload))

    def _call(
        self, cmd: str, args: dict[str, Any], evt: str | None = None, check: bool = True
    ) -> dict[str, Any]:
        """Send a command and read until its reply; events arriving meanwhile are handled."""
        nonce = uuid.uuid4().hex
        payload: dict[str, Any] = {"cmd": cmd, "args": args, "nonce": nonce}
        if evt:
            payload["evt"] = evt
        self._send(OP_FRAME, payload)
        assert self._transport is not None  # nosec B101 - _send checked it
        while True:
            op, frame = read_frame(self._transport)
            if op == OP_CLOSE:
                raise RpcError(str(frame.get("message") or "Discord closed the connection"))
            if frame.get("nonce") == nonce:
                if check and frame.get("evt") == "ERROR":
                    message = (frame.get("data") or {}).get("message", "error")
                    raise RpcError(f"{cmd} failed ({message})")
                return frame
            self._dispatch(frame)

    def _dispatch(self, frame: dict[str, Any]) -> None:
        if frame.get("cmd") != "DISPATCH":
            return
        evt, data = frame.get("evt"), frame.get("data") or {}
        if evt == "SPEAKING_START" and data.get("user_id"):
            self.timeline.start(str(data["user_id"]))
        elif evt == "SPEAKING_STOP" and data.get("user_id"):
            self.timeline.stop(str(data["user_id"]))
        elif evt == "VOICE_CHANNEL_SELECT":
            self._follow(self._selected_channel() if data.get("channel_id") else None)
