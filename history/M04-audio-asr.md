# M04 — Audio capture + streaming ASR · history

## 2026-10-17 — pure-logic tasks pulled forward (user away; autonomous)
I did these while the GPU ran the M03 benchmarks and the desktop was in use by the verifier. Both depend only on finished tasks (T016, T013).

### T044 — LocalAgreement-n (`services/asr/local_agreement.py`)
- **How it works.** Every update feeds the hypothesis for the whole utterance buffer (Whisper re-decodes from the utterance start). Words that start before the last committed word's end, minus 80 ms of timestamp jitter, are skipped. A word is committed when the last n hypotheses agree on it at the same position.
- **Matching rule.** Agreement uses NFKC + casefold + no punctuation/whitespace, so "Hello," equals "hello". The newest hypothesis's spelling is kept.
- **Committed words are never revoked.** `finalize()` commits the final decode's remainder. Words are joined by concatenation because Whisper words carry their own leading spaces, which keeps CJK correct without spaces.
- **Bug caught by my own n=3 test:** while warming up (fewer than n hypotheses), the history update dropped older tails, so 3-way agreement never formed. Fix: re-base all tails and keep the newest n−1. n=2 (the default) was unaffected.
- **Lint:** E741 on a test constant named `I`, renamed to `W_I` with a targeted regex so the "I think" strings stayed intact.
- **Verification:** 8 scripted-hypothesis tests:
  - first update commits nothing;
  - common prefix, then skip-by-timestamp on re-decode;
  - revised word stays tentative;
  - punctuation/case agreement;
  - never revoke;
  - finalize + reset;
  - CJK join with punctuation-only token ignored;
  - n=3 warm-up.

### T046 — Echo duplicate filter (`core/chatlog.py`)
- **Rule.** A final "Me" line is an echo when an "Others" line overlaps it within ±window_s (an open line uses its start) and rapidfuzz `token_set_ratio` (default_process: case/punctuation-insensitive) ≥ min_ratio. Defaults are 4 s / 80 from EchoFilterConfig.
- **New dependency.** rapidfuzz 3.14.6 (MIT) is now a runtime dependency. The license gate passed: 20 runtime packages, 0 violations.
- **Verification:** 7 tests:
  - hand-computed Indel similarity "abcd" vs "abcdef" = 80.0, used for the exact-threshold case (dropped at 80, kept at 80.5);
  - overlapping + similar → dropped;
  - same text 6 s apart → kept;
  - overlapping but different → kept;
  - partial Me and Screen lines are never judged;
  - open Others line uses its start.
- D-010 still Unresolved: the thresholds get tuned with real audio in T045.

### T041 — Device enumeration (`services/audio/devices.py`)
- **What it does.** `list_devices()` returns WASAPI inputs, WASAPI loopbacks and both defaults, via PyAudioWPatch (Apache-2.0, now a runtime dependency; license file + classifier read, gate 21/0).
- **Matching** (`match()`): exact name + host API first, then the "stable" name (USB-port number like "(3- " and the " [Loopback]" suffix removed, casefolded), then the Windows default. A loopback is saved under its output device's own name, so the Settings choice "Headphones (A50 Game)" maps back to its loopback.
- **Real devices found on the user's PC** (the fixtures use these names):
  - Astro A50 with separate **Game** and **Voice** outputs (default output = A50 Voice), plus an A50 Mic.
  - NexiGo webcam mic; Steam Streaming virtual devices; Odyssey G95C HDMI audio; Realtek S/PDIF.
- **User benefit to point out:** if Discord outputs to A50 Voice and games to A50 Game, capturing the A50 Voice loopback gives Discord-only "Others" audio without game sound. That's a hardware stand-in for the post-MVP per-app capture.
- **Verification:** 7 Tier A matching tests:
  - stable name;
  - default follow;
  - exact wins;
  - replugged port "(4- A50 Mic)" → "(3- A50 Mic)";
  - missing → default / None;
  - loopback ref round trip;
  - exact preferred over a stable duplicate.
  - Plus a live listing smoke test on this PC: inputs and loopbacks present, flags consistent, both defaults found.

