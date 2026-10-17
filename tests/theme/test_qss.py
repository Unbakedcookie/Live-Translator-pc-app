"""T012 — QSS generated from tokens (Tier A + pytest-qt parse check)."""

from dataclasses import replace

from PySide6.QtWidgets import QWidget

from livetranslator.theme.qss import build_qss
from livetranslator.theme.tokens import MIDNIGHT, PALETTES

# Distinct placeholder colours so each token's position in the output is unambiguous.
SAMPLE = replace(
    MIDNIGHT,
    bg="#000001",
    surface="#000002",
    surface_alt="#000003",
    text_primary="#000004",
    text_secondary="#000005",
    accent="#000006",
    on_accent="#000007",
    border="#000008",
)

# Hand-written from the tokens: border 1 px, space xs/sm/md/xl = 4/8/12/24, radius sm/md = 4/8,
# UI font Inter 10 pt; slider groove 4 (radius 2), handle 12 (radius 6, margin -(12-4)/2 = -4).
EXPECTED = """\
QWidget { color: #000004; font-family: "Inter"; font-size: 10pt; }
QToolTip { background: #000002; color: #000004; border: 1px solid #000008; padding: 4px 8px; border-radius: 4px; }
QMenu { background: #000002; border: 1px solid #000008; padding: 4px; border-radius: 8px; }
QMenu::item { padding: 4px 12px; border-radius: 4px; }
QMenu::item:selected { background: #000003; }
QMenu::separator { height: 1px; background: #000008; margin: 4px 0px; }
QPushButton { background: #000003; border: 1px solid #000008; border-radius: 4px; padding: 4px 12px; }
QPushButton:hover { border-color: #000006; }
QToolButton { background: transparent; border: none; border-radius: 4px; padding: 2px; }
QToolButton:hover { background: #000003; }
QToolButton:checked { background: transparent; }
QPushButton:checked { background: #000006; color: #000007; }
QLineEdit, QComboBox, QSpinBox { background: #000001; border: 1px solid #000008; border-radius: 4px; padding: 4px 8px; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border-color: #000006; }
QComboBox[flat="true"] { background: transparent; border: none; }
QComboBox[flat="true"]:hover { background: #000003; }
QComboBox::drop-down { border: none; width: 20px; subcontrol-position: center right; }
QComboBox QAbstractItemView { background: #000002; border: 1px solid #000008; border-radius: 8px; padding: 4px; outline: 0px; }
QComboBox QAbstractItemView::item { min-height: 28px; padding: 0px 8px; border-radius: 4px; color: #000004; }
QComboBox QAbstractItemView::item:hover { background: #000003; }
QComboBox QAbstractItemView::item:selected { background: #000006; color: #000007; }
QSlider::groove:horizontal { height: 4px; background: #000003; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #000006; border-radius: 2px; }
QSlider::handle:horizontal { background: #000004; width: 12px; margin: -4px 0px; border-radius: 6px; }
QScrollBar:vertical { background: transparent; width: 8px; }
QScrollBar::handle:vertical { background: #000003; border-radius: 4px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
"""  # noqa: E501


def test_qss_matches_hand_written_expectation():
    assert build_qss(SAMPLE) == EXPECTED


def test_qt_accepts_every_palette_stylesheet(qtbot, qtlog):
    for palette in PALETTES.values():
        widget = QWidget()
        qtbot.addWidget(widget)
        widget.setStyleSheet(build_qss(palette))
        widget.ensurePolished()
    parse_errors = [r for r in qtlog.records if "parse" in r.message.lower()]
    assert parse_errors == []
