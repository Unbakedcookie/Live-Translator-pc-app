"""Small modal dialogs (T063/T064; spec §5.11): where to save a transcript, and "export
before closing?". Styled with the window QSS so they match the rest of the app."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from enum import Enum
from pathlib import Path

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget

from livetranslator import APP_DISPLAY_NAME
from livetranslator.theme.qss import dialog_qss, window_qss
from livetranslator.theme.tokens import Palette

TXT_FILTER = "Text file (*.txt)"
JSON_FILTER = "JSON, every detail (*.json)"


class QuitChoice(Enum):
    EXPORT = "export"
    DISCARD = "discard"
    CANCEL = "cancel"


@contextmanager
def topmost_owner() -> Iterator[QWidget]:
    """A tiny invisible always-on-top window to own dialogs that have no window of their own
    (Quit from the tray or an overlay's menu). User 2026-10-21: the ownerless "Export before
    closing?" box opened behind a pinned overlay; being modal, it blocked the overlays, so the
    app could only be ended from Task Manager. Windows keeps an owned window above its owner,
    so the question and the save dialog after it stay in front."""
    owner = QWidget(
        None,
        Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint,
    )
    owner.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
    centre = screen.availableGeometry().center()  # the dialogs centre on the owner
    owner.setGeometry(QRect(centre, QSize(1, 1)))
    owner.show()
    try:
        yield owner
    finally:
        owner.close()
        owner.deleteLater()


def ask_save_path(parent: QWidget | None, suggested: Path) -> Path | None:
    """Save dialog for a transcript. None when cancelled. The extension follows the chosen
    type if the user didn't type one."""
    path, chosen = QFileDialog.getSaveFileName(
        parent,
        "Export conversation",
        str(suggested),
        f"{TXT_FILTER};;{JSON_FILTER}",
    )
    if not path:
        return None
    result = Path(path)
    if result.suffix.lower() not in (".txt", ".json"):
        result = result.with_suffix(".json" if chosen == JSON_FILTER else ".txt")
    return result


def ask_export_before_quit(parent: QWidget | None, palette: Palette) -> QuitChoice:
    box = QMessageBox(parent)
    box.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)  # never behind a pinned overlay
    box.setWindowTitle(APP_DISPLAY_NAME)
    box.setIcon(QMessageBox.Icon.Question)
    box.setText("Export this conversation before closing?")
    box.setInformativeText("The conversation isn't saved anywhere. Once the app closes, it's gone.")
    box.setStyleSheet(window_qss(palette) + dialog_qss(palette))
    export = box.addButton("Export…", QMessageBox.ButtonRole.AcceptRole)
    discard = box.addButton("Close without saving", QMessageBox.ButtonRole.DestructiveRole)
    cancel = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(export)
    box.setEscapeButton(cancel)
    box.exec()
    clicked = box.clickedButton()
    if clicked is export:
        return QuitChoice.EXPORT
    if clicked is discard:
        return QuitChoice.DISCARD
    return QuitChoice.CANCEL


def confirm_remove_language(
    parent: QWidget | None, palette: Palette, name: str, reasons: list[str]
) -> bool:
    """T074: removing a language something still uses. True = remove anyway."""
    box = QMessageBox(parent)
    box.setWindowTitle(APP_DISPLAY_NAME)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setText(f"Remove {name}?")
    box.setInformativeText(
        f"It's still in use: {'; '.join(reasons)}. Those lines will be translated by Qwen if "
        "it's installed, or left untranslated. You can download it again later."
    )
    box.setStyleSheet(window_qss(palette) + dialog_qss(palette))
    remove = box.addButton("Remove", QMessageBox.ButtonRole.DestructiveRole)
    keep = box.addButton("Keep", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(keep)
    box.setEscapeButton(keep)
    box.exec()
    return box.clickedButton() is remove
