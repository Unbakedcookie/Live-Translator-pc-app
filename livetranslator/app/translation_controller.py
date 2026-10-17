"""Decides what to translate, into which languages, and when (T053; spec §5.5).

- Targets = the target languages of the windows that show the utterance's source. Each
  language is translated once, however many windows use it.
- Final lines are always translated. Partial lines only when `translate_partials` is on
  (engine fast enough and not game mode), at most `PARTIAL_RATE_HZ` times per second per line.
- The worker runs translations off the UI thread; results enter the store through the
  thread-safe dispatch. Jobs for text that has since changed are skipped.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from livetranslator.core import actions as a
from livetranslator.core.languages import language
from livetranslator.core.state import AppConfig, Source, StatusLevel, Utterance
from livetranslator.core.store import Store
from livetranslator.services.errors import UnsupportedLanguage
from livetranslator.services.mt.router import TranslationRouter
from livetranslator.services.mt.worker import TranslationJob, TranslationWorker

PARTIAL_RATE_HZ = 2.0
STATUS_KEY = "translation"


def target_languages(source: Source, config: AppConfig) -> set[str]:
    return {w.target_lang for w in config.windows if source in w.sources}


def source_language(utterance: Utterance, config: AppConfig) -> str | None:
    """Detected language, or "my language" for the mic when detection didn't report one."""
    if utterance.language:
        return utterance.language
    return config.my_language if utterance.source is Source.ME else None


class TranslationController:
    def __init__(
        self,
        store: Store,
        router: TranslationRouter,
        translate_partials: bool = False,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._store = store
        self.translate_partials = translate_partials
        self._clock = clock
        self._last_partial: dict[str, float] = {}
        # What was last sent per line. A translation result updates the utterance too, and
        # without this the update would re-submit the same text (found by test_fanout).
        self._submitted: dict[str, tuple[str, bool]] = {}
        self.worker = TranslationWorker(router, self.on_result, self.is_current, self.on_error)
        store.utterance_added.connect(self._on_utterance)
        store.utterance_updated.connect(self._on_utterance)
        store.utterance_removed.connect(self._forget)
        store.session_cleared.connect(self._clear)

    def start(self) -> None:
        self.worker.start()

    def stop(self) -> None:
        self.worker.stop()

    def _forget(self, utterance_id: str) -> None:
        self._last_partial.pop(utterance_id, None)
        self._submitted.pop(utterance_id, None)

    def _clear(self) -> None:
        self._last_partial.clear()
        self._submitted.clear()

    def _on_utterance(self, utterance_id: str) -> None:
        state = self._store.state
        utterance = state.session.utterance(utterance_id)
        if utterance is None or not utterance.text.strip():
            return
        snapshot = (utterance.text, utterance.is_final)
        if self._submitted.get(utterance_id) == snapshot:
            return  # e.g. our own SetTranslation result: nothing new to translate
        if utterance.is_final:
            self._last_partial.pop(utterance_id, None)
        else:
            if not self.translate_partials:
                return
            now = self._clock()
            last = self._last_partial.get(utterance_id)
            if last is not None and now - last < 1.0 / PARTIAL_RATE_HZ:
                return
            self._last_partial[utterance_id] = now
        src = source_language(utterance, state.config)
        if src is None:
            return
        self._submitted[utterance_id] = snapshot
        for tgt in sorted(target_languages(utterance.source, state.config)):
            self.worker.submit(TranslationJob(utterance_id, utterance.text, src, tgt))

    def is_current(self, job: TranslationJob) -> bool:
        """Still worth doing: the utterance exists and its text hasn't moved on."""
        utterance = self._store.state.session.utterance(job.utterance_id)
        return utterance is not None and utterance.text == job.text

    def on_error(self, job: TranslationJob, error: Exception) -> None:
        """Called on the worker thread; the store queues the status to the UI thread."""
        pair = f"{language(job.src).english} to {language(job.tgt).english}"
        if isinstance(error, UnsupportedLanguage):
            message = f"No translation model for {pair} yet, so those lines stay untranslated."
        else:
            message = f"Translating {pair} failed. Details are in the log."
        self._store.dispatch(a.SetStatus(STATUS_KEY, StatusLevel.WARNING, message))

    def on_result(self, job: TranslationJob, text: str) -> None:
        self._store.dispatch(a.SetTranslation(job.utterance_id, job.tgt, text, job.text))
