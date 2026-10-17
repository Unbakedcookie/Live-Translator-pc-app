"""Speaker-embedding engine contract (T102; spec §5.13). No engine library imported here."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np
from numpy.typing import NDArray

SAMPLE_RATE = 16_000


@runtime_checkable
class SpeakerEmbedder(Protocol):
    name: str

    @property
    def is_loaded(self) -> bool: ...

    def load(self) -> None:
        """Load the model (slow; call from a worker thread)."""
        ...

    def unload(self) -> None: ...

    def embed(self, audio: NDArray[np.float32]) -> NDArray[np.float32]:
        """Voice fingerprint of 16 kHz mono audio (any length >= ~0.5 s)."""
        ...
