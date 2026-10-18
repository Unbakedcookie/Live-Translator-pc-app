"""Settings → Translation (T072): which engines run where, and the installed language pairs.
Installing languages moves to the Language Manager (T074)."""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtGui import QHideEvent, QShowEvent
from PySide6.QtWidgets import QLabel, QWidget

from livetranslator.core.languages import language
from livetranslator.ui.settings.context import EngineSummary, SettingsContext
from livetranslator.ui.settings.rows import Section, SettingsPage

ENGINE_POLL_MS = 1000


def pair_names(pairs: tuple[tuple[str, str], ...]) -> str:
    """'English → Spanish, Japanese → English, …' sorted by name."""
    return ", ".join(
        sorted(f"{language(src).english} → {language(tgt).english}" for src, tgt in pairs)
    )


class TranslationPage(SettingsPage):
    title_text = "Translation"
    icon_name = "translate"

    def __init__(self, ctx: SettingsContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self.intro("Everything runs on this PC. Nothing anyone says is sent over the internet.")
        self._engines: QWidget = QWidget()
        self.body.addWidget(self._engines)
        languages = self.section("Languages")
        self.pairs = languages.row("Installed pairs")
        languages.row(
            "Other combinations",
            "Languages without a direct pair go through English, for example "
            "Japanese → English → Spanish. That takes a little longer.",
        )
        self.finish()
        self._shown: EngineSummary | None = None
        # Engines load in the background: re-read while the page is on screen ("Starting…"
        # turns into "Graphics card" without leaving the page). Cheap: unchanged = no redraw.
        self._timer = QTimer(self)
        self._timer.setInterval(ENGINE_POLL_MS)
        self._timer.timeout.connect(self.refresh)

    def refresh(self) -> None:
        summary = self._ctx.engines() if self._ctx.engines else EngineSummary()
        if summary == self._shown:
            return
        self._shown = summary
        engines = Section("Engines")
        if not summary.rows:
            engines.row("Speech is off", "This session was started without speech.")
        for row in summary.rows:
            engines.row(row.role, row.engine, QLabel(row.where))
        self.body.insertWidget(self.body.indexOf(self._engines), engines)
        self._engines.setParent(None)
        self._engines.deleteLater()
        self._engines = engines
        self.pairs.set_description(pair_names(summary.pairs) or "None installed yet.")

    def showEvent(self, event: QShowEvent) -> None:
        self.refresh()
        self._timer.start()
        super().showEvent(event)

    def hideEvent(self, event: QHideEvent) -> None:
        self._timer.stop()
        super().hideEvent(event)
