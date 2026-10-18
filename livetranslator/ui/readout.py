"""Performance readout strip (T093; spec §5.10): one small line at the bottom of an overlay.

    Game mode · GPU 37 % · VRAM 4.1 / 12.0 GB · Speech 290 ms · Translate 76 ms · Lag 0.98 s

Values come from `runtime.metrics` (T091, once a second). Anything not measured yet, or not
measurable on this PC (no NVIDIA GPU), shows "n/a". Turned on in Settings → Performance.
"""

from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QLabel, QWidget

from livetranslator.core.store import Store
from livetranslator.services.metrics import GPU_UTIL, VRAM_TOTAL, VRAM_USED, metric_name
from livetranslator.theme.tokens import FONTS, Palette

NA = "n/a"
SEPARATOR = " · "
MB_PER_GB = 1024


def _ms(metrics: Mapping[str, float], kind: str) -> str:
    value = metrics.get(metric_name(kind, 50))
    return NA if value is None else f"{value:.0f} ms"


def readout_text(metrics: Mapping[str, float], game_mode: bool) -> str:
    gpu = metrics.get(GPU_UTIL)
    used, total = metrics.get(VRAM_USED), metrics.get(VRAM_TOTAL)
    lag = metrics.get(metric_name("lag", 50))
    parts = [
        f"GPU {gpu:.0f} %" if gpu is not None else f"GPU {NA}",
        (
            f"VRAM {used / MB_PER_GB:.1f} / {total / MB_PER_GB:.1f} GB"
            if used is not None and total is not None
            else f"VRAM {NA}"
        ),
        f"Speech {_ms(metrics, 'asr')}",
        f"Translate {_ms(metrics, 'mt')}",
        f"Lag {lag / 1000:.2f} s" if lag is not None else f"Lag {NA}",
    ]
    if game_mode:
        parts.insert(0, "Game mode")
    return SEPARATOR.join(parts)


class ReadoutStrip(QLabel):
    def __init__(self, store: Store, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._store = store
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)  # drag still works
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        font = QFont(FONTS.ui_family)
        font.setPointSize(FONTS.ui_size_small)
        self.setFont(font)
        store.runtime_changed.connect(self._on_runtime)
        store.config_changed.connect(
            lambda section: self.refresh() if section in ("performance", "all") else None
        )
        self.refresh()

    def apply_palette(self, palette: Palette) -> None:
        self.setStyleSheet(f"color: {palette.text_secondary}; background: transparent;")

    def _on_runtime(self, key: str) -> None:
        if key.startswith("metric:") and self.isVisible():
            self.refresh()

    def refresh(self) -> None:
        state = self._store.state
        self.setText(readout_text(state.runtime.metrics, state.config.performance.game_mode))
