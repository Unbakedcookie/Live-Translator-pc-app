"""Settings → Advanced (T072): echo filter and speech-detection tuning."""

from __future__ import annotations

from PySide6.QtWidgets import QPushButton, QWidget

from livetranslator.ui.settings.context import SettingsContext
from livetranslator.ui.settings.rows import SettingsPage, number_box, silently

PERCENT = 100
# Bounds follow EchoFilterConfig / VadConfig validators (core/state.py).
ECHO_WINDOW_MAX_S = 30
VAD_THRESHOLD_MIN = 5  # % (the model's probability must stay strictly between 0 and 1)
VAD_THRESHOLD_MAX = 95
SILENCE_MIN_MS = 100
SILENCE_MAX_MS = 3000
SILENCE_STEP_MS = 50
LINE_MIN_S = 3
LINE_MAX_S = 30


class AdvancedPage(SettingsPage):
    title_text = "Advanced"
    icon_name = "wrench"

    def __init__(self, ctx: SettingsContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        s = ctx.settings
        self.intro("The defaults suit most people. Change these only if something feels off.")

        echo = self.section("Echo filter")
        self.echo_window = number_box(0, ECHO_WINDOW_MAX_S, 1, " s")
        self.echo_window.valueChanged.connect(lambda v: s.set_echo_filter(window_s=float(v)))
        echo.row(
            "Look back",
            "If your microphone picks up your speakers, your line is dropped when it repeats "
            "something heard within this many seconds of it.",
            self.echo_window,
        )
        self.echo_ratio = number_box(0, PERCENT, 5, " %")
        self.echo_ratio.valueChanged.connect(lambda v: s.set_echo_filter(min_ratio=float(v)))
        echo.row(
            "How similar counts as an echo",
            "100 % = only exact repeats are dropped.",
            self.echo_ratio,
        )

        vad = self.section("Speech detection")
        self.threshold = number_box(VAD_THRESHOLD_MIN, VAD_THRESHOLD_MAX, 5, " %")
        self.threshold.valueChanged.connect(lambda v: s.set_vad(threshold=v / PERCENT))
        vad.row(
            "Sensitivity",
            "How sure the app must be that someone is talking. Higher ignores more noise but "
            "may miss quiet voices.",
            self.threshold,
        )
        self.silence = number_box(SILENCE_MIN_MS, SILENCE_MAX_MS, SILENCE_STEP_MS, " ms")
        self.silence.valueChanged.connect(lambda v: s.set_vad(end_silence_ms=v))
        vad.row(
            "Pause that ends a line",
            "Shorter splits sentences sooner; longer keeps slow speakers in one line.",
            self.silence,
        )
        self.longest = number_box(LINE_MIN_S, LINE_MAX_S, 1, " s")
        self.longest.valueChanged.connect(lambda v: s.set_vad(max_utterance_s=float(v)))
        vad.row(
            "Longest line", "Someone talking non-stop is cut into lines this long.", self.longest
        )

        reset = QPushButton("Restore defaults")
        reset.clicked.connect(s.reset_advanced)
        self.section().row(
            "Start over", "Puts these settings and the live text refresh back.", reset
        )
        self.finish()
        self.refresh()

    def refresh(self) -> None:
        config = self._ctx.settings.store.state.config
        values = (
            (self.echo_window, round(config.echo_filter.window_s)),
            (self.echo_ratio, round(config.echo_filter.min_ratio)),
            (self.threshold, round(config.vad.threshold * PERCENT)),
            (self.silence, config.vad.end_silence_ms),
            (self.longest, round(config.vad.max_utterance_s)),
        )
        for box, value in values:
            silently(box, lambda b=box, v=value: b.setValue(v))
