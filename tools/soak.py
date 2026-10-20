"""Long-session soak test (T112): the whole app on recorded speech, memory sampled every minute.

    python -m tools.soak                    # 15 minutes, FLEURS clips from LT_BENCH_DIR
    python -m tools.soak --minutes 2        # a quick run

The real app (windows, speech, translation, speaker labels, metrics) runs in its own test
profile (`D:/LiveTranslator/soak-profile`), so it never touches the user's settings, mic or
speakers: two pretend devices play FLEURS clips in real time instead, "Me" in English and
"Others" in several languages with pauses. Its one window sits small in a screen corner.
Qwen is off in that profile (a second copy would take ~3 GB of graphics memory beside the
user's running app); Opus-MT covers the languages played.

Writes `soak.csv` (one row a minute) and prints a summary: memory start/end/peak, lines,
delays (p50/p95), errors in the log. Not part of the app.
"""

from __future__ import annotations

import argparse
import csv
import ctypes
import os
import sys
import threading
import time
from collections.abc import Callable
from ctypes import wintypes
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from livetranslator.services.audio.devices import AudioDevice

ROOT = Path(__file__).resolve().parents[1]
PROFILE = Path(os.environ.get("LT_SOAK_PROFILE", r"D:\LiveTranslator\soak-profile"))
BENCH = Path(os.environ.get("LT_BENCH_DIR", r"D:\LiveTranslator\bench-data")) / "fleurs"
RATE = 16_000
CHUNK = 1024  # frames per callback, like the real stream
OTHERS_LANGUAGES = ("zh", "es", "ja", "ru", "fr", "de", "ko")
ME_LANGUAGE = "en"
CLIPS_PER_LANGUAGE = 6
OTHERS_GAP_S = 1.5
ME_GAP_S = 20.0  # you talk now and then
SAMPLE_S = 60
WINDOW_AT = (4560, 1180, 520, 200)  # x, y, width, height: bottom corner of the right screen
MIC = "Soak mic"
SPEAKERS = "Soak speakers"


def read_clip(path: Path) -> np.ndarray:
    from livetranslator.app.engine_check import read_wav

    return read_wav(path)


def playlist(languages: tuple[str, ...], per_language: int) -> list[np.ndarray]:
    clips: list[np.ndarray] = []
    for i in range(per_language):
        for language in languages:
            files = sorted((BENCH / language).rglob("*.wav"))
            if i < len(files):
                clips.append(read_clip(files[i]))
    if not clips:
        raise SystemExit(f"no FLEURS clips under {BENCH}")
    return clips


class Player:
    """Plays clips back to back (with pauses) as raw float32 bytes, in real time."""

    def __init__(self, clips: list[np.ndarray], gap_s: float) -> None:
        silence = np.zeros(int(gap_s * RATE), dtype=np.float32)
        parts: list[np.ndarray] = []
        for clip in clips:
            parts += [clip, silence]
        self.audio = np.concatenate(parts).astype(np.float32)
        self.pos = 0

    def next_chunk(self) -> bytes:
        end = self.pos + CHUNK
        if end <= len(self.audio):
            chunk = self.audio[self.pos : end]
        else:  # loop
            chunk = np.concatenate([self.audio[self.pos :], self.audio[: end - len(self.audio)]])
        self.pos = end % len(self.audio)
        return chunk.tobytes()


PLAYERS: dict[str, Player] = {}


class FakeStream:
    """Stands in for the PyAudio stream: feeds a Player to the capture callback."""

    def __init__(self, device: AudioDevice, on_bytes: Callable[[bytes], None]) -> None:
        self._player = PLAYERS[device.ref.name]
        self._on_bytes = on_bytes
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="soak-audio", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        period = CHUNK / RATE
        next_at = time.perf_counter()
        while not self._stop.is_set():
            self._on_bytes(self._player.next_chunk())
            next_at += period
            delay = next_at - time.perf_counter()
            if delay > 0:
                self._stop.wait(delay)

    def is_active(self) -> bool:
        return not self._stop.is_set()

    def close(self) -> None:
        self._stop.set()
        self._thread.join(1.0)


def fake_devices():
    from livetranslator.services.audio.devices import (
        LOOPBACK_SUFFIX,
        AudioDevice,
        DeviceList,
    )

    mic = AudioDevice(9001, MIC, "Windows WASAPI", 1, RATE)
    loop = AudioDevice(9002, SPEAKERS + LOOPBACK_SUFFIX, "Windows WASAPI", 1, RATE, True)
    return DeviceList((mic,), (loop,), mic, loop)


def rss_mb() -> float:
    class Counters(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    counters = Counters()
    counters.cb = ctypes.sizeof(Counters)
    kernel = ctypes.WinDLL("kernel32")
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi = ctypes.WinDLL("psapi")
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
    psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb)
    return counters.WorkingSetSize / 2**20


