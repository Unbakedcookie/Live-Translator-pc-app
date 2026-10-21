# Live Translator — Project Spec

Status: **Phase 3 master doc, as built 2026-10-20** (Phase 1 spec approved 2026-10-17; sections keep the original plan and add **As built** notes where the build differs). Read this file by section (`grep -n "^## \|^### " project-spec.md`), never as a whole.
Inputs: `docs/tasks/M00-setup.md` → "Approved decisions". Unverified values are tracked in `DATA_TRACKER.md` (D-xxx). Narrative and evidence: `history/`. Current state and what waits on the user: `TASKS.md`.

---

## 0. Start here (future sessions)
**Where the project is.** M01–M11 are built; about 700 Tier A/pytest-qt tests pass. Waiting on the user: Hugging Face upload of the language packs (then a live Language Manager test), look reviews (G3 Settings/wizard/Custom colours/icon, G5 region selector in a game), a real Discord call for speaker names (G6), game mode measured with a game running, T112 with a real call + game, MVP sign-off. `TASKS.md` lists the exact items.

**User.** Gamer on Windows 11, RTX 3060 12 GB, two 2560×1440 monitors side by side (virtual desktop 5120 wide). Doesn't run Python; launches the app from shortcuts. Wants Mandarin to work very well. Likes numbered questions with a default. Keep working autonomously until something needs them (CLAUDE.md has the process rules).

