"""Pick an engine per language pair, pivot through English when needed (T052; spec §5.5).

Engines are tried in preference order (the G4 default first). A pair no engine supports
directly is translated src -> en -> tgt if some engines cover both legs; failing that, the
`fallback` engine (Qwen, which knows many more languages) takes the pair whole. src == tgt is
passed through untouched. Each leg is cached, so a repeated line costs no engine call.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from loguru import logger

from livetranslator.services.errors import EngineError, UnsupportedLanguage
from livetranslator.services.mt.base import TranslationEngine
from livetranslator.services.mt.cache import TranslationCache
from livetranslator.services.timings import Timings

PIVOT = "en"
PreferFn = Callable[[str, str], TranslationEngine | None]  # (src, tgt) -> engine to try first


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
        timings: Timings | None = None,
        preferred: PreferFn | None = None,
        fallback: PreferFn | None = None,
    ) -> None:
        self._timings = timings
        self._preferred = preferred  # per-pair override (e.g. Qwen for Chinese)
        self._fallback = fallback  # pairs nothing installed covers (e.g. Qwen for Urdu)
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
        preferred = self._preferred(src, tgt) if self._preferred else None
        if preferred is not None and preferred.supports(src, tgt):
            return (Step(preferred, src, tgt),)
        try:
            return self._standard_route(src, tgt)
        except UnsupportedLanguage:
            fallback = self._fallback(src, tgt) if self._fallback else None
            if fallback is not None and fallback.supports(src, tgt):
                return (Step(fallback, src, tgt),)
            raise

    def _standard_route(self, src: str, tgt: str) -> tuple[Step, ...]:
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

    def warm(self, src: str, tgt: str) -> None:
        """Pre-load the model(s) for src -> tgt, each pivot leg included. Engines without a
        `warm` method, unsupported pairs and passthrough are skipped quietly."""
        try:
            steps = self.route(src, tgt)
        except UnsupportedLanguage:
            return
        for step in steps:
            warm = getattr(step.engine, "warm", None)
            if callable(warm):
                warm(step.src, step.tgt)

    def translate(self, text: str, src: str, tgt: str) -> str:
        steps = self.route(src, tgt)
        try:
            return self._run(steps, text)
        except EngineError as exc:
            if not steps or steps[0].engine in self._engines:
                raise
            # The preferred engine (e.g. Qwen's server) failed: the line still gets translated.
            logger.warning(
                "{} failed ({}); using the standard route", steps[0].engine.name, type(exc).__name__
            )
            return self._run(self._standard_route(base_language(src), base_language(tgt)), text)

    def _run(self, steps: tuple[Step, ...], text: str) -> str:
        start = time.perf_counter()
        engine_ran = False
        for step in steps:
            key = (step.engine.name, step.src, step.tgt, text)
            cached = self._cache.get(key)
            if cached is None:
                engine_ran = True
                cached = step.engine.translate([text], step.src, step.tgt)[0]
                self._cache.put(key, cached)
            text = cached
        if engine_ran and self._timings is not None:
            # T091: only real engine work counts (same-language lines and cache hits are free
            # and would drag the readout's p50 to 0 ms, as the first live run showed).
            self._timings.record("mt", time.perf_counter() - start)
        return text
