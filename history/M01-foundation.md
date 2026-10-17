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