**Everything lives on D:** (C: is full). User environment variables: `LIVETRANSLATOR_HOME=D:\Live Translator pc app\local\app` (settings, models `data\models`, logs `logs`), `HF_HOME` and `PIP_CACHE_DIR` under `local\`. PyInstaller's cache: `local\pyinstaller`. Inno Setup: `local\tools\InnoSetup`. Test profiles and benchmark data: `D:\LiveTranslator\` (`fresh-profile`, `fresh2`, `install-test-profile`, `soak-profile`, `bench-data` with FLEURS clips, `hf-staging` with the 43 packed Opus-MT pairs). `local/` and `build/` are git-ignored.

**Commands** (Git Bash, from the repo):
| What | Command |
|---|---|
| Run the app | `.venv/Scripts/python.exe -m livetranslator` (`--demo`, `--no-speech`, `--paths`, `--self-test`, `--engine-check CLIP.wav`) |
| User's own copy | Start-menu/desktop shortcut → `pythonw -m livetranslator`; after code changes stop it and relaunch the `.lnk` via `explorer.exe` |
| Tests | `.venv/Scripts/python.exe -m pytest -q` (the `-q` summary line doesn't print in this shell: use `--junitxml` for counts); `ruff check`, `ruff format`, `pyright` |
| App build | `python -m tools.build_app` → `build/dist/LiveTranslator/` (onedir; strips NVIDIA, PyAV, FFmpeg plugin, unused icon fonts; adds licences; release licence check). `--console` for a debug build, `--check` to re-check |
| Setup .exe | `python -m tools.build_installer` → `build/installer/LiveTranslator-Setup-<version>.exe` |
| Licence notices | `python -m tools.third_party` (a test fails when out of date) |
| Model hosting | `python -m tools.model_hosting pack|publish|catalog` (HF repo `<user>/live-translator-models`) |
| Long-session soak | `python -m tools.soak --minutes 15` (pretend devices play FLEURS; `soak-profile/soak.csv`) |
| Engines in a build | `LiveTranslator.exe --engine-check clip.wav` → `engine-check.txt` in the log folder (`CUDA_VISIBLE_DEVICES=-1` = a PC without NVIDIA) |

**Tier B on this PC** (`tools/verify/win.ps1`: list, shot, focus, click, drag, keys). Lessons:
- A whole-desktop `shot` without `-MaxWidth` misses translucent windows (overlays, popovers); pass `-MaxWidth`. Crop shots to the app: the user's other windows are private.
- Don't drive the desktop while the user is using it; render widgets off-screen with `QWidget.grab()` instead and leave the live look to their review.
- A built windowed exe that hits an uncaught top-level exception shows a modal message box, which looks like a hang.
- Git Bash heredocs turn `\n` inside Python strings into real newlines: edit source with escapes through the editor tools, not heredocs.

## 1. Overview
A Windows 11 desktop app that translates live:
- **Speech, both directions.** Mic → "Me", system-audio loopback → "Others". Shown as a speaker-labelled chat log.
- **Screen text.** Select a region, OCR it, then translate it.

Output appears in **floating, movable, resizable, pinnable overlay windows**. You can open several at once, e.g. one per target language. Everything runs locally on the GPU. Nothing is uploaded. Transcripts exist only in memory, and you're offered an export when the app closes.

Run: `.venv/Scripts/python.exe -m livetranslator` (package `livetranslator/`).

## 2. Goals and non-goals
**Goals**
1. As live as possible without hurting quality. Defaults are chosen by benchmark (§8, M03).
2. Very easy to use. Sensible defaults, a first-run wizard, every option reachable from Settings, nothing required to configure.
3. Light enough to run next to a game. Game mode plus a GPU/latency readout.
4. Shareable without worry. Permissive licenses only, enforced by an automated license gate on every commit (§10.1, §11). Models downloaded on first run, installer post-MVP.
5. **Speaker names from day one**: voice-based "Speaker N" labels (renamable) everywhere, plus real Discord names via an opt-in setup, because Discord restricts its voice API (§5.13).

**Non-goals (MVP)**
- Exclusive-fullscreen overlays and DirectX injection (anti-cheat risk, D-006).
- Starting with Windows.
- Cloud engines and accounts.
- Voice-out (speaking translations into a virtual mic): post-MVP (D-003, D-012).
- GPL/AGPL libraries of any kind, e.g. PyQt-Fluent-Widgets, PyQt-Frameless-Window. Nuitka is excluded too; we package with PyInstaller (§11).

## 3. UX principles
1. **Zero-config first run.** The wizard asks for 3 things (my language, mic, speakers/headphones), downloads models, and opens one window. Done.
2. **Overlay windows stay out of the way.** Chrome (title bar and controls) appears only on hover. Text stays readable at any background opacity.
3. **Every action is reachable in two ways**: hover controls or the tray menu, plus a global hotkey for in-game use.
4. **You can always get back from click-through.** Hotkey + tray item + a visible first-time hint.
5. **Status in plain words**, e.g. "Listening", "Mic not found — pick another in Settings". No stack traces in the UI.
6. **Remember everything** the user sets (§5.8), except transcripts (§5.11).

## 4. Scope
### 4.1 MVP (M01–M10)
| Area | In MVP |
|---|---|
| Floating windows | Frameless, drag, resize, pin-on-top, background + window opacity, color themes, font family/size, outline/shadow, click-through, snap to edges/other windows, lock layout, multi-monitor, multiple windows |
| Speech | Mic + loopback capture, VAD, streaming ASR with partial → final lines, auto-detect language, echo-duplicate filter |
| Translation | Pluggable engine, default chosen by benchmark, fan-out to every open window's target language, original + translation toggle |
| Chat log | In-memory, transcript window, export (.txt / .json), export offer on close |
| Speaker names | "Me" + per-person labels for others: voice diarization "Speaker N" (zero-config; click to rename), plus real Discord names via local RPC (pypresence) in opt-in own-app mode; fused when both are present (§5.13) |
| Look | Inter font, Phosphor icons (QtAwesome), 5 palettes + "pick one colour" custom palettes (materialyoucolor), contrast-checked (ColorAide), optional Mica frosted glass (win32mica), Noto fonts per language |
| OCR | One-shot region capture via hotkey; re-capture last region; Windows OCR with RapidOCR fallback |
| Hotkeys | Show/hide all, click-through toggle, pin toggle, OCR capture, re-capture, mute Me / mute Others |
| Settings | Tray menu, Settings dialog, first-run wizard, Language Manager (one-click packs), model folder, persistence |
| Performance | Game mode preset, GPU/VRAM/latency readout, CPU fallback when no CUDA |

### 4.2 Post-MVP backlog (ordered by expected value)
1. Installer (PyInstaller + Inno Setup), first-run model download (already in MVP), signed builds later.
2. OCR **auto-watch** a region (re-OCR when the pixels change).
3. Profiles (devices + languages + window layout).
4. Glossary / never-translate terms.
5. Per-app audio capture (process loopback, e.g. Discord only).
6. Push-to-translate hotkey.
7. Voice-out (Kokoro TTS → virtual mic).
8. Remember voices across sessions (opt-in; voiceprints are biometric data, D-028).

**As built:** item 1 is done in the MVP: `tools/build_app.py` + `tools/build_installer.py` (Inno Setup, per-user install, shortcut boxes offered unticked, uninstall asks before deleting settings/models). Unsigned. The app itself is MIT-licensed (`LICENSE`, user 2026-10-19). Items 2–8 are still backlog. Ideas raised by the user since: one person switching between languages (done: "I also speak", up to 4 languages, §5.4).

## 5. Feature specs

### 5.1 Floating window (shared component — approval gate G1)
- Frameless top-level `QWidget` with a translucent background. The content area is painted by us with themed background color × **background opacity** (0–100 %, default 70 %). Text is painted at full alpha, so it stays crisp.
- A separate **window opacity** (30–100 %, default 100 %) fades everything (`setWindowOpacity`).
- **Chrome on hover**: a 28 px title strip fades in when the cursor enters and out 600 ms after it leaves. It contains:
  `[pin] [title / target-language dropdown] … [style] [hide] [close]`.
  The pin icon is PureRef-style: Phosphor `push-pin` (outlined) = off, `push-pin-fill` + accent = on. All icons come from QtAwesome's Phosphor set (§6.5).
- **Frosted glass (optional, off by default)**: Windows 11 Mica/Acrylic backdrop via win32mica, toggled in the style popover. Plain translucent painting is the fallback where it isn't supported.
- **Drag**: anywhere on the background (not on controls). **Resize**: 6 px edge/corner grips. **Ctrl + mouse wheel**: font size ±1 pt.
- **Pin on top**: `SetWindowPos(HWND_TOPMOST/NOTOPMOST)` via ctypes. This avoids the flicker/re-create that Qt's flag toggle causes.
- **Click-through**: `WS_EX_LAYERED | WS_EX_TRANSPARENT` via ctypes. Exit with the global hotkey or the tray. The first time it's enabled, show a toast with the hotkey (§3.4).
- **Snap**: when a dragged edge is within 12 px of a monitor work-area edge or another window's edge, snap to it. **Lock layout** (global or per-window) disables drag/resize and hides the grips.
- **Style popover** (from the [style] button): theme palette, background opacity, window opacity, font family, font size, outline on/off + width, shadow on/off, display mode (translation only / original + translation), sources shown (Me / Others / Screen).
- **Geometry** is persisted per window with its monitor's device name. If that monitor is missing at startup, the window is moved onto the primary monitor's work area.
- **Minimum size** 160 × 60 px. Default new window: 520 × 220 px, bottom-centre of the primary monitor.
- **Multiple windows**: tray → "New window". Each has its own target language and style.
- **As built:**
  - Style popover: theme swatches + **Custom…** (2026-10-19), which opens `ui/custom_colours.py`: 21 labelled colour slots (Window, Text, Buttons and status, Names incl. Person 1–8), click a slot then pick on an embedded colour picker; saved as `WindowStyle.custom_colors` on top of the theme; warns about colours that fail 4.5:1. The one-colour generator lives on as "Make a whole theme from the picked colour". The old popover seed picker was removed (its dialog opened behind pinned overlays).
  - Windows can't be minimised to the taskbar on their own (frameless Tool windows); `ui/taskbar_button.py` is an invisible stand-in that restores them. Hidden/minimised state is `runtime.away`; Ctrl+Alt+H brings everything back.
  - Settings, the Discord guide and the colour editor are stay-on-top and placed beside the overlay (`screens.place_beside`), never under a pinned overlay.
  - Every app-wide store signal is connected to bound methods, never lambdas, so closed windows stop listening (2026-10-19 readout crash).

### 5.2 Chat log, speakers, echo filter
- An **Utterance** has: id, source (`ME` | `OTHERS` | `SCREEN`), speaker label, start/end time, original text, detected language, `is_final`, translations `{lang: text}`.
- **Partial** lines update in place: tentative text is drawn in the secondary text color, committed text in primary. The final line replaces the partial.
- The `speaker` field holds a speaker id + display name (§5.13). "Me" and "Screen" are fixed ids; others are `discord:<user_id>` or `voice:<cluster_n>`. Speaker colours come from the palette's speaker ramp (§6.5).
- **Echo duplicate filter** (D-010): drop a final `ME` utterance if an `OTHERS` utterance overlapped it within ±4 s **and** their texts' rapidfuzz `token_set_ratio` ≥ 80. Both values are tunable in Advanced settings. Pure function, Tier A tested.
- **Speaker names** are in the MVP. See §5.13.

### 5.3 Audio capture
- WASAPI via PyAudioWPatch. Two independent capture threads:
  - **Me**: the selected input device.
  - **Others**: loopback of the selected output device.
  Both default to the Windows default devices.
- Each stream is converted to 16 kHz mono float32 and fed into a ring buffer (60 s max).
- Devices are stored by **name + host API**, not index, because indices change. If the device is missing at startup → fall back to the default device + show a status message.
- **Unplugged device** → status "Reconnecting…", retry every 2 s, resume automatically.
- Mute toggles per stream (hotkey + tray). A muted stream is not processed at all, which saves GPU.
- Live **level meters** in Settings and the wizard, so users can see that the right device was picked.

### 5.4 Speech recognition (streaming)
- Engine interface `ASREngine.transcribe(audio, language|None, prompt) -> Segments(words, timestamps, lang, probs)`.
  The default implementation is faster-whisper (`large-v3-turbo`, CUDA, int8_float16; **G4 2026-10-17**). Game mode keeps turbo with 1.0 s updates. Parakeet via sherpa-onnx is a benchmark challenger only.
- **VAD**: Silero VAD (the ONNX model bundled with faster-whisper, D-016), 32 ms frames. Speech start opens an utterance. **End of speech** = ≥ 500 ms of silence closes it. Hard cut at 15 s, made at the lowest-energy point in the last 2 s.
- **Streaming policy**: our own implementation of **LocalAgreement-2** (whisper_streaming approach, MIT reference):
  - While an utterance is open, re-decode the growing buffer every **update interval** (default 0.5 s; game mode 1.0 s).
  - Commit the longest common word-prefix of the last 2 hypotheses.
  - Emit partial = committed + tentative.
  - On close, do a final decode and emit the final line.
  - A SimulStreaming (AlignAtt) variant is benchmarked in M03 and adopted only if clearly better (it needs PyTorch; extra weight).
- **Language**:
  - Me: fixed to "my language" by default (faster and fewer misdetections). An "Auto-detect my language" toggle is available.
  - Others: auto-detect per utterance. An optional "Others usually speak…" hint is available.
- **GPU scheduling**: one ASR worker thread owns the model and serves both streams with a fair queue (Others first on ties, because that's what the user is waiting to read). Running two model instances is benchmarked in M03 (D-018).
- **No CUDA** → CPU int8 with a smaller model (benchmark picks it) + a one-time notice.
- **As built:**
  - GPU: Whisper large-v3-turbo int8_float16 (warm-up decode proves the GPU; any failure falls back to the CPU and keeps the reason). CPU: Whisper small int8 (built app, card hidden: 5.2 s for a 10.9 s clip; 2026-10-20). The app never downloads a speech model by itself (`download=False`); setup does.
  - Models sit in `<models>/whisper/<key>` (plain folder) or the older Hugging Face cache layout.
  - **What the mic hears** (user request 2026-10-18/19), Settings → General: "Translate into" (`my_language`) is separate from "I speak" (same / detect any / a language) and "I also speak" (up to 3 more; `AudioConfig.mic_languages`, max 4). With 2+ languages each line is detected among just those (`detect_language` share; locks at ≥ 0.97 after ≥ 1 s; the final pass always re-detects). FLEURS: 72/72 whole lines right with 4 candidates; in the first 1.5 s 17–23/24.
  - Chinese is converted to one script (Simplified by default, OpenCC).
  - **Others speak** (2026-10-20): Detect any language (default) or 1–4 languages (`AudioConfig.others_languages`): one = forced, several = detected among them, like "I speak". Live text is right from the first word and noisy lines can't be taken for an unrelated language; whole-line accuracy on clean speech is the same either way (0/160 wrong with auto).
    Since the user's follow-up ("I know they speak Chinese, I don't know what else"): "They also speak" offers **Anything else (detect)** (the default once a language is picked; `others_anything_else`): listed languages are preferred (≥ 0.1 × the top score, D-044), any other is still heard. Others' lines are always detected among the app's 47 translatable languages (`services/asr/language_choice.py`), so nothing is tagged e.g. Icelandic any more.

### 5.5 Translation
- Engine interface `TranslationEngine.translate(texts, src, tgt) -> list[str]` plus `supports(src, tgt)` and `load()/unload()`.
  Candidates (M03 benchmark): Opus-MT / Argos (CTranslate2), MADLAD-400 3B (CTranslate2), Qwen3-4B-Instruct (llama.cpp). The user picks the default from the benchmark table (gate G4).
  - **G4 decision (2026-10-17):** default = **Opus-MT** (CTranslate2; GPU, or CPU with no NVIDIA GPU / in game mode). Argos dropped (no weights licence, D-031). Optional **"Best quality"** setting, off by default: Opus-MT still translates partials, and MADLAD-400 3B re-translates each final line (+3.5 GB VRAM, ~1 s later). Converted Opus-MT models are hosted in an HF repo under the user's account with CC-BY credits (T054).
- **Router**: picks the engine per (src, tgt). Pivots through English when no direct pair exists (Opus-MT/Argos). Skips translation when src == tgt.
- **Fan-out**: every final utterance is translated into the set of target languages of the open windows that show its source. Each language is translated once, no matter how many windows use it.
- **Partials**: translate the committed prefix at most 2×/s when the engine's p50 latency < 150 ms (decided by benchmark). This is off in game mode.
- **LRU cache** (1 000 entries) keyed by (engine, src, tgt, text).
- **Language packs**: a pack is the set of model files needed for a language **plus the Noto font(s) for its script** (e.g. Noto Sans JP/KR/SC, Noto Sans Arabic, Noto Sans Devanagari). Latin/Cyrillic are covered by Inter + Noto Sans, which ship with the app. ~15 default languages (list in §13, Q3) are offered in the wizard. More are added via the Language Manager. Every pack has a license field, and packs that aren't permissive are never offered (D-001).
- **As built:**
  - Opus-MT (CTranslate2) is the default engine; 43 X↔en pairs are converted and packed (`benchmarks/opus_convert.py`, `tools/model_hosting.py`). A language pack = that language to and from English; other pairs pivot through English. Target tags: `>>pol<<`, `>>ara<<`.
  - **Qwen3-4B (Q4_K_M) via a llama.cpp Vulkan `llama-server` subprocess** is the optional "smarter translation" (needs ~3 GB VRAM; offered when the card has ≥ 8 GB). It goes first for `smart_languages` (default Mandarin), for pairs marked `quality: rough` (en-hi, hi-en, ur-en; D-039), and as the fallback for languages with no installed pack (`smart_fallback`, 47 languages, D-038). It pauses in game mode. MADLAD-400 "Best quality" was not built (Qwen replaced it).
  - No Noto script fonts are downloaded: CJK, Arabic and Devanagari use Windows' own fonts through Qt's fallback. Inter and Noto Sans ship with the app.
  - Settings → Languages (`ui/language_manager.py`) installs/removes packs with one progress bar; downloads come from the HF repo once it's published (the catalogue gets the pack entries from `tools.model_hosting catalog`).

### 5.6 Screen OCR
- **Hotkey → region selector**: a full-virtual-desktop dim overlay. Drag a rectangle; Esc cancels. Works across both monitors.
- Grab via `mss`. OCR with **Windows.Media.Ocr** (pywinrt) using the screen-language hint (default: try installed Windows OCR languages for my languages + windows' targets). If that OCR language isn't installed on Windows (D-009) → RapidOCR (ONNX).
- **Language of the recognised text** is detected with **lingua-py**, limited to installed language packs (faster, more accurate, less RAM). That sets the MT source language.
- Result goes to the chat log as a `SCREEN` utterance (translated like speech), shown in windows whose sources include Screen. Default: an "OCR" window opens next to the region the first time.
- **Re-capture last region**: a hotkey runs the same region again (useful for game chat).
- Auto-watch is post-MVP.
- **As built:** lingua-py was not used (one 300 MB wheel); `services/langdetect.py` detects the language from script letters + function-word lists for the Latin-script languages (Swedish and 12 more added 2026-10-19). RapidOCR runs with `Det.limit_side_len 2560, limit_type max` (its default upscaled chat strips ~5×: 2 s → 0.2 s per capture). `merge_rows` joins words split across boxes and drops overlap repeats.

### 5.7 Global hotkeys
- Win32 `RegisterHotKey` via ctypes + a Qt native event filter. No low-level keyboard hooks (they're less likely to trip anti-cheat, D-020).
- Defaults (editable in Settings, conflicts reported):
  - Ctrl+Alt+H show/hide all
  - Ctrl+Alt+T click-through all
  - Ctrl+Alt+P pin all
  - Ctrl+Alt+O OCR region
  - Ctrl+Alt+R re-capture
  - Ctrl+Alt+M mute Me
  - Ctrl+Alt+N mute Others
  - Ctrl+Alt+G game mode

### 5.8 Settings and persistence
- All paths come from **platformdirs** (`user_config_dir`, `user_data_dir`, `user_log_dir` for app "LiveTranslator"), never hand-built. Logging uses **loguru** (rotating file, 7-day retention, a filter that drops any record carrying transcript text).
- **Single source of truth**: the central `Store` (§6.3). Persisted slice → `%APPDATA%\LiveTranslator\settings.json`:
  - `schema_version` + migrations.
  - Atomic write (temp file + `os.replace`), debounced 500 ms after the last change.
  - A corrupt file is renamed `settings.corrupt-<ts>.json` and defaults are loaded + notice shown.
- **Persisted**: devices, my language, labels, windows (target language, sources, display mode, style, geometry, pinned, click-through, locked), hotkeys, engine choices, game mode, model folder, echo-filter params, wizard-completed flag.
- **Never persisted**: transcripts/chat log, OCR images.
- **Model folder**: default `%LOCALAPPDATA%\LiveTranslator\models`. Changeable in Settings (this PC: `D:\LiveTranslator\models`). Changing it offers to move existing models.
- **Settings dialog pages**: General (my language, close behaviour), Speakers (§5.13), Audio (devices + meters), Windows (list, defaults, lock layout), Translation (engines, languages → Language Manager), Hotkeys, Performance (game mode, readout, ASR interval), Advanced (echo filter, VAD thresholds, logs folder).
- **As built:** pages General (Translate into, I speak, I also speak, Chinese characters, folders), Audio, Speakers, Windows, Translation (Qwen per language + fallback), Languages (pack manager), Hotkeys, Performance, Advanced (echo filter, VAD, Restore defaults, **Run setup** again), About (version, privacy, every licence). Settings screens are imported at startup (a lazy import once mixed code versions after an update). One running copy per settings folder (`QLocalServer`, name hashed by profile); a second launch shows the first copy's windows. The app registers its notification name + icon under `HKCU\Software\Classes\AppUserModelId\LiveTranslator.App` (D-037).

### 5.9 First run and model management
- **Wizard**: Welcome + privacy note → My language → Mic + speakers (meters) → Languages to install (pre-ticked: mine + the 3 most common others) + model folder + total download size → Download (progress, resumable, SHA-256 verified) → Done (opens the default window).
- **ModelManager**:
  - Model catalog in a JSON shipped with the app: id, source (HF repo + **pinned commit revision** + file list, or a direct URL for fonts/other), size, sha256, license, engine, languages.
  - Hugging Face downloads go through **huggingface_hub** (`hf_hub_download` / `snapshot_download`: resumable, cached, no token needed for ungated repos). Other files use plain HTTPS with resume.
  - Downloads into a temp file → verify SHA-256 → move into place.
  - Shows free disk space before downloading.
- **As built (T073):**
  - Wizard steps: Welcome → Your languages → Microphone and speakers (live level bars) → What to download (sizes, free space, folder; pre-ticked: your language + 3 common) → Downloading (one bar, Pause/Continue, resumes) → Done. It starts from the saved settings when run again from Settings → Advanced; closing a later run doesn't quit.
  - Setup runs when the speech model is missing, or when an NVIDIA card's cuBLAS isn't loadable (`_needs_setup`).
  - **NVIDIA libraries (D-026, accepted by the user 2026-10-19):** never in the build. On NVIDIA PCs the wizard downloads NVIDIA's own `nvidia-cublas-cu12` wheel (528 MB, pinned URL + SHA-256) into `<models>/cuda/cublas` and shows an "NVIDIA graphics libraries" row with a link to NVIDIA's licence. cuDNN isn't needed (measured). `platform/cuda.set_runtime_root` adds those folders at start.
  - `services/models.py` downloads plain HTTPS (named User-Agent) with resume, SHA-256, cancel and an atomic folder swap; sources are `url` (+zip) or `files` (several files). huggingface_hub isn't used for downloads; the Whisper/Qwen/llama.cpp/TitaNet entries point at their upstream files, the Opus-MT packs at the user's HF repo (pending).

### 5.10 Game mode and performance readout
- **Game mode** (toggle in tray/hotkey/Settings) applies a preset: smaller/faster ASR config, update interval 1.0 s, partial translation off, lighter MT engine where one exists. The exact preset is set from M03 data (D-004/D-005). **G4 preset (2026-10-17):** turbo at 1.0 s updates, partial translation off, Opus-MT on CPU (0 VRAM), "Best quality" MADLAD unloaded.
- **Readout**: an optional footer strip per window, or a tiny standalone HUD. Shows GPU %, VRAM used/total (app + total), ASR latency p50, MT latency p50, end-to-end lag (speech end → final line). Data comes via `nvidia-ml-py` (NVML), sampled at 1 Hz.

### 5.11 Privacy, close and export
- The chat log lives in memory only. Logs (`%LOCALAPPDATA%\LiveTranslator\logs`, rotating) **never contain transcript text**.
- **Close/Quit**: if the log isn't empty → dialog "Export this conversation before closing?" [Export…] [Close without saving] [Cancel]. The log is wiped on exit. Closing the last overlay window does **not** quit; the tray icon stays.
- **Export**: `.txt` (timestamp, speaker, original, translations) and `.json` (full Utterance list).
- The transcript window can also export at any time.
- Consent note for the release: D-011.

### 5.12 Tray icon
Menu:
- Show/Hide all
- New window
- Mute Me / Mute Others
- OCR region
- Game mode ✓
- Click-through ✓
- Transcript…
- Settings…
- Language Manager…
- Quit

Double-click toggles show/hide. The icon's colour shows the status (listening / paused / error). The menu also gets **Discord: Connected ✓ / Connect…**.

**As built:** the tray glyph keeps the palette colours (accent = listening, grey = paused, red = error), so it stays a status light. The **app icon** (desktop, taskbar, notifications, setup) is different since 2026-10-19: a vibrant red tile with a bold white translate glyph (`theme/icons.app_icon`, `APP_ICON` tokens), because the blue glyph blended into the desktop.

### 5.13 Speaker identification (shared design — gate G6)
Goal: every line shows *who* said it, from day one.

**Labels**
- `Me`: always the mic. Shows "Me" by default; an option uses my Discord display name when connected.
- `Others`: one label per person.
  1. **Discord name** when Discord is connected and a voice channel is active.
  2. Otherwise a **voice cluster** label "Speaker 1", "Speaker 2", …
  3. Click any label in a window → inline rename (session only). A rename of a voice cluster sticks to that voice for the session.
- `Screen`: OCR lines.

**Source B: Discord local RPC (pypresence)**
- One-click **Connect Discord** (Settings → Speakers, tray, or wizard step "optional"). The Discord desktop client shows its own authorize prompt.
- Uses scopes `rpc` + `rpc.voice.read`, then:
  - `GET_SELECTED_VOICE_CHANNEL` gives members + nicknames.
  - `VOICE_CHANNEL_SELECT` follows channel switches.
  - `SPEAKING_START`/`SPEAKING_STOP` per channel are timestamped on arrival.
- **Access reality (D-013, fact-checked 2026-10-17)**: `rpc` / `rpc.voice.read` are **approved-partner-only**. An unapproved app can only be authorized by its owner, its team and up to 50 invited testers. There's no open approval process. So zero-config Discord names for the public aren't possible. Plan:
  - **Own-app mode (opt-in)**: a guided ~5-step setup. The user creates a free Discord application in the Developer Portal, copies its Application ID, and pastes it into Settings → Speakers. As that app's owner, they're allowed to authorize it. In-app screenshots + a "Test connection" button.
  - **Tester mode**: our own app ID with up to 50 testers. Usable for a small friends beta only.
  - If neither works, Discord names stay off and voice labels still work.
- **No client secret is ever shipped.** The token exchange uses a Public Client + PKCE if Discord accepts it for the RPC code (unofficial, D-030, tested in T036). If a secret turns out to be required, own-app mode stores the user's own secret DPAPI-encrypted on their PC, and our app never contains one.
- Tokens are stored encrypted with Windows DPAPI (ctypes `CryptProtectData`) in the config dir. The Disconnect button deletes them.

**Source A: voice diarization (engine decided at G4)**
- **G4 decision (2026-10-17): per-line labels** — one TitaNet-large embedding (sherpa-onnx, CPU) per VAD line matched to running centroids (T102), plus the in-line speaker-change split (T105). Measured DER 0.10 vs 0.35 for the sliding window below (T035). The sliding-window text below is kept as the original plan.
- Runs on the `Others` loopback stream only, in its own worker, outputting speaker segments `(t0, t1, cluster_id)`.
- Default max 6 speakers. Embeddings live in memory only and are **never written to disk** (biometric data, D-028).
- Engine interface `DiarizationEngine` with two adapters, both benchmarked in T035:
  - **sherpa-onnx** (recommended default): pyannote segmentation-3.0 ONNX + an Apache-licensed speaker-embedding ONNX, downloaded from k2-fsa GitHub releases. No HF token, no torch. It's offline-only, so we run it on a sliding window (e.g. the last 10 s every 1 s) and keep cluster ids stable by matching embeddings to running centroids (D-029).
  - **diart** (user-requested, optional): true online diarization, but last released Feb 2025, pins numpy < 2, and pulls in torch + torchvision/pandas/matplotlib/optuna. Its default pyannote models are **gated** (each user needs an HF account + token), and torch CUDA bundles NVIDIA binaries under NVIDIA's EULA (D-023, D-024, D-026). So it can't be the zero-config default. If kept, it's an optional "advanced: bring your own HF token" engine, installed separately and excluded from the default bundle.

**Fusion (pure logic, Tier A)**: for a final `Others` utterance `[t0, t1]`:
1. Shift Discord events by the calibrated lag (median offset between SPEAKING_START and VAD onsets over the first 10 events; D-025).
2. If exactly one Discord speaker covers ≥ 60 % of the utterance → that name. The voice cluster active in that window is linked to that user (vote count).
3. If several Discord speakers overlap → pick the user linked to the active voice cluster (majority vote). Otherwise the one with the largest overlap.
4. No Discord data → voice cluster label (renamed name if set).
5. Nothing reliable (< 1 s audio, low confidence) → "Others".

**Utterance splitting**: the VAD segmenter also closes an utterance at a speaker change (Discord or diarization) after ≥ 300 ms of hysteresis. This way two people talking back-to-back without a pause become two lines.

**Settings → Speakers**:
- Mode: **Auto** (Discord when connected, else voice) / Voice only / Discord only / Off (single "Others").
- Connect/Disconnect Discord + status.
- Max speakers.
- "Me" label.
- Show speaker colours.

**As built:** per-line TitaNet labels (sherpa-onnx, CPU) + Discord own-app mode. Discord's token exchange needs the app's client secret (D-030 Plan A): the user pastes their own app's ID and secret in the 8-step guide (Settings → Speakers; stay-on-top, beside the overlay; "Skip" for the portal survey), both stored DPAPI-encrypted. Discord's authorize prompt is only requested by "Test connection", never by the background client (it used to pop up every 5 s); the token endpoint needs a named User-Agent (Cloudflare 1010 otherwise). The user's sign-in works (2026-10-19); names in a real call are not yet verified (G6).

**As built (2026-10-20):**
- A voice heard while Discord is live but nobody in the call speaks (a stream, a video) gets NOT_IN_CALL votes; with ≥ 3 of them (and ≥ 2× any member's) it keeps "Speaker N" even when a member talks over it (D-041).
- **Separate people talking over each other** (Settings → Speakers, experimental, off by default; `services/speakers/separation.py`, `app/separation_controller.py`). Each final Others line is checked by pyannote segmentation-3.0 (ONNX, MIT, D-043); a line with ≥ 0.5 s of two-talker speech is split by ConvTasNet sep_clean 16k (our ONNX export, CC-BY-SA-4.0, D-042). Each voice is recognised with the quick pass, and the line becomes two lines (`<id>` + `<id>-v2`), each labelled from its own voice and translated. The split is only kept when both voices give real, different text. Both models run on the CPU (onnxruntime); the feature is off in game mode. Downloads: the detector from k2-fsa's HF mirror (pinned), the separator from the app's model repo (`tools.model_hosting extras`, after the HF publish). Spike: both talkers understood 0 % → 72 %; full-app soak: 3.5–10 s per split line with other work sharing the machine (`benchmarks/results/separation.md`).

## 6. Architecture

### 6.1 Layers (strict separation)
```
ui/  (presentational: widgets read store state, emit user intents)
  │  intents → Controller methods
  ▼
