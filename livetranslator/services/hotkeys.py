"""Global hotkeys via Win32 RegisterHotKey (T081; spec §5.7, D-020).

RegisterHotKey asks Windows to post WM_HOTKEY to our thread; no keyboard hook, nothing reads
other keystrokes, which keeps us clear of anti-cheat software that flags low-level hooks.
Qt's event dispatcher hands the message to a native event filter, which emits `triggered`.
A combination already taken by another app is reported (register returns False), never raised.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from dataclasses import dataclass

from loguru import logger
from PySide6.QtCore import QAbstractNativeEventFilter, QByteArray, QCoreApplication, QObject, Signal

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312

_MODIFIERS: dict[str, int] = {
    "ctrl": MOD_CONTROL,
    "control": MOD_CONTROL,
    "alt": MOD_ALT,
    "shift": MOD_SHIFT,
    "win": MOD_WIN,
    "meta": MOD_WIN,
}
_MODIFIER_ORDER = ((MOD_CONTROL, "Ctrl"), (MOD_ALT, "Alt"), (MOD_SHIFT, "Shift"), (MOD_WIN, "Win"))

_NAMED_KEYS: dict[str, int] = {
    "Space": 0x20,
    "Enter": 0x0D,
    "Tab": 0x09,
    "Esc": 0x1B,
    "Backspace": 0x08,
    "Insert": 0x2D,
    "Delete": 0x2E,
    "Home": 0x24,
    "End": 0x23,
    "PageUp": 0x21,
    "PageDown": 0x22,
    "Left": 0x25,
    "Up": 0x26,
    "Right": 0x27,
    "Down": 0x28,
    "Pause": 0x13,
    "PrintScreen": 0x2C,
}
_KEYS: dict[str, int] = {
    **{chr(c): c for c in range(ord("A"), ord("Z") + 1)},
    **{str(d): 0x30 + d for d in range(10)},
    **{f"F{n}": 0x6F + n for n in range(1, 25)},  # F1 = 0x70 ... F24 = 0x87
    **_NAMED_KEYS,
}
_KEYS_LOWER = {name.lower(): (name, vk) for name, vk in _KEYS.items()}
_VK_TO_NAME = {vk: name for name, vk in _KEYS.items()}


class HotkeyError(ValueError):
    pass


@dataclass(frozen=True)
class Hotkey:
    modifiers: int  # MOD_* bits (without MOD_NOREPEAT)
    vk: int

    def __str__(self) -> str:
        return format_hotkey(self)


def parse_hotkey(text: str) -> Hotkey:
    """'Ctrl+Alt+H' -> Hotkey(MOD_CONTROL | MOD_ALT, 0x48). Case-insensitive.

    Needs exactly one non-modifier key and at least one modifier (a bare global key would
    swallow normal typing), except F1-F24.
    """
    parts = [p.strip() for p in text.split("+")]
    if not text.strip() or any(not p for p in parts):
        raise HotkeyError(f"not a key combination: {text!r}")
    modifiers = 0
    key: tuple[str, int] | None = None
    for part in parts:
        low = part.lower()
        if low in _MODIFIERS:
            modifiers |= _MODIFIERS[low]
        elif low in _KEYS_LOWER:
            if key is not None:
                raise HotkeyError(f"only one key allowed in {text!r}")
            key = _KEYS_LOWER[low]
        else:
            raise HotkeyError(f"unknown key {part!r} in {text!r}")
    if key is None:
        raise HotkeyError(f"no key in {text!r}")
    name, vk = key
    if modifiers == 0 and not (name.startswith("F") and name[1:].isdigit()):
        raise HotkeyError(f"{text!r} needs Ctrl, Alt, Shift or Win")
    return Hotkey(modifiers, vk)


def format_hotkey(hotkey: Hotkey) -> str:
    names = [label for bit, label in _MODIFIER_ORDER if hotkey.modifiers & bit]
    names.append(_VK_TO_NAME.get(hotkey.vk, f"0x{hotkey.vk:02X}"))
    return "+".join(names)


# ---------------------------------------------------------------- Win32 service

if sys.platform == "win32":
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _register = _user32.RegisterHotKey
    _register.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
    _register.restype = wintypes.BOOL
    _unregister = _user32.UnregisterHotKey
    _unregister.argtypes = [wintypes.HWND, ctypes.c_int]
    _unregister.restype = wintypes.BOOL


class _HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, service: HotkeyService) -> None:
        super().__init__()
        self._service = service

    def nativeEventFilter(self, eventType: QByteArray | bytes, message: int) -> object:
        name = eventType.data() if isinstance(eventType, QByteArray) else eventType
        if name == b"windows_generic_MSG":
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY and self._service.handle(int(msg.wParam)):
                return True, 0
        return False, 0


class HotkeyService(QObject):
    """Registers global hotkeys for the main thread and emits `triggered(action)`."""

    triggered = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._ids: dict[str, int] = {}
        self._actions: dict[int, str] = {}
        self._next_id = 1
        self._filter = _HotkeyFilter(self)
        app = QCoreApplication.instance()
        if app is None:
            raise RuntimeError("HotkeyService needs a running Qt application")
        app.installNativeEventFilter(self._filter)

    @property
    def registered(self) -> dict[str, int]:
        return dict(self._ids)

    def register(self, action: str, text: str) -> bool:
        """Bind `action` to `text`. False if the combination is invalid or already taken."""
        self.unregister(action)
        if sys.platform != "win32":
            return False
        try:
            hotkey = parse_hotkey(text)
        except HotkeyError as exc:
            logger.warning("hotkey for {} rejected: {}", action, exc)
            return False
        hotkey_id = self._next_id
        if not _register(None, hotkey_id, hotkey.modifiers | MOD_NOREPEAT, hotkey.vk):
            logger.warning(
                "hotkey {} for {} unavailable (error {})", text, action, ctypes.get_last_error()
            )
            return False
        self._next_id += 1
        self._ids[action] = hotkey_id
        self._actions[hotkey_id] = action
        return True

    def unregister(self, action: str) -> None:
        hotkey_id = self._ids.pop(action, None)
        if hotkey_id is not None:
            self._actions.pop(hotkey_id, None)
            if sys.platform == "win32":
                _unregister(None, hotkey_id)

    def unregister_all(self) -> None:
        for action in list(self._ids):
            self.unregister(action)

    def handle(self, hotkey_id: int) -> bool:
        action = self._actions.get(hotkey_id)
        if action is None:
            return False
        self.triggered.emit(action)
        return True

    def close(self) -> None:
        self.unregister_all()
        app = QCoreApplication.instance()
        if app is not None:
            app.removeNativeEventFilter(self._filter)
