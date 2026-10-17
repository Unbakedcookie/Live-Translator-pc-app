"""Design tokens and built-in palettes (T012; spec §6.5). The single source of style values.

Sizes are in Qt units: font sizes in points, everything else in device-independent pixels.
"""

from __future__ import annotations

from dataclasses import dataclass, fields

SPEAKER_RAMP_SIZE = 8


@dataclass(frozen=True)
class Palette:
    """A full colour scheme for one overlay window (all values are '#RRGGBB')."""

    id: str
    name: str
    is_dark: bool
    bg: str  # overlay content background (drawn at the window's background opacity)
    surface: str  # chrome strip, popovers, menus
    surface_alt: str  # hover / pressed / selected
    text_primary: str  # final text
    text_secondary: str  # tentative (partial) text, captions
    accent: str  # active toggles (pin on), focus, slider fill
    on_accent: str  # text/icons drawn on accent
    border: str
    outline: str  # overlay text outline / shadow colour
    danger: str
    ok: str
    speaker_me: str
    speaker_screen: str
    speaker_others: tuple[str, ...]  # SPEAKER_RAMP_SIZE colours, neighbours far apart in hue

    def speaker_color(self, index: int) -> str:
        """Colour for the n-th other speaker (0-based); wraps after the ramp."""
        return self.speaker_others[index % len(self.speaker_others)]


def color_tokens(palette: Palette) -> dict[str, str]:
    """Flatten a palette into `name -> '#RRGGBB'` (speaker ramp as speaker_others_1..8)."""
    tokens: dict[str, str] = {}
    for f in fields(palette):
        value = getattr(palette, f.name)
        if f.name == "speaker_others":
            for i, color in enumerate(value, start=1):
                tokens[f"speaker_others_{i}"] = color
        elif isinstance(value, str) and value.startswith("#"):
            tokens[f.name] = value
    return tokens


MIDNIGHT = Palette(
    id="midnight",
    name="Midnight",
    is_dark=True,
    bg="#0F1115",
    surface="#1A1D24",
    surface_alt="#272B34",
    text_primary="#F2F4F8",
    text_secondary="#A9B1BE",
    accent="#5B9DFF",
    on_accent="#0B1220",
    border="#2E333D",
    outline="#000000",
    danger="#FF7A7A",
    ok="#4ADE80",
    speaker_me="#7DD3FC",
    speaker_screen="#C4B5FD",
    speaker_others=(
        "#FCA5A5",
        "#5EEAD4",
        "#FCD34D",
        "#A5B4FC",
        "#BEF264",
        "#F9A8D4",
        "#67E8F9",
        "#FDBA74",
    ),
)

SUBTITLE = Palette(
    id="subtitle",
    name="Subtitle",
    is_dark=True,
    bg="#000000",
    surface="#141414",
    surface_alt="#2A2A2A",
    text_primary="#FFFFFF",
    text_secondary="#BDBDBD",
    accent="#FFD54F",
    on_accent="#000000",
    border="#3A3A3A",
    outline="#000000",
    danger="#FF6B6B",
    ok="#69F0AE",
    speaker_me="#FFE082",
    speaker_screen="#B39DDB",
    speaker_others=(
        "#80DEEA",
        "#FF8A80",
        "#C5E1A5",
        "#CE93D8",
        "#FFCC80",
        "#90CAF9",
        "#F48FB1",
        "#A5D6A7",
    ),
)

PAPER = Palette(
    id="paper",
    name="Paper",
    is_dark=False,
    bg="#FAFAF7",
    surface="#FFFFFF",
    surface_alt="#ECEDE8",
    text_primary="#1B1D21",
    text_secondary="#565B66",
    accent="#1D4ED8",
    on_accent="#FFFFFF",
    border="#D5D7DC",
    outline="#FFFFFF",
    danger="#B91C1C",
    ok="#15803D",
    speaker_me="#0369A1",
    speaker_screen="#6D28D9",
    speaker_others=(
        "#B91C1C",
        "#0F766E",
        "#B45309",
        "#4338CA",
        "#4D7C0F",
        "#BE185D",
        "#0E7490",
        "#C2410C",
    ),
)

