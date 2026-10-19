"""Settings → Languages: the Language Manager (T074; spec §5.9; gate G3).

One row per language pack (to and from English): name, what it covers, download size and
licences, and Download / Cancel / Remove. One download runs at a time with a progress bar;
removing a language something uses asks first. Presentational: everything goes through the
`LanguageController`.
"""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QPushButton, QWidget

from livetranslator.app.language_controller import LanguageController
from livetranslator.core.languages import language
from livetranslator.services.language_packs import LanguagePack
from livetranslator.theme.tokens import SETTINGS, SPACE
from livetranslator.ui.dialogs import confirm_remove_language
from livetranslator.ui.settings.context import SettingsContext
from livetranslator.ui.settings.rows import SettingRow, SettingsPage, note

PROGRESS_STEPS = 1000


def size_text(mb: int) -> str:
    return f"{mb / 1024:.1f} GB" if mb >= 1024 else f"{mb} MB"


def pack_description(pack: LanguagePack) -> str:
    into, out_of = pack.directions
    if into and out_of:
        what = "To and from English"
    elif into:
        what = "Into English only (voice chat in it gets translated for you)"
    else:
        what = "From English only"
    licences = ", ".join(pack.licences)
    if pack.is_partial:
        left = sum(e.size_mb for e in pack.missing)
        return f"{what} · partly downloaded, {size_text(left)} to go · {licences}"
    return f"{what} · {size_text(pack.size_mb)} · {licences}"


class PackControl(QWidget):
    """Status / progress on the left, one action button on the right."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.status = QLabel(self)
        self.status.setObjectName("LanguageInstalled")
        self.progress = QProgressBar(self)
        self.progress.setObjectName("LanguageProgress")
        self.progress.setRange(0, PROGRESS_STEPS)
        self.progress.setFixedWidth(SETTINGS.control_width // 2)
        self.progress.hide()
        self.button = QPushButton(self)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACE.sm)
        layout.addWidget(self.status)
        layout.addWidget(self.progress)
        layout.addWidget(self.button)


class LanguagesPage(SettingsPage):
    title_text = "Languages"
    icon_name = "globe"

    def __init__(self, ctx: SettingsContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self.intro(
            "Download a language to translate it with its own small model: fast, and it keeps "
            "working in game mode. Each one covers that language to and from English; other "
            "combinations go through English. Languages you haven't downloaded are translated "
            "by Qwen when it's on (Settings → Translation)."
        )
        self.message = note("")
        self.message.hide()
        self.body.addWidget(self.message)
        self.rows: dict[str, tuple[SettingRow, PackControl]] = {}
        controller = ctx.languages
        if controller is None or not controller.packs():
            self.empty = note(
                "Language downloads aren't available in this version yet. The languages "
                "already on this PC keep working."
            )
            self.body.addWidget(self.empty)
            self.finish()
            return
        section = self.section("Languages")
        for pack in controller.packs():
            control = PackControl()
            row = section.row(language(pack.code).label, "", control)
            control.button.clicked.connect(lambda _c=False, code=pack.code: self._on_button(code))
            self.rows[pack.code] = (row, control)
        self.finish()
        controller.progress.connect(self._on_progress)
        controller.finished.connect(self._on_finished)
        controller.changed.connect(self.refresh)
        self.refresh()

    @property
    def controller(self) -> LanguageController:
        assert self._ctx.languages is not None  # nosec B101 - rows exist only with one
        return self._ctx.languages

    # ------------------------------------------------------------ store -> rows

    def refresh(self) -> None:
        if not self.rows:
            return
        busy = self.controller.busy
        for pack in self.controller.packs():
            if pack.code not in self.rows:
                continue
            row, control = self.rows[pack.code]
            row.set_description(pack_description(pack))
            downloading = busy == pack.code
            control.progress.setVisible(downloading)
            control.status.setVisible(pack.is_installed and not downloading)
            control.status.setText("Installed")
            if downloading:
                control.button.setText("Cancel")
                control.button.setEnabled(True)
            elif pack.is_installed:
                control.button.setText("Remove")
                control.button.setEnabled(busy is None)
            else:
                control.button.setText("Continue" if pack.is_partial else "Download")
                control.button.setEnabled(busy is None)

    # ------------------------------------------------------------ actions

    def _on_button(self, code: str) -> None:
        controller = self.controller
        pack = controller.pack(code)
        if pack is None:
            return
        if controller.busy == code:
            controller.cancel()
            return
        if pack.is_installed:
            reasons = controller.in_use(code)
            name = language(code).english
            if reasons and not confirm_remove_language(self, self._ctx.palette, name, reasons):
                return
            controller.remove(code)
            self._show(f"{name} removed.")
            return
        if controller.install(code):
            _row, control = self.rows[code]
            control.progress.setValue(0)
            control.progress.setFormat("Starting…")
            self.message.hide()
            self.refresh()

    def _on_progress(self, code: str, done: int, total: int) -> None:
        if code not in self.rows:
            return
        _row, control = self.rows[code]
        control.progress.setValue(int(PROGRESS_STEPS * done / total) if total else 0)
        control.progress.setFormat(f"{done >> 20} / {total >> 20} MB")

    def _on_finished(self, code: str, ok: bool, message: str) -> None:
        self._show(message, error=not ok)
        self.refresh()

    def _show(self, text: str, error: bool = False) -> None:
        self.message.setObjectName("SettingsError" if error else "SettingsNote")
        self.message.style().unpolish(self.message)
        self.message.style().polish(self.message)
        self.message.setText(text)
        self.message.show()
