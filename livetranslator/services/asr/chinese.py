"""One Chinese script for recognised speech (Mandarin follow-up, 2026-10-18).

Whisper sometimes writes Mandarin in Traditional characters, or mixes both inside one line
(seen in the T045 live check). Lines are normalised with OpenCC (Apache-2.0) to the script
the user picked in Settings: Simplified (mainland, the default) or Traditional (Taiwan
standard). The converter is created on first use; it maps characters and common phrases and
leaves anything that isn't Chinese untouched.
"""

from __future__ import annotations

import threading
from typing import Any, Literal

ChineseScript = Literal["simplified", "traditional"]
_CONFIGS: dict[str, str] = {"simplified": "t2s", "traditional": "s2tw"}
_converters: dict[str, Any] = {}
_lock = threading.Lock()


def is_chinese(language: str | None) -> bool:
    return language is not None and language.split("-", 1)[0].lower() == "zh"


def to_script(text: str, script: ChineseScript) -> str:
    if not text:
        return text
    with _lock:
        converter = _converters.get(script)
        if converter is None:
            import opencc  # lazy: only when Chinese is actually heard

            converter = opencc.OpenCC(_CONFIGS[script])
            _converters[script] = converter
    return str(converter.convert(text))
