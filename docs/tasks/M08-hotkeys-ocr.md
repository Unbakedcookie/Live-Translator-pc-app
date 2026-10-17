# M08 — Global hotkeys + screen OCR (approval gate G5)

Spec: §5.6, §5.7. Requires **G1 approved**.

### T081 — Global hotkey service · Tier A (parse) + Tier B (live)
- Files: `livetranslator/services/hotkeys.py`, `tests/services/test_hotkeys.py`
- Depends on: T021, T014
- Acceptance: `"Ctrl+Alt+H"` ⇄ (modifiers, vk) parse/format round-trips (hand-computed vk codes). A registration conflict → reported, not a crash. Live: each default hotkey works while another app (a game or Notepad) has focus.

### T082 — Region selector overlay · Tier B · (G5)
- Files: `livetranslator/ui/region_selector.py`, `tests/ui/test_region_selector.py`
- Depends on: G1, T023
- Acceptance: covers both monitors; drag shows a rectangle + size label; Esc cancels; the returned rect is in physical pixels (cross-check against `win.ps1 shot` coordinates).

### T083 — OCR engines + flow · Tier A (fixtures) + Tier B (live)
- Files: `livetranslator/services/ocr/{grab,windows_ocr,rapid_ocr}.py`, `livetranslator/services/langdetect.py` (lingua), `livetranslator/app/ocr_controller.py`, `tests/services/ocr/test_ocr.py`, `tests/services/test_langdetect.py`
- Depends on: T016, T082, T053
- Acceptance: on 3 rendered fixture images (en, ja, es text drawn by the test) the expected text is found (normalized match). lingua (restricted to installed packs) detects the right language on 6 fixed sentences, and short/ambiguous text falls back to the hint. Windows OCR language missing → RapidOCR used. A SCREEN utterance is translated and shown. Re-capture hotkey reuses the last rect. Live: in-game chat region translated.
