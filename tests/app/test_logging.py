"""T011 — logs never contain transcript text (Tier A; spec §5.11)."""

from pathlib import Path

from loguru import logger

from livetranslator.app.log import log_uncaught, no_transcript, setup_logging


def test_filter_cases():
    assert no_transcript({"extra": {}}) is True
    assert no_transcript({"extra": {"transcript": False}}) is True
    assert no_transcript({"extra": {"transcript": True}}) is False
    assert no_transcript({"extra": {"utterance_id": 7}}) is True


def _flush_and_read(log_file: Path) -> str:
    logger.complete()
    logger.remove()
    return log_file.read_text(encoding="utf-8")


def test_transcript_records_never_reach_the_file(tmp_path: Path):
    log_file = setup_logging(tmp_path / "logs")
    logger.info("engine loaded in {} ms", 812)
    logger.bind(transcript=True).info("hola, ¿cómo estás?")
    logger.bind(utterance_id=7).info("utterance {} final, {} chars", 7, 18)
    text = _flush_and_read(log_file)
    assert "engine loaded in 812 ms" in text
    assert "utterance 7 final, 18 chars" in text
    assert "cómo" not in text


def test_tracebacks_do_not_show_local_values(tmp_path: Path):
    log_file = setup_logging(tmp_path)

    def translate() -> None:
        utterance = "my secret sentence"
        raise RuntimeError(f"engine failed after {len(utterance)} chars")

    try:
        translate()
    except RuntimeError:
        logger.exception("translation crashed")
    text = _flush_and_read(log_file)
    assert "translation crashed" in text
    assert "engine failed after 18 chars" in text
    assert "my secret sentence" not in text


def test_log_file_location(tmp_path: Path):
    assert setup_logging(tmp_path / "x") == tmp_path / "x" / "livetranslator.log"


def test_uncaught_errors_log_where_but_not_what(tmp_path: Path):
    """Under pythonw an error in a menu action vanished; now it's logged, minus its message."""
    log_file = setup_logging(tmp_path)

    def open_settings() -> None:
        raise ValueError("the line said: my secret sentence")

    try:
        open_settings()
    except ValueError as exc:
        log_uncaught(type(exc), exc, exc.__traceback__)
    text = _flush_and_read(log_file)
    assert "unhandled ValueError at test_logging.py:" in text
    assert "open_settings" in text
    assert "secret" not in text
