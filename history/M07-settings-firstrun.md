# M07 — Tray, Settings, first-run wizard, Language Manager (gate G3) — narrative

## 2026-10-17 — T071 tray icon + menu (user asleep; autonomous)

### Design
- `app/tray.py`: `Tray(QObject)` owns a `QSystemTrayIcon` + a `QMenu` themed with `window_qss` (same QSS as the overlay menus).
- Every item calls the **WindowController** (`handle_hotkey(...)` / `add_window()`), the same code paths as the global hotkeys, so tray and hotkeys can never disagree.
- Checkmarks (Mute Me, Mute Others, Game mode, Click-through) are re-read from the store on every `config_changed` / `runtime_changed` / `window_changed`; `blockSignals` while setting them so a refresh never re-triggers an action.
- Icon colour via `tray_status(state)` (pure): any ERROR status → `danger` (its message becomes the tooltip); both streams muted → `text_secondary` ("paused"); otherwise `accent` ("listening", "+ windows hidden" when hidden).
- Items for features that don't exist yet (OCR region, Transcript…, Language Manager…, Discord) are **left out** rather than shown dead; each one's task adds it. "Settings…" appears only when a settings callback is passed (T072 will pass it).
- **Closing the last window no longer quits** (spec §5.11). `WindowManager` got an `on_last_closed` hook; the app passes one that shows a Windows notification "still running … use the tray icon" when a tray exists, and quits when the system has no tray (`QSystemTrayIcon.isSystemTrayAvailable()`).

### Bugs / small catches
- pyright: `add(..., slot: Callable[[], None])` rejected `add_window` (returns the new id). Widened to `Callable[[], object]`.
- Passing `controller.add_window` straight to `triggered.connect` would have handed Qt's `checked=False` in as `target_lang` (it only worked because `False or my_language` falls through). Wrapped in a lambda.

### Verification
- **Tier A / pytest-qt (9 new tests):** `tray_status` roles + tooltips (warning ≠ error; error wins; hidden mentioned); every item changes the store / calls quit / settings; menu order; checkmarks follow store changes made elsewhere; icon role follows SetStatus/ClearStatus; double-click toggles, single click doesn't; no Settings item without a callback; WindowManager last-close hook; app-level: removing the last window → no quit, one notification, "New window" from the tray brings a window back, tray hidden on shutdown.
- **Tier B (real app, scratch profile, desktop screenshots before every click):**
  - Windows 11 put the new icon in the hidden-icons overflow (expected for a new app; the user can drag it onto the taskbar). Accent-coloured "translate" icon visible there.
  - Right-click → themed dark menu, items in spec order.
  - Mute Me → tick shown on reopen, `settings.json` `mic_enabled: false`; Mute Others → icon turned grey (paused).
  - Double-click → the scratch window disappeared from the window list; again → back.
  - Window ✕ on the last window → window gone, process still alive, Windows toast "Live Translator is still running…".
  - Quit → process exited.
- **Noted for packaging (M11):** the toast header says "Python" because the dev run has no AppUserModelID; the packaged exe needs `SetCurrentProcessExplicitAppUserModelID` + a Start-menu shortcut so Windows shows "Live Translator".
- Hover tooltip didn't appear for a synthetic cursor move (Windows only shows tray tooltips on real hover messages); the tooltip text itself is covered by the unit test.
