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

### T024 — FloatingWindow shell + app composition (user away; autonomous)
- What was built:
  - `ui/floating_window.py`: frameless, Tool and WindowDoesNotAcceptFocus (clicking the overlay never steals focus from a game), WA_TranslucentBackground.
    - Painted rounded background at bg_opacity, floored at 1/255 so a 0 % window can still be grabbed (fully transparent pixels let clicks through on Windows).
    - Border shows only while hovered.
    - ChromeBar (pin, flat language dropdown, sources label, then style / hide / close) fades in on hover and out 600 ms after leaving. A cursor-inside check keeps it while the popover is open or a drag is running.
    - Drag and resize happen locally and are committed once on mouse release, with snapping (`snap`) and edge resize (`resize_rect`, min 160×60). Locked windows ignore both.
    - Ctrl+wheel changes font size (8–72). The right-click menu has Style…, New window, Hide, Close, Quit.
    - Pin, click-through and Mica are applied to the native HWND after show.
  - `ui/style_popover.py`: palette swatches + one-colour seed + Light, bg / whole-window opacity sliders, font + size, outline + width, shadow, "show original too", sources (the last one can't be unticked), lock, click-through (closes the popover), frosted glass. It re-reads the store on every window_changed.
  - `ui/sample_content.py`: demo lines for the G1 review (replaced by TranslationView in T062). Bottom-anchored, word-wrapped, outlined via the shared `ui/text_paint.py`, drop shadow via QGraphicsDropShadowEffect, original text in the secondary colour when display=BOTH, filtered by sources.
  - `app/window_controller.py` (intents → actions, hotkey toggles), `app/window_manager.py` (create/destroy per store, default placement + cascade, restore onto existing monitors, hide one / show-hide all, quit when the last window closes until the tray exists), `app/application.py` (composition root: fonts, load settings + damaged-file notice, store, persistence, hotkeys with conflict statuses, default window), and `__main__` (plain start launches the app; Qt is only imported then).
  - Palette lookup: `theme.palette_gen.palette_for` (lru-cached). `DEFAULT_CUSTOM_SEED` moved into tokens after the style-literal lint test caught "#3B82F6" in two UI files.
- Design forks:
  - **No focus-taking.** WindowDoesNotAcceptFocus keeps a game focused; the dropdown and popups still work (verified live, check 8).
  - **Geometry is committed once per drag.** This avoids flooding the store and settings writes.
  - **The hide button is runtime-only** (not persisted). Ctrl+Alt+H "show all" brings back individually hidden windows too.
  - **T081 hotkeys were pulled forward** so click-through always has a way back (see M08 history).
- Problems hit and fixed:
  1. ruff RUF001 on the full-width "！" in the Japanese sample. It's correct Japanese, so it carries a noqa with the reason.
  2. Unused unpacked test variables.
  3. pyright optional `geometry` access in tests (typed `geom()` helpers).
  4. My PowerShell one-liner with embedded Python broke on quoting, so nothing ran. I moved the edits into a scratch .py file.
  5. **A real bug found by my own render check after the verifier**: ChromeBar only applied its QSS on palette *changes*, so every new window's strip used native Windows styling. On Paper the language and sources text was invisible; on Midnight the dropdown had a white box and the pin a highlight square. The fix applies the QSS in the constructor, plus `QToolButton:checked { background: transparent }`, plus a flat dropdown (`QComboBox[flat="true"]`). A regression test was added. The verifier missed it because its Paper-theme checks happened with the chrome hidden or the popup open.
  6. Process slip: I once staged with `git add livetranslator tests` (directory names) instead of file names. I checked that only intended files were staged and went back to explicit names.
  7. Commit-ordering trap: pre-commit stashes unstaged changes but leaves untracked files, so committing T031 before T024 made pyright see half of T024. I committed T024 first.
- Verification:
  - Tier A / pytest-qt: 252 total.
    - Window: config sync, chrome QSS from the first palette, pin ↔ native topmost, click-through and opacity, a drag commits exactly one store change, snap to x=0, right-edge resize, lock, Ctrl+wheel 16→17→16→15, chrome hover in and out, popover controls, last-source guard, language picker, close.
    - Controller: hotkey toggles. Manager: placement, cascade, off-screen restore, quit on last close, hide / show-all.
    - App: first start makes and saves one window, second start restores it, damaged-settings notice.
  - **Tier B (verifier agent, real desktop, fresh LIVETRANSLATOR_HOME): 13/16 PASS.**
    - Passed: startup at (2300, 1148, 520×220) topmost; idle look; hover chrome in and out; drag; snap X=0; resize 620/160/520; pin; **language dropdown works in the no-focus window**; style popup + Paper + background 1 %; click-through (Discord underneath got the hover, so input really passes through) + Ctrl+Alt+T recovery; Ctrl+Alt+H; new window at Y=1096 and close; lock.
    - Check 10 "FAIL" was a tooling limit: win.ps1 reads Alpha via GetLayeredWindowAttributes, which is -1 for Qt per-pixel-alpha windows. The behaviour was right (label 64 %, settings 0.64, visibly translucent; pytest asserts windowOpacity). The verifier notes were updated.
    - Check 15 partial: geometry and lock survived a restart (numeric). Theme/language were in settings.json and are covered by the in-process restore test; visual confirmation waits for the user's G1 review.
    - Check 16 (Ctrl+wheel) can't be driven by win.ps1 and is covered by pytest.
    - No ERROR or Traceback in the logs.
  - Startup timing (warm): about 1.3 s to a painted window, about 1.0 s of it Python imports. The slowest are coloraide and loguru (about 0.2 s each). Candidate later optimisation: lazy-import coloraide (only needed for custom palettes). The verifier saw >6 s on a relaunch, likely a cold start; to be re-timed.
  - Found on the user's PC: **Ctrl+Alt+M (mute Me) is already registered by another app** (error 1409). The app reports it as a status, as designed; the user will be asked about the default.
- Open for G1: the user's look-and-feel review of the palettes, widgets and live window.
