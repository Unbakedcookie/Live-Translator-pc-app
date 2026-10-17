# M00 — Setup (Phase 0) · history

## 2026-10-17 — Session 1

### Kickoff
The user supplied the base prompt (role, project idea, system rules 1–8, phases 0–4). Project idea: a Windows live-translation overlay for social apps and games. Requested features: remembered settings, audio input/output selection, small movable scalable windows, output language choice, opacity, multiple windows for multiple languages, color options, screen-capture → translate, PureRef-style pin-on-top, and suggestions for more features.

### Environment check (before asking questions)
- `git 2.42.0.windows.2`, global identity `UNBAKEDCOOKIE` / captainplanet625@gmail.com.
- `gh 2.100.0`, already authenticated as **Unbakedcookie** (keyring, scopes gist/read:org/repo/workflow). No auth step needed.
- Python 3.10.11 present. Node, Rust and the .NET SDK are absent. Project folder empty, not a repo.
- Lesson: running all the version checks in one PowerShell call meant the first missing tool (`node`) produced an error block. Output was still usable, but separate calls or `Get-Command` checks would be cleaner.

### Question round 1
I asked about: repo name/description/visibility; translation direction (others→me, me→others, both); cloud vs local vs hybrid engine plus GPU/budget; languages; latency vs accuracy; games and fullscreen mode; personal vs shareable; start with Windows; permission to screenshot the desktop and play test audio. I also proposed extra features: global hotkeys, click-through, transcript/export, original+translation toggle, profiles, snap/lock, auto-detect, per-app capture, OCR region watch, font/outline, glossary.

User answers:
- Private repo, named after the folder.
- Translate **both** directions, labelled by source (mic vs output) → "who said what" chat log.
- Engine: "search through free GitHub repos and use the best ones".
- Languages: asked whether to make add-on installs easy or ship the top 10–20.
- Plays windowed; fullscreen support to be decided by difficulty.
- "As live as possible with no latency", but compare results so quality isn't sacrificed.
- Wants to share it eventually.
- Must **not** start with Windows.
- Verification on their PC is allowed. Likes all the suggested features; most or all can go into Settings.
- The user didn't answer about GPU; I measured it instead: RTX 3060 12 GB, i5-10400F, 16 GB RAM.

### Repo creation
- GitHub repo names can't contain spaces → `Live-Translator-pc-app`. The user hadn't given a description, so I wrote one (editable later).
- `git init -b main`, committed `README.md` + `.gitignore` (staged by name), then `gh repo create --private --source . --remote origin --push`. It succeeded: https://github.com/Unbakedcookie/Live-Translator-pc-app (initial commit 3f67d75).
- CRLF warnings on commit are harmless (Windows autocrlf).

### Engine research
- Generic web searches came back thin and mostly secondary (vendor blogs, SEO directories). One directory site (aiindigo) claimed NLLB is commercially permissive, which contradicts its actual license. That's a good example of why secondary sources can't be trusted for licenses.
- Switched to **primary metadata**: `gh api repos/<repo>` for code licenses, stars and last push, and the Hugging Face model API `cardData.license` for weights. This was fast, cheap and authoritative. Reuse this method in future license checks.
- Key findings: NLLB-200 and SeamlessStreaming are **cc-by-nc-4.0**, which rules them out given the user wants to share. rhasspy/piper is archived; its successor piper1-gpl is GPL-3.0. Hunyuan-MT has no license field. Parakeet/Canary are CC-BY-4.0 (attribution needed) and cover 25 European languages only.
- SimulStreaming README: "Licence: MIT" (it also asks commercial users to fill in a questionnaire). PyAudioWPatch shows NOASSERTION on GitHub, but its LICENSE.txt is Apache-2.0.
- The recommended stack was approved as presented (see `docs/tasks/M00-setup.md`).

### Fullscreen
I explained that drawing over exclusive fullscreen requires DirectX hooking, which anti-cheat can treat as cheating (ban risk). The user agreed to **scrap fullscreen for now**.

### Question round 2 (pre-Phase-1 topics)
Proposed defaults: Python 3.12 install; Game mode + GPU/latency readout; headphones + echo duplicate filter; chat-log privacy; voice-out post-MVP; keep the name; review cadence with the window shell as the first gate. The user said yes to all. One change on #4: the log is **auto-deleted when the app closes**, and the app **offers to export the conversation first**.

### Python 3.12
- `winget install --id Python.Python.3.12 --scope user --silent` → 3.12.10 installed (user scope, no admin needed).
- `py` wasn't on PATH in the existing shell because the PATH refresh only applies to new shells. I used the absolute path `%LOCALAPPDATA%\Programs\Python\Python312\python.exe` to create `.venv`. Convention from now on: always call `.venv/Scripts/python.exe` directly.

