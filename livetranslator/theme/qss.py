"""Qt stylesheet generated from tokens (T012; spec §6.5).

Covers the standard widgets used in chrome, popovers, menus and dialogs. Overlay text is
painted directly from the palette, not through QSS. Each window applies the QSS of its own
palette, so windows can use different themes side by side.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from livetranslator.theme.tokens import FONTS, RADIUS, SETTINGS, SPACE, WINDOW, Palette


def _rule(selector: str, *declarations: str) -> str:
    return f"{selector} {{ {' '.join(d + ';' for d in declarations)} }}"


@dataclass(frozen=True)
class QssImages:
    """Icon PNGs for the parts QSS can only draw from files (G1: one look for every
    dropdown, number box and checkbox instead of the native Windows arrows and ticks)."""

    caret_down: Path
    caret_up: Path
    check: Path


def build_qss(p: Palette, images: QssImages | None = None) -> str:
    """The stylesheet for palette `p`. `images` replace the native arrows and tick;
    `window_qss` supplies them, plain `build_qss` stays pure for tests."""
    return _base_rules(p) + ("" if images is None else _image_rules(images))


def badge_qss(p: Palette) -> str:
    """A small rounded notice label (e.g. the click-through hint inside an overlay)."""
    return (
        f"background: {p.surface}; color: {p.text_primary}; "
        f"border: {WINDOW.border_width}px solid {p.border}; border-radius: {RADIUS.md}px; "
        f"padding: {SPACE.xs}px {SPACE.sm}px;"
    )


def pill_qss(p: Palette) -> str:
    """A small accent button floating over content (e.g. "New lines" in the chat, T062)."""
    return (
        f"QPushButton {{ background: {p.accent}; color: {p.on_accent}; border: none; "
        f"border-radius: {RADIUS.lg}px; padding: {SPACE.xs}px {SPACE.md}px; }}"
    )


def window_qss(p: Palette) -> str:
    """build_qss with themed Phosphor arrows and tick (needs a QApplication)."""
    from livetranslator.theme.icons import icon_file

    size = SPACE.md * 2  # drawn at half size in QSS: sharp on high-DPI screens
    return build_qss(
        p,
        QssImages(
            caret_down=icon_file("caret-down", p, "text_secondary", size),
            caret_up=icon_file("caret-up", p, "text_secondary", size),
            check=icon_file("check-bold", p, "on_accent", size),
        ),
    )


def settings_qss(p: Palette) -> str:
    """Extra rules for the Settings window (T072), added after `window_qss`. Parts are
    addressed by object name so nothing leaks into the overlays."""
    border = f"{WINDOW.border_width}px solid {p.border}"
    rules = [
        _rule("#SettingsRoot", f"background: {p.bg}"),
        _rule("#SettingsNav", "background: transparent", "border: none", "outline: none"),
        _rule(
            "#SettingsNav::item",
            f"padding: {SPACE.sm}px {SPACE.md}px",
            f"margin: {SPACE.xs // 2}px 0px",
            f"border-radius: {RADIUS.sm}px",
            f"color: {p.text_secondary}",
        ),
        _rule("#SettingsNav::item:hover", f"background: {p.surface}"),
        _rule(
            "#SettingsNav::item:selected",
            f"background: {p.surface_alt}",
            f"color: {p.text_primary}",
        ),
        _rule("QScrollArea#SettingsPage", "background: transparent", "border: none"),
        _rule("#SettingsPageBody", "background: transparent"),
        _rule(
            "#SettingsPageTitle",
            f"font-size: {SETTINGS.title_size}pt",
            f"font-weight: {FONTS.weight_bold}",
        ),
        _rule(
            "#SettingsSectionTitle",
            f"color: {p.text_secondary}",
            f"font-weight: {FONTS.weight_medium}",
        ),
        _rule(
            "#SettingsCard",
            f"background: {p.surface}",
            f"border: {border}",
            f"border-radius: {RADIUS.md}px",
        ),
        _rule("#SettingsDivider", f"background: {p.border}", "border: none"),
        _rule(
            "#SettingsRowDescription, #SettingsNote",
            f"color: {p.text_secondary}",
            f"font-size: {FONTS.ui_size_small}pt",
        ),
        _rule("#SettingsError", f"color: {p.danger}", f"font-size: {FONTS.ui_size_small}pt"),
        _rule("#SettingsWarning", f"color: {p.danger}"),
        _rule(
            "QPushButton:disabled",
            f"color: {p.text_secondary}",
            f"background: {p.surface}",
            f"border-color: {p.surface_alt}",
        ),
        _rule(
            "QPushButton#HotkeyBox",
            f"background: {p.bg}",
            "text-align: left",
            f"padding: {SPACE.xs}px {SPACE.sm}px",
        ),
        _rule(
            "QPushButton#HotkeyBox:checked",
            f"background: {p.bg}",
            f"color: {p.accent}",
            f"border-color: {p.accent}",
        ),
    ]
    return "".join(r + "\n" for r in rules)


def dialog_qss(p: Palette) -> str:
    """Message boxes (T064): `window_qss` sets light text, so they need a matching background."""
    return _rule("QMessageBox", f"background: {p.bg}") + "\n"


def transcript_qss(p: Palette) -> str:
    """The transcript window (T063), added after `window_qss` + `settings_qss`."""
    rules = [
        _rule("#TranscriptRoot", f"background: {p.bg}"),
        _rule(
            "QTextBrowser#TranscriptView",
            f"background: {p.surface}",
            f"border: {WINDOW.border_width}px solid {p.border}",
            f"border-radius: {RADIUS.md}px",
            f"padding: {SPACE.sm}px",
            f"selection-background-color: {p.accent}",
            f"selection-color: {p.on_accent}",
        ),
    ]
    return "".join(r + "\n" for r in rules)


def _image_rules(images: QssImages) -> str:
    def image(selector: str, path: Path, size: int) -> str:
        return _rule(
            selector, f'image: url("{path.as_posix()}")', f"width: {size}px", f"height: {size}px"
        )

    rules = [
        image("QComboBox::down-arrow", images.caret_down, SPACE.md),
        image("QSpinBox::up-arrow", images.caret_up, SPACE.sm + SPACE.xs // 2),
        image("QSpinBox::down-arrow", images.caret_down, SPACE.sm + SPACE.xs // 2),
        image("QCheckBox::indicator:checked", images.check, SPACE.md),
    ]
    return "".join(r + "\n" for r in rules)


def _base_rules(p: Palette) -> str:
    border = f"{WINDOW.border_width}px solid {p.border}"
    pad = f"{SPACE.xs}px {SPACE.sm}px"
    groove = SPACE.xs
    handle = SPACE.md
    handle_margin = -(handle - groove) // 2
    arrow_col = SPACE.lg + SPACE.xs  # width of the dropdown / number-box arrow column
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
            "QComboBox::drop-down",
            "border: none",
            f"width: {arrow_col}px",
            "subcontrol-position: center right",
        ),
        _rule(
            "QComboBox QAbstractItemView",
            f"background: {p.surface}",
            f"border: {border}",
            f"border-radius: {RADIUS.md}px",
            f"padding: {SPACE.xs}px",
            "outline: 0px",
        ),
        _rule(
            "QComboBox QAbstractItemView::item",
            f"min-height: {WINDOW.chrome_height}px",
            f"padding: 0px {SPACE.sm}px",
            f"border-radius: {RADIUS.sm}px",
            f"color: {p.text_primary}",
        ),
        _rule("QComboBox QAbstractItemView::item:hover", f"background: {p.surface_alt}"),
        _rule(
            "QComboBox QAbstractItemView::item:selected",
            f"background: {p.accent}",
            f"color: {p.on_accent}",
        ),
        # Number boxes: the same caret as the dropdowns, stacked in a column of the
        # dropdown arrow's width (G1 feedback: keep the app uniform).
        _rule("QSpinBox", f"padding-right: {arrow_col}px"),
        _rule(
            "QSpinBox::up-button, QSpinBox::down-button",
            "subcontrol-origin: border",
            f"width: {arrow_col}px",
            "border: none",
            "background: transparent",
            f"border-radius: {RADIUS.sm}px",
        ),
        _rule("QSpinBox::up-button", "subcontrol-position: top right"),
        _rule("QSpinBox::down-button", "subcontrol-position: bottom right"),
        _rule(
            "QSpinBox::up-button:hover, QSpinBox::down-button:hover",
            f"background: {p.surface_alt}",
        ),
        _rule("QCheckBox", f"spacing: {SPACE.sm}px"),
        _rule(
            "QCheckBox::indicator",
            f"width: {SPACE.md + SPACE.xs}px",
            f"height: {SPACE.md + SPACE.xs}px",
            f"background: {p.bg}",
            f"border: {border}",
            f"border-radius: {RADIUS.sm}px",
        ),
        _rule("QCheckBox::indicator:hover", f"border-color: {p.accent}"),
        _rule(
            "QCheckBox::indicator:checked",
            f"background: {p.accent}",
            f"border-color: {p.accent}",
        ),
        _rule("QCheckBox:disabled", f"color: {p.text_secondary}"),
        _rule(
            "QCheckBox::indicator:disabled",
            f"background: {p.surface_alt}",
            f"border-color: {p.surface_alt}",
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
        _rule(
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical",
            "background: transparent",
        ),
    ]
    return "\n".join(rules) + "\n"
