"""Window placement math: snapping, restore, default placement (T023; spec §5.1).

Pure functions on plain rectangles (Qt device-independent pixels). No Qt import, so every rule
is unit-tested with hand-computed numbers. `ui/screens.py` feeds in the real monitors.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from livetranslator.theme.tokens import SPACE, WINDOW


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    width: int
    height: int

    @property
    def left(self) -> int:
        return self.x

    @property
    def top(self) -> int:
        return self.y

    @property
    def right(self) -> int:
        """Exclusive right edge (x + width)."""
        return self.x + self.width

    @property
    def bottom(self) -> int:
        """Exclusive bottom edge (y + height)."""
        return self.y + self.height

    def moved(self, dx: int, dy: int) -> Rect:
        return Rect(self.x + dx, self.y + dy, self.width, self.height)

    def contains_point(self, px: int, py: int) -> bool:
        return self.left <= px < self.right and self.top <= py < self.bottom

    def intersection_area(self, other: Rect) -> int:
        w = min(self.right, other.right) - max(self.left, other.left)
        h = min(self.bottom, other.bottom) - max(self.top, other.top)
        return max(w, 0) * max(h, 0)


@dataclass(frozen=True)
class Monitor:
    name: str
    geometry: Rect
    work: Rect  # geometry minus taskbar
    primary: bool = False


def _best_shift(candidates: Sequence[int], threshold: int) -> int:
    best = 0
    best_abs = threshold + 1
    for shift in candidates:
        if abs(shift) < best_abs:
            best, best_abs = shift, abs(shift)
    return best if best_abs <= threshold else 0


def snap(
    moving: Rect,
    work_areas: Sequence[Rect],
    windows: Sequence[Rect],
    threshold: int = WINDOW.snap_threshold,
) -> Rect:
    """Snap a dragged window's edges to work-area edges and to other windows' edges.

    Work areas: the window's left/right/top/bottom align with the same edge of the area.
    Other windows: the window docks against them (my left to their right, ...) or aligns
    with their same edge, but only when the two overlap (within `threshold`) on the other
    axis, so a window far below never pulls a horizontal snap. Each axis snaps independently
    to its closest candidate within `threshold`.
    """
    dx: list[int] = []
    dy: list[int] = []
    for area in work_areas:
        dx += [area.left - moving.left, area.right - moving.right]
        dy += [area.top - moving.top, area.bottom - moving.bottom]
    for other in windows:
        overlaps_vertically = (
            moving.top <= other.bottom + threshold and moving.bottom >= other.top - threshold
        )
        overlaps_horizontally = (
            moving.left <= other.right + threshold and moving.right >= other.left - threshold
        )
        if overlaps_vertically:
            dx += [
                other.right - moving.left,
                other.left - moving.right,
                other.left - moving.left,
                other.right - moving.right,
            ]
        if overlaps_horizontally:
            dy += [
                other.bottom - moving.top,
                other.top - moving.bottom,
                other.top - moving.top,
                other.bottom - moving.bottom,
            ]
    return moving.moved(_best_shift(dx, threshold), _best_shift(dy, threshold))


EDGE_LEFT = 1
EDGE_RIGHT = 2
EDGE_TOP = 4
EDGE_BOTTOM = 8


def edges_at(width: int, height: int, px: int, py: int, grip: int = WINDOW.resize_grip) -> int:
    """Which resize edges (EDGE_* bits) a point inside a width x height window is on."""
    edges = 0
    if px < grip:
        edges |= EDGE_LEFT
    elif px >= width - grip:
        edges |= EDGE_RIGHT
    if py < grip:
        edges |= EDGE_TOP
    elif py >= height - grip:
        edges |= EDGE_BOTTOM
    return edges


def resize_rect(
    start: Rect,
    edges: int,
    dx: int,
    dy: int,
    min_width: int = WINDOW.min_width,
    min_height: int = WINDOW.min_height,
) -> Rect:
    """Drag the given edges by (dx, dy); the opposite edges stay put; never below the minimum."""
    left, top, right, bottom = start.left, start.top, start.right, start.bottom
    if edges & EDGE_LEFT:
        left = min(left + dx, right - min_width)
    if edges & EDGE_RIGHT:
        right = max(right + dx, left + min_width)
    if edges & EDGE_TOP:
        top = min(top + dy, bottom - min_height)
    if edges & EDGE_BOTTOM:
        bottom = max(bottom + dy, top + min_height)
    return Rect(left, top, right - left, bottom - top)


def clamp_into(rect: Rect, area: Rect) -> Rect:
    """Fit `rect` inside `area`: shrink to the area if needed (never below the minimum size),
    then move it the shortest distance so it lies inside."""
    width = max(min(rect.width, area.width), WINDOW.min_width)
    height = max(min(rect.height, area.height), WINDOW.min_height)
    x = min(max(rect.x, area.left), area.right - width)
    y = min(max(rect.y, area.top), area.bottom - height)
    return Rect(x, y, width, height)


def primary_monitor(monitors: Sequence[Monitor]) -> Monitor:
    if not monitors:
        raise ValueError("no monitors")
    return next((m for m in monitors if m.primary), monitors[0])


def monitor_for(rect: Rect, monitors: Sequence[Monitor]) -> Monitor:
    """The monitor showing most of `rect` (primary if it is on none)."""
    best = max(monitors, key=lambda m: m.geometry.intersection_area(rect))
    if best.geometry.intersection_area(rect) == 0:
        return primary_monitor(monitors)
    return best


def fully_visible(rect: Rect, monitors: Sequence[Monitor]) -> bool:
    """True if all four corners lie in some monitor's work area (allows spanning monitors)."""
    corners = (
        (rect.left, rect.top),
        (rect.right - 1, rect.top),
        (rect.left, rect.bottom - 1),
        (rect.right - 1, rect.bottom - 1),
    )
    return all(any(m.work.contains_point(x, y) for m in monitors) for x, y in corners)


def restore(rect: Rect, screen: str, monitors: Sequence[Monitor]) -> Rect:
    """Where to put a saved window at startup (spec §5.1).

    Fully visible -> unchanged (even across monitors). Otherwise it is pulled into its saved
    monitor's work area, or the primary one if that monitor is gone (unplugged, renamed).
    """
    if not monitors or fully_visible(rect, monitors):
        return rect
    target = next((m for m in monitors if m.name == screen), None) or primary_monitor(monitors)
    return clamp_into(rect, target.work)


def default_placement(
    monitors: Sequence[Monitor],
    width: int = WINDOW.default_width,
    height: int = WINDOW.default_height,
    margin: int = SPACE.xl,
    index: int = 0,
) -> Rect:
    """Bottom-centre of the primary work area; the n-th extra window is cascaded upwards."""
    work = primary_monitor(monitors).work
    x = work.left + (work.width - width) // 2
    y = work.bottom - height - margin - index * (WINDOW.chrome_height + margin)
    return clamp_into(Rect(x, y, width, height), work)
