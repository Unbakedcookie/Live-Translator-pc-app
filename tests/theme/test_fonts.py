"""T012 — fonts: per-script fallback stacks (Tier A) and bundled registration (pytest-qt)."""

from pathlib import Path

import pytest
from PySide6.QtGui import QFontDatabase

from livetranslator.theme.fonts import (
    bundled_font_files,
    overlay_families,
    register_fonts,
    script_family,
)


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("ja", "Noto Sans JP"),
        ("ko", "Noto Sans KR"),
        ("zh", "Noto Sans SC"),
        ("zh-TW", "Noto Sans TC"),
        ("zh_Hant", "Noto Sans TC"),
        ("ar", "Noto Sans Arabic"),
        ("hi", "Noto Sans Devanagari"),
        ("es", None),
        ("pt-BR", None),
        ("ru", None),
        (None, None),
        ("", None),
    ],
)
def test_script_family(language, expected):
    assert script_family(language) == expected


def test_stack_for_japanese_with_pack_installed():
    available = {"Inter", "Noto Sans", "Noto Sans JP", "Segoe UI"}
    assert overlay_families(None, "ja", available) == ["Inter", "Noto Sans JP", "Noto Sans"]


def test_user_choice_first_and_missing_fonts_skipped():
    available = {"Inter", "Noto Sans", "Segoe UI"}
    assert overlay_families("Segoe UI", "ja", available) == ["Segoe UI", "Inter", "Noto Sans"]
    assert overlay_families("Comic Neue", "es", available) == ["Inter", "Noto Sans"]


def test_case_insensitive_and_deduplicated():
    available = {"inter", "Noto Sans"}
    assert overlay_families("INTER", None, available) == ["inter", "Noto Sans"]


def test_nothing_installed_gives_empty_stack():
    assert overlay_families(None, "ko", set()) == []


def test_bundled_files_are_the_six_ttfs():
    assert [p.name for p in bundled_font_files()] == [
        "Inter-Bold.ttf",
        "Inter-Medium.ttf",
        "Inter-Regular.ttf",
        "Inter-SemiBold.ttf",
        "NotoSans-Bold.ttf",
        "NotoSans-Regular.ttf",
    ]


def test_register_bundled_fonts(qapp):
    families = register_fonts(bundled_font_files())
    assert {"Inter", "Noto Sans"} <= families
    assert {"Regular", "Medium", "SemiBold", "Bold"} <= set(QFontDatabase.styles("Inter"))


def test_broken_font_file_is_skipped(qapp, tmp_path: Path):
    broken = tmp_path / "broken.ttf"
    broken.write_bytes(b"not a font")
    assert register_fonts([broken]) == set()
