"""T021 — Win32 helpers: flag math (Tier A) and a real-window smoke test (Windows only)."""

import sys

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

from livetranslator.platform.win32 import (
    WS_EX_LAYERED,
    WS_EX_TOPMOST,
    WS_EX_TRANSPARENT,
    click_through_style,
    has_click_through,
    has_topmost,
)


def test_constants_match_winuser_h():
    assert (WS_EX_TOPMOST, WS_EX_TRANSPARENT, WS_EX_LAYERED) == (0x8, 0x20, 0x80000)


def test_click_through_on_adds_transparent_and_layered():
    # 0x00000100 (WS_EX_WINDOWEDGE) | 0x8 (TOPMOST) -> + 0x20 + 0x80000
    assert click_through_style(0x108, True) == 0x80128


def test_click_through_off_keeps_layered():
    assert click_through_style(0x80128, False) == 0x80108


def test_click_through_is_idempotent():
    once = click_through_style(0x0, True)
    assert click_through_style(once, True) == once == 0x80020
    assert click_through_style(0x80000, False) == 0x80000


def test_flag_readers():
    assert has_topmost(0x80108)
    assert not has_topmost(0x80100)
    assert has_click_through(0x80020)
    assert not has_click_through(0x80000)


@pytest.mark.skipif(sys.platform != "win32", reason="real Win32 window")
def test_real_window_flags_toggle(qtbot):
    from livetranslator.platform.win32 import (
        is_click_through,
        is_topmost,
        set_click_through,
        set_topmost,
    )

    w = QWidget()
    w.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
    w.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    w.resize(200, 100)
    qtbot.addWidget(w)
    w.show()
    qtbot.waitExposed(w)
    hwnd = int(w.winId())
    geometry_before = w.geometry()

    set_topmost(hwnd, True)
    assert is_topmost(hwnd)
    set_topmost(hwnd, False)
    assert not is_topmost(hwnd)

    set_click_through(hwnd, True)
    assert is_click_through(hwnd)
    set_click_through(hwnd, False)
    assert not is_click_through(hwnd)

    assert int(w.winId()) == hwnd  # no native window re-creation
    assert w.geometry() == geometry_before