def write_profile(models_dir: Path) -> None:
    from livetranslator.core.persistence import save_config
    from livetranslator.core.state import (
        AppConfig,
        DeviceRef,
        Geometry,
        Source,
        WindowConfig,
    )

    base = AppConfig()
    config = base.model_copy(
        update={
            "wizard_completed": True,
            "models_dir": str(models_dir),
            "windows": (
                WindowConfig(
                    id="soak",
                    sources=(Source.ME, Source.OTHERS),
                    geometry=Geometry(
                        x=WINDOW_AT[0], y=WINDOW_AT[1], width=WINDOW_AT[2], height=WINDOW_AT[3]
                    ),
                ),
            ),
            "audio": base.audio.model_copy(
                update={
                    "mic_device": DeviceRef(name=MIC, host_api="Windows WASAPI"),
                    "output_device": DeviceRef(name=SPEAKERS, host_api="Windows WASAPI"),
                    "mic_languages": (ME_LANGUAGE,),
                }
            ),
            "engines": base.engines.model_copy(
                update={"smart_languages": (), "smart_fallback": False}
            ),
            "performance": base.performance.model_copy(update={"show_readout": True}),
        }
    )
    save_config(PROFILE / "config" / "settings.json", config)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Live Translator soak test (T112)")
    parser.add_argument("--minutes", type=float, default=15.0)
    parser.add_argument("--models", type=Path, help="models folder (default: your app's)")
    args = parser.parse_args(argv)

    user_home = os.environ.get("LIVETRANSLATOR_HOME")
    os.environ["LIVETRANSLATOR_HOME"] = str(PROFILE)
    sys.path.insert(0, str(ROOT))
    from loguru import logger
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from livetranslator.app import application
    from livetranslator.app.log import setup_logging
    from livetranslator.app.paths import app_paths
    from livetranslator.core.persistence import load_config
    from livetranslator.services.audio import capture, devices
    from livetranslator.services.metrics import metric_name

    models_dir = args.models
    if models_dir is None:
        user = app_paths(Path(user_home)) if user_home else None
        if user is None:
            raise SystemExit("pass --models (LIVETRANSLATOR_HOME isn't set)")
        saved = load_config(user.settings_file).config.models_dir
        models_dir = Path(saved) if saved else user.default_models_dir
    paths = app_paths()
    paths.ensure()
    write_profile(models_dir)

    PLAYERS[MIC] = Player(playlist((ME_LANGUAGE,), CLIPS_PER_LANGUAGE), ME_GAP_S)
    PLAYERS[SPEAKERS] = Player(playlist(OTHERS_LANGUAGES, CLIPS_PER_LANGUAGE), OTHERS_GAP_S)
    devices.list_devices = fake_devices  # build_speech imports it at call time
    capture._PyAudioStream = FakeStream  # type: ignore[misc,assignment]

    app = QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)
    log_file = setup_logging(paths.log_dir)
    logger.info("soak test starting: {} min, models {}", args.minutes, models_dir)
    live = application.LiveTranslatorApp(paths, app.quit, speech=True)
    app.aboutToQuit.connect(live.shutdown)

    rows: list[dict[str, object]] = []
    started = time.perf_counter()
    csv_path = PROFILE / "soak.csv"

    def sample() -> None:
        state = live.store.state
        metrics = state.runtime.metrics
        lines = state.session.utterances
        row: dict[str, object] = {
            "minute": round((time.perf_counter() - started) / 60, 1),
            "rss_mb": round(rss_mb()),
            "lines": len(lines),
            "translated": sum(1 for u in lines if u.translations),
            "vram_used_mb": metrics.get("vram_used_mb"),
        }
        for kind in ("asr", "mt", "lag"):
            for pct in (50, 95):
                row[f"{kind}_p{pct}_ms"] = metrics.get(metric_name(kind, pct))
        rows.append(row)
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        print(row, flush=True)

    timer = QTimer()
    timer.timeout.connect(sample)
    timer.start(SAMPLE_S * 1000)
    QTimer.singleShot(5000, sample)  # a baseline once the engines start
    QTimer.singleShot(int(args.minutes * 60_000), lambda: (sample(), app.quit()))
    code = app.exec()

    errors = [
        line
        for line in log_file.read_text(encoding="utf-8", errors="replace").splitlines()
        if "| ERROR" in line and line[:10] >= time.strftime("%Y-%m-%d")
    ]
    if rows:
        rss = [int(r["rss_mb"]) for r in rows]  # type: ignore[call-overload]
        print(
            f"\nsoak: {rows[-1]['minute']} min, {rows[-1]['lines']} lines "
            f"({rows[-1]['translated']} translated); memory {rss[0]} -> {rss[-1]} MB "
            f"(peak {max(rss)}); lag p50/p95 {rows[-1]['lag_p50_ms']}/{rows[-1]['lag_p95_ms']} ms;"
            f" errors in log: {len(errors)}; rows: {csv_path}"
        )
    for line in errors[:10]:
        print(line)
    return code or (1 if errors else 0)


if __name__ == "__main__":
    sys.exit(main())
