"""Which status an overlay shows (T111; spec §9 "shown in the window footer").

One line at most: the most serious current problem. Errors before warnings before "busy"
(loading); OK statuses are never shown. Shortcut conflicts (`hotkey.*`) stay in Settings →
Hotkeys: they're permanent on some PCs and would sit in every window forever.
"""

from __future__ import annotations

from collections.abc import Mapping

from livetranslator.core.state import RuntimeStatus, StatusLevel

_RANK = {StatusLevel.ERROR: 0, StatusLevel.WARNING: 1, StatusLevel.BUSY: 2}
HIDDEN_PREFIXES = ("hotkey.",)


def headline(statuses: Mapping[str, RuntimeStatus]) -> RuntimeStatus | None:
    shown = [
        (key, status)
        for key, status in statuses.items()
        if status.level in _RANK and not key.startswith(HIDDEN_PREFIXES)
    ]
    if not shown:
        return None
    return min(shown, key=lambda item: (_RANK[item[1].level], item[0]))[1]
