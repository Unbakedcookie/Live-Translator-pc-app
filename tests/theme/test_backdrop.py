"""T012 — Mica backdrop only on Windows 11 builds (Tier A, with a fake win32mica)."""

import sys
import types

import pytest

from livetranslator.theme.backdrop import MICA_MIN_BUILD, apply_mica, mica_supported


def test_build_threshold():
    assert MICA_MIN_BUILD == 22000
    assert not mica_supported(19045)  # Windows 10 22H2
    assert not mica_supported(21999)
    assert mica_supported(22000)  # Windows 11 21H2
    assert mica_supported(26200)  # this PC


def _fake_mica(result: int, calls: list):
    module = types.ModuleType("win32mica")
    module.MicaTheme = types.SimpleNamespace(LIGHT=0, DARK=1)  # type: ignore[attr-defined]
    module.MicaStyle = types.SimpleNamespace(DEFAULT=3, ALT=4)  # type: ignore[attr-defined]

    def apply(hwnd, theme, style):
        calls.append((hwnd, theme, style))
        return result

    module.ApplyMica = apply  # type: ignore[attr-defined]
    return module


def test_old_windows_is_a_no_op(monkeypatch: pytest.MonkeyPatch):
    calls: list = []
    monkeypatch.setitem(sys.modules, "win32mica", _fake_mica(0, calls))
    assert apply_mica(1234, dark=True, build=19045) is False
    assert calls == []


def test_windows_11_applies_with_theme(monkeypatch: pytest.MonkeyPatch):
    calls: list = []
    monkeypatch.setitem(sys.modules, "win32mica", _fake_mica(0, calls))
    assert apply_mica(1234, dark=True, build=22631) is True
    assert apply_mica(99, dark=False, build=22631) is True
    assert calls == [(1234, 1, 3), (99, 0, 3)]


def test_rejected_by_windows_returns_false(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setitem(sys.modules, "win32mica", _fake_mica(0x32, []))
    assert apply_mica(1234, dark=True, build=22631) is False