app/  (controllers: translate intents into store actions + service calls)
  │
  ▼
core/  (Store, state models, reducers, persistence, chat-log logic)  ◄── services post actions
  ▲
services/  (audio, asr, mt, ocr, hotkeys, models, metrics: no Qt widgets)
```
UI never calls engines directly. Services never touch widgets. Pure logic (reducers, echo filter, LocalAgreement, router, snapping math, QSS generation, export formatting, migrations) has no Qt imports and is Tier A tested.

### 6.2 Package layout
```
livetranslator/
  __main__.py            entry point
  app/                   composition root, controllers, tray
  core/                  state.py (pydantic models), actions.py, reducers.py, store.py,
                         persistence.py (+migrations), chatlog.py (echo filter, export)
  theme/                 tokens.py (design tokens + palettes), palette_gen.py (materialyoucolor),
                         contrast.py (ColorAide checks), qss.py (QSS generator), icons.py (QtAwesome
                         Phosphor wrapper), fonts.py (Inter/Noto loading), backdrop.py (win32mica), fonts/
  ui/widgets/            small presentational pieces (IconButton, PinButton, Slider, Swatch,
                         LanguagePicker, LevelMeter, ChatLine, Toast…)
  ui/                    floating_window.py, translation_view.py, transcript_window.py,
                         settings/, wizard/, region_selector.py, dialogs.py, hud.py
  services/audio/        devices.py, capture.py, resample.py
  services/asr/          base.py, faster_whisper_engine.py, vad.py, local_agreement.py, worker.py
  services/mt/           base.py, engines/…, router.py, cache.py, worker.py
  services/ocr/          grab.py, windows_ocr.py, rapid_ocr.py
  services/speakers/     base.py (DiarizationEngine), sherpa_engine.py, diart_engine.py (optional), discord_rpc.py (pypresence),
                         fusion.py (pure), calibration.py (pure), token_store.py (DPAPI)
  services/hotkeys.py    services/models.py    services/metrics.py    services/langdetect.py (lingua)
  platform/win32.py      ctypes helpers (topmost, click-through, hotkeys, work areas)
