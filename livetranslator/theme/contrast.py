"""Contrast and colour-distance rules (T012; spec §6.5), computed with ColorAide.

- Text and speaker colours vs. their background: WCAG 2.1 contrast ratio >= 4.5.
- Non-text UI (accent on surfaces): >= 3.0 (WCAG 1.4.11).
- Speaker colours next to each other in the ramp: CIEDE2000 >= 20 so voices stay distinct.

Checks run on the opaque background colour. Overlays at reduced background opacity rely on
the text outline/shadow for legibility over arbitrary game content.
"""

from __future__ import annotations

from dataclasses import fields
from typing import TYPE_CHECKING

from coloraide import Color

if TYPE_CHECKING:
    from livetranslator.theme.tokens import Palette

TEXT_MIN_RATIO = 4.5
UI_MIN_RATIO = 3.0
SPEAKER_MIN_DELTA_E = 20.0

# (foreground, background) token pairs that carry text.
TEXT_PAIRS: tuple[tuple[str, str], ...] = (
    ("text_primary", "bg"),
    ("text_primary", "surface"),
    ("text_primary", "surface_alt"),
    ("text_secondary", "bg"),
    ("text_secondary", "surface"),
    ("on_accent", "accent"),
    ("danger", "surface"),
    ("ok", "surface"),
    ("speaker_me", "bg"),
    ("speaker_screen", "bg"),
)
# (foreground, background) pairs for non-text UI such as icons, focus rings and sliders.
UI_PAIRS: tuple[tuple[str, str], ...] = (("accent", "bg"), ("accent", "surface"))


def contrast_ratio(fg: str, bg: str) -> float:
    return Color(fg).contrast(bg, method="wcag21")


def delta_e(a: str, b: str) -> float:
    return Color(a).delta_e(b, method="2000")


def to_hex(color: Color) -> str:
    return color.convert("srgb").fit("srgb").to_string(hex=True, upper=True)


def ensure_contrast(fg: str, bg: str, minimum: float = TEXT_MIN_RATIO) -> str:
    """Return `fg`, or the nearest lightness-shifted version of it that meets `minimum` on `bg`.

    Lightness moves away from the background (lighter on dark backgrounds, darker on light
    ones) in OKLCH, keeping hue and chroma, so the colour keeps its identity.
    """
    if contrast_ratio(fg, bg) >= minimum:
        return fg.upper()
    lighten = Color(bg).luminance() < 0.18  # mid-grey in relative luminance
    color = Color(fg).convert("oklch")
    step = 0.01 if lighten else -0.01
    lightness = float(color["lightness"])
    while 0.0 <= lightness <= 1.0:
        lightness += step
        candidate = color.clone().set("lightness", min(max(lightness, 0.0), 1.0))
        hex_value = to_hex(candidate)
        if contrast_ratio(hex_value, bg) >= minimum:
            return hex_value
    return "#FFFFFF" if lighten else "#000000"


def check_palette(palette: Palette) -> list[str]:
    """Every rule the palette breaks, as readable messages (empty list = passes)."""
    values = {f.name: getattr(palette, f.name) for f in fields(palette)}
    problems: list[str] = []

    for fg, bg in TEXT_PAIRS:
        ratio = contrast_ratio(values[fg], values[bg])
        if ratio < TEXT_MIN_RATIO:
            problems.append(f"{palette.id}: {fg} on {bg} contrast {ratio:.2f} < {TEXT_MIN_RATIO}")
    for i, color in enumerate(palette.speaker_others, start=1):
        ratio = contrast_ratio(color, palette.bg)
        if ratio < TEXT_MIN_RATIO:
            problems.append(
                f"{palette.id}: speaker_others[{i}] on bg contrast {ratio:.2f} < {TEXT_MIN_RATIO}"
            )
    for fg, bg in UI_PAIRS:
        ratio = contrast_ratio(values[fg], values[bg])
        if ratio < UI_MIN_RATIO:
            problems.append(f"{palette.id}: {fg} on {bg} contrast {ratio:.2f} < {UI_MIN_RATIO}")

    sequence = (palette.speaker_me, *palette.speaker_others)
    for i in range(len(sequence) - 1):
        distance = delta_e(sequence[i], sequence[i + 1])
        if distance < SPEAKER_MIN_DELTA_E:
            problems.append(
                f"{palette.id}: speaker colours {i} and {i + 1} too similar "
                f"(dE2000 {distance:.1f} < {SPEAKER_MIN_DELTA_E})"
            )
    distance = delta_e(palette.speaker_me, palette.speaker_screen)
    if distance < SPEAKER_MIN_DELTA_E:
        problems.append(
            f"{palette.id}: speaker_me and speaker_screen too similar (dE2000 {distance:.1f})"
        )
    return problems
