"""Translation engine contract (T016; spec §5.5). No engine library is imported here.

Languages are ISO 639-1 codes ("en", "ja", "zh"...). The router (T052) asks `supports()`
before calling and pivots through English when a direct pair is missing.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable


@runtime_checkable
class TranslationEngine(Protocol):
    name: str

    @property
    def is_loaded(self) -> bool: ...

    def supports(self, src: str, tgt: str) -> bool:
        """True if this engine can translate src -> tgt directly with installed models."""
        ...

    def load(self) -> None:
        """Load models (slow; call from a worker thread)."""
        ...

    def unload(self) -> None:
        """Free models and their VRAM."""
        ...

    def translate(self, texts: Sequence[str], src: str, tgt: str) -> list[str]:
        """Translate a batch, keeping order and length. Raises UnsupportedLanguage for a pair
        `supports()` rejects, and EngineNotLoaded before `load()`."""
        ...