tests/                   mirrors the package; Tier A pytest + pytest-qt
benchmarks/              M03 harness + results (results committed as markdown, audio not committed)
```
**As built (2026-10-20):**
```
app/        application (composition root, LiveTranslatorApp, run), window_manager, tray, lifecycle,
            controllers: window, settings, speech, translation, ocr, discord, language (packs),
            setup (wizard plan/download/apply); level_probe, single_instance, paths, log,
            engine_check (--engine-check), demo (--demo feed)
core/       state, actions, reducers, store, persistence, migrations, chatlog (echo filter),
            chat_view / status_view (pure view models), export, languages, presets
theme/      tokens (incl. APP_ICON), palette_gen (+ with_colors), contrast (+ hard_to_read), qss,
            icons (+ app_icon), fonts, backdrop
ui/         floating_window, translation_view, style_popover, custom_colours, transcript_window,
            region_selector, language_manager, discord_setup, about, readout, status_strip,
            taskbar_button, screens (place_beside), session (quit/export), dialogs, gallery (dev)
ui/settings/  settings_window, rows (page/section/row blocks), one *_page per page, hotkey_box,
              level_meter, context
ui/wizard/  setup_wizard        ui/widgets/  chat_line, choice/search/font/language pickers,
                                             swatch, slider, pin/icon buttons, speaker_label, toast
