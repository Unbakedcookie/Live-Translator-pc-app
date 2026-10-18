"""Settings → Performance (T072): game mode and how often live text refreshes."""

from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QWidget

from livetranslator.ui.settings.context import SettingsContext
from livetranslator.ui.settings.rows import SettingsPage, number_box, silently

MS = 1000
INTERVAL_MIN_MS = 200  # PerformanceConfig.asr_update_interval_s bounds: 0.2 .. 3.0 s
INTERVAL_MAX_MS = 3000
INTERVAL_STEP_MS = 100
GAME_MODE_MIN_MS = 1000  # speech_controller.asr_settings: game mode never goes below 1.0 s


class PerformancePage(SettingsPage):
    title_text = "Performance"
    icon_name = "gauge"

    def __init__(self, ctx: SettingsContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        section = self.section("While you play")
        self.game_mode = QCheckBox()
        self.game_mode.toggled.connect(ctx.settings.set_game_mode)
        section.row(
            "Game mode",
            "Lighter on your graphics card: live text refreshes at most once a second, only "
            "finished lines are translated, and translation runs on the processor.",
            self.game_mode,
        )
        self.readout = QCheckBox()
        self.readout.toggled.connect(ctx.settings.set_show_readout)
        section.row(
            "Show performance readout",
            "A small line under each window: graphics card use, speed of speech and "
            "translation, and how long a line takes to appear.",
            self.readout,
        )
        self.interval = number_box(INTERVAL_MIN_MS, INTERVAL_MAX_MS, INTERVAL_STEP_MS, " ms")
        self.interval.valueChanged.connect(lambda ms: ctx.settings.set_asr_interval(ms / MS))
        self.interval_row = section.row("Live text refresh", "", self.interval)
        self.finish()
        self.refresh()

    def refresh(self) -> None:
        perf = self._ctx.settings.store.state.config.performance
        silently(self.game_mode, lambda: self.game_mode.setChecked(perf.game_mode))
        silently(self.readout, lambda: self.readout.setChecked(perf.show_readout))
        ms = round(perf.asr_update_interval_s * MS)
        silently(self.interval, lambda: self.interval.setValue(ms))
        text = "How often words still being spoken update. Lower feels snappier; higher is lighter."
        if perf.game_mode and ms < GAME_MODE_MIN_MS:
            text += f" Game mode is on, so it's {GAME_MODE_MIN_MS} ms for now."
        self.interval_row.set_description(text)
