# M01 — Foundation

Goal: project scaffold + the shared non-visual contracts everything else builds on. Spec: `project-spec.md` §6.
Gate: palette preview screenshot is part 1 of **G1** (shown together with M02).

### T010 — Dev tooling + license gate · Tier A · (first task)
- Files: `.pre-commit-config.yaml`, `requirements-dev.txt`, `pyproject.toml` (ruff, bandit, pyright sections), `tools/check_licenses.py`, `tools/license_policy.toml`, `tools/license_overrides.toml`, `tests/tools/test_check_licenses.py`
- Depends on: —
- Acceptance:
  - `pre-commit install` done.
  - Hooks per spec §10.1: gitleaks, ruff (lint + format), bandit, pyright, pip-audit, license gate. Python hooks are `local`/`system` using `.venv/Scripts/python.exe`.
  - gitleaks: use the official hook. If pre-commit can't bootstrap Go on Windows, use the pinned official gitleaks Windows binary as a `system` hook, and record which was used in history.
  - `pre-commit run --all-files` passes on the repo.
  - A planted fake token in a scratch file is caught by gitleaks (then removed, never committed).
  - License gate unit tests use hand-made metadata fixtures:
    - MIT → pass.
    - GPL-3.0 → fail.
    - LGPL-3.0 on `PySide6-Essentials` → pass; on any other package → fail.
    - UNKNOWN → fail unless the override cites a D-id.
    - The runtime-closure walker excludes dev-only packages.

### T011 — Project scaffold · Tier A
- Files: `pyproject.toml` (pytest config), `requirements.txt`, `livetranslator/__init__.py`, `livetranslator/__main__.py`, `livetranslator/app/paths.py` (platformdirs), `livetranslator/app/logging.py` (loguru, transcript filter), `tests/conftest.py`, `tests/test_smoke.py`, `tests/app/test_logging.py`
- Depends on: T010
- Acceptance:
  - `pip install -r requirements-dev.txt` succeeds in `.venv`. `requirements.txt` uses `PySide6-Essentials` (never the full `PySide6`).
  - `python -m livetranslator --version` prints the version.
  - All pre-commit hooks pass, including the license gate.
  - Paths come from platformdirs (a test with a patched base dir checks the expected subpaths).
  - The loguru filter drops records bound with `transcript=True` (hand-written cases).
  - Each new dependency is in the DATA_TRACKER license register (D-022).

### T012 — Design tokens, palettes, fonts, icons · Tier A · SHARED (G1)
- Files: `livetranslator/theme/{tokens,palette_gen,contrast,qss,icons,fonts,backdrop}.py`, `livetranslator/theme/fonts/` (Inter + Noto Sans + OFL texts), `tests/theme/test_tokens.py`, `test_palette_gen.py`, `test_contrast.py`, `test_qss.py`, `tests/test_no_hardcoded_style.py`
- Depends on: T011
- Acceptance:
  - **Palettes**: 5 built-in palettes (Midnight, Subtitle, Paper, Neon, High Contrast), each with every `color.*` token and an 8-colour speaker ramp (a test asserts the key sets are equal).
  - **Contrast** (ColorAide): every text/bg pair ≥ 4.5:1, and adjacent speaker colours ΔE2000 ≥ 20. 2 cases are hand-computed against the WCAG formula.
  - **Generated palettes** (materialyoucolor): seed `#3B82F6`, dark → passes all contrast checks. A deliberately bad seed is auto-adjusted until it passes.
  - **QSS**: the output for a fixed palette matches a hand-written expected string.
  - **Icons**: the `icons.py` wrapper only exposes the Phosphor (`ph.`) prefix. Icon colours come from tokens.
  - **Fonts**: `fonts.py` registers the bundled Inter/Noto Sans, and builds the overlay font stack per script (unit test on the stack logic).
  - **Backdrop**: `backdrop.py` applies win32mica only on Windows 11 builds that support it (version check is unit-tested). Otherwise it's a no-op.
  - **Lint test**: fails on colour/size literals outside `theme/`.

### T013 — State models + actions + reducers · Tier A · SHARED
- Files: `livetranslator/core/state.py`, `core/actions.py`, `core/reducers.py`, `tests/core/test_reducers.py`
- Depends on: T011
- Acceptance: frozen pydantic models for `AppState{config, session, runtime}`, `WindowConfig`, `WindowStyle`, `Geometry`, `Utterance`. Reducers are pure. Tests cover: add/remove/update window, set style field, add/update utterance (partial → final), clear session, runtime status set. Each test has a hand-written expected state.

### T014 — Store (thread-safe dispatch, granular signals) · Tier A · SHARED
- Files: `livetranslator/core/store.py`, `tests/core/test_store.py`
- Depends on: T013
- Acceptance: `dispatch` from a worker thread is applied on the main thread (pytest-qt `waitSignal`). Signals fire with the right key and only for the slices that changed (e.g. a style change emits `window_changed(id)` and no `utterance_*`).

### T015 — Persistence (versioned JSON, atomic, debounced, migrations) · Tier A
- Files: `livetranslator/core/persistence.py`, `core/migrations.py`, `tests/core/test_persistence.py`
- Depends on: T014
- Acceptance: round-trip config ⇄ JSON equals the original. `session` is never written (test greps the file). A corrupt file → renamed `settings.corrupt-<ts>.json` + defaults loaded. A v0 fixture migrates to v1 with the expected values. Writes go to a temp file + `os.replace`. 5 rapid changes → 1 write (debounce, pytest-qt).

### T016 — Engine interfaces · Tier A · SHARED (contract)
- Files: `livetranslator/services/asr/base.py`, `services/mt/base.py`, `services/ocr/base.py`, `tests/services/test_interfaces.py`
- Depends on: T011
- Acceptance: Protocols/ABCs per spec §5.4/5.5/5.6, with `Segment`/`Word` dataclasses. Fake engines in tests satisfy them. No engine libraries are imported here.
