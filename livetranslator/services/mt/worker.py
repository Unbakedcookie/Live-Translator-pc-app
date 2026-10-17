"""Translation worker thread (T053; spec §5.5, §6.4).

Jobs are (utterance id, text, src, tgt). The worker translates with the router and hands the
result to `on_result`; jobs whose text is outdated by the time they run (the speaker kept
talking) are skipped through `is_current`, so a slow engine never paints stale text.
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
        self._jobs: queue.Queue[TranslationJob | None] = queue.Queue()
        self._thread: threading.Thread | None = None

    def submit(self, job: TranslationJob) -> None:
        self._jobs.put(job)

    def run_pending(self) -> int:
        """Process queued jobs on the calling thread (tests, or a worker-less setup)."""
        done = 0
        while True:
            try:
                job = self._jobs.get_nowait()
            except queue.Empty:
                return done
            if job is None:
                return done
            self._handle(job)
            done += 1

    def _handle(self, job: TranslationJob) -> None:
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
            self._handle(job)

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
