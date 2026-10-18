"""Translation worker thread (T053; spec §5.5, §6.4).

Jobs are (utterance id, text, src, tgt). The worker translates with the router and hands the
result to `on_result`; jobs whose text is outdated by the time they run (the speaker kept
talking) are skipped through `is_current`, so a slow engine never paints stale text.
`WarmJob`s pre-load a language pair's model through the same queue, so loading never races
a translation (D-015: the first line of a pair otherwise waits ~0.9 s for its model).
"""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass

from loguru import logger

from livetranslator.services.errors import EngineError
from livetranslator.services.mt.router import TranslationRouter


@dataclass(frozen=True)
class TranslationJob:
    utterance_id: str
    text: str
    src: str
    tgt: str


@dataclass(frozen=True)
class WarmJob:
    src: str
    tgt: str


ResultFn = Callable[[TranslationJob, str], None]
CurrentFn = Callable[[TranslationJob], bool]


class TranslationWorker:
    def __init__(
        self,
        router: TranslationRouter,
        on_result: ResultFn,
        is_current: CurrentFn = lambda job: True,
        on_error: Callable[[TranslationJob, Exception], None] | None = None,
    ) -> None:
        self._router = router
        self._on_result = on_result
        self._is_current = is_current
        self._on_error = on_error
        self._jobs: queue.Queue[TranslationJob | WarmJob | None] = queue.Queue()
        self._thread: threading.Thread | None = None

    def submit(self, job: TranslationJob | WarmJob) -> None:
        self._jobs.put(job)

    def run_pending(self) -> int:
        """Process queued jobs on the calling thread (tests, or a worker-less setup). Returns
        the number of translation jobs (pre-loads run too but aren't counted)."""
        done = 0
        while True:
            try:
                job = self._jobs.get_nowait()
            except queue.Empty:
                return done
            if job is None:
                return done
            self._handle(job)
            done += isinstance(job, TranslationJob)

    def _handle(self, job: TranslationJob | WarmJob) -> None:
        if isinstance(job, WarmJob):
            self._router.warm(job.src, job.tgt)
            return
        if not self._is_current(job):
            return
        try:
            text = self._router.translate(job.text, job.src, job.tgt)
        except EngineError as exc:
            logger.warning("translation {}->{} failed ({})", job.src, job.tgt, type(exc).__name__)
            if self._on_error is not None:
                self._on_error(job, exc)
            return
        if self._is_current(job):
            self._on_result(job, text)

    def _run(self) -> None:
        while True:
            job = self._jobs.get()
            if job is None:
                return
            try:
                self._handle(job)
            except Exception as exc:  # spec §9: one bad line must not stop translation
                logger.error("translation worker error ({})", type(exc).__name__)
                if isinstance(job, TranslationJob) and self._on_error is not None:
                    self._on_error(job, exc)

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("worker already started")
        self._thread = threading.Thread(target=self._run, name="mt-worker", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        if self._thread is not None:
            self._jobs.put(None)
            self._thread.join(timeout)
            self._thread = None
