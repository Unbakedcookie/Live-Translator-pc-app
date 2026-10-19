"""RapidOCR engine (T083; spec §5.6; licences D-034).

The default PP-OCRv6 small models shipped inside the rapidocr wheel (~31 MB, Apache-2.0)
read Chinese (Simplified and Traditional), Japanese and Latin-script text in one pass, with
no language setting. Measured 2026-10-18: 8/8 Chinese game-chat lines exact, Japanese and
Spanish exact; Korean and Russian came out as garbage (they need other models), so those
aren't claimed.

Speed (2026-10-19, user saw a 5 s wait): RapidOCR's default scales the image's *short* side
up to 736 pixels, so a 780x130 chat strip became ~4400x736 before text detection (1.1-2 s).
`PARAMS` only shrinks images larger than 2560 pixels and skips the text-rotation check (game
text is upright): 120-175 ms, same text on Swedish, Chinese, Japanese and English strips.

Lines come back top to bottom; each box is the bounding rectangle of the model's polygon.
"""

from __future__ import annotations

import threading
from typing import Any

from livetranslator.services.errors import UnsupportedLanguage
from livetranslator.services.ocr.base import Image, OcrLine, OcrResult, merge_rows

PARAMS = {"Det.limit_type": "max", "Det.limit_side_len": 2560, "Global.use_cls": False}
# What the bundled multilingual model reads well (ko and ru excluded: measured garbage).
LANGUAGES = frozenset({"zh", "ja", "en", "es", "fr", "de", "it", "pt", "nl"})


def bounding_box(points: Any) -> tuple[int, int, int, int]:
    xs = [float(p[0]) for p in points]
    ys = [float(p[1]) for p in points]
    left, top = int(min(xs)), int(min(ys))
    return left, top, int(max(xs)) - left, int(max(ys)) - top


class RapidOcrEngine:
    name = "rapidocr"

    def __init__(self) -> None:
        self._engine: Any = None
        self._lock = threading.Lock()

    def available_languages(self) -> set[str]:
        return set(LANGUAGES)

    def recognize(self, image: Image, language: str | None = None) -> OcrResult:
        if language is not None and language.split("-", 1)[0] not in LANGUAGES:
            raise UnsupportedLanguage(f"RapidOCR's bundled model doesn't read {language}")
        with self._lock:  # one capture at a time; the model loads on first use (~0.1 s)
            if self._engine is None:
                from rapidocr import RapidOCR

                self._engine = RapidOCR(params=PARAMS)
            output = self._engine(image)
        texts = output.txts or ()
        boxes = output.boxes if output.boxes is not None else ()
        scores = output.scores or ()
        lines = [
            OcrLine(str(text), bounding_box(box), float(score))
            for text, box, score in zip(texts, boxes, scores, strict=False)
            if str(text).strip()
        ]
        return OcrResult(merge_rows(lines), None)  # one line per chat row
