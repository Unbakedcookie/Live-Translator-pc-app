"""Font loading and per-script fallback stacks (T012; spec §5.5, §6.5).

Bundled: Inter (UI + Latin/Greek/Cyrillic overlay text) and Noto Sans (fallback), both
OFL-1.1, in theme/fonts/. Script-specific Noto fonts (JP/KR/SC/Arabic/...) arrive with
language packs (M05) and are registered from the models folder with the same function.
Qt walks the family list per glyph, so mixed-script lines render with the right font.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable
from pathlib import Path

from loguru import logger
from PySide6.QtGui import QFontDatabase

from livetranslator.theme.tokens import FONTS

FONTS_DIR = Path(__file__).resolve().parent / "fonts"

# Language (ISO 639-1, optionally with region/script) -> Noto family for its script.
SCRIPT_FAMILIES: dict[str, str] = {
    "ja": "Noto Sans JP",
    "ko": "Noto Sans KR",
    "zh": "Noto Sans SC",
    "zh-hant": "Noto Sans TC",
    "zh-tw": "Noto Sans TC",
    "zh-hk": "Noto Sans TC",
    "ar": "Noto Sans Arabic",
    "fa": "Noto Sans Arabic",
    "ur": "Noto Sans Arabic",
    "hi": "Noto Sans Devanagari",
    "mr": "Noto Sans Devanagari",
    "ne": "Noto Sans Devanagari",
    "th": "Noto Sans Thai",
    "he": "Noto Sans Hebrew",
    "bn": "Noto Sans Bengali",
}


def script_family(language: str | None) -> str | None:
    """Noto family needed for `language`, or None when Inter/Noto Sans already cover it."""
    if not language:
        return None
    code = language.lower().replace("_", "-")
    if code in SCRIPT_FAMILIES:
        return SCRIPT_FAMILIES[code]
    return SCRIPT_FAMILIES.get(code.split("-", 1)[0])


def overlay_families(
    user_family: str | None, language: str | None, available: Collection[str]
) -> list[str]:
    """Font family fallback list for overlay text: user choice -> Inter -> script Noto ->
    Noto Sans, keeping only installed families (case-insensitive) and dropping duplicates."""
    installed = {name.casefold(): name for name in available}
    stack: list[str] = []
    for family in (
        user_family,
        FONTS.overlay_family,
        script_family(language),
        FONTS.fallback_family,
    ):
        if family is None:
            continue
        resolved = installed.get(family.casefold())
        if resolved is not None and resolved not in stack:
            stack.append(resolved)
    return stack


def bundled_font_files() -> list[Path]:
    return sorted(FONTS_DIR.glob("*.ttf"))


def register_fonts(paths: Iterable[Path]) -> set[str]:
    """Register font files with Qt (needs a QGuiApplication). Returns the family names added."""
    families: set[str] = set()
    for path in paths:
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id == -1:
            logger.warning("font could not be loaded: {}", path.name)
            continue
        families.update(QFontDatabase.applicationFontFamilies(font_id))
    return families


def available_families() -> set[str]:
    return set(QFontDatabase.families())
