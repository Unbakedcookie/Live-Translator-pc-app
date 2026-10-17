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
