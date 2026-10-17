# M07 — Tray, Settings, first-run wizard, Language Manager (approval gate G3)

Spec: §5.8, §5.9, §5.12. Requires **G1 approved**.

### T071 — Tray icon + menu · Tier B
- Files: `livetranslator/app/tray.py`, `tests/app/test_tray.py`
- Depends on: G1, T014
- Acceptance: every menu item from §5.12 dispatches the right action (pytest-qt). Checkmarks reflect the store. The icon colour reflects status. Double-click toggles show/hide. Tier B: menu screenshot.

### T072 — Settings dialog · Tier B · (G3)
- Files: `livetranslator/ui/settings/*.py`, `tests/ui/test_settings.py`
- Depends on: G1, T041, T054
- Acceptance: pages General / Speakers (page shell; contents in T104) / Audio (with level meters) / Windows / Translation / Hotkeys / Performance / Advanced. Every control reads from and writes to the Store only. A change persists after restart.

### T073 — First-run wizard · Tier B · (G3)
- Files: `livetranslator/ui/wizard/*.py`, `tests/ui/test_wizard.py`
- Depends on: T072, T054
- Acceptance: the 6 steps of §5.9. Total download size shown before downloading. Cancel mid-download → resumable. On finish, the default window opens and `wizard_completed` is set. Tier B: fresh profile (temp `%APPDATA%` override) run end to end.

### T074 — Language Manager · Tier B · (G3)
- Files: `livetranslator/ui/language_manager.py`, `tests/ui/test_language_manager.py`
- Depends on: T054
- Acceptance: the list shows installed/available/size/license. One-click install with progress, and remove. Languages used by open windows can't be removed without a warning.