services/   audio (capture, devices, ring, resample, level), asr (faster_whisper_engine, vad,
            local_agreement, worker, chinese), mt (router, cache, worker, engines/opus_mt,
            engines/qwen_llama), ocr (grab, windows_ocr, rapid_ocr), speakers (sherpa_engine,
            clusters, change, fusion, calibration, discord_rpc, token_store, worker),
            models (catalogue + downloader), language_packs, langdetect, hotkeys, metrics, timings
platform/   win32 (ctypes), cuda (NVIDIA library folders), app_identity (registry name + icon)
data/       model_catalog.json, third_party.json (generated)
tools/      build_app, build_installer + installer/LiveTranslator.iss, app_entry, model_hosting,
            third_party, release_license_check, check_licenses (+ policy/overrides), soak,
            palette_preview, verify/win.ps1
```

### 6.3 Central store
- `AppState` (frozen pydantic) = `config` (persisted) + `session` (chat log, not persisted) + `runtime` (engine status, device status, metrics; not persisted).
- `Store(QObject)` holds the current state.
  - `dispatch(action)` is **thread-safe**: off the main thread it's queued to the main thread via a queued signal.
  - Reducers are pure `(state, action) -> state`.
- Granular signals: `config_changed(path)`, `window_changed(window_id)`, `utterance_added(id)`, `utterance_updated(id)`, `runtime_changed(key)`. Widgets subscribe only to what they show.
- `Persistence` subscribes to `config_changed` → debounced atomic save.

### 6.4 Threads
| Thread | Owns | Talks via |
|---|---|---|
| Main (Qt) | Store, all widgets | signals |
| Capture ×2 | WASAPI streams → ring buffers | lock-free-ish deque + events |
| VAD/segmenter | utterance open/close per stream | queue → ASR worker |
| ASR worker (1) | Whisper model on GPU | job queue in; `dispatch` out |
| MT worker (1) | translation engines | job queue in; `dispatch` out |
| OCR (on demand) | grab + OCR | `dispatch` out |
| Metrics | NVML sampling 1 Hz | `dispatch` out |
| Diarization worker | diarization engine on the Others stream | segments → fusion |
| Discord RPC | pypresence IPC client (asyncio loop in its own thread) | events → fusion; `dispatch` out |
Workers stop cleanly on quit (sentinel + join with timeout). Models load lazily on a worker, never on the UI thread.

### 6.5 Design tokens (shared — gate G1)
- `theme/tokens.py` is the only place colours, fonts, sizes, spacing, radii and durations are defined. Components read tokens; QSS is generated from them. No literals in components (lint check in tests: grep for `#[0-9a-f]{6}` / `rgb(` outside `theme/`).
- Token groups:
  - `color.*`: bg, surface, text.primary, text.secondary, accent, speaker.me, speaker.others, speaker.screen, outline, border, danger, ok
  - `font.*`: family.ui, family.overlay, size scale
  - `space.*`: 4/8/12/16/24
  - `radius.*`
  - `motion.*`: fade durations
  - `overlay.*`: outline width, shadow blur/offset
