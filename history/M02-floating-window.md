# M02 — Floating window shell (gate G1) · history

## 2026-10-17 — Session 2 (user away; autonomous)

### Hardware correction found while starting T021
- Qt's `QGuiApplication.screens()` reports **one** screen: "Odyssey G95C", 5120×1440, devicePixelRatio 1.0, work area 5120×1392 (a 48 px taskbar).
- Phase 0 had recorded "two 2560×1440 monitors". That was inferred from `win.ps1`'s 5120-px virtual desktop and never checked against the monitor list.
- Fixed in: DATA_TRACKER D-014, TASKS.md conventions, the M00 hardware note, the M02 task text, and my user-profile memory.
- Lesson: report a hardware fact only after asking the OS for it directly, not from an aggregate number.

### T021 — Win32 helpers
- `platform/win32.py`:
  - ctypes `GetWindowLongPtrW` / `SetWindowLongPtrW` / `SetWindowPos`.
  - `set_topmost` uses HWND_TOPMOST / NOTOPMOST with SWP_NOMOVE | NOSIZE | NOACTIVATE.
  - `set_click_through` toggles WS_EX_TRANSPARENT, adds WS_EX_LAYERED when enabling, and never removes LAYERED, because Qt uses it for window opacity. It then calls SetWindowPos with SWP_FRAMECHANGED so Windows re-reads the style.
  - The pure flag functions are separated out so they can be tested without a window.
- **Design fork: monitors from Qt (`ui/screens.py`) instead of Win32 EnumDisplayMonitors.** Window geometry is stored in Qt device-independent pixels, and Qt handles per-monitor DPI, so mixing in physical Win32 coordinates would invite scaling bugs on other users' PCs. The task text was updated to match. The `Geometry` docstring said "physical pixels" and was corrected.
- Verification:
  - Hand-computed flag math: 0x108 → 0x80128 when enabling, 0x80128 → 0x80108 when disabling, idempotent in both directions.
  - **A real-window smoke test** on this PC: topmost and click-through toggle on a real frameless translucent Qt window and read back via Win32. The HWND is unchanged (no re-creation) and so is the geometry.

### T023 — Placement math (`ui/geometry.py`, pure)
- `Rect`, `Monitor`.
- `snap`:
  - Work-area edges align with the same edge.
  - Other windows: dock or align, only when the two overlap on the other axis (± threshold).
  - Each axis snaps independently to the nearest candidate within 12 px.
- `clamp_into`: shrink to fit, never below the 160×60 minimum, then move the shortest distance.
- `restore`: a fully visible window (all four corners inside some work area) is left alone, so windows spanning monitors survive. Otherwise it's pulled into its saved monitor, or into the primary if that monitor is gone.
- `default_placement`: bottom-centre of the primary work area, with extra windows cascading upwards. On this PC: (2300, 1148, 520×220).
- **Bug found by the tests, in my expectation rather than the code.** In "dock beside another window", the test window's top was 10 px from the other window's top, so it correctly aligned as well. I moved the case to y=1060 and documented the edge distances in the test.
- Verification: 17 hand-computed tests on the user's ultrawide and a dual 2560×1440 layout (seam crossing, missing monitor, taskbar on only one monitor).
