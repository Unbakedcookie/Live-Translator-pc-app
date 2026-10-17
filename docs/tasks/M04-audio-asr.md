# M04 — Audio capture + streaming ASR

Goal: live "Me" and "Others" utterances (partial → final) into the Store. Spec: §5.2–5.4, §6.4. No UI. Lines show up in M06; until then they're checked with a debug console printer.

### T041 — Device enumeration · Tier A (+ Tier B smoke)
- Files: `livetranslator/services/audio/devices.py`, `tests/services/audio/test_devices.py`
- Depends on: T011
- Acceptance: lists inputs and loopback outputs with name + host API. `match(saved, available)` → exact, then name-only, then default (hand-made fixtures). The smoke run lists the user's real devices.

### T042 — Capture + resample · Tier A (+ Tier B smoke)
- Files: `services/audio/capture.py`, `services/audio/resample.py`, `tests/services/audio/test_resample.py`
- Depends on: T041
- Acceptance: resampling 48 kHz stereo → 16 kHz mono preserves a 1 kHz sine (frequency and amplitude within 1 %, hand-checked). Ring buffer wraps correctly. Device-lost → status + 2 s retry (simulated). Smoke: record 5 s of mic + loopback to scratchpad WAVs and listen-check.

### T043 — VAD segmenter · Tier A
- Files: `services/asr/vad.py`, `tests/services/asr/test_vad.py`
- Depends on: T042
- Acceptance: on synthetic signals (silence / speech WAV from the corpus / silence), utterance open/close times are within 1 frame of expected. ≥ 500 ms silence closes; the 15 s hard cut lands at the lowest-energy point (hand-built signal).

### T044 — LocalAgreement-2 policy · Tier A
- Files: `services/asr/local_agreement.py`, `tests/services/asr/test_local_agreement.py`
- Depends on: T016
- Acceptance: given scripted hypothesis sequences, committed/tentative outputs match hand-written expectations (including a word revision, punctuation differences, and a final flush).

### T045 — faster-whisper engine + ASR worker · Tier B (integration)
- Files: `services/asr/faster_whisper_engine.py`, `services/asr/worker.py`, `tests/services/asr/test_worker.py`
- Depends on: T043, T044, G4
- Acceptance: the worker serves 2 streams fairly (unit test with a fake engine: interleaving order as expected). Lazy model load off the main thread. Integration: playing a corpus clip through loopback produces partials then a final line with WER close to the M03 value. CUDA missing → CPU fallback path (forced by env var in a test).

### T046 — Echo duplicate filter · Tier A
- Files: `livetranslator/core/chatlog.py`, `tests/core/test_echo_filter.py`
- Depends on: T013
- Acceptance: hand-built utterance pairs: overlapping + similar → ME dropped; similar but 6 s apart → kept; overlapping but different → kept; threshold edge (ratio exactly 80) → dropped. Params come from config (D-010).
