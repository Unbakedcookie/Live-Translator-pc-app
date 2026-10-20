"""Custom palettes from one seed colour (T012; spec §6.5).

materialyoucolor (Material 3 dynamic colour, tonal-spot scheme) supplies surfaces, text,
accent and error colours. Speaker colours are generated in HCT at a fixed chroma/tone so they
stay vivid even for grey seeds; the ramp hues are ordered so neighbours sit >= 135 degrees
apart. Every text colour is then pushed through `ensure_contrast`, so any seed yields a
palette that passes `check_palette`.
"""

from __future__ import annotations

import importlib
from dataclasses import replace
from functools import lru_cache
from typing import Any

from livetranslator.theme.contrast import (
    TEXT_MIN_RATIO,
    UI_MIN_RATIO,
    ensure_contrast,
    relative_luminance,
)
from livetranslator.theme.tokens import DEFAULT_PALETTE_ID, PALETTES, SPEAKER_RAMP_SIZE, Palette

# materialyoucolor ships without type information.
_hct: Any = importlib.import_module("materialyoucolor.hct")
_scheme: Any = importlib.import_module("materialyoucolor.scheme.scheme_tonal_spot")
_dyn: Any = importlib.import_module("materialyoucolor.dynamiccolor.material_dynamic_colors")

SPEAKER_CHROMA = 48.0
SPEAKER_TONE_DARK = 80.0
SPEAKER_TONE_LIGHT = 40.0
OK_HUE = 145.0  # green
SCREEN_HUE_OFFSET = 90.0
# SPEAKER_RAMP_SIZE (8) hues at 22.5 + 45k degrees from the seed hue, ordered so neighbours
# are >= 135 degrees apart and the first is opposite "Me" (which uses the seed hue itself).
_RAMP_STEPS = (4, 0, 5, 1, 6, 2, 7, 3)


def hex_to_argb(color: str) -> int:
    value = color.lstrip("#")
    if len(value) != 6:
        raise ValueError(f"expected '#RRGGBB', got {color!r}")
    return 0xFF000000 | int(value, 16)


def argb_to_hex(argb: int) -> str:
    return f"#{argb & 0xFFFFFF:06X}"


def _hct_hex(hue: float, chroma: float, tone: float) -> str:
    return argb_to_hex(_hct.Hct.from_hct(hue % 360.0, chroma, tone).to_int())


def ramp_hues(seed_hue: float) -> list[float]:
    return [(seed_hue + 22.5 + 45.0 * step) % 360.0 for step in _RAMP_STEPS]


DARK_BG_LUMINANCE = 0.4  # a custom background darker than this counts as a dark theme


@lru_cache(maxsize=32)
def palette_for(
    palette_id: str,
    custom_seed: str | None,
    custom_dark: bool,
    custom_colors: tuple[tuple[str, str], ...] = (),
) -> Palette:
    """The palette a window uses: generated from its seed if it has one, else a built-in
    (unknown ids fall back to the default so a stale setting never breaks a window), then
    any colours the user set one by one."""
    if custom_seed:
        base = generate_palette(custom_seed, dark=custom_dark)
    else:
        base = PALETTES.get(palette_id, PALETTES[DEFAULT_PALETTE_ID])
    return with_colors(base, custom_colors)


def with_colors(base: Palette, colors: tuple[tuple[str, str], ...]) -> Palette:
    """`base` with some colours replaced (names as in tokens.color_names). Unknown names are
    ignored. A new background decides whether the result counts as dark."""
    if not colors:
        return base
    others = list(base.speaker_others)
    changes: dict[str, object] = {}
    for name, color in colors:
        if name.startswith("speaker_others_"):
            index = int(name.removeprefix("speaker_others_")) - 1
            if 0 <= index < SPEAKER_RAMP_SIZE:
                others[index] = color
        elif name in base.__dataclass_fields__ and name not in ("id", "name", "is_dark"):
            changes[name] = color
    bg = str(changes.get("bg", base.bg))
    return replace(
        base,
        id=f"{base.id}_edited",
        name=f"{base.name} (custom)",
        is_dark=relative_luminance(bg) < DARK_BG_LUMINANCE,
        speaker_others=tuple(others),
        **changes,  # type: ignore[arg-type]
    )


def generate_palette(seed: str, *, dark: bool = True, name: str | None = None) -> Palette:
    seed_hct = _hct.Hct.from_int(hex_to_argb(seed))
    scheme = _scheme.SchemeTonalSpot(seed_hct, dark, 0.0)
    colors = _dyn.MaterialDynamicColors

    def role(dynamic_color: Any) -> str:
        return argb_to_hex(dynamic_color.get_argb(scheme))

    bg = role(colors.surface)
    surface = role(colors.surfaceContainer)
    surface_alt = role(colors.surfaceContainerHighest)
    accent = role(colors.primary)
    tone = SPEAKER_TONE_DARK if dark else SPEAKER_TONE_LIGHT
    seed_hue = float(seed_hct.hue)

    def text_on(fg: str, *backgrounds: str, minimum: float = TEXT_MIN_RATIO) -> str:
        for background in backgrounds:
            fg = ensure_contrast(fg, background, minimum)
        return fg

    text_primary = text_on(role(colors.onSurface), bg, surface, surface_alt)
    ramp = tuple(text_on(_hct_hex(h, SPEAKER_CHROMA, tone), bg) for h in ramp_hues(seed_hue))

    return Palette(
        id=f"custom_{seed.lstrip('#').upper()}_{'dark' if dark else 'light'}",
        name=name or f"Custom {seed.upper()}",
        is_dark=dark,
        bg=bg,
        surface=surface,
        surface_alt=surface_alt,
        text_primary=text_primary,
        text_secondary=text_on(role(colors.onSurfaceVariant), bg, surface),
        accent=text_on(accent, bg, surface, minimum=UI_MIN_RATIO),
        on_accent=ensure_contrast(role(colors.onPrimary), accent),
        border=role(colors.outlineVariant),
        outline="#000000" if dark else "#FFFFFF",
        danger=text_on(role(colors.error), surface),
        ok=text_on(_hct_hex(OK_HUE, SPEAKER_CHROMA, tone), surface),
        speaker_me=text_on(_hct_hex(seed_hue, SPEAKER_CHROMA, tone), bg),
        speaker_screen=text_on(_hct_hex(seed_hue + SCREEN_HUE_OFFSET, 36.0, tone), bg),
        speaker_others=ramp,
    )
