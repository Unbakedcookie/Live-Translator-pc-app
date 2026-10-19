"""Real Whisper: language detection among the languages the user speaks (2026-10-19)."""

import os
from pathlib import Path

import numpy as np
import pytest

from livetranslator.services.asr.faster_whisper_engine import FasterWhisperEngine
from tests.real_models import REAL_MODELS

FLEURS = Path(os.environ.get("LT_BENCH_DIR", r"D:\LiveTranslator\bench-data")) / "fleurs"
TURBO = REAL_MODELS / "models--dropbox-dash--faster-whisper-large-v3-turbo"


def wav(path: Path) -> np.ndarray:
    """FLEURS clips: 16 kHz mono, 32-bit float WAV."""
    raw = path.read_bytes()
    pos = 12
    while pos < len(raw):
        size = int.from_bytes(raw[pos + 4 : pos + 8], "little")
        if raw[pos : pos + 4] == b"data":
            return np.frombuffer(raw[pos + 8 : pos + 8 + size], dtype=np.float32).copy()
        pos += 8 + size
    raise ValueError(path)


@pytest.mark.skipif(not (TURBO.exists() and FLEURS.exists()), reason="needs the real model + data")
def test_whole_lines_are_detected_among_the_users_languages():
    engine = FasterWhisperEngine(REAL_MODELS)
    engine.load()
    try:
        for language, pair in (("es", ("es", "en")), ("ja", ("ja", "en")), ("en", ("zh", "en"))):
            clip = sorted((FLEURS / language).rglob("*.wav"))[0]
            code, share = engine.detect_language(wav(clip), pair)
            assert code == language and share > 0.9, (language, code, share)
    finally:
        engine.unload()
