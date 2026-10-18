"""Screen capture of a region (T083; spec §5.6) via mss.

Coordinates are physical screen pixels on the virtual desktop (what the region selector
returns and what `tools/verify/win.ps1 shot` reports). The result is the OCR contract's
H x W x 3 RGB uint8 array.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from livetranslator.services.ocr.base import Image


@dataclass(frozen=True)
class Region:
    x: int
    y: int
    width: int
    height: int

    @property
    def is_empty(self) -> bool:
        return self.width <= 0 or self.height <= 0


def bgra_to_rgb(raw: bytes | bytearray | memoryview, width: int, height: int) -> Image:
    """mss gives BGRA rows; the OCR contract wants RGB."""
    pixels = np.frombuffer(bytes(raw), dtype=np.uint8).reshape(height, width, 4)
    return np.ascontiguousarray(pixels[:, :, 2::-1])


def grab(region: Region) -> Image:
    if region.is_empty:
        raise ValueError(f"empty region {region}")
    import mss  # lazy: only when someone actually captures

    box = {"left": region.x, "top": region.y, "width": region.width, "height": region.height}
    with mss.mss() as screen:
        shot = screen.grab(box)
    return bgra_to_rgb(shot.bgra, shot.width, shot.height)
