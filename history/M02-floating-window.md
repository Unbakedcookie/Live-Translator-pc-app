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

### T022 — Widget kit (`ui/widgets/`, `ui/gallery.py`)
- What was built:
  - `IconButton`: a flat Phosphor tool button; an optional checked icon/role turns it into a toggle.
  - `PinButton`: push-pin (text_secondary) / push-pin-fill (accent) with tooltips.
  - `LabeledSlider`: label, slider and a live "70 %" readout. Fractions in and out; `set_value` doesn't emit, so a store push never echoes back as a user change.
  - `PaletteSwatch` / `SwatchRow`: exclusive palette picker. Each swatch is a circle in the palette's bg with accent, Me and first-speaker dots, and the selection ring takes the owning window's accent. Selecting a custom palette clears every built-in swatch.
  - `ColourSeedPicker`: a swatch of the generated palette; clicking opens QColorDialog and emits the '#RRGGBB' seed.
  - `LanguagePicker`: the 15 default languages as "English · Native" labels. It emits the ISO code, and an unknown code is added on the fly.
  - `Toast`: a frameless tooltip-type window that doesn't take focus and deletes itself after MOTION.toast_ms.
  - `core/languages.py`: the 15-language catalog approved in spec section 13 Q3.
  - QSS gained `QToolButton` rules (transparent, radius sm, padding xs/2, surface_alt on hover); the hand-written expected QSS string in test_qss was updated to match.
  - Gallery: `python -m livetranslator.ui.gallery` shows every widget in all 5 palettes.
- Design: every widget gets its colours via `apply_palette` or the generated QSS. Widgets that read the store are NoFocus, so they never steal keyboard focus from a game.
- Problem hit: my toast test touched the widget after WA_DeleteOnClose had already deleted it ("Internal C++ object already deleted"). The widget was right; the test now waits for `destroyed`.
- Verification:
  - 8 pytest-qt tests. The pin icon's actual pixel colour flips text_secondary to accent on click, and the tooltip changes. Also covered: icon recolour on palette change, slider fraction and silent set_value, swatch selection and custom clearing, language picker (15 entries, labels, silent set, unknown code), seed picker id, toast self-deletion, and the gallery building 5 panels.
  - Gallery render (scratchpad gallery.png) inspected: correct in all 5 palettes. A cosmetic nit for the G1 review: Paper's combobox shows the native Windows dropdown arrow.
