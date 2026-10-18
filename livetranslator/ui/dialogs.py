"""Small modal dialogs (T063/T064; spec §5.11): where to save a transcript, and "export
before closing?". Styled with the window QSS so they match the rest of the app."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

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
