"""Settings → Speakers (T072 page; spec §5.13). Discord and renaming are added by T103/T104."""

from __future__ import annotations

from PySide6.QtWidgets import QLineEdit, QPushButton, QWidget

from livetranslator.core.state import MAX_SPEAKERS_LIMIT, SpeakerMode
from livetranslator.theme.tokens import SETTINGS
from livetranslator.ui.discord_setup import DiscordSetup
from livetranslator.ui.settings.context import SettingsContext
from livetranslator.ui.settings.rows import SettingRow, SettingsPage, note, number_box, silently
from livetranslator.ui.widgets.choice_combo import ChoiceCombo

MODES: list[tuple[str, object]] = [
    ("By voice (Speaker 1, 2…)", SpeakerMode.AUTO),
    ("Off: everyone is “Others”", SpeakerMode.OFF),
]
MAX_SPEAKERS_MIN = 1  # SpeakerConfig allows 1 (a saved 1 must show as 1)
ME_LABEL_MAX = 24


def shown_mode(mode: SpeakerMode) -> SpeakerMode:
    """Voice-only and Discord-only behave like Auto until Discord exists (T103)."""
    return SpeakerMode.OFF if mode is SpeakerMode.OFF else SpeakerMode.AUTO


class SpeakersPage(SettingsPage):
    title_text = "Speakers"
    icon_name = "users-three"

    def __init__(self, ctx: SettingsContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        labels = self.section("Who said it")
        self.mode = ChoiceCombo(MODES)
        self.mode.setFixedWidth(SETTINGS.control_width)
        self.mode.apply_palette(ctx.palette)
        self.mode.choice_changed.connect(lambda m: ctx.settings.set_speaker_mode(m))
        labels.row(
            "Label other people",
            "Each voice heard on your speakers gets its own label and colour.",
            self.mode,
        )
        self.max_speakers = number_box(MAX_SPEAKERS_MIN, MAX_SPEAKERS_LIMIT)
        self.max_speakers.valueChanged.connect(ctx.settings.set_max_speakers)
        labels.row(
            "Most voices to tell apart",
            "Once this many are known, a new voice gets the closest existing label.",
            self.max_speakers,
        )
        self.me_label = QLineEdit()
        self.me_label.setFixedWidth(SETTINGS.control_width)
        self.me_label.setMaxLength(ME_LABEL_MAX)
        self.me_label.editingFinished.connect(self._on_me_label)
        labels.row("Name on your own lines", "Shown instead of “Me”.", self.me_label)
        self.discord_row: SettingRow | None = None
        self.discord_setup: DiscordSetup | None = None
        if ctx.discord is not None:
            setup = QPushButton("Set up…")
            setup.clicked.connect(self.open_discord_setup)
            self.discord_row = self.section("Discord").row("Discord names", "", setup)
        self.body.addWidget(
            note(
                "Voices are told apart in memory only. Nothing about anyone's voice is saved, "
                "and it's all forgotten when the app closes."
            )
        )
        self.finish()
        self.refresh()

    def _on_me_label(self) -> None:
        self._ctx.settings.set_me_label(self.me_label.text())
        label = self._ctx.settings.store.state.config.speakers.me_label
        silently(self.me_label, lambda: self.me_label.setText(label))  # blank → back to saved

    def open_discord_setup(self) -> None:
        if self._ctx.discord is None:
            return
        if self.discord_setup is None:
            self.discord_setup = DiscordSetup(self._ctx.discord, self._ctx.palette)
        self.discord_setup.load()
        self.discord_setup.show()
        self.discord_setup.raise_()
        self.discord_setup.activateWindow()

    def refresh(self) -> None:
        speakers = self._ctx.settings.store.state.config.speakers
        if self.discord_row is not None:
            status = self._ctx.settings.store.state.runtime.statuses.get("discord")
            if not speakers.discord_app_id:
                text = "Show people's Discord names instead of Speaker 1, 2… (one-time setup)."
            elif status is not None:
                text = status.message
            else:
                text = "Set up. Names appear while you're in a voice channel."
            self.discord_row.set_description(text)
        self.mode.set_choice(shown_mode(speakers.mode))
        silently(self.max_speakers, lambda: self.max_speakers.setValue(speakers.max_speakers))
        if not self.me_label.hasFocus():
            silently(self.me_label, lambda: self.me_label.setText(speakers.me_label))
