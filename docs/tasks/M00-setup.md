# M00 — Setup (Phase 0)

## Tasks

### T001 — Repo init and initial push · Tier A · Done
- Files: `README.md`, `.gitignore`
- Depends on: —
- Acceptance: local git repo on `main`; private GitHub repo `Unbakedcookie/Live-Translator-pc-app` created via `gh`; initial commit pushed; `origin` tracks `main`.

### T002 — Python 3.12 + project venv · Tier A · Done
- Files: `.venv/` (gitignored)
- Depends on: —
- Acceptance: `.venv/Scripts/python.exe --version` → 3.12.x. System Python 3.10 untouched.

### T003 — Documentation skeleton · Tier A · Done
- Files: `CLAUDE.md`, `TASKS.md`, `docs/tasks/M00-setup.md`, `history/README.md`, `history/M00-setup.md`, `DATA_TRACKER.md`
- Depends on: T001
- Acceptance: layout matches CLAUDE.md "Docs layout"; TASKS.md is an index only.

### T004 — Agent roster + desktop verify helper · Tier B · Done
- Files: `.claude/agents/{test-runner,verifier,fact-checker,code-reviewer,archivist,benchmarker}.md`, `tools/verify/win.ps1`
- Depends on: T003
- Acceptance: each agent has frontmatter (name, description, tools, model, effort, maxTurns) and a restricted tool list; `win.ps1 -Action list` reports windows with Topmost/Alpha; `win.ps1 -Action shot` produces a correct PNG (checked visually).

---

## Approved decisions (inputs for Phase 1 spec)

### Product
- Windows desktop app for live translation while using social apps (Discord etc.) and games.
- **Both directions are translated**: mic = "Me", system-audio loopback = "Others". Output is a speaker-labelled chat log.
- Floating, scalable, movable translation windows. Multiple windows at once, e.g. one per target language.
- Per-window features: output language, opacity, color theme, **pin on top** (PureRef-style pin icon), font size/family, text outline/shadow.
- Screen-capture → OCR → translate.
- Settings remembered across sessions (input/output audio devices, languages, windows, positions, themes).
- **Does NOT start with Windows.** The user launches it manually.
- Must be super easy and user-friendly.
- Must be shareable with other people later. So: an installer eventually, models downloaded on first run, permissive licenses only.

### User-approved extra features (put most or all in Settings; trim to MVP in Phase 1)
Global hotkeys (show/hide all, pin toggle, capture-translate, push-to-translate) · click-through mode · transcript view + export · original + translation display toggle · profiles (devices + languages + layout) · snap to edges / lock layout · auto-detect source language · per-app audio capture (e.g. Discord only) · OCR region auto-watch · font/outline options · glossary (never-translate terms).

### Phase 0 follow-up answers (2026-10-17)
1. Install Python 3.12: **yes** (done).
2. **Game mode** (smaller/lighter models) + live GPU/latency readout: **yes**.
3. Assume headphones + **echo duplicate filter** (drop "Me" lines that match recent "Others" speech): **yes**.
4. Chat log privacy: kept **in memory only, nothing uploaded**. It is **auto-deleted when the app closes**, and on close the app **offers to export the conversation first**.
5. Voice-out (speak my translation into a virtual mic): **post-MVP**. The MVP translates both sides as text.
6. App name "Live Translator" for now.
7. Review cadence: screenshots + user tries it live. The first approval gate is the **floating window shell** (drag, resize, pin, opacity, colors).
- **Exclusive fullscreen: scrapped for now.** Support windowed/borderless only. No DirectX injection (anti-cheat ban risk).
- Languages: Whisper handles about 99 languages for speech-to-text. Translation ships with roughly the 15 most common languages, plus a **one-click Language Manager** for add-on packs.
- Latency: "as live as possible" without sacrificing quality. Benchmark the candidates and compare before choosing defaults.

### Approved tech stack
| Layer | Choice |
|---|---|
| Language | Python 3.12 (project venv) |
| UI | PySide6 (Qt 6 Widgets), QSS generated from a central design-token theme |
| ASR | faster-whisper + large-v3-turbo (CUDA, RTX 3060 12 GB) |
| Streaming policy | SimulStreaming / whisper_streaming approach + Silero VAD |
| ASR challenger | NVIDIA Parakeet TDT v3 via sherpa-onnx (benchmark only) |
| Translation | Pluggable engine interface. Benchmark Opus-MT/Argos (CTranslate2), MADLAD-400 (ct2), Qwen3-4B (llama.cpp) |
| Audio | WASAPI mic + loopback (PyAudioWPatch). Per-app process loopback later |
| OCR | Windows built-in OCR (WinRT) first, RapidOCR fallback; screen grab via mss |
| TTS / virtual mic (post-MVP) | Kokoro + VirtualDrivers/Virtual-Audio-Driver |
| State / settings | Central store (pydantic models) → versioned JSON in `%APPDATA%`. Model folder configurable (default can point to D:) |
| Tests / tooling | pytest, pytest-qt, ruff. Packaging later: PyInstaller + Inno Setup |

**Excluded for licensing:** NLLB-200, SeamlessStreaming (CC-BY-NC); piper1-gpl (GPL-3.0; don't bundle); TranslateGemma (Gemma terms not reviewed); Hunyuan-MT (license unspecified).

### Hardware (user PC)
RTX 3060 12 GB (driver 610.74), i5-10400F 6-core, 16 GB RAM, two 2560×1440 monitors, D: 291 GB free, C: 75 GB free. Parsec virtual display adapter present.

### Open question for Phase 1: Discord speaker names (asked 2026-10-17)
The loopback stream is one mixed audio signal, so the app can't tell *which* other person is talking from the audio alone. Options to spec in Phase 1 (see DATA_TRACKER D-013):
- **A. Voice-based speaker separation (diarization)**: "Speaker 1 / Speaker 2", which you can rename. Works on every platform. No real names. Some accuracy and latency cost.
- **B. Discord local RPC**: `SPEAKING_START`/`SPEAKING_STOP` events with user IDs, joined to channel member names. Gives real Discord names. Needs the user's own Discord developer application plus the RPC scope (access rules unverified). Discord only.
- **C. A + B combined**: B labels the people Discord reports, A covers other platforms.
- Rejected: self-bots or reading Discord's memory (against Discord's ToS, ban risk). A voice bot that receives per-user audio is too heavy (needs DAVE E2EE support and must be invited to each server).
