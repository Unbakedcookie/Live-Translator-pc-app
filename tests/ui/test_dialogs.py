"""Quit dialogs stay in front of pinned overlays (user 2026-10-21: the "Export before
closing?" box opened behind a chat window and, being modal, locked the app). Real desktop
windows: Windows itself is asked which window is on top."""

import ctypes
import sys
from collections.abc import Callable
from ctypes import wintypes
from pathlib import Path

import pytest
from PySide6.QtCore import QRect, Qt, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

from livetranslator.platform.win32 import set_topmost
from livetranslator.theme.tokens import DEFAULT_PALETTE_ID, PALETTES
from livetranslator.ui.dialogs import (
    QuitChoice,
    ask_export_before_quit,
    ask_save_path,
    topmost_owner,
)

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows z-order")

GA_ROOT = 2
WM_CLOSE = 0x0010
user32 = ctypes.windll.user32 if sys.platform == "win32" else None


def on_top_at_centre(hwnd: int) -> bool:
    """Is `hwnd` the window the user sees (and clicks) at its own centre?"""
    assert user32 is not None
    user32.WindowFromPoint.argtypes = [wintypes.POINT]
    user32.WindowFromPoint.restype = wintypes.HWND
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetAncestor.restype = wintypes.HWND
    rect = wintypes.RECT()
    user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect))
    centre = wintypes.POINT((rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2)
    hit = user32.WindowFromPoint(centre)
    return int(user32.GetAncestor(hit, GA_ROOT) or 0) == hwnd


def pinned_overlay(qtbot) -> QWidget:
    """Stand-in for a pinned chat window covering the middle of the screen."""
    overlay = QWidget(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
    qtbot.addWidget(overlay)
    screen = QApplication.primaryScreen().availableGeometry()
    overlay.setGeometry(QRect(screen.center().x() - 400, screen.center().y() - 300, 800, 600))
    overlay.show()
    qtbot.waitExposed(overlay)
    set_topmost(int(overlay.winId()), True)
    return overlay


def when_shown(find: Callable[[], int], results: list[bool]) -> None:
    """Once the dialog `find` locates is up: record whether it's on top, then close it."""

    def check() -> None:
        hwnd = find()
        if not hwnd:
            QTimer.singleShot(50, check)
            return
        QTimer.singleShot(500, lambda: settle(hwnd))  # let it finish opening

    def settle(hwnd: int) -> None:
        results.append(on_top_at_centre(hwnd))
        assert user32 is not None
        user32.PostMessageW(wintypes.HWND(hwnd), WM_CLOSE, 0, 0)  # = Cancel

    QTimer.singleShot(150, check)


def message_box() -> int:
    box = QApplication.activeModalWidget()
    return int(box.winId()) if isinstance(box, QMessageBox) else 0


def save_dialog() -> int:
    assert user32 is not None
    user32.FindWindowW.restype = wintypes.HWND
    hwnd = int(user32.FindWindowW(None, "Export conversation") or 0)
    return hwnd if hwnd and user32.IsWindowVisible(wintypes.HWND(hwnd)) else 0


def test_the_check_sees_a_dialog_hidden_behind_an_overlay(qtbot):
    """The bug as the user saw it. (A save dialog with no owner borrows whichever window is
    active, so whether it hides varies; the fix always gives it the topmost owner.)"""
    overlay = pinned_overlay(qtbot)
    seen: list[bool] = []
    when_shown(message_box, seen)
    QMessageBox(QMessageBox.Icon.Question, "plain", "a plain box, as before the fix").exec()
    assert seen == [False]
    overlay.close()


def test_quit_question_and_save_dialog_open_in_front_of_a_pinned_overlay(qtbot, tmp_path: Path):
    overlay = pinned_overlay(qtbot)
    palette = PALETTES[DEFAULT_PALETTE_ID]
    seen: list[bool] = []
    with topmost_owner() as owner:
        when_shown(message_box, seen)
        assert ask_export_before_quit(owner, palette) is QuitChoice.CANCEL
        when_shown(save_dialog, seen)
        assert ask_save_path(owner, tmp_path / "conversation.txt") is None
    assert seen == [True, True]
    assert not owner.isVisible()
    overlay.close()
