"""Settings → General (T072): the language you read, the language(s) you speak, folders."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QPushButton, QVBoxLayout, QWidget

from livetranslator.app.settings_controller import mic_choice, others_choice
from livetranslator.core.languages import DEFAULT_LANGUAGES
from livetranslator.core.state import MAX_MIC_LANGUAGES
from livetranslator.theme.tokens import SETTINGS, SPACE, Palette
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


ALSO_SPEAK_HELP = (
    "Switch between several languages? Pick each one; every line is checked against just "
    "these. Another box appears when you fill one."
)


class AlsoSpeak(QWidget):
    """ "I also speak": up to MAX_MIC_LANGUAGES - 1 pickers (user request 2026-10-19). Only
    the filled ones plus one empty picker show; emptying one closes the gap."""

    changed = Signal()

    def __init__(
        self, palette: Palette, codes: Sequence[str] = (), parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACE.xs)
        self.boxes: list[ChoiceCombo] = []
        for _ in range(MAX_MIC_LANGUAGES - 1):
            box = ChoiceCombo(also_items(), "")
            box.setFixedWidth(SETTINGS.control_width)
            box.apply_palette(palette)
            box.choice_changed.connect(lambda _c: self._on_choice())
            layout.addWidget(box)
            self.boxes.append(box)
        self.set_codes(codes)

    def codes(self) -> tuple[str, ...]:
        chosen: list[str] = []
        for box in self.boxes:
            code = str(box.current_choice() or "")
            if code and code not in chosen:
                chosen.append(code)
        return tuple(chosen)

    def set_codes(self, codes: Sequence[str]) -> None:
        codes = list(codes)[: len(self.boxes)]
        for i, box in enumerate(self.boxes):
            box.set_choice(codes[i] if i < len(codes) else "")
            box.setVisible(i <= len(codes))

    def _on_choice(self) -> None:
        self.set_codes(self.codes())  # close gaps, show the next empty picker
        self.changed.emit()


def others_items() -> list[tuple[str, object]]:
    return [
        ("Detect any language", "auto"),
        *((lang.label, lang.code) for lang in DEFAULT_LANGUAGES),
    ]


OTHERS_HELP = (
    "Detect any language works anywhere. If you know what people around you speak, pick "
    "it: their lines are never taken for an unrelated language, and live text is right from "
    "the first word."
)
OTHERS_ALSO_HELP = "Pick more if people switch between languages. Another box appears as you go."


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
        self.also = AlsoSpeak(ctx.palette, also)
        self.also.changed.connect(self._on_speak)
        self.also_row = lang.row("I also speak", ALSO_SPEAK_HELP, self.also)
        # "Others speak" (user request 2026-10-20): detect any (default) or the room's
        # languages, which keeps noisy, short lines from being taken for another language.
        others, others_also = others_choice(store.state.config.audio.others_languages)
        self.others = ChoiceCombo(others_items(), others)
        self.others.setFixedWidth(SETTINGS.control_width)
        self.others.apply_palette(ctx.palette)
        self.others.choice_changed.connect(lambda _c: self._on_others())
        lang.row("Others speak", OTHERS_HELP, self.others)
        self.others_also = AlsoSpeak(ctx.palette, others_also)
        self.others_also.changed.connect(self._on_others)
        self.others_also_row = lang.row("They also speak", OTHERS_ALSO_HELP, self.others_also)
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
        self._ctx.settings.set_mic_languages(str(self.speak.current_choice()), self.also.codes())

    def _on_others(self) -> None:
        self._ctx.settings.set_others_languages(
            str(self.others.current_choice()), self.others_also.codes()
        )

    def refresh(self) -> None:
        config = self._ctx.settings.store.state.config
        silently(self.language, lambda: self.language.set_language(config.my_language))
        first, also = mic_choice(config.audio.mic_languages)
        self.speak.set_choice(first)
        self.also.set_codes(also)
        self.also_row.setEnabled(first != "auto")  # "any language" already covers it
        others, others_also = others_choice(config.audio.others_languages)
        self.others.set_choice(others)
        self.others_also.set_codes(others_also)
        self.others_also_row.setEnabled(others != "auto")  # any language covers them all
        self.chinese.set_choice(config.engines.chinese_script)
