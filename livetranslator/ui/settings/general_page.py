"""Settings → General (T072): my language, where models and logs live."""

from __future__ import annotations

from PySide6.QtWidgets import QPushButton, QWidget

from livetranslator.theme.tokens import SETTINGS
from livetranslator.ui.settings.context import SettingsContext
from livetranslator.ui.settings.rows import SettingsPage, silently
from livetranslator.ui.widgets.language_picker import LanguagePicker


class GeneralPage(SettingsPage):
    title_text = "General"
    icon_name = "gear-six"

    def __init__(self, ctx: SettingsContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        store = ctx.settings.store
        self.language = LanguagePicker(store.state.config.my_language)
        self.language.setFixedWidth(SETTINGS.control_width)
        self.language.apply_palette(ctx.palette)
        self.language.language_changed.connect(ctx.settings.set_my_language)
        lang = self.section("Language")
        lang.row(
            "My language",
            "What you speak. Your microphone is recognised in this language, and new windows "
            "translate into it.",
            self.language,
        )

        storage = self.section("Storage")
        models = QPushButton("Open folder")
        models.clicked.connect(lambda: ctx.open_folder(ctx.models_dir))
        storage.row("Speech and translation models", str(ctx.models_dir), models)
        logs = QPushButton("Open folder")
        logs.clicked.connect(lambda: ctx.open_folder(ctx.log_dir))
        storage.row(
            "Log files",
            f"{ctx.log_dir}\nLogs never contain what anyone said.",
            logs,
        )
        self.finish()

    def refresh(self) -> None:
        code = self._ctx.settings.store.state.config.my_language
        silently(self.language, lambda: self.language.set_language(code))
