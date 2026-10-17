"""T012 — built-in palettes and tokens (Tier A)."""

import re

import pytest

from livetranslator.theme.tokens import (
    DEFAULT_PALETTE_ID,
    MIDNIGHT,
    PALETTES,
    SPEAKER_RAMP_SIZE,
    WINDOW,
    color_tokens,
    default_outline_width,
)

HEX = re.compile(r"^#[0-9A-F]{6}$")


def test_five_builtin_palettes():
    assert list(PALETTES) == ["midnight", "subtitle", "paper", "neon", "high_contrast"]
    assert DEFAULT_PALETTE_ID == "midnight"


def test_every_palette_defines_every_colour_token():
    key_sets = {pid: set(color_tokens(p)) for pid, p in PALETTES.items()}
    reference = key_sets["midnight"]
    assert all(keys == reference for keys in key_sets.values())
    assert {"bg", "text_primary", "speaker_me", "speaker_others_1", "speaker_others_8"} <= reference
    # 13 named colours (bg ... speaker_screen) + the speaker ramp.
    assert len(reference) == 13 + SPEAKER_RAMP_SIZE


@pytest.mark.parametrize("palette", PALETTES.values(), ids=PALETTES.keys())
def test_colours_are_uppercase_hex_and_ramp_is_full(palette):
    assert len(palette.speaker_others) == SPEAKER_RAMP_SIZE
    for name, value in color_tokens(palette).items():
        assert HEX.match(value), f"{palette.id}.{name} = {value!r}"


def test_speaker_colour_wraps_after_ramp():
    assert MIDNIGHT.speaker_color(0) == MIDNIGHT.speaker_others[0]
    assert MIDNIGHT.speaker_color(7) == MIDNIGHT.speaker_others[7]
    assert MIDNIGHT.speaker_color(8) == MIDNIGHT.speaker_others[0]


def test_outline_thinner_on_light_palettes():
    # G1 feedback default (2026-10-17): 2 px on dark palettes, 1 px on light ones.
    assert default_outline_width(MIDNIGHT) == 2
    assert default_outline_width(PALETTES["paper"]) == 1
    assert [p.id for p in PALETTES.values() if not p.is_dark] == ["paper"]


def test_window_metrics_match_spec():
    # spec §5.1: 28 px chrome, 6 px grips, 12 px snap, min 160x60, default 520x220,
    # background opacity 70 %, window opacity 30-100 %.
    assert (WINDOW.chrome_height, WINDOW.resize_grip, WINDOW.snap_threshold) == (28, 6, 12)
    assert (WINDOW.min_width, WINDOW.min_height) == (160, 60)
    assert (WINDOW.default_width, WINDOW.default_height) == (520, 220)
    assert WINDOW.bg_opacity_default == 0.70
    assert (WINDOW.window_opacity_min, WINDOW.window_opacity_default) == (0.30, 1.0)
