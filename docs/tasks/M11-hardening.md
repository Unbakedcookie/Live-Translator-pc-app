# M11 — MVP hardening + sign-off

Spec: §9, §10, §11.

### T111 — Error paths · Tier A + Tier B
- Files: `livetranslator/app/errors.py`, tests per service
- Depends on: M04–M10
- Acceptance:
  - Each failure produces the specified plain-language status and recovery:
    - §9 failures: no CUDA, missing model, corrupt model, device unplugged, OCR language missing, worker crash.
    - Discord not running / token revoked.
  - Logs contain no transcript text or speaker names (test greps logs after a scripted session).

### T112 — End-to-end live sessions · Tier B
- Files: `history/M11-hardening.md` (evidence)
- Depends on: T111
- Acceptance:
  - A 15-minute Discord call (or YouTube in a foreign language) + a borderless game with pinned windows.
  - Latency and speaker accuracy recorded against §8.
  - No crash; memory stable (RSS sampled every minute).

### T113 — User guide, licenses page, release license checklist · Tier A
- Files: `README.md` (user guide), `livetranslator/ui/about.py`, `THIRD_PARTY_LICENSES.md` (generated), `tools/release_license_check.py`, `tests/tools/test_release_license_check.py`
- Depends on: T111
- Acceptance:
  - **Guide** covers: install, first run, hotkeys, click-through recovery, Discord own-app setup, privacy.
  - **About page** lists every shipped dependency/model/font license, with the Qt/PySide6 LGPL notice + source offer.
  - **Release check** fails on:
    - GPL-only Qt DLLs in a build folder (fixture folders).
    - Missing OFL/LGPL/Apache NOTICE texts.
    - Unused QtAwesome fonts left in the bundle.
  - Every DATA_TRACKER item touching release is reviewed with the user (D-021, D-026, D-027 in particular).
