"""faster-whisper speech engine (T045; spec §5.4; benchmark: benchmarks/results/asr.md).

- Models are CTranslate2 conversions downloaded from Hugging Face at a pinned revision into
  the app's models folder (once), then always loaded from disk.
- Device "auto": CUDA with int8_float16 when a GPU and the NVIDIA libraries are usable, else
  CPU int8 with the smaller model (spec §5.4 "No CUDA"). The GPU is proven with a short
  warm-up decode inside `load()`, because cuBLAS is only loaded at the first decode.
- Partials decode greedily without temperature fallback (fast); finals use beam 5 with
  fallback (accurate). Measured on the RTX 3060: turbo int8 ≈ 0.3-0.4 s per partial.
- PyAV: faster-whisper imports `av` only to decode audio files. We always pass arrays, and
  the av wheel bundles GPL x264/x265 DLLs (D-027), so the shipped app leaves av out and a
  stand-in module satisfies the import.
"""

from __future__ import annotations

import sys
import threading
import types
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np

from livetranslator.platform.cuda import add_cuda_dll_dirs, cuda_device_count
from livetranslator.services.asr.base import (
    SAMPLE_RATE,
    Audio,
    Segment,
    Transcription,
    Word,
)
from livetranslator.services.errors import EngineError, EngineNotLoaded

Device = Literal["auto", "cuda", "cpu"]

PARTIAL_BEAM = 1
FINAL_BEAM = 5
WARMUP_S = 1.0


@dataclass(frozen=True)
class WhisperModelSpec:
    key: str
    repo: str
    revision: str  # pinned commit (T054 rule: never "main")
    size_mb: int
    licence: str


# Licences: D-001 (OpenAI Whisper weights MIT); conversion repos checked in DATA_TRACKER.
WHISPER_MODELS: dict[str, WhisperModelSpec] = {
    "large-v3-turbo": WhisperModelSpec(
        "large-v3-turbo",
        "dropbox-dash/faster-whisper-large-v3-turbo",  # formerly mobiuslabsgmbh/ (same commit)
        "0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf",
        1620,
        "MIT",
    ),
    "small": WhisperModelSpec(
        "small",
        "Systran/faster-whisper-small",
        "536b0662742c02347bc0e980a01041f333bce120",
        484,
        "MIT",
    ),
}
GPU_MODEL = "large-v3-turbo"
CPU_MODEL = "small"


def ensure_av_importable() -> None:
    """Let `import faster_whisper` work without PyAV (see module docstring)."""
    try:
        import av  # noqa: F401  # pyright: ignore[reportUnusedImport]
    except ImportError:
        stub = types.ModuleType("av")
        stub.__doc__ = "Stand-in: Live Translator never decodes audio files (D-027)."
        sys.modules["av"] = stub


def plain_folder(spec: WhisperModelSpec, models_dir: Path) -> Path:
    """Where the setup wizard / Language Manager put a Whisper model (catalogue `dest`)."""
    return models_dir / "whisper" / spec.key


def model_path(spec: WhisperModelSpec, models_dir: Path, *, download: bool) -> Path:
    """Local folder of `spec`: the plain folder the app downloads to (T073), else an older
    Hugging Face cache copy; with `download`, fetches the cache copy (developer runs)."""
    from huggingface_hub import snapshot_download

    folder = plain_folder(spec, models_dir)
    if (folder / "model.bin").is_file():
        return folder
    try:
        return Path(
            snapshot_download(
                spec.repo, revision=spec.revision, cache_dir=models_dir, local_files_only=True
            )
        )
    except Exception as missing:
        if not download:
            raise EngineError(f"speech model {spec.key} is not downloaded") from missing
    return Path(snapshot_download(spec.repo, revision=spec.revision, cache_dir=models_dir))


def is_downloaded(spec: WhisperModelSpec, models_dir: Path) -> bool:
    try:
        model_path(spec, models_dir, download=False)
    except EngineError:
        return False
    return True


