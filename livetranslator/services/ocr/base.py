"""Screen OCR engine contract (T016; spec §5.6). No engine library is imported here.

Images are H x W x 3 uint8 RGB arrays (the grabber converts from the screen's BGRA). Boxes are
(x, y, width, height) in image pixels.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
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


ROW_OVERLAP = 0.5  # boxes overlapping this much of the shorter one's height share a row
_CJK = re.compile(r"[぀-ヿ一-鿿가-힯]")


def _without_repeat(text: str, piece: str) -> str:
    """`piece` minus its start when that start repeats the end of `text` ("[Lag]" + "g] Erik"
    -> "Erik", measured 2026-10-19)."""
    for size in range(min(len(text), len(piece)), 0, -1):
        if text.endswith(piece[:size]):
            return piece[size:].lstrip()
    return piece


def merge_rows(lines: Sequence[OcrLine]) -> tuple[OcrLine, ...]:
    """Join boxes on the same row, left to right (2026-10-19: RapidOCR returned a chat tag
    "[Lag]" and the message after it as two boxes, so the tag became its own line). Rows come
    out top to bottom; CJK pieces are joined without a space."""
    rows: list[list[OcrLine]] = []
    for line in sorted(lines, key=lambda item: item.box[1]):
        top, height = line.box[1], line.box[3]
        for row in rows:
            r_top = min(item.box[1] for item in row)
            r_bottom = max(item.box[1] + item.box[3] for item in row)
            overlap = min(top + height, r_bottom) - max(top, r_top)
            if overlap >= ROW_OVERLAP * min(height, r_bottom - r_top):
                row.append(line)
                break
        else:
            rows.append([line])
    merged: list[OcrLine] = []
    for row in rows:
        row.sort(key=lambda item: item.box[0])
        text, right_edge = row[0].text, row[0].box[0] + row[0].box[2]
        for item in row[1:]:
            piece = item.text
            if item.box[0] < right_edge:  # boxes overlap: the shared letters were read twice
                piece = _without_repeat(text, piece)
            if piece:
                gap = "" if _CJK.search(text[-1:]) and _CJK.search(piece[:1]) else " "
                text = f"{text}{gap}{piece}"
            right_edge = max(right_edge, item.box[0] + item.box[2])
        left = min(item.box[0] for item in row)
        top = min(item.box[1] for item in row)
        right = max(item.box[0] + item.box[2] for item in row)
        bottom = max(item.box[1] + item.box[3] for item in row)
        scores = [item.confidence for item in row if item.confidence is not None]
        confidence = min(scores) if scores else None
        merged.append(OcrLine(text, (left, top, right - left, bottom - top), confidence))
    return tuple(merged)


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
