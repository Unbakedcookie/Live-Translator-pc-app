"""Speaker fingerprints with NeMo TitaNet through sherpa-onnx on the CPU (T102; T035; D-029).

TitaNet-large (CC-BY-4.0) takes ~0.1 s per line on the CPU and needs no graphics memory.
The model file lives in `<models>/speakers/`; see DATA_TRACKER for licences.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from livetranslator.services.errors import EngineError, EngineNotLoaded
from livetranslator.services.speakers.base import SAMPLE_RATE

FOLDER = "speakers"
TITANET_LARGE = "nemo_en_titanet_large.onnx"
THREADS = 2


def model_file(models_dir: Path, name: str = TITANET_LARGE) -> Path:
    return models_dir / FOLDER / name


class SherpaEmbedder:
    def __init__(self, models_dir: Path, model: str = TITANET_LARGE) -> None:
        self.name = f"sherpa-onnx {model}"
        self._path = model_file(models_dir, model)
        self._extractor: Any = None
        self._lock = threading.Lock()

    @property
    def is_loaded(self) -> bool:
        return self._extractor is not None

    def load(self) -> None:
        if self._extractor is not None:
            return
        if not self._path.is_file():
            raise EngineError(f"speaker model {self._path.name} is not installed")
        import sherpa_onnx

        config = sherpa_onnx.SpeakerEmbeddingExtractorConfig(
            model=str(self._path), num_threads=THREADS
        )
        self._extractor = sherpa_onnx.SpeakerEmbeddingExtractor(config)

    def unload(self) -> None:
        with self._lock:
            self._extractor = None

    def embed(self, audio: NDArray[np.float32]) -> NDArray[np.float32]:
        with self._lock:
            extractor = self._extractor
            if extractor is None:
                raise EngineNotLoaded("load() the speaker model first")
            stream = extractor.create_stream()
            stream.accept_waveform(SAMPLE_RATE, np.ascontiguousarray(audio, dtype=np.float32))
            stream.input_finished()
            vector = np.asarray(extractor.compute(stream), dtype=np.float32)
        return vector
