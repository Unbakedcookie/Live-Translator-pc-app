# TASKS — index only (no narrative; keep < ~10 KB)

## Current state
- **Phase:** 1 **approved 2026-10-17** (spec rev 2; diarization default sherpa-onnx, diart benchmark-only). Speaker plan stands (voice labels + opt-in Discord own-app + ≤ 50 testers); the user may report a bot-based approach → possible post-MVP add-on. → **Phase 2 starts with T010.**
- **Next:** M02 floating window shell (gate G1). M03 benchmarks are unblocked (T016 done).
- **Tests:** 160 passing
- **Last commit:** `chore: Phase 0 docs skeleton, agent roster, verify helper` (see `git log -1`)
- **Open flags:** D-013 (Discord voice API partner-only → opt-in own-app mode), D-021 (LGPL compliance steps), D-024 (gated pyannote models), D-026/D-027 (NVIDIA + FFmpeg binaries), D-029/D-030 (sherpa models, secretless token), D-004/D-005/D-015 (unmeasured).
- **Session start:** read this file + the milestone file in play (M01 next).

## Task map
| Milestone | Task IDs | Spec file | History file | Gate | Status |
|---|---|---|---|---|---|
| M00 Setup | T001–T004 | `docs/tasks/M00-setup.md` | `history/M00-setup.md` | — | Done 2026-10-17 |
| M01 Foundation | T010–T016 | `docs/tasks/M01-foundation.md` | `history/M01-foundation.md` | G1 (palettes) | Code done (T010–T016 ✓); G1 palettes pending |
| M02 Floating window | T021–T025 | `docs/tasks/M02-floating-window.md` | `history/M02-floating-window.md` | **G1** | Planned |
| M03 Benchmarks + spikes | T031–T036 | `docs/tasks/M03-benchmarks.md` | `history/M03-benchmarks.md` | **G4** | Planned |
| M04 Audio + ASR | T041–T046 | `docs/tasks/M04-audio-asr.md` | `history/M04-audio-asr.md` | — | Planned |
| M05 Translation | T051–T054 | `docs/tasks/M05-translation.md` | `history/M05-translation.md` | — | Planned |
| M06 Translation view | T061–T064 | `docs/tasks/M06-translation-view.md` | `history/M06-translation-view.md` | **G2** | Planned |
| M07 Settings + first run | T071–T074 | `docs/tasks/M07-settings-firstrun.md` | `history/M07-settings-firstrun.md` | **G3** | Planned |
| M08 Hotkeys + OCR | T081–T083 | `docs/tasks/M08-hotkeys-ocr.md` | `history/M08-hotkeys-ocr.md` | **G5** | Planned |
| M09 Game mode | T091–T093 | `docs/tasks/M09-game-mode.md` | `history/M09-game-mode.md` | — | Planned |
| M10 Speakers | T101–T105 | `docs/tasks/M10-speakers.md` | `history/M10-speakers.md` | **G6** | Planned |
| M11 Hardening | T111–T113 | `docs/tasks/M11-hardening.md` | `history/M11-hardening.md` | MVP sign-off | Planned |
| Post-MVP | backlog | `project-spec.md` §4.2 | — | — | — |

Gates: G1 tokens + widget kit + floating window shell · G2 chat line look · G3 settings/wizard/language manager · G4 engine defaults (ASR, MT, diarization) · G5 OCR selector · G6 speaker labels + Discord setup. UI after G1 waits for G1 approval; non-UI work (M03–M05 logic) continues meanwhile.

## Milestone status
- **M00 Setup** — Private repo created & pushed; Python 3.12.10 venv; docs skeleton; 6-agent roster; `tools/verify/win.ps1` tested (list + window shot). Stack approved.
- **Phase 1** — Approved 2026-10-17: `project-spec.md` rev 2, M01–M11 task files, license register (D-022) fact-checked.
- **M01 Foundation** — T010 done: pre-commit (gitleaks, ruff, bandit, pyright, pip-audit, license gate) all passing; license gate has 24 tests and was probed on 43 real packages; a planted fake token was blocked.
  T011 done: package skeleton, `--version`/`--paths`, platformdirs paths (`LIVETRANSLATOR_HOME` override), loguru with transcript filter + `diagnose=False`; runtime deps PySide6-Essentials/loguru/platformdirs pass the gate (6 packages).
  T012 done: tokens + 5 palettes + one-colour generator, all contrast/ΔE-checked; QSS; Phosphor icons; Inter/Noto Sans bundled; Mica helper; style-literal lint test. Defaults applied while user away (thin outline on light, purpler Neon); preview v2 awaiting G1 confirmation.
  T013–T016 done (user away): frozen pydantic state + pure reducers with change lists; thread-safe Store with narrow signals; versioned/atomic/debounced settings (damaged files set aside); ASR/MT/OCR engine contracts. Code complete; only G1 palette sign-off open.

## Conventions
- **Python:** `.venv/Scripts/python.exe` (3.12.10). Never use the system 3.10.
- **Install deps:** `.venv/Scripts/python.exe -m pip install -r requirements-dev.txt` (includes `requirements.txt`).
- **Fresh/test profile:** set `LIVETRANSLATOR_HOME=<dir>` to keep all settings/data/logs in one folder (tests do this automatically).
- **Hooks:** `.venv/Scripts/pre-commit.exe run --all-files`. Hook entries use `.venv\\Scripts\\python.exe` (pre-commit splits entries POSIX-style on Windows). License gate by hand: `.venv/Scripts/python.exe tools/check_licenses.py`.
- **PowerShell gotcha:** `Set-Content -Encoding utf8` adds a BOM and `Get-Content` misreads UTF-8 without a BOM, so edit files with the Edit/Write tools, not PS pipelines.
- **Tests:** `.venv/Scripts/python.exe -m pytest -q`
- **Lint:** `.venv/Scripts/python.exe -m ruff check .`
- **Run app:** `.venv/Scripts/python.exe -m livetranslator`
- **Verify helper (Tier B):** `powershell -NoProfile -ExecutionPolicy Bypass -File tools/verify/win.ps1 -Action <list|shot|focus|move|click|drag|scroll|keys> ...`
  - Physical pixels. `shot -MaxWidth N` prints `origin` and `scale`: screen = origin + px / scale.
  - `list` reports Topmost (pin), Alpha (opacity, -1 = none), ClickThrough per window.
  - Desktop: two 2560×1440 monitors side by side (virtual 5120×1440).
- **Screenshots:** save to the session scratchpad, never into the repo.
- **Palette preview:** `.venv/Scripts/python.exe -m tools.palette_preview --out <scratchpad>/palette-preview.png` (repo tools that import the app run with `-m tools.<name>`).
- **Git:** stage by name; commit after tier passes; push only on request. pre-commit hooks must pass (from T010 on).
- **Licenses:** a new dependency needs a D-022 register row + fact-check before it goes in `requirements.txt`.
- **Task IDs:** milestone Mnn → tasks Tnn1… (e.g. M06 → T061). Cite IDs in code comments.
