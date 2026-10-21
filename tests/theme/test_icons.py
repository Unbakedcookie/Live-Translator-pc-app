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


def test_app_icon_is_a_red_tile_with_a_white_glyph(qapp):
    """User request 2026-10-19: the blue glyph blended into the desktop."""
    from PySide6.QtGui import QColor

    from livetranslator.theme.icons import app_icon
    from livetranslator.theme.tokens import APP_ICON

    image = app_icon().pixmap(APP_ICON.size, APP_ICON.size).toImage()
    edge = APP_ICON.size // 2
    assert image.pixelColor(edge, 2) == QColor(APP_ICON.tile)  # top middle: the tile
    assert image.pixelColor(0, 0).alpha() == 0  # rounded corner
    colours = {
        image.pixelColor(x, y).name().upper()
        for x in range(0, APP_ICON.size, 4)
        for y in range(0, APP_ICON.size, 4)
    }
    assert APP_ICON.glyph in colours


def test_tray_states_are_readable_at_a_glance(qapp):
    """2026-10-20: the tray icon by the clock was the old blue glyph. Listening = the red
    app tile, paused = grey tile, a problem = red tile with a yellow dot."""
    from PySide6.QtGui import QColor

    from livetranslator.theme.icons import app_icon
    from livetranslator.theme.tokens import APP_ICON

    size = APP_ICON.size
    top = (size // 2, 2)
    corner = (round(size * 0.85), round(size * 0.85))
    listening = app_icon("listening").pixmap(size, size).toImage()
    paused = app_icon("paused").pixmap(size, size).toImage()
    attention = app_icon("attention").pixmap(size, size).toImage()
    assert listening.pixelColor(*top) == QColor(APP_ICON.tile)
    assert paused.pixelColor(*top) == QColor(APP_ICON.tile_paused)
    assert attention.pixelColor(*top) == QColor(APP_ICON.tile)
    assert attention.pixelColor(*corner) == QColor(APP_ICON.badge)  # the dot
    assert listening.pixelColor(*corner) != QColor(APP_ICON.badge)