### Verify helper (`tools/verify/win.ps1`)
- Goal: a dependency-free way for the `verifier` agent to list windows (with Topmost, layered alpha and click-through flags, so pin and opacity can be checked **numerically**, not just visually), take screenshots, and drive mouse and keyboard. No computer-use tool is available in this environment, so this script is our "hands and eyes".
- Bug 1: `Graphics.CopyFromScreen` with `SourceCopy -bor CaptureBlt` threw `InvalidEnumArgumentException (1087111200)`. Cause: .NET Framework validates `CopyPixelOperation` against single defined values and rejects the combined flag. `CaptureBlt` is needed so layered (translucent) windows are captured. Fix: P/Invoke GDI `BitBlt` with `SRCCOPY | CAPTUREBLT` onto the bitmap's HDC.
- Verified: `-Action list` showed real windows with sensible rects; a topmost utility window (AsPowerBar) reported `Topmost=True`; the NVIDIA overlay reported `Alpha=0`. `-Action shot -Title "Visual Studio Code" -MaxWidth 800` produced a correct PNG, which I viewed (it showed the VS Code window and chat). The coordinate mapping is printed (`origin`, `scale`).
- Desktop: two 2560×1440 monitors (virtual 5120×1440). Discord was open on monitor 1 in a Chinese–English language-exchange server, which is a likely real-world test scenario.
- Not yet exercised: click/drag/scroll/keys. They get exercised the first time the verifier drives the window shell (M01). Record any issues then.

### Mid-turn user question: Discord speaker names
The user asked whether the app can tell which Discord user is speaking and label chat lines with their Discord names, and whether this works on every platform.
Answer: not from audio alone, because loopback is one mixed stream. Options: (A) diarization, which works everywhere but gives "Speaker N" (renameable); (B) Discord local RPC `SPEAKING_START/STOP` events + member names, which gives real names on Discord only and needs the user's own Discord developer app (current RPC scope access rules unverified, D-013); (C) both. Self-bots and memory reading are rejected (ToS/ban). A voice bot is too heavy (DAVE E2EE mandatory since 2026-03-01, invite needed per server). Left as an open Phase 1 decision.

### Agent roster
Created `.claude/agents/`: test-runner (haiku), verifier (sonnet), fact-checker (sonnet), code-reviewer (sonnet, plan mode), archivist (haiku), plus a **benchmarker** (haiku), added because comparing ASR/MT engines on latency and quality is a core part of this project.
Also created `CLAUDE.md` holding the condensed standing rules, so the new Phase 1 chat has them without the user re-pasting the base prompt.

### What slowed us down
- Thin, low-quality web search results for model comparisons. Primary API metadata was far better.
- The .NET enum quirk in screenshot capture (one iteration).
- PATH not refreshed after the winget install (minor).

## 2026-10-17 — Session 2: Phase 1 (spec + task breakdown)

### What was done
- Read TASKS.md + M00 "Approved decisions", then wrote `project-spec.md` (sections 1-13) and the milestone task files `docs/tasks/M01`-`M10` (43 tasks, each with a Tier A/B label). Updated the TASKS.md map and added D-015 to D-021 to DATA_TRACKER.

### Design forks and choices made in the draft (all pending user approval)
- **MVP trim.** In: hotkeys, click-through, transcript + export, original+translation toggle, snap/lock, auto-detect, font/outline, Language Manager, game mode + readout, CPU fallback. Post-MVP: installer, OCR auto-watch, diarization, Discord RPC names, profiles, glossary, per-app capture, push-to-translate, voice-out. Reasoning: the core loop (hear, translate, show in an overlay) has to work well before the extras.
- **Streaming policy.** I chose our own LocalAgreement-2 on top of faster-whisper rather than SimulStreaming. AlignAtt needs the PyTorch whisper backend (heavy). SimulStreaming stays a benchmark challenger.
- **VAD.** Use the Silero ONNX model bundled in faster-whisper to avoid a torch dependency (D-016, to be verified).
- **Opacity.** Two controls: background opacity (painted, text stays crisp) and whole-window opacity. Pin and click-through use ctypes `SetWindowPos`/ex-styles to avoid the flicker caused by Qt flag toggling.
- **Hotkeys.** `RegisterHotKey` instead of low-level keyboard hooks (anti-cheat caution, D-020).
- **Store.** Frozen pydantic state + pure reducers + a thread-safe `dispatch` that queues to the main thread, with granular signals. Persistence is debounced and atomic, and the session (chat log) is never persisted.
- **Licensing catch.** PySide6 is LGPL-3.0, not permissive. It's allowed with dynamic linking (onedir), so I added the exception to spec section 11 + D-021.
- **Gates.** G1 window shell (blocks UI), G2 chat line, G3 settings/wizard, G4 engine defaults from benchmark, G5 OCR selector. Non-UI milestones (M03-M05) can proceed while G1 waits for feedback.

### What slowed us
- A multi-file bash heredoc failed with "unexpected EOF while looking for matching quote". The cause was most likely apostrophes in the content clashing with how the tool wraps the command, so nothing was written. Switched to one Write call per file. Lesson: use Write for multi-file docs and keep shell appends free of apostrophes, or use a PowerShell here-string.

