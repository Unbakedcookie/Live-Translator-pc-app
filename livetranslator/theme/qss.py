"""Qt stylesheet generated from tokens (T012; spec §6.5).

Covers the standard widgets used in chrome, popovers, menus and dialogs. Overlay text is
painted directly from the palette, not through QSS. Each window applies the QSS of its own
palette, so windows can use different themes side by side.
"""

from __future__ import annotations

from livetranslator.theme.tokens import FONTS, RADIUS, SPACE, WINDOW, Palette


def _rule(selector: str, *declarations: str) -> str:
    return f"{selector} {{ {' '.join(d + ';' for d in declarations)} }}"


def build_qss(p: Palette) -> str:
    border = f"{WINDOW.border_width}px solid {p.border}"
    pad = f"{SPACE.xs}px {SPACE.sm}px"
    groove = SPACE.xs
    handle = SPACE.md
    handle_margin = -(handle - groove) // 2
    rules = [
        _rule(
            "QWidget",
            f"color: {p.text_primary}",
            f'font-family: "{FONTS.ui_family}"',
            f"font-size: {FONTS.ui_size}pt",
        ),
        _rule(
            "QToolTip",
            f"background: {p.surface}",
            f"color: {p.text_primary}",
            f"border: {border}",
            f"padding: {pad}",
            f"border-radius: {RADIUS.sm}px",
        ),
        _rule(
            "QMenu",
            f"background: {p.surface}",
            f"border: {border}",
            f"padding: {SPACE.xs}px",
            f"border-radius: {RADIUS.md}px",
        ),
        _rule(
            "QMenu::item", f"padding: {SPACE.xs}px {SPACE.md}px", f"border-radius: {RADIUS.sm}px"
        ),
        _rule("QMenu::item:selected", f"background: {p.surface_alt}"),
        _rule(
            "QMenu::separator",
            f"height: {WINDOW.border_width}px",
            f"background: {p.border}",
            f"margin: {SPACE.xs}px 0px",
        ),
        _rule(
            "QPushButton",
            f"background: {p.surface_alt}",
            f"border: {border}",
            f"border-radius: {RADIUS.sm}px",
            f"padding: {SPACE.xs}px {SPACE.md}px",
        ),
        _rule("QPushButton:hover", f"border-color: {p.accent}"),
        _rule(
            "QToolButton",
            "background: transparent",
            "border: none",
            f"border-radius: {RADIUS.sm}px",
            f"padding: {SPACE.xs // 2}px",
        ),
        _rule("QToolButton:hover", f"background: {p.surface_alt}"),
        _rule("QToolButton:checked", "background: transparent"),  # state shows in the icon
        _rule("QPushButton:checked", f"background: {p.accent}", f"color: {p.on_accent}"),
        _rule(
            "QLineEdit, QComboBox, QSpinBox",
            f"background: {p.bg}",
            f"border: {border}",
            f"border-radius: {RADIUS.sm}px",
            f"padding: {pad}",
        ),
        _rule(
            "QLineEdit:focus, QComboBox:focus, QSpinBox:focus",
            f"border-color: {p.accent}",
        ),
        _rule(
            'QComboBox[flat="true"]',
            "background: transparent",
            "border: none",
        ),
        _rule('QComboBox[flat="true"]:hover', f"background: {p.surface_alt}"),
        _rule(
            "QComboBox QAbstractItemView",
            f"background: {p.surface}",
            f"selection-background-color: {p.surface_alt}",
            f"border: {border}",
        ),
        _rule(
            "QSlider::groove:horizontal",
            f"height: {groove}px",
            f"background: {p.surface_alt}",
            f"border-radius: {groove // 2}px",
        ),
        _rule(
            "QSlider::sub-page:horizontal",
            f"background: {p.accent}",
            f"border-radius: {groove // 2}px",
        ),
        _rule(
            "QSlider::handle:horizontal",
            f"background: {p.text_primary}",
            f"width: {handle}px",
            f"margin: {handle_margin}px 0px",
            f"border-radius: {handle // 2}px",
        ),
        _rule("QScrollBar:vertical", "background: transparent", f"width: {SPACE.sm}px"),
        _rule(
            "QScrollBar::handle:vertical",
            f"background: {p.surface_alt}",
            f"border-radius: {SPACE.sm // 2}px",
            f"min-height: {SPACE.xl}px",
        ),
        _rule(
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical",
            "height: 0px",
        ),
    ]
    return "\n".join(rules) + "\n"
