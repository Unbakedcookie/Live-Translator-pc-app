"""T012 — Phosphor-only icons coloured from the palette (pytest-qt)."""

import pytest
from PySide6.QtCore import QSize

from livetranslator.theme.icons import has_icon, icon
from livetranslator.theme.tokens import MIDNIGHT, PAPER


def test_known_icons_exist(qapp):
    for name in ("push-pin", "push-pin-fill", "palette", "x", "gear", "translate", "discord-logo"):
        assert has_icon(name), name
        assert not icon(name, MIDNIGHT).isNull()


def test_other_icon_sets_are_rejected(qapp):
    with pytest.raises(ValueError, match="bare Phosphor"):
        icon("fa5s.thumbtack", MIDNIGHT)
    assert not has_icon("mdi.pin")


def test_unknown_name_is_value_error(qapp):
    with pytest.raises(ValueError, match="unknown Phosphor icon"):
        icon("definitely-not-an-icon", MIDNIGHT)
    assert not has_icon("definitely-not-an-icon")


@pytest.mark.parametrize(("palette", "role"), [(MIDNIGHT, "accent"), (PAPER, "danger")])
def test_icon_is_drawn_in_the_palette_colour(qapp, palette, role):
    image = icon("square-fill", palette, role).pixmap(QSize(32, 32)).toImage()
    center = image.pixelColor(16, 16)
    assert center.name().upper() == getattr(palette, role)
