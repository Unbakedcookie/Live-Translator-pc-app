"""Windows.Media.Ocr engine (T083; spec §5.6, D-009) through the pywinrt projections.

Built into Windows 10/11, nothing to download, but it reads only the languages whose Windows
OCR pack is installed (on the user's PC on 2026-10-18: en-US only). Other languages go to the
RapidOCR fallback.

- Small text is upscaled first: Windows OCR misses glyphs under ~15 pixels tall.
- Japanese/Chinese results come back with spaces between characters; those are removed
  (Korean keeps its spaces: it is written with them).
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

import numpy as np

from livetranslator.services.errors import UnsupportedLanguage
from livetranslator.services.ocr.base import Image, OcrLine, OcrResult

MIN_HEIGHT = 48  # pixels; smaller captures are upscaled (whole multiples keep edges crisp)
MAX_SCALE = 4
# Japanese/Chinese punctuation, kana and Han (not Hangul: Korean is written with spaces).
_CJK = "[　-〿぀-ヿㇰ-ㇿ㐀-䶿一-鿿＀-￯]"
# A space next to such a character on either side (that text isn't written with spaces).
_CJK_GAP = re.compile(rf"(?<={_CJK}) | (?={_CJK})")


def base_code(tag: str) -> str:
    """'en-US' -> 'en'."""
    return tag.split("-", 1)[0].lower()


def upscale(image: Image) -> tuple[Image, int]:
    """Nearest-neighbour upscale so the capture is at least MIN_HEIGHT tall."""
    height = image.shape[0]
    if height >= MIN_HEIGHT:
        return image, 1
    scale = min(MAX_SCALE, -(-MIN_HEIGHT // max(height, 1)))
    return np.repeat(np.repeat(image, scale, axis=0), scale, axis=1), scale


def join_cjk(text: str) -> str:
    return _CJK_GAP.sub("", text)


class WindowsOcrEngine:
    name = "windows-ocr"

    def __init__(self) -> None:
        self._engines: dict[str, Any] = {}

    def _tags(self) -> dict[str, str]:
        from winrt.windows.media.ocr import OcrEngine

        return {
            base_code(lang.language_tag): lang.language_tag
            for lang in OcrEngine.available_recognizer_languages
        }

    def available_languages(self) -> set[str]:
        try:
            return set(self._tags())
        except Exception:  # WinRT unavailable (very old Windows): no languages
            return set()

    def _engine(self, language: str) -> Any:
        engine = self._engines.get(language)
        if engine is not None:
            return engine
        from winrt.windows.globalization import Language
        from winrt.windows.media.ocr import OcrEngine

        tag = self._tags().get(base_code(language))
        if tag is None:
            raise UnsupportedLanguage(f"Windows OCR has no {language} pack installed")
        engine = OcrEngine.try_create_from_language(Language(tag))
        if engine is None:
            raise UnsupportedLanguage(f"Windows OCR couldn't start for {language}")
        self._engines[language] = engine
        return engine

    def recognize(self, image: Image, language: str | None = None) -> OcrResult:
        code = base_code(language) if language else next(iter(sorted(self._tags())), None)
        if code is None:
            raise UnsupportedLanguage("no Windows OCR language is installed")
        engine = self._engine(code)
        scaled, scale = upscale(image)
        result = asyncio.run(_recognize(engine, _bitmap(scaled)))
        lines: list[OcrLine] = []
        for line in result.lines:
            text = join_cjk(line.text) if code in ("ja", "zh") else line.text
            rects = [w.bounding_rect for w in line.words]
            if rects:
                left = min(r.x for r in rects)
                top = min(r.y for r in rects)
                right = max(r.x + r.width for r in rects)
                bottom = max(r.y + r.height for r in rects)
                box = (
                    int(left / scale),
                    int(top / scale),
                    int((right - left) / scale),
                    int((bottom - top) / scale),
                )
            else:
                box = (0, 0, 0, 0)
            lines.append(OcrLine(text, box))
        return OcrResult(tuple(lines), code)


def _bitmap(image: Image) -> Any:
    from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
    from winrt.windows.storage.streams import DataWriter

    height, width, _ = image.shape
    alpha = np.full((height, width, 1), 255, dtype=np.uint8)
    bgra = np.concatenate([image[:, :, 2::-1], alpha], axis=2)
    writer = DataWriter()
    writer.write_bytes(np.ascontiguousarray(bgra).tobytes())
    return SoftwareBitmap.create_copy_from_buffer(
        writer.detach_buffer(), BitmapPixelFormat.BGRA8, width, height
    )


async def _recognize(engine: Any, bitmap: Any) -> Any:
    return await engine.recognize_async(bitmap)