- **Palettes** (per-window theme): Midnight (default dark), Subtitle (black bg, white text + outline), Paper (light), Neon (dark, vivid speaker colours), High Contrast. A palette = a full set of `color.*` tokens, including a **speaker ramp** of 8 distinct colours for others.
- **Custom "one colour" palette**: the user picks a single seed colour → **materialyoucolor** (Material 3 dynamic colour) generates the whole palette (dark or light scheme) and the speaker ramp from tonal hues.
- **Contrast checks** with **ColorAide**: every text/background token pair (built-in and generated) must reach WCAG 2 contrast ≥ 4.5:1. Speaker colours vs bg ≥ 4.5:1, and adjacent speaker colours must stay distinguishable (ΔE2000 ≥ 20). A generated palette that fails is auto-adjusted by shifting tone, then re-checked (Tier A tests).
- **Fonts**: **Inter** (bundled) for UI and Latin/Cyrillic overlay text, plus Noto Sans as fallback. Script-specific **Noto** fonts are downloaded with language packs (§5.5) and registered at startup with `QFontDatabase.addApplicationFont`. The overlay font stack is `[user choice] → Inter → Noto Sans <script>`.
- **Icons**: **QtAwesome** with the **Phosphor** set only (one set, consistent weights). Recommendation over Fluent UI System Icons: Phosphor (MIT) is bundled in QtAwesome (v1.3.0 font, Confirmed D-022); Fluent is not, so it would need separate font/SVG loading. Phosphor also has outline/fill pairs (e.g. `push-pin`/`push-pin-fill`, exact names checked against the QtAwesome charmap in T022) that suit toggles. Icon colours come from tokens.
- **Backdrop**: optional Mica/Acrylic via **win32mica** (Windows 11 only), off by default.

