"""Settings → General (T072): the language you read, the language(s) you speak, folders."""

from __future__ import annotations

from PySide6.QtWidgets import QPushButton, QWidget

from livetranslator.app.settings_controller import mic_choice
from livetranslator.core.languages import DEFAULT_LANGUAGES
from livetranslator.theme.tokens import SETTINGS
from livetranslator.ui.settings.context import SettingsContext
from livetranslator.ui.settings.rows import SettingsPage, silently
from livetranslator.ui.widgets.choice_combo import ChoiceCombo
from livetranslator.ui.widgets.language_picker import LanguagePicker


def speak_items() -> list[tuple[str, object]]:
    return [
        ("Same as above", "same"),
        ("Detect any language", "auto"),
        *((lang.label, lang.code) for lang in DEFAULT_LANGUAGES),
    ]


def also_items() -> list[tuple[str, object]]:
    return [("Nothing else", ""), *((lang.label, lang.code) for lang in DEFAULT_LANGUAGES)]


CHINESE_SCRIPTS: list[tuple[str, object]] = [
    ("Simplified (简体)", "simplified"),
    ("Traditional (繁體)", "traditional"),
]


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
            "Translate into",
            "The language you read. New windows translate into it.",
            self.language,
        )
        # "I speak" is separate (user request 2026-10-18): practise another language and your
        # own lines get translated too, so you can check yourself.
        first, also = mic_choice(store.state.config.audio.mic_languages)
        self.speak = ChoiceCombo(speak_items(), first)
        self.speak.setFixedWidth(SETTINGS.control_width)
        self.speak.apply_palette(ctx.palette)
        self.speak.choice_changed.connect(lambda _c: self._on_speak())
        lang.row(
            "I speak",
            "What your microphone hears. If it's not the language above, your own lines are "
            "translated too, so you can check what you said.",
            self.speak,
        )
        self.also = ChoiceCombo(also_items(), also)
        self.also.setFixedWidth(SETTINGS.control_width)
        self.also.apply_palette(ctx.palette)
        self.also.choice_changed.connect(lambda _c: self._on_speak())
        self.also_row = lang.row(
            "I also speak",
            "If you switch between two languages, each line is checked against both.",
            self.also,
        )
        self.chinese = ChoiceCombo(CHINESE_SCRIPTS, store.state.config.engines.chinese_script)
        self.chinese.setFixedWidth(SETTINGS.control_width)
        self.chinese.apply_palette(ctx.palette)
        self.chinese.choice_changed.connect(lambda s: ctx.settings.set_chinese_script(str(s)))
        lang.row(
            "Chinese characters",
            "How spoken Mandarin is written in your windows. The recogniser sometimes mixes "
            "both; this keeps every line in one.",
            self.chinese,
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

    def _on_speak(self) -> None:
        self._ctx.settings.set_mic_languages(
            str(self.speak.current_choice()), str(self.also.current_choice() or "")
        )

    def refresh(self) -> None:
        config = self._ctx.settings.store.state.config
        silently(self.language, lambda: self.language.set_language(config.my_language))
        first, also = mic_choice(config.audio.mic_languages)
        self.speak.set_choice(first)
        self.also.set_choice(also)
        self.also_row.setEnabled(first != "auto")  # "any language" already covers it
        self.chinese.set_choice(config.engines.chinese_script)
