"""Errors shared by every engine (T016). Messages are plain language, never transcript text."""

from __future__ import annotations


class EngineError(RuntimeError):
    """An engine failed in a way the user may need to act on (spec §9)."""


class EngineNotLoaded(EngineError):
    """`load()` has not been called, or the engine was unloaded."""


class UnsupportedLanguage(EngineError):
    """The engine can't handle this language or language pair."""