## 7. Shared components and approval gates
| Gate | What you approve | Blocks | Built in |
|---|---|---|---|
| **G1** | Design tokens + 5 palettes, widget kit (buttons, pin, sliders, swatches), **FloatingWindow shell** (drag, resize, pin, opacity, colours, click-through, snap, lock) | all UI after it (M06–M09) | M01 (tokens) + M02 |
| **G2** | ChatLine + translation view look (partial vs final, speaker colours, original+translation layout) | transcript window, OCR results | M06 |
| **G3** | Settings dialog + first-run wizard + Language Manager flow | release | M07 |
| **G4** | Default engines from benchmark table (quality vs latency vs VRAM) | M04/M05 defaults | M03 |
| **G5** | OCR region selector feel | OCR polish | M08 |
| **G6** | Speaker labels: names/colours in the chat line, rename interaction, Connect Discord flow | release | M10 |
Engine interfaces (`ASREngine`, `TranslationEngine`) and the Store/action contract are shared code contracts. They're defined in M01 and changed only with a note in history.
While G1 waits for feedback, the independent non-UI milestones (M03, M04, M05 logic) continue.

## 8. Performance budgets (targets; D-015)
| Metric | Normal | Game mode |
|---|---|---|
| First partial text after speech starts | ≤ 1.0 s | ≤ 1.5 s |
| Final translated line after speech ends | ≤ 1.5 s | ≤ 2.5 s |
| App VRAM (incl. diarization) | ≤ 6 GB | ≤ 3 GB |
| Speaker label correct (2–4 people, Discord connected / voice only) | ≥ 95 % / ≥ 80 % of lines | same |
| CPU (6-core i5) while listening | ≤ 25 % | ≤ 15 % |
| Idle (both muted) | no GPU work | — |
These are measured in M03/M09 and adjusted with the user if they can't be met.

**Measured so far:** see `history/M03-benchmarks.md`, `M09-game-mode.md` and the T112 soak (`history/M11-hardening.md`, 2026-10-20: recorded speech in 8 languages for 15 min, 140 lines, all translated, no errors, memory flat at ~1.4 GB; delay from speech end to translated line p50 1.2 s, p95 1.5 s rising to 3.3 s when a rare slow translation (3 of 140, 1.8–3.4 s, not reproducible alone) fell inside the 50-line window). CPU-only PCs (Whisper small): ~0.5× real time per final line. Not yet measured with a game running or in a real Discord call.

## 9. Error handling
- Every service failure becomes a `runtime` status with a plain-language message + suggested action. It's shown in the window footer and the tray tooltip.
- CUDA/cuDNN missing → CPU fallback (§5.4). Model missing or corrupt → offer to re-download. Device missing → fallback + retry (§5.3). OCR language missing → RapidOCR.
- Uncaught exceptions are logged (without transcript text), shown as a toast, and the app keeps running. Worker threads restart once, then show an error status.

## 10. Testing and verification
- **Tier A** (pytest): reducers, store dispatch, persistence round-trip + migrations + corrupt-file recovery, echo filter, LocalAgreement, VAD segmenter on synthetic audio, router/pivot/cache, fan-out set, export formats, snapping math, geometry restore onto missing monitor, QSS generation, hotkey string parsing, model catalog verification. Expected values are hand-computed in the tests.
- **pytest-qt**: widget signal wiring (no visual claims).
- **Tier B** (`verifier`): real app on this PC, using `tools/verify/win.ps1` with a fresh screenshot before every interaction. Covers window behaviour, overlay over a borderless game, click-through, hotkeys, live Discord call / YouTube audio, OCR on a real game chat.
- **Benchmarks** (`benchmarker`): latency/quality/VRAM tables in `benchmarks/results/*.md`.
- All pre-commit hooks pass before every commit (§10.1).

### 10.1 Dev tooling (task T010, the first task of M01)
**pre-commit** runs on every commit. Python hooks are `local` / `language: system` and use `.venv/Scripts/python.exe`, so the tool versions are pinned in `requirements-dev.txt`.
| Hook | What it guards | When |
|---|---|---|
| gitleaks | secrets (tokens, client secrets, keys) | every commit |
| ruff (lint + format check) | style/bugs | every commit |
| bandit (`-c pyproject.toml`, asserts allowed in tests) | insecure Python patterns | every commit |
| pyright (basic mode; strict for `core/` and `theme/`) | type errors | every commit |
| pip-audit (audits the installed venv: runtime + dev) | known-vulnerable dependencies | when `requirements*.txt` changes + manual run |
| license gate: `tools/check_licenses.py` wrapping **pip-licenses** | only allow-listed licenses in the **runtime** dependency closure (walked from `requirements.txt` via `importlib.metadata`). Dev tools are excluded. | when `requirements*.txt` changes + manual run |
- License allow-list (source of truth: `tools/license_policy.toml`): MIT, MIT-0, 0BSD, BSD, BSD-2/3-Clause, ISC, Zlib, Apache-2.0, PSF-2.0, Python-2.0, MPL-2.0 (file-level; unmodified), Unlicense, HPND, OFL-1.1 (fonts), CC0-1.0, CC-BY-4.0 (models; attribution), and LGPL-3.0 **only** for `PySide6-Essentials` / `shiboken6`.
- SPDX expressions are evaluated properly: `OR` = any option allowed, `AND` = all allowed, `WITH` judged on the base license. Multiple trove classifiers are treated as AND (safe direction).
- Fail on: GPL, AGPL, any NC/ND, "UNKNOWN". An `UNKNOWN` can only be cleared by an override file `tools/license_overrides.toml`, which needs a DATA_TRACKER reference (D-022) per entry.

