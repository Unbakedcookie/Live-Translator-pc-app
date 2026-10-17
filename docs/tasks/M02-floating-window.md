# M02 — Floating window shell (approval gate G1)

Goal: the overlay window every feature displays in. Spec: `project-spec.md` §5.1, §6.5. **SHARED. Nothing that depends on it is built until G1 is approved.**
Review: screenshots + the user tries it live (drag, resize, pin, opacity, colours).

### T021 — win32 helpers · Tier A (+ Tier B smoke)
- Files: `livetranslator/platform/win32.py`, `livetranslator/ui/screens.py` (Qt monitor adapter), `tests/platform/test_win32.py`
- Depends on: T011
- Acceptance: `set_topmost(hwnd, bool)`, `is_topmost(hwnd)`, `set_click_through(hwnd, bool)`, `is_click_through(hwnd)`. Unit tests check flag math (ex-style bit ops, hand-computed). Monitors come from Qt (`QScreen`: name, geometry, work area, in Qt device-independent pixels with per-monitor DPI) instead of raw Win32 enumeration; decided in T021 because geometry is persisted in Qt coordinates. Smoke test on a real window: the flags really toggle (read back via Win32).

### T022 — Widget kit · Tier B · SHARED (G1)
- Files: `livetranslator/ui/widgets/{icon_button,pin_button,slider,swatch,colour_seed_picker,language_picker,toast}.py`, `tests/ui/test_widgets.py`
- Depends on: T012
- Acceptance: all icons are QtAwesome Phosphor (exact `ph.` names checked against the installed charmap; pin uses an outline/fill pair); all styling comes from tokens; the colour-seed picker previews a generated palette; pytest-qt checks signals (pin toggled, slider value). A demo gallery (`python -m livetranslator.ui.gallery`) shows every widget in all 5 palettes. Screenshot reviewed by the user.

### T023 — Snapping + geometry math · Tier A
- Files: `livetranslator/ui/geometry.py`, `tests/ui/test_geometry.py`
- Depends on: T011
- Acceptance: pure functions. `snap(rect, targets, threshold=12)` and `restore(geometry, monitors)` (a missing monitor → moved onto the primary work area, size clamped). Hand-computed cases, including the user's single 5120×1440 ultrawide (work area 5120×1392), a dual 2560×1440 layout, a window spanning two monitors, and a missing monitor.

### T024 — FloatingWindow shell · Tier B · SHARED (G1)
- Files: `livetranslator/ui/floating_window.py`, `livetranslator/ui/style_popover.py`, `tests/ui/test_floating_window.py`
- Depends on: T014, T021, T022, T023
- Acceptance (verifier, fresh screenshot before each step):
  1. Hover shows chrome; leaving hides it after about 600 ms.
  2. Drag moves the window, and it snaps to the monitor edge and to a 2nd window.
  3. Edge/corner resize works and respects the minimum size.
  4. The pin icon toggles the Topmost flag (`win.ps1 list`).
  5. Background opacity 0–100 % leaves the text crisp; window opacity fades everything (Alpha in `list`).
  6. Palette switch recolours everything.
  7. Ctrl+wheel changes the font size.
  8. Click-through: clicks pass to the window below; toggling back works.
  9. Lock disables drag/resize.
  10. Restart → same geometry/style.
  - Demo text is sample lines (no engines yet).

### T025 — G1 review round · Tier B
- Files: `history/M02-floating-window.md` (feedback log)
- Depends on: T024
- Acceptance: the user approves the look and feel (or the requested changes are made and re-shown). Approval recorded in history + TASKS.md.
