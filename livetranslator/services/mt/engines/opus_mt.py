"""Helsinki-NLP Opus-MT on CTranslate2 (T051; spec §5.5; D-031).

One small Marian model per direction (≈ 75 MB each at int8), converted to CTranslate2 by
`benchmarks/opus_convert.py` into `<models>/opus-mt/<src>-<tgt>/` together with its
SentencePiece models, an `opus_mt.json` (repo, revision, licence, target-language tag) and the
attribution file. Pairs load lazily on first use, so only the directions in use take VRAM.
Missing pairs are pivoted through English by the router (T052).
"""

from __future__ import annotations

import json
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from livetranslator.platform.cuda import add_cuda_dll_dirs, cuda_device_count
from livetranslator.services.errors import EngineNotLoaded, UnsupportedLanguage

Device = Literal["auto", "cuda", "cpu"]
FOLDER = "opus-mt"
BEAM = 4
MAX_TOKENS = 256
EOS = "</s>"


@dataclass(frozen=True)
class OpusPair:
    src: str
    tgt: str
    path: Path
    language_tag: str  # e.g. ">>cmn_Hans<<" for multi-target models, else ""


def installed_pairs(models_dir: Path) -> dict[tuple[str, str], OpusPair]:
    pairs: dict[tuple[str, str], OpusPair] = {}
    root = models_dir / FOLDER
    if not root.is_dir():
        return pairs
    for folder in sorted(root.iterdir()):
        meta = folder / "opus_mt.json"
        if not (folder / "model.bin").is_file() or not meta.is_file() or "-" not in folder.name:
            continue
        src, tgt = folder.name.split("-", 1)
        info: dict[str, Any] = json.loads(meta.read_text(encoding="utf-8"))
        pairs[(src, tgt)] = OpusPair(src, tgt, folder, str(info.get("language_tag", "")))
    return pairs


class OpusMtEngine:
    """TranslationEngine over the installed Opus-MT pairs. Thread-safe."""

    def __init__(self, models_dir: Path, device: Device = "auto") -> None:
        self.name = "opus-mt"
        self._pairs = installed_pairs(models_dir)
        self._device_choice: Device = device
        self.device: str | None = None
        self._models: dict[tuple[str, str], tuple[Any, Any, Any]] = {}
        self._lock = threading.Lock()

    @property
    def is_loaded(self) -> bool:
        return self.device is not None

    def pairs(self) -> list[tuple[str, str]]:
        return sorted(self._pairs)

    def supports(self, src: str, tgt: str) -> bool:
        return (src, tgt) in self._pairs

    def load(self) -> None:
        if self.device is not None:
            return
        self.device = self._pick_device(self._device_choice)

    @staticmethod
    def _pick_device(choice: Device) -> str:
        use_gpu = choice == "cuda" or (choice == "auto" and cuda_device_count() > 0)
        if use_gpu:
            add_cuda_dll_dirs()
        return "cuda" if use_gpu else "cpu"

    def set_device(self, choice: Device) -> bool:
        """Move to the processor or back (game mode, T092). Loaded pairs are dropped (returns
        True then) and reload on first use on the new device. Done under the translate lock, so
        a line being translated finishes first and the next never sees a half-switched engine."""
        device = self._pick_device(choice)
        with self._lock:
            if choice == self._device_choice:
                return False
            self._device_choice = choice
            if self.device is None:
                return False  # not loaded yet: load() will use the new choice
            self._models.clear()
            self.device = device
            return True

    def unload(self) -> None:
        with self._lock:
            self._models.clear()
            self.device = None

    def _model(self, pair: OpusPair) -> tuple[Any, Any, Any]:
        key = (pair.src, pair.tgt)
        cached = self._models.get(key)
        if cached is not None:
            return cached
        import ctranslate2
        import sentencepiece

        compute = "int8_float16" if self.device == "cuda" else "int8"
        translator = ctranslate2.Translator(
            str(pair.path), device=self.device or "cpu", compute_type=compute
        )
        source = sentencepiece.SentencePieceProcessor(model_file=str(pair.path / "source.spm"))
        target = sentencepiece.SentencePieceProcessor(model_file=str(pair.path / "target.spm"))
        loaded = (translator, source, target)
        self._models[key] = loaded
        return loaded

    def warm(self, src: str, tgt: str) -> bool:
        """Load a pair ahead of its first line (~0.9 s on the GPU, ~2 s on the processor).
        Any thread; False if the pair isn't installed or the engine isn't loaded."""
        pair = self._pairs.get((src, tgt))
        if pair is None:
            return False
        with self._lock:
            if self.device is None:
                return False
            self._model(pair)
        return True

    def translate(self, texts: Sequence[str], src: str, tgt: str) -> list[str]:
        pair = self._pairs.get((src, tgt))
        if pair is None:
            raise UnsupportedLanguage(f"no Opus-MT model for {src} -> {tgt}")
        with self._lock:
            if self.device is None:
                raise EngineNotLoaded("load() the translation engine first")
            translator, source, target = self._model(pair)
            prefix = [pair.language_tag] if pair.language_tag else []
            batch = [[*prefix, *source.encode(text, out_type=str), EOS] for text in texts]
            results = translator.translate_batch(
                batch, beam_size=BEAM, max_decoding_length=MAX_TOKENS
            )
        return [str(target.decode(r.hypotheses[0])) for r in results]
