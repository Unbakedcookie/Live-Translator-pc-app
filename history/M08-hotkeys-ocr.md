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

## 2026-10-18 — T082 region selector + T083 OCR building blocks (in progress)
- **Region selector** (`ui/region_selector.py`): a dimmed pane per monitor, drag a box with a live "W × H" label; Esc, right-click or a mere click cancels. The result comes from Windows' own cursor position (`GetCursorPos`, physical pixels) at press and release, so it's right on mixed-DPI setups and matches what mss captures; Qt's logical coordinates are only used for drawing. Tests: corner order, physical result, click/Esc cancel, one pane per screen.
- **Grab** (`services/ocr/grab.py`): mss → RGB array.
- **Windows OCR** (`services/ocr/windows_ocr.py`): pywinrt `Windows.Media.Ocr`; upscales captures under 48 px tall (missed small glyphs otherwise); removes the spaces Windows puts between Japanese/Chinese characters but keeps Korean spacing (a first version stripped Hangul spaces too — caught in review of my own regex). **This PC has only the en-US OCR pack** (D-009 resolved); it reads English and Spanish fixtures exactly.
- **Language detection** (`services/langdetect.py`): spec named lingua-py, but its wheel is a single 304 MB binary. Replaced by writing-system rules + function words (D-033, user to confirm). 8/8 fixed sentences. Bug caught by a test: `casefold()` turns "ß" into "ss", so German's ß never counted — uses `lower()` now.
- **RapidOCR** fallback: licence closure fact-checked (D-034): shippable if the build strips opencv's LGPL FFmpeg DLL (verified cv2 works without it). opencv 4.12 forced numpy down to 2.2.6 (pip did it silently); switched to 4.14.0.94 and restored numpy 2.5.4. Prototype on rendered lines: ja and es read perfectly (~1.1–1.7 s on CPU); the default model failed on Korean and Russian (needs their language models — later).
- Not yet wired into the app (controller, hotkeys, OCR window): next.

## 2026-10-18 — T083 screen translation wired in
- **RapidOCR engine** (`services/ocr/rapid_ocr.py`): bundled PP-OCRv6 small (31 MB) reads zh (both scripts), ja and Latin text with no language setting; Korean/Russian not claimed (measured garbage). Lines sorted top to bottom, polygon → bounding box, confidence kept.
- **OcrController** (`app/ocr_controller.py`): capture(region) on a background thread → grab → first reader that finds text (RapidOCR, then Windows OCR) → one finished `SCREEN` line per OCR row with its detected language → the translation controller translates them like speech. Re-capture skips rows already shown (chat scrolled by one → only the new row is added); a second press while busy is ignored; grab failures and "no text" become plain status messages. The first capture opens a "Screen" window **beside the region** (`ui/geometry.beside`: right, else left, below, above, inside the work area) when no window shows Screen lines.
- **Entry points:** hotkeys `ocr_region` (Ctrl+Alt+O) → region selector → capture; `ocr_recapture` (Ctrl+Alt+R) → last region; tray "Translate screen region…"; overlay right-click "Translate a screen region…". The Hotkeys page now lists both actions (they exist now).
- **Bug found by a semi-live test** (a small on-screen window with two chat rows, captured through the real grabber + RapidOCR, no mouse automation because the user was at the PC): "[队伍] Mika: wait for me at the gate" was detected as Chinese because of its two-character team tag. Language detection now lets a writing system win only if it has at least as many characters as Latin letters. Both rows now come out right (zh / en). First capture 3.9 s cold (model load), ~1.2 s after.
- Tests: controller (rows + languages, re-capture only new rows, reader fallback, grab failure, first-capture window, re-capture without a region), RapidOCR on rendered zh/ja/es lines (exact), no Korean claim, beside() placement, mixed-script detection. A test bug on the way: my Japanese comparison used NFKD, which splits で into て + a voicing mark — RapidOCR was right.
- **Waiting on the user (G5):** the region selector look, and a real in-game chat capture.

## 2026-10-19 — "Is Swedish in this? I screenshotted it with screen translate and it didn't work"
- Cause: the screen-text detector (D-033) knew only 7 Latin-script languages (en, es, fr, de, it, pt, nl). Swedish scored nothing, fell back to the hint (the user's language, English), and English -> English is passed through, so the line stayed Swedish. Both OCR engines read the Swedish exactly (checked on a rendered chat line).
- Fix: function words + own letters for 13 more Latin-script languages (sv, da, no, fi, pl, tr, id, ms, vi, cs, hu, ro, tl); test with one game-chat sentence in each of 19 languages, all right.
- Live check (Tier B, real app, fresh screenshots): a Swedish chat panel, Ctrl+Alt+O, drag. First run translated (SV→EN) but RapidOCR returned "[Lag]" and the message as separate boxes, so the tag became its own untranslated line. Added `ocr.base.merge_rows` (boxes overlapping ≥ 50 % vertically are one row, left to right, CJK joined without a space). Second run showed "[Team] g] Sara": the raw boxes were "[Lag]" (x 29-85) and an overlapping "g] Erik: …" (x 67-477) re-reading "g]"; merging now drops text repeated where boxes overlap. Third run: "[Team] Erik: Can you help me with the mission?" / "[Team] Sara: See you at the bridge in five minutes, don't forget the keys!".
- Seen, not fixed: the second line's translation appeared a few seconds after the first (Qwen); to measure.
