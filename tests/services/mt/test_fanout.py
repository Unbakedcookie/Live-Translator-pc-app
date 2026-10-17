"""T053 — fan-out, partial throttle, stale-job skipping, worker thread (Tier A, pytest-qt)."""

from collections.abc import Sequence

import pytest

from livetranslator.app.translation_controller import (
    TranslationController,
    source_language,
    target_languages,
)
from livetranslator.core import actions as a
from livetranslator.core.state import AppConfig, AppState, Source, Utterance, WindowConfig
from livetranslator.core.store import Store
from livetranslator.services.errors import UnsupportedLanguage
from livetranslator.services.mt.router import TranslationRouter

WINDOWS = (
    WindowConfig(id="w1", target_lang="en", sources=(Source.OTHERS,)),
    WindowConfig(id="w2", target_lang="ja", sources=(Source.ME, Source.OTHERS)),
    WindowConfig(id="w3", target_lang="en", sources=(Source.SCREEN,)),
)


class CountingEngine:
    name = "fake"
    is_loaded = True

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def supports(self, src: str, tgt: str) -> bool:
        return src != "xx"

    def load(self) -> None:
        pass

    def unload(self) -> None:
        pass

    def translate(self, texts: Sequence[str], src: str, tgt: str) -> list[str]:
        if src == "xx":
            raise UnsupportedLanguage("xx")
        self.calls.extend((t, src, tgt) for t in texts)
        return [f"{tgt}:{t}" for t in texts]


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


@pytest.fixture
def env(qapp):
    store = Store(AppState(config=AppConfig(my_language="en", windows=WINDOWS)))
    engine = CountingEngine()
    clock = Clock()
    controller = TranslationController(store, TranslationRouter([engine]), clock=clock)
    return store, engine, controller, clock


def utt(uid: str, source: Source, text: str, lang: str | None, final: bool) -> Utterance:
    return Utterance(
        id=uid, source=source, speaker_id=str(source), start=0.0, committed=text,
        language=lang, is_final=final,
    )  # fmt: skip


def test_targets_and_source_language():
    config = AppConfig(my_language="de", windows=WINDOWS)
    assert target_languages(Source.OTHERS, config) == {"en", "ja"}
    assert target_languages(Source.ME, config) == {"ja"}
    assert target_languages(Source.SCREEN, config) == {"en"}
    assert source_language(utt("u", Source.ME, "hallo", None, True), config) == "de"
    assert source_language(utt("u", Source.OTHERS, "hola", None, True), config) is None
    assert source_language(utt("u", Source.OTHERS, "hola", "es", True), config) == "es"


def test_final_others_line_fans_out_once_per_language(env):
    store, engine, controller, _ = env
    store.dispatch(a.AddUtterance(utt("u1", Source.OTHERS, "hola amigos", "es", True)))
    assert controller.worker.run_pending() == 2
    assert sorted(engine.calls) == [("hola amigos", "es", "en"), ("hola amigos", "es", "ja")]
    assert store.state.session.utterance("u1").translations == {
        "en": "en:hola amigos",
        "ja": "ja:hola amigos",
    }


def test_partials_ignored_unless_enabled(env):
    store, _engine, controller, _ = env
    store.dispatch(a.AddUtterance(utt("u1", Source.OTHERS, "hola", "es", False)))
    assert controller.worker.run_pending() == 0


def test_partial_throttle_two_per_second(env):
    store, engine, controller, clock = env
    controller.translate_partials = True
    store.dispatch(a.AddUtterance(utt("u1", Source.ME, "w0", "en", False)))  # t = 0.0 -> sent
    for step in range(1, 11):  # t = 0.1 .. 1.0, text changes every 100 ms
        clock.t = step / 10
        store.dispatch(a.UpdateUtterance("u1", {"committed": f"w{step}"}))
    # Sent at t = 0.0, 0.5 and 1.0 only (>= 0.5 s apart). ME -> {ja} = 1 target each.
    assert controller.worker.run_pending() == 3
    # Only the newest text is still current; older jobs are skipped, not painted.
    assert engine.calls == [("w10", "en", "ja")]


def test_final_bypasses_throttle(env):
    store, engine, controller, clock = env
    controller.translate_partials = True
    store.dispatch(a.AddUtterance(utt("u1", Source.ME, "hello", "en", False)))
    controller.worker.run_pending()
    clock.t = 0.1
    store.dispatch(a.UpdateUtterance("u1", {"committed": "hello there", "is_final": True}))
    controller.worker.run_pending()
    assert engine.calls[-1] == ("hello there", "en", "ja")


def test_unknown_source_language_is_skipped(env):
    store, _engine, controller, _ = env
    store.dispatch(a.AddUtterance(utt("u1", Source.OTHERS, "???", None, True)))
    assert controller.worker.run_pending() == 0


def test_engine_error_does_not_crash(env):
    store, _engine, controller, _ = env
    store.dispatch(a.AddUtterance(utt("u1", Source.OTHERS, "zzz", "xx", True)))
    controller.worker.run_pending()  # UnsupportedLanguage logged, nothing dispatched
    assert store.state.session.utterance("u1").translations == {}


def test_real_worker_thread_delivers_on_main_thread(env, qtbot):
    store, _engine, controller, _ = env
    controller.start()
    try:
        with qtbot.waitSignal(store.utterance_updated, timeout=3000):
            store.dispatch(a.AddUtterance(utt("u1", Source.SCREEN, "Quête terminée", "fr", True)))
        assert store.state.session.utterance("u1").translations == {"en": "en:Quête terminée"}
    finally:
        controller.stop()


def test_same_language_passes_through_unchanged(env):
    store, engine, controller, _ = env
    store.dispatch(a.AddUtterance(utt("u1", Source.SCREEN, "Quest complete", "en", True)))
    controller.worker.run_pending()
    assert store.state.session.utterance("u1").translations == {"en": "Quest complete"}
    assert engine.calls == []


def test_result_does_not_retrigger_translation(env):
    # Regression: SetTranslation emits utterance_updated; it must not re-submit the line.
    store, _engine, controller, _ = env
    store.dispatch(a.AddUtterance(utt("u1", Source.OTHERS, "hola", "es", True)))
    assert controller.worker.run_pending() == 2
    assert controller.worker.run_pending() == 0
