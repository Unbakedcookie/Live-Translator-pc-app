"""Screen translation flow (T083; spec §5.6).

capture(region) runs off the UI thread: grab the pixels → read the text (first engine that
finds any) → detect each line's language → add one finished "Screen" line per new text line.
The translation controller then translates them like speech.

- One line per OCR line: the main use is game chat, where every row is its own message.
- Re-capturing the same chat only adds rows not already shown (recent Screen lines).
- The first time, if no window shows Screen lines, one opens next to the region.
- Nothing is saved: the image is dropped after reading (spec §5.11).
"""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable, Sequence

from loguru import logger

from livetranslator.core import actions as a
from livetranslator.core.state import Source, StatusLevel, Utterance
from livetranslator.core.store import Store
from livetranslator.services.errors import EngineError
from livetranslator.services.langdetect import detect
from livetranslator.services.ocr.base import Image, OcrEngine, OcrResult
from livetranslator.services.ocr.grab import Region

STATUS_KEY = "ocr"
RECENT = 40  # how many recent Screen lines a re-capture is compared against
Grab = Callable[[Region], Image]
OpenWindow = Callable[[Region], None]


def normalized_line(text: str) -> str:
    return " ".join(text.split()).casefold()


def new_lines(texts: Sequence[str], recent: Sequence[str]) -> list[str]:
    """Rows not already shown (case/space-insensitive), in order, without repeats."""
    seen = {normalized_line(t) for t in recent}
    out: list[str] = []
    for text in texts:
        key = normalized_line(text)
        if key and key not in seen:
            seen.add(key)
            out.append(text.strip())
    return out


class OcrController:
    def __init__(
        self,
        store: Store,
        engines: Sequence[OcrEngine],
        grab: Grab,
        open_screen_window: OpenWindow,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._store = store
        self._engines = list(engines)
        self._grab = grab
        self._open_window = open_screen_window
        self._clock = clock
        self.last_region: Region | None = None
        self._busy = threading.Lock()

    # ------------------------------------------------------------ entry points (UI thread)

    def capture(self, region: Region) -> None:
        if region.is_empty:
            return
        self.last_region = region
        if not any(Source.SCREEN in w.sources for w in self._store.state.config.windows):
            self._open_window(region)
        threading.Thread(target=self.run, args=(region,), name="ocr", daemon=True).start()

    def recapture(self) -> bool:
        """The re-capture hotkey: the last region again. False if there is none yet."""
        if self.last_region is None:
            self._status(StatusLevel.WARNING, "Pick a screen region first (screen hotkey).")
            return False
        self.capture(self.last_region)
        return True

    # ------------------------------------------------------------ work (any thread)

    def run(self, region: Region) -> int:
        """Read `region` and add its new lines. Returns how many were added."""
        if not self._busy.acquire(blocking=False):
            return 0  # a capture is still running: ignore the extra key press
        try:
            self._status(StatusLevel.BUSY, "Reading the screen…")
            try:
                image = self._grab(region)
            except Exception as exc:
                logger.warning("screen grab failed ({})", type(exc).__name__)
                self._status(StatusLevel.WARNING, "Couldn't capture that part of the screen.")
                return 0
            result = self._read(image)
            if result is None:
                self._status(StatusLevel.WARNING, "No screen-text reader is available.")
                return 0
            return self._add(result)
        finally:
            self._busy.release()

    def _read(self, image: Image) -> OcrResult | None:
        last: OcrResult | None = None
        for engine in self._engines:
            try:
                result = engine.recognize(image)
            except EngineError as exc:
                logger.info("{} couldn't read ({})", engine.name, type(exc).__name__)
                continue
            if result.text.strip():
                return result
            last = result
        return last

    def _add(self, result: OcrResult) -> int:
        state = self._store.state
        recent = [u.text for u in state.session.utterances if u.source is Source.SCREEN][-RECENT:]
        rows = new_lines([line.text for line in result.lines], recent)
        if not rows:
            message = "No new text there." if result.lines else "No text found there."
            self._status(StatusLevel.OK, message)
            return 0
        hint = state.config.my_language
        now = self._clock()
        actions: list[a.Action] = []
        for i, text in enumerate(rows):
            language = detect(text, hint=result.language or hint)
            utterance = Utterance(
                id=f"ocr-{uuid.uuid4().hex[:8]}",
                source=Source.SCREEN,
                speaker_id="screen",
                start=now + i * 1e-3,  # keeps the rows in screen order
                end=now + i * 1e-3,
                committed=text,
                language=language,
                is_final=True,
            )
            actions.append(a.AddUtterance(utterance))
        for action in actions:
            self._store.dispatch(action)
        self._store.dispatch(a.ClearStatus(STATUS_KEY))
        return len(rows)

    def _status(self, level: StatusLevel, message: str) -> None:
        self._store.dispatch(a.SetStatus(STATUS_KEY, level, message))
