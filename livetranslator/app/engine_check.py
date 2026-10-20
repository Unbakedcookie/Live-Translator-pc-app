"""`LiveTranslator --engine-check <clip.wav>`: load the real speech and translation engines
the way the app does, transcribe and translate one clip, and report which device each used.

Checks a build without opening any window (2026-10-19: the processor-only path and Opus-MT
on the graphics card in the built app had no live check). The built app has no console, so
the report goes to `engine-check.txt` in the log folder as well as to stdout when there is
one. Exit code 0 = speech worked.
"""

from __future__ import annotations

import faulthandler
import os
import sys
import time
from pathlib import Path

import numpy as np

from livetranslator.app.paths import app_paths
from livetranslator.core.persistence import load_config

SAMPLE_RATE = 16_000
REPORT_FILE = "engine-check.txt"
HANG_FILE = "engine-check-exit.txt"
HANG_S = 20
PCM = 1
FLOAT = 3
EXTENSIBLE = 0xFFFE


def read_wav(path: Path) -> np.ndarray:
    """16 kHz mono WAV, 16-bit PCM or 32-bit float, as float32 samples."""
    raw = path.read_bytes()
    if raw[:4] != b"RIFF" or raw[8:12] != b"WAVE":
        raise ValueError("not a WAV file")
    pos, fmt, bits, channels, rate = 12, None, 0, 0, 0
    while pos + 8 <= len(raw):
        chunk, size = raw[pos : pos + 4], int.from_bytes(raw[pos + 4 : pos + 8], "little")
        body = raw[pos + 8 : pos + 8 + size]
        if chunk == b"fmt ":
            fmt = int.from_bytes(body[0:2], "little")
            channels = int.from_bytes(body[2:4], "little")
            rate = int.from_bytes(body[4:8], "little")
            bits = int.from_bytes(body[14:16], "little")
            if fmt == EXTENSIBLE:
                fmt = int.from_bytes(body[24:26], "little")
        elif chunk == b"data":
            if rate != SAMPLE_RATE or channels != 1:
                raise ValueError(f"needs 16 kHz mono, got {rate} Hz x {channels}")
            if fmt == FLOAT and bits == 32:
                return np.frombuffer(body, dtype="<f4").astype(np.float32)
            if fmt == PCM and bits == 16:
                return np.frombuffer(body, dtype="<i2").astype(np.float32) / 32768.0
            raise ValueError(f"unsupported WAV format {fmt} / {bits} bit")
        pos += 8 + size + (size & 1)
    raise ValueError("no audio data")


def run_check(clip: Path, models_dir: Path | None = None) -> tuple[int, list[str]]:
    from livetranslator.platform.cuda import cuda_device_count, set_runtime_root
    from livetranslator.services.asr.faster_whisper_engine import FasterWhisperEngine
    from livetranslator.services.mt.engines.opus_mt import OpusMtEngine

    paths = app_paths()
    if models_dir is None:
        config = load_config(paths.settings_file).config
        models_dir = Path(config.models_dir) if config.models_dir else paths.default_models_dir
    lines = [
        f"models: {models_dir}",
        f"CUDA_VISIBLE_DEVICES={os.environ.get('CUDA_VISIBLE_DEVICES', '(not set)')}",
    ]
    set_runtime_root(models_dir / "cuda")
    lines.append(f"NVIDIA cards seen: {cuda_device_count()}")
    audio = read_wav(clip)
    lines.append(f"clip: {clip.name}, {len(audio) / SAMPLE_RATE:.1f} s")

    asr = FasterWhisperEngine(models_dir, download=False)
    started = time.perf_counter()
    try:
        asr.load()
    except Exception as exc:
        lines.append(f"speech: FAILED to load ({type(exc).__name__}: {exc})")
        return 1, lines
    lines.append(
        f"speech: {asr.model_used} on {asr.device_used}, loaded in "
        f"{time.perf_counter() - started:.1f} s"
        + (f" (graphics card failed: {asr.gpu_error})" if asr.gpu_error else "")
    )
    started = time.perf_counter()
    result = asr.transcribe(audio, final=True)
    lines.append(
        f"speech: {(time.perf_counter() - started) * 1000:.0f} ms, language {result.language}: "
        f"{result.text.strip()[:200]}"
    )
    asr.unload()

    mt = OpusMtEngine(models_dir)
    src = result.language or ""
    if src == "en" or not mt.supports(src, "en"):
        lines.append(f"translation: no installed model for {src or '?'} -> en, skipped")
        return 0, lines
    started = time.perf_counter()
    mt.load()
    english = mt.translate([result.text], src, "en")[0]
    lines.append(
        f"translation: {src} -> en on {mt.device}, {(time.perf_counter() - started) * 1000:.0f}"
        f" ms incl. load: {english.strip()[:200]}"
    )
    return 0, lines


def engine_check(clip: Path) -> int:
    try:
        code, lines = run_check(clip)
    except Exception as exc:  # the report must still be written
        code, lines = 1, [f"FAILED: {type(exc).__name__}: {exc}"]
    report = "\n".join(lines) + "\n"
    log_dir = app_paths().log_dir
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / REPORT_FILE).write_text(report, encoding="utf-8")
    if sys.stdout is not None:
        sys.stdout.write(report)
    # If shutting down hangs, say where (every thread's stack) instead of lingering.
    hang = (log_dir / HANG_FILE).open("w", encoding="utf-8")
    faulthandler.dump_traceback_later(HANG_S, exit=True, file=hang)
    return code