### T042 — Capture + resample (`services/audio/{resample,ring,capture}.py`)
- **Resampler.**
  - `StreamResampler`: downmix to mono → Blackman windowed-sinc low-pass (101 taps, cutoff 0.45 × 16 kHz = 7.2 kHz) → linear interpolation at in_rate/16000 steps.
  - Filter history and fractional position carry across chunks. Works for any input rate (48 kHz and 44.1 kHz on this PC).
  - Uses numpy only, avoiding scipy (+~40 MB) and python-soxr (LGPL).
- **Ring buffer.** `RingBuffer`: 60 s by default, absolute sample indices, `read(start, end)` skips overwritten data, thread-safe.
- **Capture worker.** `AudioCapture`:
  - A PyAudioWPatch float32 callback stream on its own thread; bytes → resampler → ring → optional on_audio.
  - A missing device or a stream that stops reports a plain-language WARNING ("… isn't available. Reconnecting…" / "… stopped. Reconnecting…"), retries every 2 s, then reports OK "Listening to …".
  - Stream opening is injectable, so recovery is tested without hardware.
- **Noted:** WASAPI loopback sends no packets while nothing plays, so "Others" silence means no data rather than an error.
- **Verification:**
  - 6 resample/ring tests: 1 kHz sine at 48 k and 44.1 k stereo in odd chunk sizes → 32000 ±1 samples for 2 s, frequency within 1 %, amplitude 0.5 within 1 %; chunked == one-shot to 1e-6; a 12 kHz tone is suppressed below 0.01 (no aliasing); downmix, FIR sum 1, odd-tap guard; ring wrap / absolute reads hand-traced.
  - 3 capture tests: 1 s of 48 k stereo → 16000 ±1 samples; open failure, then stream death, then recovery gives the exact status sequence and every stream is closed.
  - A **live smoke test** on the user's default mic (A50): about 1.2 s of capture, more than 8000 samples arrived. Counted only, nothing stored.
- **Deferred (needs the user present):** the acceptance's "record 5 s of mic + loopback to scratchpad WAVs and listen-check". I didn't record the user's room or Discord audio while they were away.

### T043 — VAD segmenter (`services/asr/vad.py`)
- **D-016 confirmed in practice.** faster-whisper 1.2.1 ships `assets/silero_vad_v6.onnx`. Its `SileroVADModel` runs whole recordings in a batch, so I wrote a **streaming** wrapper (`SileroVad`): one 512-sample frame (32 ms) plus 64 samples of context per call, carrying the h/c state. It runs on CPU via onnxruntime (single thread).
- **`Segmenter` (pure).**
  - Opens at p ≥ threshold (0.5), backed up by a 3-frame pre-roll.
  - Releases below threshold − 0.15 (hysteresis).
  - Closes after ceil(end_silence_ms / 32) = 16 silent frames, at the frame after the last speech frame.
  - Hard cut at ceil(max_utterance_s × 1000 / 32) = 469 frames, at the lowest-energy frame within the last 63 frames (2 s), then reopens there.
  - `flush()` closes at the end of the stream.
- **New `VadConfig` section** in AppConfig (threshold, end_silence_ms, max_utterance_s) for the spec's Advanced settings. "vad" was added to the UpdateConfigSection literals. Old settings files load unchanged because the field has defaults.
- **Verification:**
  - 9 tests:
    - frame math (16 / 469 / 63);
    - silence-speech-silence → open 17, close 70;
    - a 15-frame pause doesn't split;
    - hysteresis keeps a p = 0.4 stretch open;
    - flush;
    - hard cut at the planted quietest frame 450 (close and reopen at 450), then the silence close at 469;
    - custom config;
    - frame energy;
    - **real Silero on a FLEURS clip** padded with 1 s of silence each side: no speech probability ≥ 0.5 in the padding, the first open is not inside the padding, and the final close is by silence within the trailing second.
- **Flaky test found and fixed.** The T042 live mic smoke failed once in the full suite while the ASR benchmark's CPU config saturated the cores; it passes alone. Cause: a fixed 1.2 s sleep; the device open was slower under load. Fix: poll up to 5 s for ≥ 0.5 s of samples.