### Open questions sent to the user (spec section 13)
Discord names post-MVP; OCR auto-watch post-MVP; default 15 languages; the two opacity controls; profiles/glossary post-MVP; performance targets.

## 2026-10-17 - Session 2b: Phase 1 revision 2 (user additions + fact-checks)

### User feedback on draft 1
- Wants to share the app "without worrying". If the PySide6 license is a problem, a workaround is needed.
- **Speaker names on day one**, not post-launch.
- Additions:
  - Dev tooling early: pre-commit with gitleaks, ruff, bandit, pip-audit, pip-licenses, pyright.
  - UI: QtAwesome + one icon set (Phosphor or Fluent, my pick), Inter, Noto via the Language Manager, materialyoucolor, ColorAide, win32mica.
  - Utilities: platformdirs, loguru, huggingface_hub, lingua-py, jiwer.
  - Speakers: diart (A) + pypresence (B).
- Avoid GPL/AGPL (PyQt-Fluent-Widgets, PyQt-Frameless-Window, Nuitka). Log all licenses and have fact-checker confirm them.

### Fact-checks (2 background fact-checker agents, about 2 min each)
1. **License sweep** of about 45 components (PyPI JSON / GitHub API / HF API). All shipped candidates are permissive except PySide6 (LGPL) and the gated pyannote models.
   - QtAwesome bundles Phosphor 1.3.0 (MIT) but not Fluent. That decided the icon set: Phosphor.
   - QtAwesome also bundles Codicons (CC-BY), to be stripped from the build.
   - The user's exclusions were confirmed: PyQt-Fluent-Widgets GPL-3.0, PyQt-Frameless-Window GPL-3.0, Nuitka AGPL-3.0.
   - Red flags: NVIDIA CUDA wheels sit under the NVIDIA EULA; faster-whisper pulls in PyAV/FFmpeg; diart pins numpy<2 and has heavy dependencies.
2. **Deep questions:**
   - **PySide6 LGPL:** shareable if we use Essentials only + onedir + license texts + **self-hosted Qt source or a written offer** (a qt.io link is not enough) + no reverse-engineering ban + a build scan for GPL-only Qt DLLs. Not a blocker. A wxPython contingency is noted, but not planned.
   - **Discord RPC:** `rpc`/`rpc.voice.read` are approved-partner-only (owner/team + 50 testers). No open approval process was found. Zero-config Discord names for the public are therefore NOT possible. That clashes with the user's day-one wish.
     - The plan became voice labels (zero-config) + an opt-in own-app setup.
     - A Discord RPC spike (T036) was moved early, into M03.
   - **diart:** last release Feb 2025, default models gated on HF (each end user would need a token), torch-heavy.
     - Recommended sherpa-onnx (ONNX models from GitHub releases, no token, no torch) as the default, using a sliding window because it is offline-only.
     - diart is kept as an optional/benchmark engine pending the user's decision.

### Doc changes
- The spec now covers: goals, the MVP table, the new section 5.13 (speaker identification: labels, Discord own-app mode, diarization adapters, fusion algorithm, utterance splitting), fonts/icons/palette generation/contrast in 6.5, the dev tooling table in 10.1, the LGPL compliance plan + transitive binaries in 11, and new gate G6.
- New tasks:
  - T010 dev tooling + license gate (first task).
  - T035 diarization benchmark, T036 Discord RPC spike.
  - M10 Speakers (T101-T105).
- Hardening was renumbered from M10 to M11 (T111-T113). The draft M10-hardening.md was replaced, since it had never been committed.
- DATA_TRACKER: D-013 resolved (blocked for zero-config); D-016/D-017/D-021 updated; new D-022 license register + D-023 to D-030.

### Design forks
- Icons: Phosphor over Fluent. It is bundled in QtAwesome and has outline/fill pairs for toggles.
- License gate: walk the runtime dependency closure from requirements.txt so dev tools are excluded, with LGPL allowed only for PySide6-Essentials/shiboken6.
- Discord token handling: no secret is ever shipped. Try a Public Client + PKCE. If Discord needs a secret, it is the user's own one, encrypted with DPAPI on their PC.

### User decision (2026-10-17, end of Phase 1)
- **Approved**: spec rev 2. Sub-decisions: diart is benchmark-only with sherpa-onnx as the default; host the Qt source copy on GitHub releases; start T010.
- **Speaker plan (Q1)**: the user asked how another person's small Discord program shows who is talking.
- My answer, most likely first:
  1. Their own Discord app (the owner can always authorize it), which matches our opt-in mode.
  2. A voice bot, which receives per-user audio. It is legitimate but needs an invite, hosting and DAVE support. Candidate post-MVP add-on.
  3. A client mod (BetterDiscord/Vencord), which breaks the ToS. Rejected.
  4. Screen-reading the speaking ring. Fragile.
- The current plan stands unless the user reports it was a bot.
