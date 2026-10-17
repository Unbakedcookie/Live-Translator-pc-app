"""T012 — contrast and speaker-distinctness rules (Tier A).

Hand-computed WCAG 2.1 values (relative luminance L, ratio = (L1 + 0.05) / (L2 + 0.05)):
  #777777: channel 119/255 = 0.466667 -> ((0.466667 + 0.055) / 1.055) ** 2.4 = 0.184447
           vs white: 1.05 / 0.234447 = 4.4786
  #3B82F6: R 0.043734, G 0.223228, B 0.921583 (linearised)
           L = 0.2126 R + 0.7152 G + 0.0722 B = 0.235489
           vs black: 0.285489 / 0.05 = 5.7098
"""

from dataclasses import replace

import pytest
from coloraide import Color

from livetranslator.theme.contrast import check_palette, contrast_ratio, delta_e, ensure_contrast
from livetranslator.theme.tokens import MIDNIGHT, PALETTES


def test_wcag_hand_computed_cases():
    assert contrast_ratio("#FFFFFF", "#000000") == pytest.approx(21.0)
    assert contrast_ratio("#777777", "#FFFFFF") == pytest.approx(4.4786, abs=0.001)
    assert contrast_ratio("#3B82F6", "#000000") == pytest.approx(5.7098, abs=0.001)


def test_contrast_is_symmetric():
    assert contrast_ratio("#000000", "#777777") == pytest.approx(
        contrast_ratio("#777777", "#000000")
    )


def test_delta_e_identical_is_zero_and_red_green_far():
    assert delta_e("#FF0000", "#FF0000") == pytest.approx(0.0)
    assert delta_e("#FF0000", "#00FF00") > 50


@pytest.mark.parametrize("palette", PALETTES.values(), ids=PALETTES.keys())
def test_builtin_palettes_pass_every_rule(palette):
    assert check_palette(palette) == []


def test_low_contrast_text_is_reported():
    bad = replace(MIDNIGHT, text_secondary="#2A2D33")
    problems = check_palette(bad)
    assert any(p.startswith("midnight: text_secondary on bg contrast") for p in problems)


def test_similar_neighbour_speakers_are_reported():
    ramp = (MIDNIGHT.speaker_me, *MIDNIGHT.speaker_others[1:])
    problems = check_palette(replace(MIDNIGHT, speaker_others=ramp))
    assert any("speaker colours 0 and 1 too similar" in p for p in problems)


def test_ensure_contrast_keeps_passing_colour():
    assert ensure_contrast("#f2f4f8", "#0F1115") == "#F2F4F8"


def test_ensure_contrast_darkens_on_mid_grey():
    # #808080 has luminance 0.216 (> 0.18), so text must get darker.
    fixed = ensure_contrast("#777777", "#808080")
    assert contrast_ratio(fixed, "#808080") >= 4.5
    assert Color(fixed).luminance() < Color("#777777").luminance()


def test_ensure_contrast_lightens_and_keeps_hue():
    fixed = ensure_contrast("#3B82F6", "#1E3A8A")
    assert contrast_ratio(fixed, "#1E3A8A") >= 4.5
    before = Color("#3B82F6").convert("oklch")["hue"]
    after = Color(fixed).convert("oklch")["hue"]
    assert abs(before - after) < 10
