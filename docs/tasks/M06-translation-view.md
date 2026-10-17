# M06 — Translation view, transcript, export (approval gate G2)

Goal: the chat log visible in the floating windows. Spec: §5.2, §5.11. Requires **G1 approved**.

### T061 — ChatLine component · Tier B · SHARED (G2)
- Files: `livetranslator/ui/widgets/chat_line.py`, `tests/ui/test_chat_line.py`
- Depends on: G1
- Acceptance: speaker label in the speaker colour; partial (tentative text in secondary colour) vs final; display modes "translation only" and "original + translation"; outline/shadow rendering; wraps correctly at narrow widths. Screenshots in all 5 palettes reviewed by the user.

### T062 — TranslationView inside FloatingWindow · Tier B
- Files: `livetranslator/ui/translation_view.py`, `tests/ui/test_translation_view.py`
- Depends on: T061, T053
- Acceptance: shows only sources/target selected for that window. Auto-scroll sticks to the bottom unless the user scrolled up ("↓ new" pill to jump back). Updating a partial doesn't flicker. Max 200 lines rendered (older ones stay in the transcript). Live test: YouTube/Discord audio → lines appear.

### T063 — Transcript window + export · Tier A (format) + Tier B (UI)
- Files: `livetranslator/ui/transcript_window.py`, `livetranslator/core/export.py`, `tests/core/test_export.py`
- Depends on: T062
- Acceptance: `.txt` and `.json` output for a fixed 3-utterance session equals a hand-written expected file. The window lists everything, has search + copy, and exports via a save dialog.

### T064 — Close/quit flow · Tier B
- Files: `livetranslator/ui/dialogs.py`, `livetranslator/app/lifecycle.py`, `tests/app/test_lifecycle.py`
- Depends on: T063
- Acceptance: empty log → quits immediately. Non-empty → Export / Close without saving / Cancel behave as specified. Closing the last overlay window keeps the tray. After quit, no transcript file exists anywhere unless exported (search `%APPDATA%`/`%LOCALAPPDATA%` dirs).
