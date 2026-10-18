"""T083 — screen grab conversion and Windows OCR on images drawn by the test."""

import sys
import unicodedata

import numpy as np
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter

from livetranslator.services.errors import UnsupportedLanguage
from livetranslator.services.ocr.base import OcrEngine
from livetranslator.services.ocr.grab import Region, bgra_to_rgb
from livetranslator.services.ocr.windows_ocr import (
    WindowsOcrEngine,
    base_code,
    join_cjk,
    upscale,
)


def render(text: str, size: int = 22, width: int = 640, height: int = 64) -> np.ndarray:
    """Light text on a dark game-chat-like background, as an RGB array."""
    image = QImage(width, height, QImage.Format.Format_RGB888)
    image.fill(QColor(20, 22, 30))
    painter = QPainter(image)
    font = QFont("Segoe UI")
    font.setPixelSize(size)
    painter.setFont(font)
    painter.setPen(QColor(235, 235, 235))
    painter.drawText(image.rect().adjusted(8, 0, -8, 0), Qt.AlignmentFlag.AlignVCenter, text)
    painter.end()
    ptr = image.constBits()
    rows = np.frombuffer(ptr, dtype=np.uint8).reshape(height, image.bytesPerLine())
    return rows[:, : width * 3].reshape(height, width, 3).copy()


def normalized(text: str) -> str:
    """Lower case, accents and punctuation removed, single spaces."""
    plain = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    kept = "".join(c if c.isalnum() else " " for c in plain.casefold())
    return " ".join(kept.split())


def test_bgra_to_rgb():
    raw = bytes([1, 2, 3, 255, 10, 20, 30, 255])  # two pixels, B G R A
    assert bgra_to_rgb(raw, 2, 1).tolist() == [[[3, 2, 1], [30, 20, 10]]]
    assert Region(0, 0, 0, 5).is_empty and not Region(0, 0, 1, 1).is_empty


def test_helpers():
    assert base_code("en-US") == "en" and base_code("ja") == "ja"
    assert join_cjk("門 で 待っ て て 、 OK go") == "門で待ってて、OK go"
    small = np.zeros((16, 30, 3), dtype=np.uint8)
    big, scale = upscale(small)
    assert scale == 3 and big.shape == (48, 90, 3)  # ceil(48 / 16) = 3
    tall = np.zeros((60, 10, 3), dtype=np.uint8)
    assert upscale(tall)[1] == 1


windows_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows.Media.Ocr")


@windows_only
def test_reads_english(qapp):
    engine = WindowsOcrEngine()
    assert isinstance(engine, OcrEngine)
    assert "en" in engine.available_languages()
    result = engine.recognize(render("Quest complete: return to town"), "en")
    assert normalized(result.text) == "quest complete return to town"
    assert result.language == "en" and result.lines[0].box[2] > 100


@windows_only
def test_reads_spanish_with_the_latin_pack(qapp):
    """Only en-US is installed here; it still reads Spanish words (accents may drop)."""
    result = WindowsOcrEngine().recognize(render("Vamos al puente del norte"), "en")
    assert normalized(result.text) == "vamos al puente del norte"


@windows_only
def test_small_text_is_upscaled_and_boxes_map_back(qapp):
    image = render("Party invite from Mika", size=11, width=260, height=18)
    result = WindowsOcrEngine().recognize(image, "en")
    assert "party invite" in normalized(result.text)
    x, y, w, h = result.lines[0].box
    assert 0 <= x < 40 and 0 <= y < 18 and w < 260 and 0 < h <= 18  # original pixels


@windows_only
def test_missing_language_pack_is_reported(qapp):
    engine = WindowsOcrEngine()
    if "ja" in engine.available_languages():
        pytest.skip("this PC has the Japanese OCR pack")
    with pytest.raises(UnsupportedLanguage):
        engine.recognize(render("テスト"), "ja")


def test_korean_keeps_its_spaces():
    assert join_cjk("문 앞에서 기다려") == "문 앞에서 기다려"
