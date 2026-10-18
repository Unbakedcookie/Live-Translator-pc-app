# ruff: noqa: RUF001  (real Chinese punctuation on purpose)
"""T111 — after a scripted session, the log files hold no conversation text and no names."""

import sys
from pathlib import Path

import numpy as np
import pytest
from loguru import logger

from livetranslator.app.application import LiveTranslatorApp
from livetranslator.app.demo import SCRIPT, line_steps
from livetranslator.app.log import setup_logging
from livetranslator.app.ocr_controller import OcrController
from livetranslator.app.paths import app_paths
from livetranslator.core import actions as a
from livetranslator.services.ocr.base import OcrLine, OcrResult
from livetranslator.services.ocr.grab import Region

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="real app windows")

IMAGE = np.zeros((4, 4, 3), dtype=np.uint8)
SCREEN_TEXT = "队长：在桥那边集合"
SPEAKER_NAME = "Mikazuki"
DISCORD_NAME = "Shirogane"


class Reader:
    name = "fake"

    def available_languages(self) -> set[str]:
        return {"zh"}

    def recognize(self, image, language=None) -> OcrResult:
        return OcrResult((OcrLine(SCREEN_TEXT, (0, 0, 10, 10)),))


def test_logs_never_contain_what_was_said_or_who_said_it(qtbot, tmp_path: Path):
    paths = app_paths(tmp_path)
    log_file = setup_logging(paths.log_dir, level="DEBUG")
    live = LiveTranslatorApp(paths, lambda: None)
    try:
        for i, demo_line in enumerate(SCRIPT):  # one pass of the demo conversation
            for _, action in line_steps(demo_line, f"demo-{i}", float(i)):
                live.store.dispatch(action)
        live.store.dispatch(a.RenameSpeaker("voice:0", SPEAKER_NAME))
        live.discord.on_members({"42": DISCORD_NAME})
        ocr = OcrController(live.store, [Reader()], lambda region: IMAGE, lambda region: None)
        ocr.run(Region(0, 0, 10, 10))  # no real screen in a test
        live.open_transcript()
        logger.info("a normal log line still gets through")
    finally:
        live.shutdown()
        logger.complete()
    text = log_file.read_text(encoding="utf-8")
    logger.remove()  # leave no file handler pointing into tmp_path for later tests
    assert "a normal log line still gets through" in text  # the log works
    said = {SCREEN_TEXT, SPEAKER_NAME, DISCORD_NAME}
    for line in SCRIPT:
        said.add(line.text)
        said.update(line.translations.values())
    leaked = [s for s in said if s and s in text]
    assert leaked == []
