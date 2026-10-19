"""Logging setup (T011; spec §5.8, §5.11).

Privacy rule: logs never contain transcript text, speaker names or OCR text.
- Code must not put such text in log messages. Log ids, lengths and timings instead.
- Safety net: any record bound with `transcript=True` is dropped before reaching a sink.
- `diagnose=False` keeps loguru from printing local variable values in tracebacks, which
  could otherwise leak an utterance held in a variable.
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path
from types import TracebackType
from typing import Any

from loguru import logger

LOG_FILE = "livetranslator.log"
ROTATION = "5 MB"
RETENTION = "7 days"


def no_transcript(record: Any) -> bool:
    """loguru filter: keep the record unless it is marked as carrying transcript text."""
    return not record["extra"].get("transcript", False)


def setup_logging(log_dir: Path, *, level: str = "INFO", console: bool = False) -> Path:
    """Send logs to a rotating file in `log_dir` (and optionally stderr). Returns the file."""
    logger.remove()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / LOG_FILE
    logger.add(
        log_file,
        level=level,
        rotation=ROTATION,
        retention=RETENTION,
        encoding="utf-8",
        enqueue=True,
        backtrace=False,
        diagnose=False,
        filter=no_transcript,
    )
    if console and sys.stderr is not None:
        logger.add(sys.stderr, level=level, backtrace=False, diagnose=False, filter=no_transcript)
    return log_file


def log_uncaught(
    exc_type: type[BaseException], exc: BaseException, tb: TracebackType | None
) -> None:
    """sys.excepthook: an error inside a Qt slot (e.g. a menu action) is otherwise lost under
    pythonw, which has no console (user report 2026-10-18: "Settings doesn't appear"). Logs
    the error type and where it happened, never the message, which could quote a line."""
    del exc
    frames = traceback.extract_tb(tb)
    where = " <- ".join(f"{Path(f.filename).name}:{f.lineno} {f.name}" for f in reversed(frames))
    logger.error("unhandled {} at {}", exc_type.__name__, where or "?")


def install_excepthook() -> None:
    sys.excepthook = log_uncaught