class FasterWhisperEngine:
    """ASREngine on faster-whisper. Thread-safe: one decode at a time."""

    def __init__(
        self,
        models_dir: Path,
        device: Device = "auto",
        gpu_model: str = GPU_MODEL,
        cpu_model: str = CPU_MODEL,
        download: bool = True,
    ) -> None:
        self.name = "faster-whisper"
        self._models_dir = models_dir
        self._device = device
        self._gpu_model = WHISPER_MODELS[gpu_model]
        self._cpu_model = WHISPER_MODELS[cpu_model]
        self._download = download
        self._model: Any = None
        self._lock = threading.Lock()
        self.device_used: str | None = None
        self.model_used: str | None = None
        self.gpu_error: str | None = None  # why "auto" fell back to the CPU

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def needs_download(self) -> WhisperModelSpec | None:
        """The model `load()` would have to download first (for a status message)."""
        use_gpu = self._device == "cuda" or (self._device == "auto" and cuda_device_count() > 0)
        spec = self._gpu_model if use_gpu else self._cpu_model
        return None if is_downloaded(spec, self._models_dir) else spec

    def _open(self, spec: WhisperModelSpec, device: str, compute_type: str) -> Any:
        ensure_av_importable()
        from faster_whisper import WhisperModel

        path = model_path(spec, self._models_dir, download=self._download)
        return WhisperModel(str(path), device=device, compute_type=compute_type)

    def load(self) -> None:
        if self._model is not None:
            return
        if self._device in ("auto", "cuda") and cuda_device_count() > 0:
            add_cuda_dll_dirs()
            try:
                model = self._open(self._gpu_model, "cuda", "int8_float16")
                self._warm_up(model)
            except Exception as exc:  # missing cuBLAS/cuDNN, out of VRAM, driver issues
                if self._device == "cuda":
                    raise EngineError(f"GPU speech model failed: {type(exc).__name__}") from exc
                self.gpu_error = f"{type(exc).__name__}: {exc}"
            else:
                self._model, self.device_used, self.model_used = model, "cuda", self._gpu_model.key
                return
        elif self._device == "cuda":
            raise EngineError("no CUDA GPU found")
        model = self._open(self._cpu_model, "cpu", "int8")
        self._model, self.device_used, self.model_used = model, "cpu", self._cpu_model.key

    @staticmethod
    def _warm_up(model: Any) -> None:
        silence = np.zeros(int(WARMUP_S * SAMPLE_RATE), dtype=np.float32)
        segments, _ = model.transcribe(silence, language="en", beam_size=1, vad_filter=False)
        list(segments)

    def unload(self) -> None:
        with self._lock:
            self._model = None
            self.device_used = self.model_used = None

    def detect_language(self, audio: Audio, candidates: Sequence[str]) -> tuple[str, float]:
        """The likeliest of `candidates` for this audio and its share of their combined
        probability (Whisper scores every language; 1.0 = certain among them)."""
        shares = self.language_scores(audio, candidates)
        pick = max(candidates, key=lambda code: shares.get(code, 0.0))
        return pick, shares.get(pick, 0.0)

    def language_scores(self, audio: Audio, candidates: Sequence[str]) -> dict[str, float]:
        """Each candidate's share of the candidates' combined probability (sums to 1)."""
        with self._lock:
            model = self._model
            if model is None:
                raise EngineNotLoaded("load() the speech model first")
            _language, _probability, scores = model.detect_language(audio)
        by_code = dict(scores)
        total = sum(by_code.get(code, 0.0) for code in candidates)
        return {code: (by_code.get(code, 0.0) / total if total else 0.0) for code in candidates}

    def transcribe(
        self,
        audio: Audio,
        *,
        language: str | None = None,
        prompt: str | None = None,
        final: bool = False,
    ) -> Transcription:
        with self._lock:
            model = self._model
            if model is None:
                raise EngineNotLoaded("load() the speech model first")
            options: dict[str, Any] = {
                "language": language,
                "initial_prompt": prompt,
                "word_timestamps": True,
                "vad_filter": False,  # our own VAD already cut the utterance
                "condition_on_previous_text": False,
                "beam_size": FINAL_BEAM if final else PARTIAL_BEAM,
            }
            if not final:
                options["temperature"] = 0.0  # no fallback re-decodes for partials
            segments, info = model.transcribe(audio, **options)
            converted = tuple(_segment(s) for s in segments)
        return Transcription(converted, info.language, info.language_probability)


def _segment(segment: Any) -> Segment:
    words = tuple(
        Word(w.word, float(w.start), float(w.end), float(w.probability))
        for w in (segment.words or ())
    )
    return Segment(
        segment.text,
        float(segment.start),
        float(segment.end),
        words,
        float(segment.avg_logprob),
        float(segment.no_speech_prob),
    )