NEON = Palette(
    id="neon",
    name="Neon",
    is_dark=True,
    bg="#170A2E",
    surface="#22103F",
    surface_alt="#321A57",
    text_primary="#F5F3FF",
    text_secondary="#C0B6DE",
    accent="#F472B6",
    on_accent="#1A0B14",
    border="#4A3373",
    outline="#000000",
    danger="#FF5C7A",
    ok="#3CFFA0",
    speaker_me="#22D3EE",
    speaker_screen="#E879F9",
    speaker_others=(
        "#F87171",
        "#34D399",
        "#FBBF24",
        "#818CF8",
        "#A3E635",
        "#F472B6",
        "#38BDF8",
        "#FB923C",
    ),
)

HIGH_CONTRAST = Palette(
    id="high_contrast",
    name="High Contrast",
    is_dark=True,
    bg="#000000",
    surface="#000000",
    surface_alt="#262626",
    text_primary="#FFFFFF",
    text_secondary="#E6E6E6",
    accent="#FFFF00",
    on_accent="#000000",
    border="#FFFFFF",
    outline="#000000",
    danger="#FF6E6E",
    ok="#00FF7F",
    speaker_me="#00FFFF",
    speaker_screen="#FF80FF",
    speaker_others=(
        "#FFA500",
        "#00FF7F",
        "#FF80C0",
        "#C0FF00",
        "#8CA0FF",
        "#FFFF00",
        "#FF6E6E",
        "#00E5FF",
    ),
)

PALETTES: dict[str, Palette] = {p.id: p for p in (MIDNIGHT, SUBTITLE, PAPER, NEON, HIGH_CONTRAST)}
DEFAULT_PALETTE_ID = MIDNIGHT.id


@dataclass(frozen=True)
class Fonts:
    ui_family: str = "Inter"
    overlay_family: str = "Inter"
    fallback_family: str = "Noto Sans"
    ui_size_small: int = 9
    ui_size: int = 10
    ui_size_large: int = 12
    overlay_size_default: int = 16
    overlay_size_min: int = 8
    overlay_size_max: int = 72
    weight_regular: int = 400
    weight_medium: int = 500
    weight_bold: int = 700


@dataclass(frozen=True)
class Spacing:
    xs: int = 4
    sm: int = 8
    md: int = 12
    lg: int = 16
    xl: int = 24


@dataclass(frozen=True)
class Radius:
    sm: int = 4
    md: int = 8
    lg: int = 12


@dataclass(frozen=True)
class Motion:
    chrome_fade_ms: int = 150
    chrome_hide_delay_ms: int = 600
    toast_ms: int = 2500


@dataclass(frozen=True)
class OverlayText:
    outline_width_default: int = 2  # dark palettes: dark outline around light text
    outline_width_light: int = 1  # light palettes: a thick light halo looks soft (G1 feedback)
    outline_width_max: int = 6
    shadow_blur: int = 8
    shadow_offset: int = 1


@dataclass(frozen=True)
class WindowMetrics:
    chrome_height: int = 28
    icon_size: int = 16
    resize_grip: int = 6
    snap_threshold: int = 12
    min_width: int = 160
    min_height: int = 60
    default_width: int = 520
    default_height: int = 220
    bg_opacity_default: float = 0.70
    window_opacity_default: float = 1.0
    window_opacity_min: float = 0.30
    border_width: int = 1


FONTS = Fonts()
SPACE = Spacing()
RADIUS = Radius()
MOTION = Motion()
OVERLAY = OverlayText()
WINDOW = WindowMetrics()


def default_outline_width(palette: Palette) -> int:
    """Default overlay text outline for a palette: thinner on light palettes."""
    return OVERLAY.outline_width_default if palette.is_dark else OVERLAY.outline_width_light
