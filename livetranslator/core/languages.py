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
    Language("vi", "Vietnamese", "Tiếng Việt"),  # user request 2026-10-18
)

# Heard in voice chat and named in the Language Manager / Qwen prompts, but not offered as
# window targets by default (T074, 2026-10-18: unknown codes used to read "UR", and Qwen was
# asked to translate "from UR").
OTHER_LANGUAGES: tuple[Language, ...] = (
    Language("id", "Indonesian", "Bahasa Indonesia"),
    Language("th", "Thai", "ไทย"),
    Language("nl", "Dutch", "Nederlands"),
    Language("sv", "Swedish", "Svenska"),
    Language("fi", "Finnish", "Suomi"),
    Language("da", "Danish", "Dansk"),
    Language("no", "Norwegian", "Norsk"),
    Language("ur", "Urdu", "اردو"),
    Language("tl", "Tagalog", "Tagalog"),
    Language("cs", "Czech", "Čeština"),
    Language("hu", "Hungarian", "Magyar"),
    Language("he", "Hebrew", "עברית"),
    Language("el", "Greek", "Ελληνικά"),
    Language("bn", "Bengali", "বাংলা"),
    Language("ta", "Tamil", "தமிழ்"),
    Language("te", "Telugu", "తెలుగు"),
    Language("mr", "Marathi", "मराठी"),
    Language("fa", "Persian", "فارسی"),
    Language("ms", "Malay", "Bahasa Melayu"),
    Language("sr", "Serbian", "Српски"),
    Language("hr", "Croatian", "Hrvatski"),
    Language("bs", "Bosnian", "Bosanski"),
    Language("sk", "Slovak", "Slovenčina"),
    Language("sl", "Slovenian", "Slovenščina"),
    Language("ro", "Romanian", "Română"),
    Language("bg", "Bulgarian", "Български"),
    Language("ca", "Catalan", "Català"),
    Language("lt", "Lithuanian", "Lietuvių"),
    Language("lv", "Latvian", "Latviešu"),
    Language("et", "Estonian", "Eesti"),
    Language("sw", "Swahili", "Kiswahili"),
)

_BY_CODE = {lang.code: lang for lang in (*DEFAULT_LANGUAGES, *OTHER_LANGUAGES)}


def language(code: str) -> Language:
    """Catalog entry for `code`; unknown codes get a neutral entry using the code itself."""
    found = _BY_CODE.get(code.split("-", 1)[0].lower())
    return found if found is not None else Language(code, code.upper(), code.upper())
