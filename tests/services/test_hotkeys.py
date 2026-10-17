"""T081 — hotkey parsing (Tier A, hand-checked virtual-key codes) and a live Win32 round trip."""

import ctypes
import sys

import pytest

from livetranslator.core.state import DEFAULT_HOTKEYS
from livetranslator.services.hotkeys import (
    MOD_ALT,
    MOD_CONTROL,
    MOD_SHIFT,
    MOD_WIN,
    Hotkey,
    HotkeyError,
    format_hotkey,
    parse_hotkey,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Ctrl+Alt+H", Hotkey(MOD_CONTROL | MOD_ALT, 0x48)),  # 'H' = 0x48
        ("ctrl + alt + t", Hotkey(MOD_CONTROL | MOD_ALT, 0x54)),  # 'T' = 0x54
        ("Shift+Win+5", Hotkey(MOD_SHIFT | MOD_WIN, 0x35)),  # '5' = 0x35
        ("Control+F1", Hotkey(MOD_CONTROL, 0x70)),
        ("F24", Hotkey(0, 0x87)),  # F-keys may stand alone
        ("Alt+PageDown", Hotkey(MOD_ALT, 0x22)),
        ("Meta+Space", Hotkey(MOD_WIN, 0x20)),
    ],
)
def test_parse(text, expected):
    assert parse_hotkey(text) == expected


@pytest.mark.parametrize(
    "text", ["", "Ctrl+", "Ctrl+Alt", "H", "Ctrl+H+J", "Ctrl+Banana", "++", "Alt++H"]
)
def test_parse_rejects(text):
    with pytest.raises(HotkeyError):
        parse_hotkey(text)


def test_format_is_canonical_and_round_trips():
    assert format_hotkey(parse_hotkey("alt+shift+ctrl+o")) == "Ctrl+Alt+Shift+O"
    for text in DEFAULT_HOTKEYS.values():
        assert format_hotkey(parse_hotkey(text)) == text


def test_all_default_hotkeys_parse_and_are_distinct():
    parsed = [parse_hotkey(t) for t in DEFAULT_HOTKEYS.values()]
    assert len(set(parsed)) == len(parsed) == 8


@pytest.mark.skipif(sys.platform != "win32", reason="Win32 hotkeys")
def test_live_register_trigger_conflict_unregister(qtbot):
    from livetranslator.services.hotkeys import HotkeyService

    service = HotkeyService()
    other = HotkeyService()
    combo = "Ctrl+Alt+Shift+F24"  # practically never bound by anything else
    try:
        assert service.register("test_action", combo)
        assert not other.register("dupe", combo)  # already taken -> reported, not raised

        # Simulate the key press with keybd_event (synthetic input to this desktop).
        user32 = ctypes.windll.user32
        keys = (0x11, 0x12, 0x10, 0x87)  # Ctrl, Alt, Shift, F24
        with qtbot.waitSignal(service.triggered, timeout=3000) as blocker:
            for vk in keys:
                user32.keybd_event(vk, 0, 0, 0)
            for vk in reversed(keys):
                user32.keybd_event(vk, 0, 2, 0)  # KEYEVENTF_KEYUP
        assert blocker.args == ["test_action"]

        service.unregister("test_action")
        assert other.register("now_free", combo)
    finally:
        service.close()
        other.close()


def test_invalid_text_is_rejected_without_raising(qapp):
    from livetranslator.services.hotkeys import HotkeyService

    service = HotkeyService()
    try:
        assert not service.register("x", "Ctrl+Banana")
        assert service.registered == {}
    finally:
        service.close()
