"""T052 — routing, pivot, passthrough, cache (Tier A with fake engines)."""

from collections.abc import Sequence

import pytest

from livetranslator.services.errors import UnsupportedLanguage
from livetranslator.services.mt.cache import DEFAULT_SIZE, TranslationCache
from livetranslator.services.mt.router import TranslationRouter, base_language


class FakeEngine:
    is_loaded = True

    def __init__(self, name: str, pairs: set[tuple[str, str]]) -> None:
        self.name = name
        self.pairs = pairs
        self.calls: list[tuple[str, str, str]] = []

    def supports(self, src: str, tgt: str) -> bool:
        return (src, tgt) in self.pairs

    def load(self) -> None:
        pass

    def unload(self) -> None:
        pass

    def translate(self, texts: Sequence[str], src: str, tgt: str) -> list[str]:
        self.calls.extend((t, src, tgt) for t in texts)
        return [f"{tgt}({t})" for t in texts]


def test_direct_pair_prefers_first_engine():
    preferred = FakeEngine("madlad", {("es", "en"), ("ja", "ko")})
    fallback = FakeEngine("argos", {("es", "en")})
    router = TranslationRouter([preferred, fallback])
    assert router.translate("hola", "es", "en") == "en(hola)"
    assert preferred.calls == [("hola", "es", "en")] and fallback.calls == []


def test_pivot_through_english():
    argos = FakeEngine("argos", {("ja", "en"), ("en", "ko")})
    router = TranslationRouter([argos])
    steps = router.route("ja", "ko")
    assert [(s.src, s.tgt) for s in steps] == [("ja", "en"), ("en", "ko")]
    assert router.translate("こんにちは", "ja", "ko") == "ko(en(こんにちは))"


def test_pivot_can_mix_engines():
    a = FakeEngine("a", {("ja", "en")})
    b = FakeEngine("b", {("en", "ko")})
    steps = TranslationRouter([a, b]).route("ja", "ko")
    assert [s.engine.name for s in steps] == ["a", "b"]


def test_same_language_passes_through_without_engine():
    engine = FakeEngine("x", {("en", "es")})
    router = TranslationRouter([engine])
    assert router.route("en", "en") == ()
    assert router.translate("hi", "en-US", "en") == "hi"
    assert engine.calls == []


def test_unsupported_pair_raises_and_supports_reports():
    router = TranslationRouter([FakeEngine("x", {("en", "es")})])
    assert router.supports("en", "es")
    assert not router.supports("ja", "ko")
    with pytest.raises(UnsupportedLanguage):
        router.translate("x", "ja", "ko")


def test_cache_hit_avoids_engine_call():
    engine = FakeEngine("x", {("es", "en")})
    cache = TranslationCache()
    router = TranslationRouter([engine], cache)
    router.translate("hola", "es", "en")
    router.translate("hola", "es", "en")
    assert len(engine.calls) == 1
    assert (cache.hits, cache.misses) == (1, 1)


def test_lru_evicts_oldest():
    assert DEFAULT_SIZE == 1000
    cache = TranslationCache(maxsize=3)
    for i in range(3):
        cache.put(("e", "a", "b", str(i)), str(i))
    assert cache.get(("e", "a", "b", "0")) == "0"  # touch 0 -> 1 is now the oldest
    cache.put(("e", "a", "b", "3"), "3")
    assert cache.get(("e", "a", "b", "1")) is None
    assert [cache.get(("e", "a", "b", k)) for k in ("0", "2", "3")] == ["0", "2", "3"]
    assert len(cache) == 3


def test_default_cache_holds_1000():
    cache = TranslationCache()
    for i in range(1001):
        cache.put(("e", "a", "b", str(i)), str(i))
    assert len(cache) == 1000
    assert cache.get(("e", "a", "b", "0")) is None


def test_base_language():
    assert base_language("zh-TW") == "zh"
    assert base_language("EN") == "en"
