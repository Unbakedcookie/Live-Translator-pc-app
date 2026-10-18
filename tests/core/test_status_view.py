"""T111 — which status an overlay shows (Tier A)."""

from livetranslator.core.state import RuntimeStatus, StatusLevel
from livetranslator.core.status_view import headline


def s(level: StatusLevel, message: str) -> RuntimeStatus:
    return RuntimeStatus(level=level, message=message)


def test_most_serious_first_ok_never_shown():
    assert headline({}) is None
    assert headline({"asr": s(StatusLevel.OK, "ready")}) is None
    statuses = {
        "asr": s(StatusLevel.BUSY, "Loading…"),
        "audio.me": s(StatusLevel.WARNING, "No microphone found."),
        "translation": s(StatusLevel.ERROR, "Translation failed."),
    }
    assert headline(statuses) == statuses["translation"]
    del statuses["translation"]
    assert headline(statuses) == statuses["audio.me"]
    del statuses["audio.me"]
    assert headline(statuses) == statuses["asr"]


def test_ties_are_stable_and_shortcut_conflicts_stay_in_settings():
    statuses = {
        "z": s(StatusLevel.WARNING, "later key"),
        "a": s(StatusLevel.WARNING, "earlier key"),
        "hotkey.mute_me": s(StatusLevel.ERROR, "Ctrl+Alt+M is taken"),
    }
    assert headline(statuses) == statuses["a"]  # the hotkey error is never shown here
