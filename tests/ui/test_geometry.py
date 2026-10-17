"""T023 — snapping / restore / placement math (Tier A, hand-computed)."""

from livetranslator.ui.geometry import (
    Monitor,
    Rect,
    clamp_into,
    default_placement,
    fully_visible,
    monitor_for,
    restore,
    snap,
)

# The user's PC: one 5120x1440 ultrawide, 48 px taskbar -> work area 5120x1392.
ULTRAWIDE = [Monitor("Odyssey G95C", Rect(0, 0, 5120, 1440), Rect(0, 0, 5120, 1392), True)]
# A common dual setup: two 2560x1440 side by side, taskbar only on the primary (left).
DUAL = [
    Monitor("LEFT", Rect(0, 0, 2560, 1440), Rect(0, 0, 2560, 1392), True),
    Monitor("RIGHT", Rect(2560, 0, 2560, 1440), Rect(2560, 0, 2560, 1440)),
]
WORK = Rect(0, 0, 5120, 1392)


# ---------------------------------------------------------------- snap


def test_snap_to_work_area_left_and_bottom():
    # left 9 px from the edge -> 0; bottom = 1150 + 230 = 1380, 12 px above 1392 -> moves +12.
    assert snap(Rect(9, 1150, 520, 230), [WORK], []) == Rect(0, 1162, 520, 230)


def test_no_snap_beyond_threshold():
    assert snap(Rect(13, 500, 520, 230), [WORK], []) == Rect(13, 500, 520, 230)


def test_snap_right_edge_of_work_area():
    # right = 4590 + 520 = 5110 -> 10 px short of 5120.
    assert snap(Rect(4590, 400, 520, 230), [WORK], []) == Rect(4600, 400, 520, 230)


def test_dock_beside_another_window():
    other = Rect(1000, 1000, 520, 220)  # right edge 1520
    # Left at 1526 (6 px gap), vertically overlapping -> docks at 1520. y=1060 keeps every
    # vertical edge pair > 12 px apart (tops 60, bottoms 1260 vs 1220 = 40), so y stays.
    assert snap(Rect(1526, 1060, 400, 200), [], [other]) == Rect(1520, 1060, 400, 200)


def test_closest_candidate_wins():
    other = Rect(1000, 1000, 520, 220)
    # left 1526 -> dock (-6); top 1003 -> align tops (-3). Each axis independently.
    assert snap(Rect(1526, 1003, 400, 200), [], [other]) == Rect(1520, 1000, 400, 200)


def test_far_window_on_other_axis_does_not_pull():
    other = Rect(1000, 100, 520, 220)  # bottom 320, moving top 900: no vertical overlap
    assert snap(Rect(1526, 900, 400, 200), [], [other]) == Rect(1526, 900, 400, 200)


def test_stack_below_another_window():
    other = Rect(2000, 800, 520, 220)  # bottom 1020
    assert snap(Rect(2005, 1030, 520, 220), [], [other]) == Rect(2000, 1020, 520, 220)


# ---------------------------------------------------------------- clamp / restore


def test_clamp_moves_shortest_distance():
    assert clamp_into(Rect(5000, -50, 520, 220), WORK) == Rect(4600, 0, 520, 220)


def test_clamp_shrinks_oversized_window_but_not_below_minimum():
    assert clamp_into(Rect(-10, -10, 6000, 2000), WORK) == Rect(0, 0, 5120, 1392)
    tiny = Rect(0, 0, 100, 50)
    assert clamp_into(tiny, Rect(0, 0, 120, 40)) == Rect(-40, -20, 160, 60)


def test_restore_keeps_visible_window():
    r = Rect(2300, 1148, 520, 220)
    assert restore(r, "Odyssey G95C", ULTRAWIDE) == r


def test_restore_keeps_window_spanning_two_monitors():
    spanning = Rect(2300, 500, 520, 220)  # 2300..2820 crosses the 2560 seam
    assert fully_visible(spanning, DUAL)
    assert restore(spanning, "LEFT", DUAL) == spanning


def test_restore_window_from_missing_monitor_goes_to_primary():
    # Saved on the right monitor of a dual setup; now only the ultrawide exists... and the
    # window was at x=6000 (beyond 5120): pulled back into the primary work area.
    assert restore(Rect(6000, 300, 520, 220), "RIGHT", ULTRAWIDE) == Rect(4600, 300, 520, 220)


def test_restore_into_saved_monitor_if_present():
    # Partly below the left monitor's taskbar (bottom 1500 > 1392) -> clamped into LEFT.
    assert restore(Rect(100, 1280, 520, 220), "LEFT", DUAL) == Rect(100, 1172, 520, 220)


def test_monitor_for_picks_largest_overlap():
    assert monitor_for(Rect(2400, 0, 520, 220), DUAL).name == "RIGHT"  # 160 left vs 360 right
    assert monitor_for(Rect(9000, 0, 100, 100), DUAL).name == "LEFT"  # off-screen -> primary


# ---------------------------------------------------------------- default placement


def test_default_placement_bottom_centre_on_ultrawide():
    # x = (5120 - 520) / 2 = 2300; y = 1392 - 220 - 24 = 1148
    assert default_placement(ULTRAWIDE) == Rect(2300, 1148, 520, 220)


def test_default_placement_cascades_upwards():
    # second window: y = 1148 - (28 + 24) = 1096
    assert default_placement(ULTRAWIDE, index=1) == Rect(2300, 1096, 520, 220)


def test_default_placement_uses_primary_in_dual():
    # (2560 - 520) / 2 = 1020
    assert default_placement(DUAL) == Rect(1020, 1148, 520, 220)


# ---------------------------------------------------------------- resize


def test_edges_at_corners_and_sides():
    from livetranslator.ui.geometry import EDGE_BOTTOM, EDGE_LEFT, EDGE_RIGHT, EDGE_TOP, edges_at

    assert edges_at(520, 220, 2, 2) == EDGE_LEFT | EDGE_TOP
    assert edges_at(520, 220, 517, 218) == EDGE_RIGHT | EDGE_BOTTOM
    assert edges_at(520, 220, 260, 219) == EDGE_BOTTOM
    assert edges_at(520, 220, 260, 110) == 0  # grip is 6 px: 6..513 / 6..213 is the body
    assert edges_at(520, 220, 6, 6) == 0
    assert edges_at(520, 220, 514, 110) == EDGE_RIGHT  # 520 - 6 = 514 is inside the grip


def test_resize_right_bottom_grows():
    from livetranslator.ui.geometry import EDGE_BOTTOM, EDGE_RIGHT, resize_rect

    start = Rect(100, 100, 520, 220)
    assert resize_rect(start, EDGE_RIGHT | EDGE_BOTTOM, 80, 30) == Rect(100, 100, 600, 250)


def test_resize_left_keeps_right_edge_and_minimum():
    from livetranslator.ui.geometry import EDGE_LEFT, EDGE_TOP, resize_rect

    start = Rect(100, 100, 520, 220)  # right 620, bottom 320
    assert resize_rect(start, EDGE_LEFT, -50, 0) == Rect(50, 100, 570, 220)
    # Dragging left edge far right stops at right - 160 = 460; top stops at 320 - 60 = 260.
    assert resize_rect(start, EDGE_LEFT | EDGE_TOP, 900, 900) == Rect(460, 260, 160, 60)