## 2026-10-17 — T045 faster-whisper engine + ASR worker + app wiring (commit fde9494; user away)
- **Engine (`FasterWhisperEngine`):**
  - Pinned CT2 conversions are downloaded once into the app models folder via huggingface_hub: turbo for GPU (int8_float16), small for CPU (int8).
  - On "auto" it proves the GPU with a 1 s warm-up decode, because cuBLAS only loads at the first decode. Any failure falls back to CPU, and the reason is kept.
  - Partials decode greedily at temperature 0; finals use beam 5 with fallback.
  - The ASR contract gained `final: bool`.
- **PyAV licensing (D-027 resolved):**
  - Local inspection: `avutil_license()` reports LGPLv3, but the wheel bundles `libx264` and `libx265` DLLs.
  - The fact-checker found that pyav-ffmpeg patches FFmpeg's configure to move x264/x265 out of the GPL list. In substance the wheel is GPL-encumbered.
  - faster-whisper only uses `av` to decode files, so `ensure_av_importable()` installs a stand-in module when av is absent.
  - The licence gate gained an `[excluded]` table (`av = "D-027"`, tested). It passes 40 packages and lists av as "excl". The packaging step (T113) must strip it.
  - Also added protobuf's "3-Clause BSD License" spelling as an alias.
- **Worker design fork:** the spec's separate VAD thread is folded into the ASR thread.
  - VAD costs about 0.1 ms per frame and lags by at most one decode (~0.4 s). One thread keeps the ordering deterministic.
  - Each step runs VAD on all streams, then exactly one decode. Finals go first, oldest first. Otherwise the least recently served stream with at least one interval of new audio goes next, and Others wins ties.
  - Under GPU overload every stream is simply decoded less often. The benchmark showed 2 streams at a 0.5 s interval don't fit, so this degradation matters.
  - The Others language locks once detection probability reaches 0.7.
  - Times are estimated when audio is read, because WASAPI loopback sends nothing during silence.
- **SpeechController:**
  - Devices are matched by saved name, falling back to the Windows default.
  - The fallback warning has its own status key: a test showed the capture's "Listening to…" status was overwriting it.
  - The mic is closed while muted.
  - The echo filter (T046) runs on the main thread and works whichever line finishes first.
- **Integration run setup:** real VAD, the real model on GPU, and the store, fed FLEURS clips in 0.25 s chunks "in real time".
- **First pass:** en WER 7.4%, es 3.0%, ja CER **21%**. Reading the output lines turned up two bugs.
  1. **"cornered the the inmates":**
     - Cause: LocalAgreement's 80 ms boundary tolerance took a committed word a second time after its timestamp shifted in the final decode.
     - Fix: drop a tail prefix that equals the last committed words *and* overlaps them in time. A genuine "very very" starts later and is kept.
     - Covered by 2 tests with hand-computed values.
  2. **A Japanese sentence lost its opening, "まもなく暴動鎮圧用の装備を着用した警":**
     - Traced call by call: the utterance itself opened about 2.6 s late, yet the same clip on its own is detected from frame 43.
     - Our SileroVad wrapper matches faster-whisper's own batched call exactly (max diff 0.0), so this is how the model behaves when its recurrent state carries over.
     - After a long utterance plus silence, the model stayed under 0.04 for more than 4 s of speech. faster-whisper never sees this because it resets for every file.
     - Fix: `vad.reset()` whenever an utterance closes on silence.
     - Verified on 4-clip streams in ja/en/es/zh: onsets now land on the real speech start (ja 18.05 s vs 18.08 s true; en 0.5–1 s earlier than before).
- **Second pass (5 clips × 5 languages):**

  | Language | Error rate | Benchmark |
  |---|---|---|
  | en | 5.4% | 5.9% |
  | es | 3.7% | 3.2% |
  | de | 1.0% | 5.3% |
  | ja | **4.6%** | 3.4% |
  | zh | 17.7% | 14.2% |

  - Partial p50 318 ms, final p50 407 ms.
  - zh is weaker because Whisper mixes in Traditional characters (聯合). A possible later fix is a Simplified-Chinese initial prompt.
- **Model load:** the first load took 66 s from a cold disk; warm loads take 4.9–5.1 s.
- **Live Tier B check:**
  - Setup: scratch profile, mic muted, loopback of the Windows default output. FLEURS es and ja clips were played with System.Media.SoundPlayer.
  - Result: translated English lines appeared in the overlay. The Spanish line was correct.
  - The Japanese line carried the ASR error 基金→危機 into the translation ("crisis").
