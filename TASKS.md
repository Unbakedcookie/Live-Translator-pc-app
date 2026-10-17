# TASKS — index only (no narrative; keep < ~10 KB)

## Current state
- **Phase:** 0 complete → **next: Phase 1** (write `project-spec.md` + milestone task files). Wait for approval before app code.
- **Tests:** 0 (no app code yet)
- **Last commit:** `chore: Phase 0 docs skeleton, agent roster, verify helper` (see `git log -1`)
- **Open flags:** DATA_TRACKER D-004/D-005 (latency & VRAM unmeasured), D-006 (fullscreen overlay), D-013 (Discord speaker names) — all Unresolved.
- **Session start:** read this file + `docs/tasks/M00-setup.md` ("Approved decisions") for Phase 1.

## Task map
| Milestone | Task IDs | Spec file | History file | Status |
|---|---|---|---|---|
| M00 Setup | T001–T004 | `docs/tasks/M00-setup.md` | `history/M00-setup.md` | Done 2026-10-17 |
| M01+ | defined in Phase 1 | — | — | — |

## Milestone status
- **M00 Setup** — Private repo created & pushed; Python 3.12.10 venv; docs skeleton; 6-agent roster; `tools/verify/win.ps1` tested (list + window shot). Stack approved.

## Conventions
- **Python:** `.venv/Scripts/python.exe` (3.12.10). Never use the system 3.10.
- **Install deps:** `.venv/Scripts/python.exe -m pip install -r requirements.txt` (created in Phase 2).
- **Tests:** `.venv/Scripts/python.exe -m pytest -q`
- **Lint:** `.venv/Scripts/python.exe -m ruff check .`
- **Run app:** defined in Phase 1 spec (planned: `.venv/Scripts/python.exe -m livetranslator`).
- **Verify helper (Tier B):** `powershell -NoProfile -ExecutionPolicy Bypass -File tools/verify/win.ps1 -Action <list|shot|focus|move|click|drag|scroll|keys> ...`
  - Physical pixels. `shot -MaxWidth N` prints `origin` and `scale`: screen = origin + px / scale.
  - `list` reports Topmost (pin), Alpha (opacity, -1 = none), ClickThrough per window.
  - Desktop: two 2560×1440 monitors side by side (virtual 5120×1440).
- **Screenshots:** save to the session scratchpad, never into the repo.
- **Git:** stage by name; commit after tier passes; push only on request.
