"""Screen OCR engine contract (T016; spec §5.6). No engine library is imported here.

Images are H x W x 3 uint8 RGB arrays (the grabber converts from the screen's BGRA). Boxes are
(x, y, width, height) in image pixels.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import numpy as np
from numpy.typing import NDArray

Image = NDArray[np.uint8]


@dataclass(frozen=True)
class OcrLine:
    text: str
    box: tuple[int, int, int, int]
    confidence: float | None = None


@dataclass(frozen=True)
class OcrResult:
    lines: tuple[OcrLine, ...]
    language: str | None = None  # the OCR language used, if the engine needs one

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines if line.text.strip())


@runtime_checkable
class OcrEngine(Protocol):
    name: str

    def available_languages(self) -> set[str]:
        """Languages this engine can read right now (e.g. installed Windows OCR packs)."""
        ...

    def recognize(self, image: Image, language: str | None = None) -> OcrResult:
        """Read text in `image`. Raises UnsupportedLanguage if `language` isn't available."""
        ...