- **Not verified yet:**
  - Two real streams at once (mic + loopback) on live audio.
  - Long sessions (ring/VAD drift over hours).
  - The CPU fallback on a PC without a GPU. It was only forced through the unit tests' fake engine.

## 2026-10-18 — Crash at start with mic + speakers both on (fixed)
- **Found when relaunching the user's app** (real profile: mic and speakers both enabled): the process died seconds after start with `Assertion failed: hostApi->info.defaultInputDevice < hostApi->info.deviceCount (pa_front.c)` + an access violation (`python -X faulthandler`).
- **Cause:** PortAudio's `Pa_Initialize`/`Pa_Terminate` aren't thread-safe. The device list and each capture stream create and terminate their own `PyAudio()`, and with both streams on, the two capture threads did it at the same moment. All my test runs had the mic muted (one capture), which is why it never showed. The code review the night before had flagged "overlapping PyAudio init/terminate" as a risk.
- **Fix:** one `PORTAUDIO_LOCK` (RLock) around every PortAudio start/open and stop/close/terminate (`devices.list_devices`, `capture._PyAudioStream`). Audio callbacks don't take it.
- **Verified:** 3 of 3 starts with the user's real settings stay up (window listed after 12 s, no assertion in the logs); full suite 536 passed.

## 2026-10-18 — One Chinese script for Mandarin (Mandarin follow-up)
- The T045 live check saw Whisper write some Mandarin lines in Traditional characters (mixed with Simplified). Offline, on 150 FLEURS clips, it never did — so it's an occasional live drift, but mixed scripts in one conversation look broken.
- **Fix:** `services/asr/chinese.py` converts recognised Chinese (partials and finals) with OpenCC (Apache-2.0, D-036) to the script chosen in Settings → General → "Chinese characters": **Simplified (default)** or Traditional (Taiwan standard). Applied at publish time in the ASR worker, so the agreement logic still works on Whisper's raw words; non-Chinese text is untouched. The setting is pushed to the worker live.
- Tests: conversion both ways + untouched ASCII; a fake Whisper emitting Traditional (or Simplified) characters → every partial and the final come out in the chosen script; Settings round trip. Suite 552 passed.

## 2026-10-19 — "I speak" separate from "Translate into" (user request 2026-10-18)
- User: "we should separate my language to be recognized and the translation to language. sometimes I speak another language and I want my English translation to see if I'm correct." Also the earlier "small issue when one person is swapping between 2 languages".
- Before: the mic was always decoded in `my_language` (forced), so Spanish practice was transcribed as (bad) English and never translated.
- Now `AudioConfig.mic_languages`: () = the language you translate into (unchanged default), ("auto",) = detect any (locks like Others at p >= 0.7), or 1-3 codes. With 2+, `ASRWorker._detect_me` asks the engine for the likeliest of *those* (`FasterWhisperEngine.detect_language` → (code, share of the candidates' probability)); re-checked on each partial until sure, and always once more on the whole line before the final decode. Own lines then carry their real language, so translation turns a Spanish line into the window's English.
- Measured on FLEURS (20 clips each, leading silence trimmed — the first run without trimming showed a fake English bias because Whisper says "en" for silence): constrained ≥ free detection everywhere; es/en 19-20/20 from 0.6 s, zh/en 18-19/20, ja/en 13-15/20 under 1.5 s, all 80/80 on whole lines. Lock rule chosen from the data: share ≥ 0.97 and ≥ 1.0 s → 63/64 right (one zh clip). The final re-check makes the final text right even then.
- Settings → General: "Translate into" (was "My language"), "I speak" (Same as above / Detect any language / a language), "I also speak" (Nothing else / a language; disabled for "any"). `mic_languages_for` / `mic_choice` map the two combos to the saved tuple (tested both ways); config validation (≤ 3, no duplicates, "auto" alone).
- Tests: worker (two languages: detection among them, stops when sure, final re-check, decode language; any language locks), validation, resolver, settings page, real Whisper detection on FLEURS. Suite 651.
