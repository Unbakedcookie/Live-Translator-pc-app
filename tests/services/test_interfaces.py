"""T016 — engine contracts (Tier A): fakes satisfy them; base modules stay library-free."""

import subprocess  # nosec B404
import sys
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pytest

from livetranslator.services.asr.base import (
    SAMPLE_RATE,
    ASREngine,
    Audio,
    Segment,
    Transcription,
    Word,
)
from livetranslator.services.errors import EngineNotLoaded, UnsupportedLanguage
from livetranslator.services.mt.base import TranslationEngine
from livetranslator.services.ocr.base import Image, OcrEngine, OcrLine, OcrResult

ROOT = Path(__file__).resolve().parents[2]


class FakeASR:
    name = "fake-asr"

    def __init__(self) -> None:
        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def load(self) -> None:
        self._loaded = True

    def unload(self) -> None:
        self._loaded = False

    def transcribe(
        self,
        audio: Audio,
        *,
        language: str | None = None,
        prompt: str | None = None,
        final: bool = False,
    ) -> Transcription:
        if not self._loaded:
            raise EngineNotLoaded("load() first")
        seconds = len(audio) / SAMPLE_RATE
        word = Word(" hello", 0.0, seconds, 0.9)
        return Transcription((Segment(" hello", 0.0, seconds, (word,)),), language or "en", 0.99)


class FakeMT:
    name = "fake-mt"
    is_loaded = True

    def supports(self, src: str, tgt: str) -> bool:
        return (src, tgt) == ("es", "en")

    def load(self) -> None:
        pass

    def unload(self) -> None:
        pass

    def translate(self, texts: Sequence[str], src: str, tgt: str) -> list[str]:
        if not self.supports(src, tgt):
            raise UnsupportedLanguage(f"{src}->{tgt}")
        return [f"EN({t})" for t in texts]


class FakeOCR:
    name = "fake-ocr"

    def available_languages(self) -> set[str]:
        return {"en"}

    def recognize(self, image: Image, language: str | None = None) -> OcrResult:
        h, w = image.shape[:2]
        return OcrResult((OcrLine("Quest complete", (0, 0, w, h), 0.97),), language)


def test_fakes_satisfy_protocols():
    asr: ASREngine = FakeASR()
    mt: TranslationEngine = FakeMT()
    ocr: OcrEngine = FakeOCR()
    assert isinstance(asr, ASREngine)
    assert isinstance(mt, TranslationEngine)
    assert isinstance(ocr, OcrEngine)
    assert not isinstance(object(), ASREngine)


def test_asr_contract_flow():
    engine = FakeASR()
    audio = np.zeros(SAMPLE_RATE * 2, dtype=np.float32)
    with pytest.raises(EngineNotLoaded):
        engine.transcribe(audio)
    engine.load()
    result = engine.transcribe(audio, language="es")
    assert result.language == "es"
    assert result.segments[0].end == 2.0
    engine.unload()
    assert not engine.is_loaded


def test_transcription_helpers():
    t = Transcription(
        (
            Segment(" Hola,", 0.0, 0.6, (Word(" Hola,", 0.0, 0.6),)),
            Segment("  ", 0.6, 0.7),
            Segment(" ¿qué tal?", 0.7, 1.5, (Word(" ¿qué", 0.7, 1.0), Word(" tal?", 1.0, 1.5))),
        ),
        "es",
    )
    assert t.text == "Hola, ¿qué tal?"
    assert [w.text for w in t.words] == [" Hola,", " ¿qué", " tal?"]


def test_mt_contract():
    engine = FakeMT()
    assert engine.translate(["hola", "adiós"], "es", "en") == ["EN(hola)", "EN(adiós)"]
    with pytest.raises(UnsupportedLanguage):
        engine.translate(["x"], "ja", "ko")


def test_ocr_result_text():
    result = FakeOCR().recognize(np.zeros((40, 300, 3), dtype=np.uint8))
    assert result.lines[0].box == (0, 0, 300, 40)
    multi = OcrResult(
        (
            OcrLine("line one", (0, 0, 1, 1)),
            OcrLine(" ", (0, 0, 1, 1)),
            OcrLine("two", (0, 0, 1, 1)),
        )
    )
    assert multi.text == "line one\ntwo"


ENGINE_LIBRARIES = {
    "faster_whisper",
    "ctranslate2",
    "torch",
    "onnxruntime",
    "sherpa_onnx",
    "winrt",
    "rapidocr",
    "llama_cpp",
}


def test_base_modules_import_no_engine_libraries():
    code = (
        "import sys\n"
        "import livetranslator.services.asr.base, livetranslator.services.mt.base, "
        "livetranslator.services.ocr.base\n"
        f"print(sorted({{m.split('.')[0] for m in sys.modules}} & {ENGINE_LIBRARIES!r}))\n"
    )
    out = subprocess.run(  # nosec B603
        [sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=True
    )
    assert out.stdout.strip() == "[]"
