"""Discord token storage, encrypted with Windows DPAPI (T103; spec §5.13).

`CryptProtectData` ties the encryption to the signed-in Windows user: another account (or
another PC) can't read the file. Disconnect deletes it. Nothing here is ever logged.
"""

from __future__ import annotations

import ctypes
import json
import sys
from ctypes import wintypes
from pathlib import Path
from typing import Any

_ENTROPY = b"LiveTranslator/discord/v1"  # app-specific: other DPAPI users can't decrypt by accident


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data: bytes) -> _Blob:
    buffer = ctypes.create_string_buffer(data, len(data))
    return _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))


def _crypt(data: bytes, protect: bool) -> bytes:
    if sys.platform != "win32":
        raise OSError("DPAPI is only available on Windows")
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    func = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    source, entropy, out = _blob(data), _blob(_ENTROPY), _Blob()
    ok = func(
        ctypes.byref(source),
        None,
        ctypes.byref(entropy),
        None,
        None,
        0x1,  # CRYPTPROTECT_UI_FORBIDDEN
        ctypes.byref(out),
    )
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(out.pbData)


def protect(data: bytes) -> bytes:
    return _crypt(data, protect=True)


def unprotect(data: bytes) -> bytes:
    return _crypt(data, protect=False)


class TokenStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def save(self, values: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_bytes(protect(json.dumps(values).encode("utf-8")))
        tmp.replace(self.path)

    def load(self) -> dict[str, Any] | None:
        """The stored values, or None when there are none or they can't be read (e.g. the
        file was copied from another Windows account)."""
        try:
            raw = unprotect(self.path.read_bytes())
            values = json.loads(raw.decode("utf-8"))
        except (OSError, ValueError):
            return None
        return values if isinstance(values, dict) else None

    def delete(self) -> None:
        self.path.unlink(missing_ok=True)
