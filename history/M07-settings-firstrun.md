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

## 2026-10-18 — T072 Settings window (user asleep; G3 look review queued)

### Design
- **Logic first:** `app/settings_controller.py` — `SettingsController` turns page intents into store actions (same pattern as WindowController), plus a pure `check_hotkey(hotkeys, action, text)` that normalises a combination and refuses invalid ones or ones another action already uses (message names that action).
- **"Any function can get a shortcut"** (user request from G1 rounds): three new bindable actions with no default — `new_window`, `lock_all`, `open_settings` (`UNBOUND_HOTKEY_ACTIONS`; the reducer now accepts `HOTKEY_ACTION_NAMES`). OCR actions stay hidden until OCR exists (no dead rows).
- **Recorder:** `HotkeyBox` grabs the keyboard while recording and uses the Windows virtual-key code (`nativeVirtualKey`) so Shift+1 is "Shift+1", not "!". The app **unregisters all global hotkeys while recording** (otherwise pressing an existing shortcut would fire it instead of being recorded) and re-registers when recording ends; Esc or focus loss cancels.
- **Re-registration releases everything first** (`unregister_all`): when "Restore defaults" swaps two actions' keys, registering the first would otherwise collide with our own old registration of the second.
- **Shared blocks (gate G3):** `ui/settings/rows.py` — `SettingsPage` (scrolling, big title), `Section` (heading + card with dividers), `SettingRow` (title + explanation | control), `number_box`, `silently`. Styling via `settings_qss` object names + new `SETTINGS` tokens.
- **Uniform dropdowns:** short lists (devices, speaker mode) use `ChoiceCombo` = the shared SearchCombo popup with the search box hidden (`searchable = False`), so every dropdown looks like the language one (G1 "keep the app uniform").
- **Number boxes are whole numbers** (ms, %, s) so the already-approved QSpinBox styling covers them without touching shared QSS.
- **Pages:** General (my language; models/logs folders), Audio (mic/speakers device + on/off + live meters), Speakers (mode, max voices, Me label — Discord/rename come with T103/T104), Windows (lock all, new window, list with Close), Translation (what runs where + installed pairs), Hotkeys, Performance (game mode, refresh interval), Advanced (echo filter, VAD, restore defaults). "Readout", "Best quality" and Discord are left out until they exist.
- **Meters:** `SpeechController.level_db(source)` = RMS dBFS of the last 100 ms in the stream's ring buffer (None when not capturing); `meter_fraction` maps −60…0 dB to the bar. Timer runs only while the Audio page is visible.
- Changes apply immediately and save via the store's debounced persistence (no OK/Apply). Closing only hides the window. Tray "Settings…", a new "Settings…" item in each overlay's right-click menu, and the optional hotkey all open it.
- Mica: the spec makes frosted glass optional/off by default, so the window is solid `bg`.

### Bugs found while building
- **Heredoc trap again** (`"\n"` became a real newline in qss.py). Fixed with Edit; back to Edit/Write only for source.
- **Status key prefix:** runtime changes are announced as `status:<key>`, so the Hotkeys page's "another program uses this" note never refreshed live. Caught by the UI test; fixed.
- **Qt drops a modifier key's own flag on its press event** (pressing Ctrl with Shift held reported only Shift), so the live "Ctrl+Shift+…" feedback was wrong. `held_modifiers` adds/removes the key's own modifier.
- **Stale refusal:** after removing the conflicting shortcut, the old "already used for…" message stayed. Errors now clear whenever the shortcut set changes.
- **Misaligned rows:** rows without a shortcut hid the ✕ button and their box shifted right; the button now keeps its space when hidden.
- First meter check looked dead: the test clip itself was −69 dB RMS (one of T035's deliberately quiet "as recorded" voices). A −23 dB clip filled about half the bar; the maths was right.

### Verification
- **Tier A:** `check_hotkey` (normalise, F-keys alone, own combo, bare key, unknown key, clash message, damaged saved entry), all intents incl. reset paths, `rms_dbfs` (square 0 dB, 0.1× → −20 dB, sine −3.01 dB, silence/empty/−120 dB → floor), `meter_fraction`, `combo_text`.
- **pytest-qt (15 UI + 1 app test):** 8 pages in order; close hides/reopens; every page writes the store and re-reads it on change; device list keeps an unplugged saved device and strips "[Loopback]"; speech-off and broken-PortAudio notices; recorder (live modifier text, capture, Esc); Hotkeys page set/refuse/clear/stale-error/"taken" warning/restore; app: Settings opens on a page, reopens via the hotkey path, tray has "Settings…", **a change persists after restart**.
- **Tier B (real app, scratch profile, real models, mic muted; screenshots before interactions):** all 8 pages screenshotted; speakers dropdown opens in the shared popup style; Others meter moved with a −23 dB clip (level −20…−29 dB logged); recorded Ctrl+Shift+L for "Lock all windows" → saved, no conflict → pressing it globally locked the window (`locked: true` in settings.json); assigning it again to "Open a new window" was refused with the message and did **not** toggle the lock (hotkeys paused while recording); ✕ removed it.
- Nav clicks in the page tour reused coordinates from one fresh screenshot of the unmoved window; each page was screenshotted after its click.

### Code review (code-reviewer subagent) and fixes
No high-severity defects; findings fixed before commit:
- **Settings window could block Windows shutdown/logoff** (closeEvent always ignored → "Live Translator is preventing shutdown"). Now accepts while the session is ending (`ui/session.py: session_ending()`; Qt 6 `isSavingSession` is an instance method — first attempt called it on the class and pyright caught it). Same for the Transcript window.
- **Hidden OCR defaults blocked combinations:** Ctrl+Alt+O/R were refused as "already used for Translate a screen region", a feature with no row and no way to clear it. `check_hotkey` now only treats actions this build performs as clashes (`active_hotkeys`).
- **Recording could stay on** after clicking empty page space or a label (the nav was NoFocus): page bodies take click focus, the box stops on hide (page switch / close), the nav is keyboard-focusable now.
- **Translation page** now re-reads engines every second while visible, and shows "Not available" when speech failed to load instead of "Starting…" forever. Installed pairs are read once (a damaged model folder shows none instead of raising inside a store signal).
- Hidden Settings no longer refreshes all 8 pages on every config change (showEvent re-reads).
- "Most voices" minimum 1 (the model allows 1); a blank "Me" name snaps back to the saved one; a damaged saved shortcut says "isn't valid" instead of blaming another program; recorder says when a key can't be used; the module-level assert became a RuntimeError.
- Open (needs hardware): whether a USB device plugged in while capture runs shows up in the Audio dropdown (PortAudio may not re-enumerate while an instance is open). Check with the user's headset.
