"""Label + slider + live percentage, for opacity-style 0..1 values (T022)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSlider, QWidget

from livetranslator.theme.tokens import SPACE

STEPS = 100


class LabeledSlider(QWidget):
    value_changed = Signal(float)  # fraction, emitted while dragging

    def __init__(
        self,
        label: str,
        minimum: float,
        maximum: float,
        value: float,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._label = QLabel(label, self)
        self._slider = QSlider(Qt.Orientation.Horizontal, self)
        self._slider.setRange(round(minimum * STEPS), round(maximum * STEPS))
        self._slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._value_label = QLabel(self)
        self._value_label.setMinimumWidth(
            self._value_label.fontMetrics().horizontalAdvance("100 %")
        )
        self._value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACE.sm)
        layout.addWidget(self._label)
        layout.addWidget(self._slider, 1)
        layout.addWidget(self._value_label)
        self._slider.valueChanged.connect(self._on_slider)
        self.set_value(value)

    def value(self) -> float:
        return self._slider.value() / STEPS

    def set_value(self, value: float) -> None:
        """Set without emitting value_changed (used when the store pushes state)."""
        self._slider.blockSignals(True)
        self._slider.setValue(round(value * STEPS))
        self._slider.blockSignals(False)
        self._value_label.setText(f"{self._slider.value()} %")

    def _on_slider(self, raw: int) -> None:
        self._value_label.setText(f"{raw} %")
        self.value_changed.emit(raw / STEPS)
