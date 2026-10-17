"""Pick an engine per language pair, pivot through English when needed (T052; spec §5.5).

Engines are tried in preference order (the G4 default first). A pair no engine supports
directly is translated src -> en -> tgt if some engines cover both legs. src == tgt is passed
through untouched. Each leg is cached, so a repeated line costs no engine call.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from livetranslator.services.errors import UnsupportedLanguage
from livetranslator.services.mt.base import TranslationEngine
from livetranslator.services.mt.cache import TranslationCache

PIVOT = "en"


def base_language(code: str) -> str:
    """'zh-TW' -> 'zh'; region/script variants share a translation model for routing."""
    return code.split("-", 1)[0].lower()


@dataclass(frozen=True)
class Step:
    engine: TranslationEngine
    src: str
    tgt: str


class TranslationRouter:
    def __init__(
        self,
        engines: Sequence[TranslationEngine],
        cache: TranslationCache | None = None,
        pivot: str = PIVOT,
    ) -> None:
        self._engines = list(engines)
        self._cache = cache if cache is not None else TranslationCache()
        self._pivot = pivot

    def _direct(self, src: str, tgt: str) -> TranslationEngine | None:
        return next((e for e in self._engines if e.supports(src, tgt)), None)

    def route(self, src: str, tgt: str) -> tuple[Step, ...]:
        """The steps for src -> tgt: () for passthrough. Raises UnsupportedLanguage."""
        src, tgt = base_language(src), base_language(tgt)
        if src == tgt:
            return ()
        direct = self._direct(src, tgt)
        if direct is not None:
            return (Step(direct, src, tgt),)
        if self._pivot not in (src, tgt):
            first = self._direct(src, self._pivot)
            second = self._direct(self._pivot, tgt)
            if first is not None and second is not None:
                return (Step(first, src, self._pivot), Step(second, self._pivot, tgt))
        raise UnsupportedLanguage(f"no installed translation for {src} -> {tgt}")

    def supports(self, src: str, tgt: str) -> bool:
        try:
            self.route(src, tgt)
        except UnsupportedLanguage:
            return False
        return True

    def translate(self, text: str, src: str, tgt: str) -> str:
        for step in self.route(src, tgt):
            key = (step.engine.name, step.src, step.tgt, text)
            cached = self._cache.get(key)
            if cached is None:
                cached = step.engine.translate([text], step.src, step.tgt)[0]
                self._cache.put(key, cached)
            text = cached
        return text
