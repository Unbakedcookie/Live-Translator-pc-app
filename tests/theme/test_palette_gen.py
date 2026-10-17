"""T012 — one-colour custom palettes (Tier A)."""

import itertools

import pytest

from livetranslator.theme import palette_gen
from livetranslator.theme.contrast import check_palette
from livetranslator.theme.palette_gen import argb_to_hex, generate_palette, hex_to_argb, ramp_hues
from livetranslator.theme.tokens import SPEAKER_RAMP_SIZE


def test_spec_seed_dark_passes():
    p = generate_palette("#3B82F6")
    assert p.id == "custom_3B82F6_dark"
    assert p.is_dark
    assert p.outline == "#000000"
    assert len(p.speaker_others) == SPEAKER_RAMP_SIZE
    assert check_palette(p) == []


@pytest.mark.parametrize("seed", ["#EF4444", "#22C55E", "#808080", "#FFFF66", "#000000", "#FFFFFF"])
@pytest.mark.parametrize("dark", [True, False], ids=["dark", "light"])
def test_extreme_seeds_pass(seed, dark):
    assert check_palette(generate_palette(seed, dark=dark)) == []


def test_bad_tone_is_auto_adjusted(monkeypatch: pytest.MonkeyPatch):
    # Force speaker colours to tone 25 on a ~tone-6 background: far below 4.5:1 before fixing.
    monkeypatch.setattr(palette_gen, "SPEAKER_TONE_DARK", 25.0)
    p = generate_palette("#3B82F6")
    raw_me = palette_gen._hct_hex(266.34, palette_gen.SPEAKER_CHROMA, 25.0)
    assert p.speaker_me != raw_me
    assert check_palette(p) == []


def test_ramp_hues_hand_computed():
    # 22.5 + 45k for k in (4, 0, 5, 1, 6, 2, 7, 3)
    assert ramp_hues(0.0) == [202.5, 22.5, 247.5, 67.5, 292.5, 112.5, 337.5, 157.5]
    assert ramp_hues(350.0) == [192.5, 12.5, 237.5, 57.5, 282.5, 102.5, 327.5, 147.5]


def test_ramp_neighbours_far_apart():
    hues = ramp_hues(123.0)
    for a, b in itertools.pairwise(hues):
        gap = abs(a - b) % 360
        assert min(gap, 360 - gap) >= 135


def test_hex_argb_round_trip():
    assert hex_to_argb("#3B82F6") == 0xFF3B82F6
    assert argb_to_hex(0xFF3B82F6) == "#3B82F6"
    with pytest.raises(ValueError):
        hex_to_argb("#FFF")
