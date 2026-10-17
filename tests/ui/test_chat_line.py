"""T061 — chat line layout (Tier A with a fake 10 px-per-character font) + paint smoke."""

from PySide6.QtGui import QImage, QPainter

from livetranslator.core.chat_view import ChatLineData
from livetranslator.core.state import WindowStyle
from livetranslator.theme.fonts import bundled_font_files, register_fonts
from livetranslator.theme.tokens import MIDNIGHT
from livetranslator.ui.widgets.chat_line import (
    Role,
    Row,
    Run,
    chat_fonts,
    layout_line,
    layout_rows,
    paint_rows,
    rows_height,
    speaker_color,
)


def ten(text: str) -> float:
    return 10.0 * len(text)


def rows(line: ChatLineData, width: float = 200) -> list[Row]:
    return layout_rows(line, width, ten, ten, ten)


# Label "Mika" + two spaces = 6 chars = 60 px indent; width 200 leaves 140 px = 14 chars.


def test_wraps_with_hanging_indent_and_role_change_between_rows():
    line = ChatLineData("u", "Mika", 0, "Okay wait for", "me at the gate", None)
    # "Okay wait for me" is 16 chars > 14, so row 1 ends after "for".
    assert rows(line) == [
        Row((Run(0, "Mika  ", Role.LABEL), Run(60, "Okay wait for", Role.STABLE))),
        Row((Run(60, "me at the gate", Role.CHANGING),)),
    ]


def test_role_change_inside_a_row():
    line = ChatLineData("u", "Mika", 0, "Okay wait", "for me", None)
    # Row 1 "Okay wait for": stable "Okay wait", changing "for" starts after
    # "Okay wait " (10 chars = 100 px) -> x = 60 + 100 = 160.
    assert rows(line) == [
        Row(
            (
                Run(0, "Mika  ", Role.LABEL),
                Run(60, "Okay wait", Role.STABLE),
                Run(160, "for", Role.CHANGING),
            )
        ),
        Row((Run(60, "me", Role.CHANGING),)),
    ]


def test_original_rows_follow_in_the_original_font():
    line = ChatLineData("u", "Mika", 0, "Okay", "", "わかった、門で待ってて。")
    # 12 chars = 120 px fits in 140.
    assert rows(line) == [
        Row((Run(0, "Mika  ", Role.LABEL), Run(60, "Okay", Role.STABLE))),
        Row((Run(60, "わかった、門で待ってて。", Role.ORIGINAL),), original=True),
    ]


def test_long_word_breaks_by_characters_and_empty_text_keeps_the_label():
    long = ChatLineData("u", "Mika", 0, "", "abcdefghijklmnopqrst", None)  # 20 chars
    assert rows(long) == [
        Row((Run(0, "Mika  ", Role.LABEL), Run(60, "abcdefghijklmn", Role.CHANGING))),
        Row((Run(60, "opqrst", Role.CHANGING),)),
    ]
    empty = ChatLineData("u", "Mika", 0, "", "", None)
    assert rows(empty) == [Row((Run(0, "Mika  ", Role.LABEL),))]


def test_speaker_colours_come_from_the_palette():
    assert speaker_color(MIDNIGHT, "me") == MIDNIGHT.speaker_me
    assert speaker_color(MIDNIGHT, "screen") == MIDNIGHT.speaker_screen
    assert speaker_color(MIDNIGHT, 9) == MIDNIGHT.speaker_others[9 % 8]


def test_real_fonts_layout_and_paint(qtbot):
    register_fonts(bundled_font_files())
    fonts = chat_fonts(WindowStyle(font_size=16), "en")
    line = ChatLineData("u", "Mika", 0, "Okay, wait for me", "at the gate.", "orig")
    laid = layout_line(line, 180, fonts)
    assert len(laid) >= 3 and laid[-1].original
    text_h = fonts.text_metrics.height()
    assert rows_height(laid, fonts) > text_h * 2
    image = QImage(200, 200, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    painter = QPainter(image)
    paint_rows(painter, laid, 0, 0, fonts, MIDNIGHT, WindowStyle(), 0)
    painter.end()
    painted = sum(
        1 for x in range(0, 200, 4) for y in range(0, 200, 4) if image.pixelColor(x, y).alpha()
    )
    assert painted > 20
