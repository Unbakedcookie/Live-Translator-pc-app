# M08 — Global hotkeys + screen OCR · history

## 2026-10-17 — T081 pulled forward (user away; autonomous)

### Why now
- **Click-through needed a way out.** M02's floating window (gate G1) has a click-through mode. Once it's on, the window ignores the mouse, and spec §3.4 says the way back is a hotkey or the tray. The tray is M07, which comes after G1, so without hotkeys the G1 demo could trap a window with no way back.
- **Nothing blocks it.** T081 depends only on T021 + T014 (both done), so building it before M02's window was allowed by the dependency map.
- **OCR comes later.** The OCR hotkey actions (T083) are registered when OCR exists.

### What was built (`services/hotkeys.py`)
- `parse_hotkey` / `format_hotkey`:
  - Case-insensitive modifiers: Ctrl/Control, Alt, Shift, Win/Meta.
  - Keys: A–Z, 0–9, F1–F24, plus named keys.
  - Exactly one key, and at least one modifier unless it's an F-key (a bare global letter would swallow typing).
  - Output uses the canonical order Ctrl, Alt, Shift, Win.
- `HotkeyService(QObject)`:
  - `RegisterHotKey(NULL, id, mods | MOD_NOREPEAT, vk)` on the main thread.
  - A `QAbstractNativeEventFilter` catches WM_HOTKEY and emits `triggered(action)`.
  - A combination that's invalid or already taken returns False with a log line (no raise).
  - `close()` unregisters everything and removes the filter.
- **Anti-cheat note (D-020):** there's no keyboard hook. Windows only tells us about our own combinations.

### Problem hit
- pyright: `bytes(QByteArray)` works at runtime but isn't in PySide6's stubs. I switched to `QByteArray.data()`.

### Verification
- 19 tests: parse cases with hand-checked VK codes ('H' = 0x48, 'T' = 0x54, '5' = 0x35, F1 = 0x70, F24 = 0x87, PageDown = 0x22, Space = 0x20), rejects, canonical format and round trip, and all 8 default hotkeys distinct.
- **Live Win32 round trip on this PC:**
  - Register Ctrl+Alt+Shift+F24.
  - A second service trying the same combo gets False.
  - A synthetic press via keybd_event delivers `triggered("test_action")`.
  - After unregistering, the other service can take the combo.
- Still open for T081's acceptance: "each default hotkey works while a game has focus". That's checked in the M02 G1 live session and with the user's games.