## 11. Packaging and licensing
- MVP runs from the venv. The installer (PyInstaller + Inno Setup) is post-MVP.
- **Shipped code and models must be permissive** (allow-list in §10.1). This is enforced automatically by the license gate on every dependency change.
- **PySide6/Qt (LGPL-3.0)** is the one exception. LGPL lets anyone share an app that *uses* the library, free or paid, as long as we follow its rules. Compliance plan (D-021, fact-check pending):
  1. Depend on **`PySide6-Essentials` only**, not the full `PySide6` (whose Addons include some GPL-only Qt modules). Use only LGPL modules (QtCore/QtGui/QtWidgets/QtSvg/QtNetwork).
  2. Package as PyInstaller **onedir** so the Qt/PySide DLLs are separate, replaceable files. Never modify Qt.
  3. Ship the LGPL-3.0 + GPL-3.0 texts and a prominent "uses Qt/PySide6 under LGPLv3" notice (About → Licenses). **Host the exact matching Qt/PySide6 source tarballs ourselves** as release assets, plus a 3-year written offer. A link to qt.io alone is *not* enough.
  4. Our terms never forbid reverse engineering or replacing the Qt libraries. No onefile, no UPX on Qt DLLs.
  5. A release script scans the build folder and fails if any GPL-only Qt DLL is present (Qt6Charts*, Qt6DataVisualization*, Qt6Quick3D*, Qt6VirtualKeyboard*, Qt6Graphs*, …).
  6. A release checklist item verifies 1–5. Fact-checked 2026-10-17: shareable on these terms (D-021, Medium; "onedir satisfies LGPL §4d" is an inference).
  - **Workaround if anything breaks** (e.g. a fact-check finds a blocker): only `ui/` and `platform/` touch Qt, and the Store/services are Qt-free except for signals behind `core/store.py`. So the UI can be swapped without touching engines. The candidate is wxPython (wxWindows Library Licence, which explicitly allows binary distribution under any terms). This is a contingency, not planned work.
- Fonts: Inter and Noto are OFL-1.1. They're free to bundle/redistribute; we just can't sell the fonts on their own. OFL text included.
- PyInstaller is GPL-2.0-or-later **with a bootloader exception** that lets bundled apps use any license (Confirmed, D-022). Inno Setup has its own permissive license.
- **Transitive binaries to clear before release**: NVIDIA CUDA/cuBLAS/cuDNN runtime wheels (NVIDIA EULA redistribution terms, D-026), and PyAV/FFmpeg pulled in by faster-whisper (LGPL/GPL build flags, D-027; we never decode files, so we can probably exclude it from the bundle). QtAwesome bundles six icon fonts, including Codicons (CC-BY-4.0); we strip the unused ones from the build and keep Phosphor (MIT).
- Every model in the catalog carries its license. CC-BY models need attribution in an About → Licenses page (generated from the catalog + `pip-licenses`).
- Excluded: NLLB-200, SeamlessStreaming (CC-BY-NC), piper1-gpl (GPL), TranslateGemma (unreviewed), Hunyuan-MT (unspecified) (D-002). Also excluded: PyQt-Fluent-Widgets, PyQt-Frameless-Window, PyQt5/6 (GPL), Nuitka (AGPL-3.0). All three were fact-checked on 2026-10-17 (D-022).
- Every license is recorded in the DATA_TRACKER license register (D-022) and confirmed by `fact-checker` before the dependency is added.
- Benchmark datasets (e.g. FLEURS, CC-BY-4.0) are used locally for measurement only and never shipped (D-017).
- New dependencies are added to D-001 with their license before use.
- **As built:**
  - Installer and build exist (see §0 commands). The build strips `nvidia/*`, cuBLAS/cuDNN/cudart/NVRTC DLLs, PyAV (`av`, D-027: a stub keeps faster-whisper importable) and opencv's FFmpeg plugin (D-034); keeps only Phosphor of QtAwesome's fonts; copies `licenses/`, `THIRD_PARTY_LICENSES.md` (generated by `tools/third_party.py`) and `LICENSE.txt` (MIT). `tools/release_license_check.py` runs on every build (0 blocking, 0 warnings on 2026-10-20). App folder ~453 MB; setup ~130 MB.
  - Inno Setup 6.7.3 builds the setup (free for a free app; D-040). The NVIDIA cuBLAS wheel is downloaded by the wizard from NVIDIA's package (D-026, accepted).
  - Still open before a public release: Qt/PySide6 source hosting + written offer (D-021), D-027 review, D-011 consent note.

## 12. Milestone plan
| M | Name | Main output | Gate | Depends on |
|---|---|---|---|---|
| M01 | Foundation | **dev tooling (pre-commit + license gate)**, scaffold, tokens + palettes + fonts/icons, state models, Store, persistence, engine interfaces | (G1 part 1: palettes preview) | — |
| M02 | Floating window shell | widget kit + FloatingWindow + win32 helpers | **G1** | M01 |
| M03 | Engine benchmarks + spikes | harness, ASR + MT + diarization + VRAM tables, Discord RPC spike, defaults | **G4** | M01 |
| M04 | Audio + ASR pipeline | devices, capture, VAD, LocalAgreement, ASR worker, echo filter | — | M01, M03 |
| M05 | Translation pipeline | engines, router, cache, fan-out, MT worker, model catalog + downloader | — | M01, M03 |
| M06 | Translation view + transcript | ChatLine, view in window, transcript window, export, close dialog | **G2** | G1, M04, M05 |
| M07 | Settings, tray, first run | tray, Settings pages, wizard, Language Manager | **G3** | G1, M05 |
| M08 | Hotkeys + OCR | global hotkeys, region selector, OCR engines | **G5** | G1, M05 |
| M09 | Game mode + readout | presets, NVML metrics, HUD | — | M04, M05, M06 |
| M10 | Speaker identification | diarization worker, Discord RPC, fusion, calibration, splitting, rename UI, Speakers settings | **G6** | M03, M04, M06, M07 |
| M11 | MVP hardening | error paths, CPU fallback, end-to-end live tests, user guide, license/LGPL checklist | MVP sign-off | all |
Task details: `docs/tasks/Mxx-*.md`. Index: `TASKS.md`.

## 13. Open questions (Phase 1, for the user)
1. **Speaker names**: decided 2026-10-17 → day one. Fact-check: Discord's voice API is partner-only, so Discord names need the opt-in own-app setup (§5.13). Pending: user confirms this plan + the diarization default (sherpa-onnx vs diart).
2. **OCR auto-watch**: post-MVP. The MVP has one-shot + re-capture hotkey. (Accepted.)
3. **Default ~15 languages**: en, es, pt, fr, de, it, ru, uk, pl, tr, ar, hi, ja, ko, zh. (Default: this list.)
4. **Window opacity model**: separate background opacity (text stays crisp) + whole-window opacity. (Default: both.)
5. **Profiles and glossary**: post-MVP. (Default: yes.)
6. **Performance targets** in §8. (Default: accept as targets, revisit after M03.)

**Answered since** (2026-10-17 → 2026-10-19): Discord own-app plan + per-line TitaNet labels accepted (G4/G6 work); default language list kept, plus Vietnamese and 31 more in "other languages"; Qwen for Mandarin on by default with Simplified script; installer via Inno Setup with shortcuts unticked; D-026 NVIDIA download accepted; app licence MIT; everything on D:. Pending: Hugging Face account/username for the pack upload.
