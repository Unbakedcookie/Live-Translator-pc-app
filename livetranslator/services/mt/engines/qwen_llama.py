"""Qwen3-4B-Instruct through llama.cpp's llama-server (Mandarin follow-up, 2026-10-18).

Why: on casual/gaming Mandarin, Opus-MT mistranslates common slang (麦 "mic" → "wheat",
开黑 "play together" → "keep it dark", 副本 "dungeon instance" → "copy"); Qwen got all of
those right at ~0.26 s per line (history/M03, D-005: 2.8 GB of graphics memory).

How: the Vulkan build of llama-server (MIT; no NVIDIA DLLs needed) runs as a hidden child
process bound to 127.0.0.1 on a free port, loading the Q4_K_M GGUF (Apache-2.0). Lines are
sent to its OpenAI-style chat endpoint, one request per line, temperature 0.

Files (under the models folder):
    llama.cpp/vulkan/llama-server.exe (+ its DLLs)
    qwen3-4b/Qwen3-4B-Instruct-2507-Q4_K_M.gguf
"""

from __future__ import annotations

import json
import socket
import subprocess  # nosec B404 - starts our own bundled llama-server binary
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Sequence
from pathlib import Path

from loguru import logger

from livetranslator.core.languages import language
from livetranslator.platform.win32 import kill_with_this_process
from livetranslator.services.errors import EngineError, EngineNotLoaded, UnsupportedLanguage

SERVER_DIR = Path("llama.cpp") / "vulkan"
SERVER_EXE = "llama-server.exe"
MODEL_FILE = Path("qwen3-4b") / "Qwen3-4B-Instruct-2507-Q4_K_M.gguf"
CONTEXT = 2048
MAX_TOKENS = 256
START_TIMEOUT_S = 120.0
REQUEST_TIMEOUT_S = 30.0
# Languages the app lets Qwen3 translate (both directions). Qwen3 is trained on 119
# languages; the first rows are its strongest. The rest are for pairs with no installed
# Opus-MT model (fallback, 2026-10-18), where a rougher translation beats none (D-038).
LANGUAGES = frozenset(
    (
        *("en", "zh", "ja", "ko", "es", "fr", "de", "it", "pt", "ru"),
        *("ar", "hi", "th", "vi", "id", "tr", "pl", "nl", "uk"),
        *("ur", "bn", "ta", "te", "mr", "fa", "he", "ms", "tl", "sr", "hr", "bs"),
        *("cs", "sk", "sl", "ro", "bg", "el", "hu", "fi", "sv", "no", "da", "ca"),
        *("lt", "lv", "et", "sw"),
    )
)
PROMPT = (
    "You translate live voice and game chat from {src} to {tgt}. Keep the tone, slang and "
    "gaming terms natural for a {tgt} speaker. Reply with the translation only, no notes."
)


def server_path(models_dir: Path) -> Path:
    return models_dir / SERVER_DIR / SERVER_EXE


def model_path(models_dir: Path) -> Path:
    return models_dir / MODEL_FILE


def installed(models_dir: Path) -> bool:
    return server_path(models_dir).is_file() and model_path(models_dir).is_file()


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def clean_reply(text: str) -> str:
    """Strip a stray 'Translation:' prefix or wrapping quotes some replies add."""
    reply = text.strip()
    for prefix in ("Translation:", "翻译：", "翻译:"):  # noqa: RUF001 - full-width colon on purpose
        if reply.startswith(prefix):
            reply = reply[len(prefix) :].strip()
    if len(reply) >= 2 and reply[0] == reply[-1] and reply[0] in "\"'“”":
        reply = reply[1:-1].strip()
    return reply


class QwenLlamaEngine:
    name = "qwen"

    def __init__(self, models_dir: Path) -> None:
        self._models_dir = models_dir
        self._proc: subprocess.Popen[bytes] | None = None
        self._port = 0
        self._lock = threading.Lock()  # one request at a time; start/stop never overlap

    @property
    def is_loaded(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def supports(self, src: str, tgt: str) -> bool:
        return src != tgt and src in LANGUAGES and tgt in LANGUAGES and installed(self._models_dir)

    def load(self) -> None:
        with self._lock:
            if self.is_loaded:
                return
            if not installed(self._models_dir):
                raise EngineNotLoaded("Qwen translation files aren't installed")
            self._port = free_port()
            server = server_path(self._models_dir)
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
            self._proc = subprocess.Popen(  # nosec B603 - fixed binary, fixed arguments
                [
                    str(server),
                    "-m",
                    str(model_path(self._models_dir)),
                    "-ngl",
                    "99",
                    "-c",
                    str(CONTEXT),
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(self._port),
                ],
                cwd=server.parent,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=flags,
            )
            handle = getattr(self._proc, "_handle", None)  # Windows process handle
            if handle is not None and not kill_with_this_process(int(handle)):
                logger.warning("couldn't tie the Qwen server to the app; it stops on normal exit")
            deadline = time.monotonic() + START_TIMEOUT_S
            while time.monotonic() < deadline:
                if self._proc.poll() is not None:
                    code = self._proc.returncode
                    self._proc = None
                    raise EngineError(f"the Qwen server stopped while starting (exit {code})")
                if self._healthy():
                    self._warm_up()
                    logger.info("Qwen translation ready")
                    return
                time.sleep(0.25)
            self._stop()
            raise EngineError("the Qwen server didn't start in time")

    def _warm_up(self) -> None:
        """One tiny request: the graphics card's first one took ~10 s (measured 2026-10-18),
        later ones 0.2-0.5 s. Paid here, at start, instead of on someone's first line."""
        try:
            self._one("ok", "en", "zh")
        except EngineError as exc:
            logger.warning("Qwen warm-up failed ({})", type(exc).__name__)

    def _healthy(self) -> bool:
        try:
            url = f"http://127.0.0.1:{self._port}/health"
            with urllib.request.urlopen(url, timeout=2) as r:  # nosec B310 - our localhost server
                return r.status == 200
        except (OSError, urllib.error.URLError):
            return False

    def unload(self) -> None:
        with self._lock:
            self._stop()

    def _stop(self) -> None:
        if self._proc is not None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            self._proc = None

    def translate(self, texts: Sequence[str], src: str, tgt: str) -> list[str]:
        if not self.supports(src, tgt):
            raise UnsupportedLanguage(f"Qwen isn't set up for {src} -> {tgt}")
        with self._lock:
            if not self.is_loaded:
                raise EngineNotLoaded("start the Qwen engine first")
            return [self._one(text, src, tgt) for text in texts]

    def warm(self, src: str, tgt: str) -> bool:
        """The server holds one model for every pair: starting it is the whole warm-up."""
        if not self.supports(src, tgt):
            return False
        self.load()
        return True

    def _one(self, text: str, src: str, tgt: str) -> str:
        system = PROMPT.format(src=language(src).english, tgt=language(tgt).english)
        body = json.dumps(
            {
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": text},
                ],
                "temperature": 0,
                "max_tokens": MAX_TOKENS,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"http://127.0.0.1:{self._port}/v1/chat/completions",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_S) as r:  # nosec B310
                reply = json.load(r)
        except (OSError, urllib.error.URLError, ValueError) as exc:
            raise EngineError(f"Qwen request failed ({type(exc).__name__})") from exc
        return clean_reply(str(reply["choices"][0]["message"]["content"]))
