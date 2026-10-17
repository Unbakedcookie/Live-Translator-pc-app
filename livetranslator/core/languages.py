"""Language catalog (T022; spec §5.5, §13 Q3 approved 2026-10-17).

The ~15 default languages offered in pickers and the first-run wizard. More are added by the
Language Manager (M05/M07). Names are plain facts (English + endonym), not copied tables.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Language:
    code: str  # ISO 639-1
    english: str
    native: str

    @property
    def label(self) -> str:
        return self.english if self.english == self.native else f"{self.english} · {self.native}"


DEFAULT_LANGUAGES: tuple[Language, ...] = (
    Language("en", "English", "English"),
    Language("es", "Spanish", "Español"),
    Language("pt", "Portuguese", "Português"),
    Language("fr", "French", "Français"),
    Language("de", "German", "Deutsch"),
    Language("it", "Italian", "Italiano"),
    Language("ru", "Russian", "Русский"),
    Language("uk", "Ukrainian", "Українська"),
    Language("pl", "Polish", "Polski"),
    Language("tr", "Turkish", "Türkçe"),
    Language("ar", "Arabic", "العربية"),
    Language("hi", "Hindi", "हिन्दी"),
    Language("ja", "Japanese", "日本語"),
    Language("ko", "Korean", "한국어"),
    Language("zh", "Chinese", "中文"),
)

_BY_CODE = {lang.code: lang for lang in DEFAULT_LANGUAGES}


def language(code: str) -> Language:
    """Catalog entry for `code`; unknown codes get a neutral entry using the code itself."""
    found = _BY_CODE.get(code.split("-", 1)[0].lower())
    return found if found is not None else Language(code, code.upper(), code.upper())
