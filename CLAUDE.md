# CLAUDE.md — operating rules for this repo

Auto-loaded every session. These are the user's standing rules (condensed from the base prompt, 2026-10-17). Follow them strictly.

## Start of every session
Read ONLY `TASKS.md` and the ONE milestone file in `docs/tasks/` currently in play. Read `project-spec.md` by section, never whole.

## Phases (strictly in order)
0. Environment & tech scoping — **DONE 2026-10-17** (see `docs/tasks/M00-setup.md` → "Approved decisions").
1. Spec & MVP: write `project-spec.md`; break work into tasks in `docs/tasks/Mxx-<name>.md` + task map in `TASKS.md`. Mark every task Tier A or B. Flag shared components and schedule them early with an approval gate. **Wait for approval before writing app code.**
2. Execution loop per task: implement → tests (`test-runner`) → tier verification (`verifier` for Tier B) → append narrative to `history/` → 1–3 line status in `TASKS.md` (`archivist`) → local commit → report. Pause for user look-and-feel review on every UI piece.
3. Expand `project-spec.md` into a detailed master doc for future autonomous sessions.
4. Retrospective (only when asked): read `history/`, review procedures, propose an updated base prompt.

## Architecture
- Strict separation: UI is presentational; logic/engines/IO live in separate modules.
- Single source of truth: one central store; UI only references and reacts to it.
- Design tokens only (central theme file). Never hardcode colors, fonts, spacing in components.
- Small composable UI pieces.
- **Lock shared components first**: build, show, get explicit approval BEFORE building anything that depends on them. If the user can't refine one now, pause that feature area and work on something independent.

## Code delivery
- No placeholders / TODOs / "insert logic here". Complete, working code.
- Ask before overwriting major structural files, renaming folders, or deleting significant code.
- Context economy: search then read slices; append to long logs with a shell append; keep replies short and factual — detail goes in files.

## Debugging
On any error: (1) state the cause, (2) explain the fix in plain English, (3) only then apply it. No blind rewrites, no apologizing loops.

## Git
- Commit locally only after the task's verification tier passes; also commit before risky refactors.
- Push ONLY when the user asks.
- Stage files by name — never `git add .` / `-A`.
- Messages like `feat: ...`, `fix: ...`, `chore: ...`, `docs: ...`.
- If a git command fails, stop and explain before any force-push or complex rebase.

## Docs layout
- `project-spec.md` — product/architecture spec.
- `TASKS.md` — SHORT index only (task map, 1–3 line milestone status, current-state block, conventions). No narrative. Keep < ~10 KB.
- `docs/tasks/Mxx-<name>.md` — task specs (ID, title, files, depends-on, acceptance criteria, tier).
- `history/Mxx-<name>.md` — FULL verbose append-only narrative (design forks, bugs and how found, user feedback rounds, verification steps, what slowed us). Never trimmed. Index in `history/README.md`.
- `DATA_TRACKER.md` — see below.
- Code comments cite task IDs (e.g. `# T061`).

## Data & assumption integrity
- Any unverified constant/threshold/assumption/license/benchmark claim → `DATA_TRACKER.md` with status Unresolved / Medium confidence / Resolved.
- Surface relevant tracker items whenever work touches them, before any release, and periodically.
- Respect licensing; never copy copyrighted tables/content into the product. This app must stay shareable: no non-commercial (CC-BY-NC) or unreviewed-license models/code in the shipped product.
- When a value is wrong, fix it in the safe direction first, then record the remaining uncertainty.

## Verification tiers
- **Tier A** — pure logic: hand-computed expected values asserted in pytest.
- **Tier B** — visual/layout/gesture/integration: run the real app on this PC and check it. Take a FRESH screenshot before EVERY interaction; read coordinates from it; never act on stale coordinates. Helper: `tools/verify/win.ps1`.
- Always report exactly what was verified and how; say plainly if anything was skipped.

## Subagents (`.claude/agents/`)
Implementation stays in the main session. Delegate noisy/mechanical/self-contained work with complete instructions; don't delegate tiny tasks.
Roster: `test-runner` (haiku), `verifier` (sonnet), `fact-checker` (sonnet), `code-reviewer` (sonnet, plan mode), `archivist` (haiku), `benchmarker` (haiku — engine latency/quality runs).
