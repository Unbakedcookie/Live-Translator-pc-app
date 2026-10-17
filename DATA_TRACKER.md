# DATA_TRACKER — unverified data, assumptions, licenses, thresholds

Status: **Unresolved** (unverified) · **Medium** (one source or indirect evidence) · **Resolved** (verified at a primary source, or by 2+ independent sources, or measured on the user's PC).
Surface the relevant items whenever work touches them, before any release, and periodically.

| ID | Item | Value / claim | Source | Status | Touches | Notes / next step |
|---|---|---|---|---|---|---|
| D-001 | Licenses of chosen components | faster-whisper MIT; whisper-large-v3-turbo MIT; SimulStreaming MIT; whisper_streaming MIT; CTranslate2 MIT; argos-translate MIT (code); MADLAD-400 Apache-2.0; opus-mt-ja-en Apache-2.0; Qwen3-4B-Instruct-2507 Apache-2.0; Kokoro (code + 82M weights) Apache-2.0; RapidOCR Apache-2.0; PaddleOCR Apache-2.0; PyAudioWPatch Apache-2.0 (LICENSE.txt); Virtual-Audio-Driver MIT; whisper.cpp MIT; m2m100 MIT | GitHub API `license.spdx_id`, HF API `cardData.license`, queried 2026-10-17 | Medium | packaging, every engine | Metadata is primary but is only one source. Transitive dependency licenses not yet checked. Each Opus-MT pair and each Argos language package has its own license; check every pack we ship or offer. |
| D-002 | Excluded (non-commercial / restrictive) | NLLB-200 cc-by-nc-4.0; seamless-streaming cc-by-nc-4.0; piper1-gpl GPL-3.0; TranslateGemma "gemma" terms; Hunyuan-MT-7B license unspecified | HF/GitHub API 2026-10-17 | Resolved (excluded) | MT/TTS choice | Exclusion is the safe direction. TranslateGemma could be re-evaluated if its terms are reviewed. |
| D-003 | Kokoro non-English phonemizer | May depend on espeak-ng (GPL-3.0) for some languages | Memory, unverified | Unresolved | voice-out (post-MVP) | Check before bundling TTS. |
| D-004 | Speed claims | faster-whisper "up to 4× faster" than openai/whisper; SimulStreaming "~5× faster" than WhisperStreaming; Kokoro "~100× real-time on GPU" | Project READMEs / vendor pages (self-reported) | Unresolved | ASR/MT/TTS defaults | Measure on the RTX 3060 in the benchmark milestone (`benchmarker`). |
| D-005 | VRAM budget | Assumed: Whisper turbo int8_float16 ≈ 1.5–2 GB; Qwen3-4B Q4 ≈ 3 GB; MADLAD-3B ct2 int8 ≈ 3–4 GB; must leave headroom for games | Memory estimates | Unresolved | Game mode, engine defaults | Measure with `nvidia-smi` during benchmarks. |
| D-006 | Pinned topmost window over "fullscreen" games | Assumed visible over borderless games and Win11 fullscreen-optimized games; not visible over true exclusive fullscreen | General Windows behavior, unverified per game | Unresolved | overlay/pin | Exclusive fullscreen scrapped for MVP. DX injection rejected (anti-cheat ban risk). Test with the user's games. |
| D-007 | Python 3.10 end of life | Oct 2026 | Memory | Medium | env | Irrelevant now: project uses 3.12.10. |
| D-008 | Download sizes | CUDA pip wheels ≈ 1–2 GB; models ≈ 1.5–4 GB total | Estimate | Unresolved | first-run UX, installer | Measure when installing. |
| D-009 | Windows OCR language coverage | Depends on installed Windows language packs | Memory | Unresolved | OCR | Check the API on the user's PC; fall back to RapidOCR. |
| D-010 | Echo duplicate-filter thresholds | Time window and similarity threshold not yet defined | — | Unresolved | chat log | Define in spec; tune with real tests. |
| D-011 | Transcribing other people (consent laws) | Mitigation: in-memory only, deleted on close, export offered, nothing uploaded | Not legal advice | Medium | chat log, release | Revisit before public release (add a disclosure/notice?). |
| D-012 | Virtual audio driver distribution | Unsigned kernel drivers won't load on Win11 without test-signing; distributing a driver needs signing | Memory | Unresolved | voice-out (post-MVP) | Investigate before voice-out milestone. |
| D-013 | Discord speaker names | RPC has `SPEAKING_START`/`SPEAKING_STOP` with `user_id` + `channel_id` (confirmed in discord-api-types / discord.js docs). Whether the `rpc` scope still requires approval or tester-listing is unverified. DAVE E2EE is mandatory for voice since 2026-03-01 (Discord blog + dev docs), so bots need DAVE support. | discord-api-types.dev, discord.js docs, discord.com blog, docs.discord.com | Resolved (blocked for zero-config) | speaker labels | **Fact-check 2026-10-17**: docs.discord.com OAuth2 + RPC pages say `rpc`/`rpc.voice.read` are "only available to approved partners". Unapproved apps: owner/team + max 50 testers, 10 guilds. No open approval process found. SPEAKING payload has `user_id` only; nick data via GET_SELECTED_VOICE_CHANNEL is unverified. Plan: opt-in own-app mode (§5.13). Live test in T036. |
| D-014 | Desktop geometry | **One** 5120×1440 super-ultrawide (Samsung Odyssey G95C), scale 100 % (devicePixelRatio 1.0), work area 5120×1392 (48 px taskbar). Corrected 2026-10-17: Phase 0 recorded "two 2560×1440 monitors" by inferring from the 5120 px virtual width | Qt `QGuiApplication.screens()` (T021) | Resolved | verifier, geometry, default placement | Code and tests still cover multi-monitor layouts for other users. Re-check if the setup changes. |
| D-015 | Latency / resource budgets | First partial ≤ 1.0 s; final translated line ≤ 1.5 s after speech end; app VRAM ≤ 6 GB (game mode ≤ 3 GB); CPU ≤ 25 % | Phase 1 targets (spec §8), not measured | Unresolved | M03, M09 | Measure in M03 and M09; revise with the user if unreachable. |
| D-016 | Silero VAD source | Assumed to be bundled as ONNX inside faster-whisper (MIT), so no torch/silero-vad dependency is needed | fact-checker 2026-10-17: faster-whisper 1.2.1 ships `faster_whisper/assets/silero_vad_v6.onnx`; snakers4/silero-vad repo is MIT | Medium | M04 T043 | The v6 model file's own license line was not read. Confirm when installing (T043). |
| D-017 | Benchmark datasets | google/fleurs is CC-BY-4.0 and not gated. Used locally for measurement only, never shipped or committed. Attribute it if results are published | HF datasets API (fact-checker 2026-10-17) | Medium | M03 | One source. Fine for local benchmarks. |
| D-018 | One vs two Whisper instances for two streams | Assumed one worker with a fair queue is enough at a 0.5 s update interval | Assumption | Unresolved | M03 T032, M04 T045 | Measure sustained decodes/s on the 3060. |
| D-019 | llama-cpp-python CUDA wheels on Windows | **Resolved 2026-10-17: no usable prebuilt.** The newest CUDA cp312 win wheel on abetlen's index is 0.3.4 (Dec 2024), which predates Qwen3 support; PyPI 0.3.36 would need MSVC + CUDA toolkit (not installed). **Alternative adopted for the benchmark:** official llama.cpp `llama-server.exe` release builds (MIT, tag b11714) as a localhost subprocess, in CUDA 12.4 and **Vulkan** flavours | abetlen wheel index listing (cu121–cu124), PyPI JSON, GitHub releases API | Resolved | M03 T033, M05 | If Qwen wins G4, ship llama-server as a subprocess; Vulkan avoids NVIDIA runtime DLLs (see D-026). |
| D-020 | Global hotkeys and anti-cheat | `RegisterHotKey` assumed safe; low-level keyboard hooks avoided because some anti-cheats flag them | General knowledge, unverified per game | Unresolved | M08 T081 | Test with the user's games; note any anti-cheat warnings. |
| D-021 | PySide6 / Qt license | PySide6/-Essentials/-Addons/shiboken6 6.12.0 = `LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only`. Shareable under LGPLv3 if we: use **Essentials only** (no GPL-only modules, e.g. Quick3D/VirtualKeyboard/Graphs/Charts/DataViz); package onedir with replaceable DLLs; ship LGPL+GPL texts + a notice; **host the matching Qt source ourselves** + a written offer (a qt.io link isn't enough); no reverse-engineering ban in our terms; scan the build for GPL-only DLLs | PyPI metadata ×4 (Confirmed), doc.qt.io/qt-6/lgpl.html, doc.qt.io/qt-6/licensing.html, Qt FAQ quoted on the pyside mailing list (fact-checker 2026-10-17) | Medium | packaging, T113 | "Onedir satisfies LGPL §4d" is an inference, and the Qt/PyInstaller deployment page is unread. Re-check at installer time. Contingency: swap the UI to wxPython (spec §11). |
| D-022 | **License register** (all planned dependencies) | See the "License register" table below | fact-checker 2026-10-17 (PyPI JSON, GitHub API/LICENSE, HF API) | Mixed (per row) | every dependency, license gate T010 | Rows marked Medium need a second source (usually reading the LICENSE file inside the installed wheel during T010/T011). |
| D-023 | diart maintenance/compat | Last release 0.9.2 (2025-02-12). Pins numpy < 2. Heavy dependencies (torch, torchvision, pandas, matplotlib, optuna, rx). README says Python 3.10–3.12 but PyPI says 3.8–3.10. Open issue about pyannote 4.0 | PyPI, GitHub issues (fact-checker) | Medium | T035, T102 | Benchmark only in a separate venv. Not the default engine. |
| D-024 | pyannote models gated | pyannote/segmentation, segmentation-3.0 and embedding are MIT but **gated** (HF account + terms + token). wespeaker-voxceleb-resnet34-LM is ungated but **CC-BY-4.0**. VoxCeleb training-data terms not reviewed | HF API (fact-checker) | Medium | diart, sherpa-onnx | Don't mirror the gated weights without checking the gate terms. sherpa-onnx re-hosts segmentation-3.0 as ONNX: verify that this redistribution is clean (D-029). |
| D-025 | Discord event vs audio lag | Unknown offset between SPEAKING_START and the loopback audio onset | — | Unresolved | T036, T101 | Measure over 20 events in T036. Calibrate at runtime. |
| D-026 | NVIDIA CUDA runtime redistribution | ctranslate2 needs the cuBLAS/cuDNN wheels, and torch CUDA (if used) bundles more. These fall under the NVIDIA EULA, not BSD/MIT | fact-checker red flag | Unresolved | packaging | Check NVIDIA's redistribution attachment before the installer. Option: download CUDA libs on first run instead of bundling. **Also:** llama.cpp's Vulkan build (30 MB) needs no NVIDIA runtime DLLs; if it's fast enough (T033), it sidesteps D-026 for the MT engine. ASR (ctranslate2) still needs cuBLAS/cuDNN. |
| D-027 | PyAV / FFmpeg via faster-whisper | `av` bundles FFmpeg, which may be an LGPL or GPL build | fact-checker red flag | Unresolved | packaging | We feed numpy audio and never decode files. Try to exclude `av` from the bundle, or verify that the wheel's FFmpeg is an LGPL build. |
| D-028 | Voiceprints are biometric data | Speaker embeddings can count as biometric data under GDPR, BIPA and similar laws | General knowledge, not legal advice | Medium | §5.13, release | Mitigation: memory only, never persisted or uploaded. Cross-session voice memory stays post-MVP and opt-in. Disclose in the privacy note. |
| D-029 | sherpa-onnx diarization models | sherpa-onnx assumed Apache-2.0. Segmentation-3.0 ONNX (MIT upstream). 3D-Speaker/WeSpeaker embeddings assumed Apache-2.0; NeMo TitaNet assumed CC-BY-4.0. Offline-only API, so streaming means sliding-window re-runs | fact-checker 2026-10-17: sherpa-onnx code Apache-2.0; pyannote/segmentation-3.0 MIT (HF-gated "auto"; get the ONNX from sherpa-onnx releases and ship the MIT notice ourselves); **Revai reverb-diarization = NON-COMMERCIAL (§3.2), excluded**; NVIDIA TitaNet-large CC-BY-4.0; 3D-Speaker and WeSpeaker weights: licences unverified (dataset-dependent); C API shows only OfflineSpeakerDiarization | Medium | T035, T102 | Shippable pair: **pyannote seg-3.0 (MIT) + TitaNet-large (CC-BY-4.0)**. Never reverb. 3D-Speaker/WeSpeaker only after their cards are read. Streaming = sliding-window re-runs (measure stability in T035). |
| D-031 | Argos Translate model packages | The `.argosmodel` zips (e.g. en_ja 1.1) contain **no licence file**. The README only credits training data (OPUS, CCAligned, WikiMatrix [CC-BY-SA], Wiktionary via Wiktextract) and bundles Stanza models (Apache-2.0). The weights' licence is unstated | Inspected en_ja.argosmodel 2026-10-17 (T033); fact-checker 2026-10-17: argos-translate / argos-train / argospm-index are MIT-or-CC0 for **code only**, no weights licence anywhere; WikiMatrix = CC-BY-SA 4.0 (OPUS page + HF), CCAligned = no licence | Unresolved → **treat as NOT shippable** | M03 T033, M05 | Benchmark proxy only. **Ship Helsinki-NLP Opus-MT instead**, converted to CTranslate2 ourselves: en→es/fr/ru/zh, es/fr/de/ja/ko→en Apache-2.0; en→de, ru→en, zh→en CC-BY-4.0; en→ja = `opus-mt-en-jap` (Apache-2.0); en→ko only `opus-mt-tc-big-en-ko` (CC-BY-4.0). gaudi/*-ctranslate2 tags say Apache even when upstream is CC-BY, so use the upstream licence. |
| D-030 | Discord token exchange without a secret | Public Client flag / PKCE may allow it (unofficial userdoccers wiki). Official docs show `client_secret` | fact-checker | Unresolved | T036 | Test in T036. Never commit or ship a secret (gitleaks). |

## License register (D-022)
Status: C = Confirmed (2 primary sources) · M = Medium (1 source, or a conflict that doesn't change the answer). "Ship" = included in the distributed app.

| Component | Ship | License | Status | Notes |
|---|---|---|---|---|
| PySide6-Essentials / shiboken6 6.12.0 | yes | LGPL-3.0-only (chosen option) | C | See D-021. The full `PySide6`/Addons package is never installed. |
| QtAwesome 1.4.2 | yes | MIT | C | Bundles FA 5/6 (OFL), Elusive (OFL), MDI (Apache-2.0), **Phosphor 1.3.0 (MIT)**, Remix (Apache-2.0), Codicons (CC-BY-4.0). Strip all but Phosphor from the build. **No Fluent icons.** |
| QtPy 2.4.3 | yes | MIT | M | |
| Phosphor icons | yes | MIT | C | Via QtAwesome. Keep the MIT notice. |
| Fluent UI System Icons | no | MIT | M | Not chosen (not in QtAwesome). |
| Inter 4.1 (Regular/Medium/SemiBold/Bold static TTF) | yes (bundled, `livetranslator/theme/fonts/`) | OFL-1.1 | C | GitHub API + the release's LICENSE.txt (bundled as `OFL-Inter.txt`). Source: github.com/rsms/inter v4.1 `Inter-4.1.zip` sha256 9883FDD4…B11E (T012). Can't sell the font alone. No Reserved Font Name line; unmodified. |
| Noto Sans 2.015 (Regular/Bold, hinted TTF) | yes (bundled) | OFL-1.1 | M | Release `OFL.txt` (bundled as `OFL-NotoSans.txt`). Source: notofonts/latin-greek-cyrillic `NotoSans-v2.015.zip` sha256 0C34DF07…58F5 (T012). One direct source. |
| Noto Sans CJK / script Noto fonts | yes (downloaded per pack, M05) | OFL-1.1 | M | The noto-cjk LICENSE file says OFL, but the GitHub API says null. CJK fonts are ~16 MB+ per weight, so download only the weights we use. |
| materialyoucolor 3.0.4 | yes | MIT | C | GitHub API MIT + the wheel's `dist-info/licenses/LICENSE` is the MIT text (read 2026-10-17, T012). Override in `tools/license_overrides.toml`. |
| pillow 13.0.0 (via materialyoucolor) | yes | MIT-CMU | M | Permissive; keep the copyright + permission notice. Read from the wheel's LICENSE (T012). Only used by materialyoucolor's image quantizer, which we don't call, so it could be excluded from the bundle later. |
| coloraide 8.13.1 | yes | MIT | C | |
| win32mica 3.0 | yes | MIT | C | |
| platformdirs 4.13.3 | yes | MIT | M | |
| loguru 0.7.3 | yes | MIT | C | Pulls in colorama + win32-setctime on Windows (rows below). |
| colorama 0.4.x (via loguru) | yes | BSD (classifier) | M | Found by the license gate (T011). Read the LICENSE file before release. |
| win32-setctime (via loguru) | yes | MIT (classifier) | M | Found by the license gate (T011). Read the LICENSE file before release. |
| huggingface_hub 2.2.0 | yes | Apache-2.0 | C | Include the license text. |
| lingua-language-detector 2.2.0 | yes | Apache-2.0 | C | Model size not yet checked. |
| pypresence 4.6.2 | yes | MIT | C | Maintained (released 2026-07-08). |
| numpy 2.5.4 | yes | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | M | Installed License-Expression (gate, T016); every component allowed. Keep the bundled third-party notices. |
| pydantic 2.14.1 | yes | MIT | C | GitHub API + installed License-Expression MIT (gate, T013). |
| pydantic-core, annotated-types, typing-inspection (via pydantic) | yes | MIT | M | License-Expression from installed metadata (gate, T013). |
| typing-extensions (via pydantic) | yes | PSF-2.0 | M | License-Expression (gate, T013). |
| rapidfuzz 3.14.6 | yes | MIT | C | |
| mss 10.2.0 | yes | MIT | C | |
| winrt-runtime / winrt-Windows.Media.Ocr 3.2.1 | yes | MIT | C | |
| nvidia-ml-py 13.615.71 | yes | BSD (clause count unverified) | M | Read the wheel's license file. |
| faster-whisper 1.2.1 | yes | MIT | C | Brings ctranslate2, onnxruntime and av (D-027). |
| Silero VAD v6 (bundled) | yes | MIT | M | D-016. |
| RapidOCR 3.10.0 + default PP-OCR models | yes | Apache-2.0 | C / M | Models per RapidOCR's MODEL_LICENSES.md only. Needs NOTICE + modification note. |
| diart 0.9.2 | optional / benchmark | MIT | C | D-023. Not in the default bundle. |
| pyannote.audio 4.0.7 | optional / benchmark | MIT | M | |
| torch 2.14.1 / torchaudio 2.11.0 | optional / benchmark | BSD-3 (+ third-party components) / BSD-2 | M / C | CUDA builds carry NVIDIA EULA parts (D-026). Not in the default bundle. |
| pyannote segmentation / segmentation-3.0 / embedding | optional | MIT, **gated** | M | D-024. |
| pyannote wespeaker-voxceleb-resnet34-LM | optional | CC-BY-4.0 | M | Attribution needed. |
| sherpa-onnx + diarization models | yes (planned) | Apache-2.0? / mixed | Unresolved | D-029. |
| faster-whisper 1.2.1 / ctranslate2 4.8.3 | yes (if chosen at G4) | MIT / MIT | C (faster-whisper) / M | Installed for T032. ctranslate2 from PyPI metadata; confirm when added to requirements.txt. |
| nvidia-cublas-cu12 12.9 / nvidia-cudnn-cu12 9.27 | benchmark now; ship TBD | NVIDIA EULA | Unresolved | D-026. |
| onnxruntime 1.31 / av 19.0.1 (via faster-whisper) | transitive | MIT / BSD + FFmpeg (LGPL/GPL build?) | M / Unresolved | D-027 for av. |
| sentencepiece 0.2.2 | yes (if an SP-based MT engine wins) | Apache-2.0 | M | Installed for T033. |
| MADLAD-400 3B ct2 int8 (Nextcloud-AI, rev aa32bbde) | model, if chosen | Apache-2.0 | M | HF API cardData; upstream google/madlad400-3b-mt is Apache-2.0 as well, so 2 sources: C once the Nextcloud card is read. |
| Qwen3-4B-Instruct-2507 GGUF Q4_K_M (unsloth, rev a06e946b) | model, if chosen | Apache-2.0 | M | HF API cardData; upstream Qwen repo is Apache-2.0 too. |
| llama.cpp llama-server b11714 (CUDA 12.4 / Vulkan builds) | binary, if Qwen chosen | MIT | M | GitHub API. The CUDA build's cudart zip = NVIDIA DLLs (D-026). |
| Argos Translate packages | benchmark only | **none stated** | Unresolved | D-031. |
| PyInstaller 6.22.3 | build | GPL-2.0-or-later WITH Bootloader-exception | C | The exception allows any license for the bundled app. |
| Inno Setup | build | Inno Setup License (permissive, custom) | M | Free for commercial use. |
| pre-commit, gitleaks, ruff, pip-licenses, pytest, pytest-qt | dev | MIT | M | |
| bandit, pip-audit, jiwer, sacrebleu | dev | Apache-2.0 | M | |
| pyright / basedpyright | dev | MIT (GitHub shows NOASSERTION) | M | Read the LICENSE file. |
| google/fleurs | benchmark data | CC-BY-4.0 | M | D-017. |
| PyQt-Fluent-Widgets | **excluded** | GPL-3.0 | M | |
| PyQt-Frameless-Window | **excluded** | GPL-3.0 | M | |
| Nuitka | **excluded** | AGPL-3.0 | M | |
