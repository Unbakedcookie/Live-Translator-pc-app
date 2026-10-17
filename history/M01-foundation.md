# M01 — Foundation · history

## 2026-10-17 — T010 Dev tooling + license gate

### Context
- Phase 1 was approved. The user accepted the 5-step Discord own-app setup; they can't ask the other developer how their program worked.
- T010 is the first task. It puts the commit-time guards in place before any app code exists.

### What was built
- **`requirements-dev.txt`**: pinned dev tools (bandit 1.9.4, packaging 26.3, pip-audit 2.10.1, pip-licenses 5.5.5, pre-commit 4.7.0, pyright 1.1.414, pytest 9.1.1, ruff 0.17.1).
- **`pyproject.toml`**: tool config only, with project metadata coming in T011.
  - ruff: py312, line length 100, rule sets E/F/W/I/B/UP/SIM/RUF.
  - bandit: asserts allowed in test files.
  - pyright: basic mode, strict for `tools/`.
  - pytest: importlib import mode, `pythonpath=["."]`.
- **`.pre-commit-config.yaml`**:
  - gitleaks v8.30.1 (official hook).
  - Local system hooks for ruff lint, ruff format check, bandit, pyright, pip-audit and the license gate.
- **`tools/check_licenses.py`**, the license gate:
  - It walks `requirements.txt`, then the installed distributions, then their Requires-Dist (honouring markers and requested extras). The result is the runtime closure; dev tools are excluded by construction.
  - It asks pip-licenses (`--from=all --with-system`) for three fields per package.
  - It picks the most reliable field, in this order: override, then License-Expression, then classifiers, then a short License field. A full license text counts as UNKNOWN.
  - It evaluates SPDX expressions with a small parser (WITH, then AND, then OR).
  - Classifier lists are ANDed (safe direction).
  - LGPL is allowed only for pyside6-essentials and shiboken6.
  - An override must cite a `D-xxx` id. An override can't launder GPL, because the override license is still evaluated.
- **`tools/license_policy.toml`**: allow-list + classifier aliases. **`tools/license_overrides.toml`**: empty template.

### Design forks
- **Getting the license data.** Option A: pip-licenses (the user asked for it). Option B: read importlib.metadata directly.
  - I chose pip-licenses for the data and my own code for the decisions. Its built-in `--fail-on`/`--allow-only` do plain string matching, which can't handle `LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only` for PySide6 only.
  - Before writing the parser, I probed pip-licenses' real JSON output (`License-Expression` / `License-Classifier` / `License-Metadata`).
- **pip-audit scope.** I chose to audit the installed venv instead of `-r requirements.txt`. The `-r` mode resolves into a temp venv on every run (slow, and it would re-download PySide6). The venv mode also covers the dev tools. Spec section 10.1 was updated to match.
- **Unknown free-text license names** (e.g. "Some Custom License") are treated as one unknown license with a clear reason, instead of a confusing "cannot parse" from splitting on spaces.

### Problems hit, and how they were found
1. **ruff/pyright/bandit findings on the first run.**
   - Formatting in 2 files: auto-fixed with `ruff format`.
   - pyright: `__doc__` may be None. Replaced with a literal description.
   - bandit B105 false positive: a variable named `token` compared to `"("` looked like a hard-coded password. Renamed to `tok`.
   - bandit also parsed the free text after `# nosec B404 -` as test ids and printed warnings. Moved the justification to its own comment line.
2. **BOM.** A PowerShell `Set-Content -Encoding utf8` rewrite put a UTF-8 BOM in `check_licenses.py`. Found by checking the file's first bytes; stripped with Python.
3. **Hooks couldn't start: "[WinError 2] The system cannot find the file specified".**
   - Cause: the entries used `.venv/Scripts/python.exe`. pre-commit accepted the path, but Windows couldn't launch it from the forward-slash relative path.
   - The first fix, single backslashes, failed with "Executable `.venvScriptspython.exe` not found". pre-commit splits `entry` POSIX-style, so the backslashes were eaten as escapes.
   - Final fix: doubled backslashes in a plain YAML scalar. A comment in the config explains why.
