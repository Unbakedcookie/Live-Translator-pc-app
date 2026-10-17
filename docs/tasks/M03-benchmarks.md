# M03 — Engine benchmarks (approval gate G4)

Goal: measure, then choose default ASR/MT engines and game-mode presets on the user's RTX 3060. Spec: §5.4, §5.5, §8. Independent of UI, so it can run while G1 waits.
Delegate runs to `benchmarker`. ASR/MT word-error metrics use **jiwer**. Resolves or updates D-004, D-005, D-015, D-018, D-019, D-023–D-025, D-029, D-030.

### T031 — Benchmark corpus + harness · Tier A
- Files: `benchmarks/corpus.py`, `benchmarks/harness.py`, `benchmarks/README.md`, `tests/benchmarks/test_metrics.py`
- Depends on: T016
- Acceptance: downloads a small FLEURS subset (en, es, ja, ko, zh, ru, de, fr; about 20 utterances each) into `D:\LiveTranslator\bench-data` (outside the repo; D-017). WER/CER (jiwer) and chrF (sacrebleu) are computed; metric code is checked against 2 hand-computed examples. Measures latency p50/p95 and peak VRAM (NVML).

### T032 — ASR benchmark · Tier A (measured)
- Files: `benchmarks/asr_bench.py`, `benchmarks/results/asr.md`
- Depends on: T031
- Acceptance: table for faster-whisper large-v3-turbo (float16, int8_float16), a smaller config for game mode/CPU, and Parakeet TDT v3 (sherpa-onnx, European languages only). Columns: WER/CER per language, latency for 2 s/5 s/10 s buffers, VRAM. Also runs the LocalAgreement update loop at 0.5 s and 1.0 s (decodes per second sustained) and 1 vs 2 model instances serving 2 streams.

### T033 — MT benchmark · Tier A (measured)
- Files: `benchmarks/mt_bench.py`, `benchmarks/results/mt.md`
- Depends on: T031
- Acceptance: Opus-MT/Argos (ct2, direct + pivot via en), MADLAD-400 3B (ct2 int8), Qwen3-4B-Instruct Q4 (llama.cpp). Columns: chrF per pair (en↔es, en↔ja, en↔ko, en↔zh, en↔ru, ja→ko pivot), latency p50/p95 for a sentence, VRAM, disk size, license per model file. Install problems (e.g. the llama-cpp-python CUDA wheel, D-019) are recorded.

### T035 — Diarization benchmark (sherpa-onnx vs diart) · Tier A (measured)
- Files: `benchmarks/diar_bench.py`, `benchmarks/results/diarization.md`, `benchmarks/README.md` (setup notes)
- Depends on: T031
- Acceptance:
  - **Test material**: 2-, 3- and 4-speaker mixes built from FLEURS clips with known speaker turns (the ground truth comes from construction). Includes one back-to-back turn with no pause.
  - **sherpa-onnx**: sliding window (10 s window, 1 s hop) with centroid matching for stable ids.
  - **diart**: run in a **separate throwaway venv** (numpy < 2 pin), with gated models via the developer's own HF token. Never added to `requirements.txt`.
  - **Table**: DER (pyannote.metrics or our own, checked against a hand-computed toy case), label-switch rate, latency to a stable label, VRAM/CPU, install size, zero-config yes/no.
  - **Licenses**: each embedding/segmentation model's license verified (D-029).
  - **Outcome**: a recommendation for G4.

### T036 — Discord RPC spike · Tier B
- Files: `benchmarks/discord_rpc_spike.py`, `benchmarks/results/discord_rpc.md`
- Depends on: T011
- Acceptance: with the user's own Discord application (owner = user, no secret committed; gitleaks passes):
  1. pypresence `authorize` → token exchange. Try Public Client + PKCE first and record whether a secret is required (D-030).
  2. `GET_SELECTED_VOICE_CHANNEL` returns member nicks/global names.
  3. `SPEAKING_START`/`STOP` arrive for *other* members in a real call. Measure the event-vs-loopback-audio lag over 20 events (D-025).
  4. Write the own-app setup steps with screenshots for the wizard.
  - A spike result of "blocked" is a valid outcome. Record it and fall back to voice labels.

### T034 — Recommendation + G4 decision · Tier A
- Files: `benchmarks/results/summary.md`, `project-spec.md` §5.4/§5.5/§5.10/§5.13/§8 updated, `DATA_TRACKER.md`
- Depends on: T032, T033, T035, T036
- Acceptance: the user is shown a 1-screen comparison with a recommended default for normal mode + game mode + CPU fallback. The user's choice is recorded. DATA_TRACKER items are updated with measured values.