4. **Mojibake.** The single-backslash edit went through a PowerShell `Get-Content` pipeline, which read the BOM-less UTF-8 file as ANSI and corrupted the em dash and section sign in the header comment. Found in the on-disk diff and fixed by rewriting the file with the Write tool. Lesson, now in the TASKS.md conventions: never edit files through PowerShell pipelines.
5. **gitleaks without Go.** Go is not installed. pre-commit 4.7 bootstrapped a Go toolchain by itself, so no fallback binary was needed.
6. **pyright needs Node.** The pip `pyright` package downloaded a prebuilt Node (26.12.0) on its first run. It's cached, and nothing is needed from the user.

### Verification (Tier A)
- `pytest`: **24 passed**. Hand-written expectations cover:
  - Licenses: MIT pass; GPL fail; LGPL on pyside6-essentials pass and elsewhere fail; the real PySide6 expression; OR/AND/parentheses; WITH; CC-BY-NC fail; expression preferred over classifier; classifiers ANDed; metadata alias vs full text; free-text name; unparseable input; UNKNOWN fails until an override with a D-id; an override can't launder GPL.
  - Overrides file validation.
  - Requirements parsing.
  - Closure: extras, markers, dev tools excluded, missing packages reported, name normalisation, false root marker.
- `pre-commit run --all-files`: all 7 hooks passed. With no `requirements.txt` yet, the license gate reports "nothing to check".
- **Real-data probe:** the gate ran against a scratch requirements file (pip-audit, pre-commit, bandit[toml], pytest). It produced a 43-package closure, including the Windows-only colorama, and classified all of them correctly with 0 violations.
- **gitleaks probe:** I staged a file with a randomly generated fake `ghp_` token. The gitleaks hook failed with "leaks found: 1, RuleID github-pat". The file was unstaged and deleted, and never committed.
- Skipped: the `test-runner` delegation. The suite runs in 0.14 s and I ran it directly, so delegating would have been a tiny task (CLAUDE.md: don't delegate tiny tasks). I also updated TASKS.md directly instead of via `archivist`, for the same reason.

## 2026-10-17 - T011 Project scaffold

### What was built
- `requirements.txt` with the first runtime dependencies: PySide6-Essentials 6.12.0 (never the full PySide6, D-021), loguru 0.7.3, platformdirs 4.13.3. `requirements-dev.txt` now starts with `-r requirements.txt`, so one install covers everything.
- `livetranslator/__init__.py`: APP_NAME, display name and `__version__` 0.1.0 (single source).
- `livetranslator/app/paths.py`: AppPaths.
  - config = %APPDATA%\LiveTranslator (holds settings.json).
  - data = %LOCALAPPDATA%\LiveTranslator, with models in `data\models` by default.
  - logs = %LOCALAPPDATA%\LiveTranslator\Logs.
  - `LIVETRANSLATOR_HOME` override puts config/, data/ and logs/ under one folder.
- `livetranslator/app/log.py`:
  - loguru, rotating at 5 MB, kept for 7 days, UTF-8, enqueue.
  - Filter drops records bound with transcript=True.
  - `diagnose=False` and `backtrace=False`.
- `livetranslator/__main__.py`: `--version`, `--paths`. A plain start creates the folders, starts logging, records the startup, and prints help until the UI is wired in (M02/M07).
- Tests:
  - conftest autouse fixture: every test gets its own LIVETRANSLATOR_HOME, and logger handlers are removed afterwards so Windows can delete the tmp dirs.
  - test_smoke: a real `python -m livetranslator --version` subprocess, `--paths` output, and a plain start.
  - test_paths: explicit home, env home, real Windows platformdirs defaults, and `ensure()` creating only the app folders.
  - test_logging: filter cases, transcript records never reaching the file, tracebacks not showing local values, log file location.

### Design forks
- **platformdirs arguments.** `appauthor=False` avoids the `LiveTranslator\LiveTranslator` double folder that is platformdirs' default on Windows. `roaming=True` only for config, so settings sit in %APPDATA% per spec 5.8.
- **Why an env override instead of patching env vars in tests.** platformdirs on Windows asks the shell (SHGetKnownFolderPath via ctypes), not APPDATA/LOCALAPPDATA, so patching those variables would not isolate tests. The override also gives T073 its fresh-profile run.
- **`diagnose=False` is a privacy decision**, not just style. loguru's diagnose mode prints local variable values in tracebacks, which would leak an utterance held in a variable. A test proves the secret string does not appear.
- **Renamed `app/logging.py` to `app/log.py`** so it does not shadow the stdlib name. Task file updated.
- **No `[project]` table in pyproject.** The app runs from the repo and packaging is post-MVP, so the version lives in one place.

### Problems hit
- One ruff-format failure (a call that fit on one line). Fixed with `ruff format`.
- pre-commit printed "Failed to write cache file ... Access is denied" from ruff. Cause: pre-commit runs ruff on file batches in parallel, and the processes collide on the cache file on Windows. Harmless; the checks themselves passed.

### Verification (Tier A)
- pytest: 35 passed (24 license gate + 11 new).
- `python -m livetranslator --version` printed "Live Translator 0.1.0".
- `--paths` on the real profile printed the expected Roaming/Local folders.
- After the full test run, `%APPDATA%\LiveTranslator` and `%LOCALAPPDATA%\LiveTranslator` did NOT exist, so tests never touched the real profile.
- License gate on the real runtime closure: 6 packages, 0 violations. LGPL accepted only for pyside6-essentials/shiboken6. New transitive dependencies colorama (BSD) and win32-setctime (MIT) were added to the D-022 register.
- pre-commit run --all-files: all 7 hooks passed.

## 2026-10-17 - T012 Design tokens, palettes, fonts, icons

### What was built
- `theme/tokens.py`:
  - `Palette` dataclass with 13 named colours + an 8-colour speaker ramp.
  - 5 built-in palettes: Midnight (default), Subtitle, Paper, Neon, High Contrast.
  - Frozen token groups FONTS, SPACE, RADIUS, MOTION, OVERLAY, WINDOW, with values from spec 5.1/6.5.
- `theme/contrast.py` (ColorAide):
  - WCAG 2.1 ratio rules: text >= 4.5, accent UI >= 3.0.
  - CIEDE2000 >= 20 between neighbouring speaker colours and between Me and Screen.
  - `ensure_contrast` shifts OKLCH lightness away from the background, keeping hue and chroma.
- `theme/palette_gen.py` (materialyoucolor, tonal-spot scheme):
  - Surfaces, text, accent and error colours come from Material roles.
  - Speaker colours are generated in HCT (chroma 48; tone 80 dark / 40 light), ramp hues 22.5 + 45k degrees from the seed, ordered so neighbours are >= 135 degrees apart.
  - Every text colour goes through `ensure_contrast`.
- `theme/qss.py`: QSS for QWidget, tooltips, menus, buttons, inputs/combos, sliders and scrollbars, built only from tokens.
- `theme/icons.py`: QtAwesome Phosphor-only wrapper. Bare names only (dotted names rejected); colours come from palette roles.
- `theme/fonts.py`:
  - Registers the bundled TTFs.
  - Script mapping from language to Noto family (JP/KR/SC/TC/Arabic/Devanagari/Thai/Hebrew/Bengali).
  - `overlay_families` builds the stack: user choice, then Inter, then script Noto, then Noto Sans; filtered to installed fonts, case-insensitive, deduplicated.
- `theme/backdrop.py`: win32mica only when the build is >= 22000. Returns True only when ApplyMica returns 0.
- Bundled fonts:
  - Inter 4.1 Regular/Medium/SemiBold/Bold (static extras/ttf).
  - Noto Sans 2.015 Regular/Bold (hinted).
  - Both OFL texts.
- `tools/palette_preview.py`: G1 part 1 review sheet. Mock overlay panels at 70 % bg opacity over a striped, colourful "game" backdrop.

### License gate in action (first real catches)
- **materialyoucolor**: UNKNOWN, because its metadata is blank. I read the wheel's `dist-info/licenses/LICENSE` (the MIT text) and added an override citing D-022. Register status moved to Confirmed (GitHub API + file).
- **pillow 13.0.0**: MIT-CMU, which was not on the allow-list. Pulled in only by materialyoucolor (for an image quantizer we never call). I read the LICENSE (permissive, notice-preserving) and added MIT-CMU to the allow-list. A candidate to exclude from the bundle later.
- Fonts: downloaded the official release zips into a fresh scratch folder, recorded SHA-256, and copied out only the TTFs + license texts. Both are OFL-1.1, read from the release files.

### Design forks
- **Palette representation.** A frozen dataclass rather than a dict, so "every palette defines every token" is guaranteed by construction. `color_tokens()` flattens it for tests/QSS.
- **Speaker colours in generated palettes.** Material's `tertiary` came out near-white (#EFDFFF) for a blue seed, too close to the text colour, so I generate speakers from HCT instead of Material roles.
- **materialyoucolor 3.0.4 defaults to spec 2025**, which gives muted primaries (#B6C6EE for the #3B82F6 seed). I kept it, because the accent still passes 3:1 and looks calm on an overlay. Revisit if the user wants punchier custom palettes.
- **Contrast checks use the opaque background colour.** At 70 % background opacity over a game, legibility comes from the text outline. This is documented in contrast.py, and the preview checks it visually.
- **Font weights on Windows.** Qt registers "Inter Medium" / "Inter SemiBold" as extra family aliases, but `QFont("Inter")` with weight 500/600 resolves to the right file (checked with QFontInfo), so no special handling is needed.
- **CJK before packs are installed.** Yu Gothic, Malgun Gothic and Microsoft YaHei are present on this PC, and Qt's per-glyph fallback uses them, so Japanese/Korean/Chinese render even without our Noto packs.
- **Icon colour test.** A test renders `square-fill` and reads the centre pixel, which must equal the palette role colour. That proves colours really come from tokens.
- **Style-literal lint test.** It uses `tokenize` (STRING and FSTRING_MIDDLE tokens), so comments like "# T012" and issue refs like "#12" never trigger. It also flags QColor(<number or string>). The checker itself is tested with bad and good snippets.

### Problems hit
- One wrong expected count in my own test (15 + 8 instead of 13 + 8 colour tokens). It was caught by reasoning before the first run.
- ruff format (4 files) and RUF007 (use itertools.pairwise) were fixed.
- `python tools/palette_preview.py` failed with ModuleNotFoundError: running by path puts tools/ on sys.path, not the repo root. Fix: run as `python -m tools.palette_preview`. Convention added to TASKS.md.
- The ruff cache "Access is denied" warning appeared again (parallel pre-commit batches). Harmless.

### Verification (Tier A + render check)
- pytest: 108 passed (73 new). Hand-computed WCAG cases are in the test docstring:
  - #777777 on white = 4.4786.
  - #3B82F6 on black = 5.7098.
  - white/black = 21.
  - QSS output compared against a hand-written 18-line expectation.
  - ramp_hues(0) and ramp_hues(350) written out by hand.
  - Window metrics match spec 5.1.
- All 5 built-in palettes and 18 generated palettes (9 seeds, including black, white, grey and pale yellow, in dark and light) pass every rule. A forced bad tone (speaker tone 25 on a dark background) gets auto-adjusted and passes.
- Qt parses every palette's QSS with no warnings (qtlog).
- pre-commit: all 7 hooks pass. pyright strict covers `theme/` and `tools/`.
- Palette preview rendered (1656x648) and inspected by me. Every palette is readable over the busy backdrop, and speakers are distinct.
  - Paper's white outline looks slightly soft on a light background.
  - Neon and Midnight look similar at a glance.
  - Both points were raised with the user for G1 feedback.

## 2026-10-17 - T012 follow-up: G1 part 1 defaults applied (user away)
- The user left ("running to the store") and asked me to keep building, applying defaults where no specific answer is needed. Defaults applied:
  - Q1 Midnight stays the default.
  - Q2 thinner outlines on light palettes: new token `OVERLAY.outline_width_light = 1` + `default_outline_width(palette)` (2 px dark, 1 px light).
  - Q3 Neon more purple: bg #0B0614 -> #170A2E, surface #160D26 -> #22103F, surface_alt #26173F -> #321A57, border #3B2A5C -> #4A3373, text_secondary #B8B0D0 -> #C0B6DE.
  - Q4 Inter + size OK.
  - Q5 continue.
- Contrast/dE rules still pass for every palette (tests). The preview was re-rendered (palette-preview-v2.png): Neon now reads as clearly purple, and Paper's text looks crisper with the 1 px halo. The user still needs to confirm G1 part 1 when back.

## 2026-10-17 - T013 State models, actions, reducers (user away; autonomous)

### What was built
- `core/state.py`: frozen pydantic models (`extra="forbid"`, `validate_default=True`).
  - Config models: AppConfig (schema_version 1, my_language, audio, speakers, engines, performance, echo_filter, hotkeys with the spec 5.7 defaults, windows, lock_layout, models_dir, wizard_completed), WindowConfig, WindowStyle, Geometry.
  - Session and runtime models: Utterance (committed + tentative text, is_final, translations), SessionState (utterances + session-only speaker renames), RuntimeState (statuses, metrics, all_hidden).
  - Constraints come from tokens: opacity 0-1, window opacity >= 0.30, font size 8-72, geometry >= 160x60, language-code regex, '#RRGGBB' seed (uppercased), Discord app ID 15-21 digits.
  - Window sources are deduplicated and kept in enum order, so JSON stays stable.
- `core/actions.py`: frozen dataclass actions for config, windows (incl. UpdateAllWindows for the pin-all/click-through-all hotkeys), session (Add/Update/Remove utterance, SetTranslation, ClearSession, RenameSpeaker), runtime (status/metric/all_hidden), plus Batch.
- `core/reducers.py`: `reduce(state, action) -> (state, changes)`. A Change has a kind (CONFIG/WINDOW/UTTERANCE_ADDED/UPDATED/REMOVED/SESSION_CLEARED/SPEAKER/RUNTIME) and a key.
  - Generic `fields` updates are re-validated through `model_validate`. Plain `model_copy(update=)` would skip validation, which is why I didn't use it.
  - No-op updates return the same state object with no changes.
  - Unknown ids: ignored (race-safe).
  - Duplicate ids, unknown fields and bad values raise ValueError, and the state is unchanged.
  - Window changes emit both WINDOW(id) and CONFIG("windows"), so persistence only has to watch CONFIG.

### Design forks
- **Change list from the reducer vs. diffing states in the store.** I chose the reducer's change list: it's pure and Tier A-testable, and diffing nested tuples on every partial update would cost more.
- **Utterance ids are strings supplied by the producer** (e.g. "others-17"), not allocated by the store. A pure reducer can't hand an id back to a worker thread.
- **Speaker renames live in the session** (memory only), per spec 5.13: renames are session-only, and voiceprints and names are never persisted.
- **`EngineConfig` fields are None = "use the recommended default from G4"**, so G4 can pick the defaults without a config migration.
- **Default `pinned=True`** for new windows. It's an overlay, so on-top is the expected behaviour in games. Easy to change.

### Problems hit
- pyright strict: the variable `changes` was annotated as `list[Change]` in one match branch and assigned a tuple in another. A declared type applies to the whole function, so I renamed one of them to `replaced: Changes`.
- ruff F841: an unused variable in a test.

### Verification (Tier A)
- 23 reducer tests, each with a hand-written expected state and change list:
  - window add/remove/update/style/validation, dedup/order of sources, no-op updates, update-all;
  - my_language, config sections, hotkeys, ReplaceConfig change list;
  - utterance partial to final, translations, immutability of the old state, missing ids, remove/clear, rename;
  - runtime;
  - Batch atomicity (failure leaves the input state untouched);
  - duplicate window ids rejected.
- Full suite 132 passed. pre-commit: all 7 hooks pass (pyright strict on core/). License gate: 18 runtime packages, 0 violations (pydantic + 4 transitive dependencies added to the register).
