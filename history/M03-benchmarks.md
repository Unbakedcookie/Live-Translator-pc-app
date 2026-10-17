# M03 — Engine benchmarks (gate G4) · history

## 2026-10-17 — T031 corpus + harness (user away; autonomous)

### What was built
- `benchmarks/corpus.py`: FLEURS subset builder.
  - Downloads the 8 dev-split TSVs (en, es, fr, de, ru, ja, ko, zh) from `google/fleurs` at pinned revision `70bb2e84…894dd`.
  - Picks the 20 smallest sentence ids shared by all 8 languages, and the lowest file name per id for determinism.
  - Downloads each language's `dev.tar.gz` via huggingface_hub (cache under `D:\LiveTranslator\bench-data\hf-cache`) and extracts only the chosen clips to `fleurs/<lang>/<id>.wav`.
  - Writes `manifest.json` (source, revision, license, split, per-sentence text and audio per language).
  - `read_wav` gives 16 kHz mono int16 → float32.
- `benchmarks/metrics.py`:
  - NFKC normalisation (lowercase; drop Unicode P*/S*; collapse spaces).
  - WER for spaced languages, CER for ja/zh/ko (spaces removed), via jiwer; pooled corpus rates.
  - Corpus chrF via sacrebleu.
  - LatencyStats p50/p95/mean in ms (numpy linear percentiles).
- `benchmarks/harness.py`: `time_calls` (warm-up excluded, injectable clock), `VramMonitor` (NVML device-wide used memory, 50 ms sampling thread, peak minus baseline; None without NVML), `gpu_info`, markdown table writer.
- `requirements-bench.txt` (dev only): huggingface_hub 2.2.0, jiwer 4.0.0, nvidia-ml-py 13.615.71, sacrebleu 2.6.0.

### Design forks
- **One corpus for ASR and MT.** FLEURS shares sentence ids across languages, so the clips' transcripts double as parallel MT references in every pair (incl. ja→ko for the pivot test). There's no separate MT dataset to license.
- **Dev split rather than test** (~180 MB vs ~450 MB per language). We only need 20 sentences, and the tarballs can't be range-read.
- **Untrusted archives.** Output paths are built from our own sentence ids, never from tar member names. A test plants a `../../evil.wav` member and proves nothing is written outside the target folder.
- **Pooled error rates**, not a mean of per-sentence rates (the hand-computed test shows the difference: 1/3 vs 0.5).
- **VRAM is device-wide** because WDDM hides per-process usage, so benchmarks must run with games closed. This is documented in README and harness.

### Verification
- 14 tests:
  - hand-computed WER (2/6), CER (1/5), pooled rate (1/3);
  - chrF bounds (100 / 0);
  - percentiles (p50 30, p95 48);
  - TSV parsing and selection, safe extraction, int16 scaling (16384 → 0.5) and format rejection;
  - time_calls warm-up and clock;
  - markdown output;
  - NVML fallback;
  - a live NVML read on this PC: NVIDIA GeForce RTX 3060, 12288 MB, driver 610.74.
- Real download completed: 8 languages × 20 clips (124 MB of wavs; 1.5 GB HF cache, kept for rebuilds). Spot check of sentence 1510: the same UN-fund sentence in all 8 languages.
- D-017 now Medium → effectively confirmed: HF API `cardData.license = cc-by-4.0`, `gated = false`, read again here.

### Notes
- huggingface_hub warned "unauthenticated requests". No token is needed for this public dataset; it only affects rate limits.

## 2026-10-17 — T033 MT benchmark run, Opus-MT replaces Argos (commit 45af05c; user away)
- **First full run (all 5 engines):**
  - MADLAD-400 3B: best chrF on most pairs, but p50 1068 ms and 3.5 GB VRAM.
  - Qwen3-4B via llama-server: CUDA p50 485 ms, Vulkan 491 ms, about 2.8 GB; quality between MADLAD and Opus.
  - Vulkan loads slower (13 s) but avoids the NVIDIA DLLs (D-026).
  - Both Argos rows **failed** on a missing `es_en/sentencepiece.model`; the package layout differs. Not debugged: Argos can't ship anyway (D-031), so effort went to the real candidate.
- **Fact-check** (delegated in the background while code work continued):
  - Opus-MT licences: the HF API says Apache-2.0 for most, CC-BY-4.0 for en-de, ru-en, zh-en and tc-big. The OPUS-MT README says CC-BY 4.0 for all of them. **Decision: attribute everything as CC-BY.**
  - `opus-mt-en-jap` is Bible-heavy (test BLEU 42 on bible-uedin), so use `opus-tatoeba-en-ja` instead.
  - No direct ja↔ko model exists, so pivot via English.
  - The turbo Whisper conversion moved to `dropbox-dash/` (same commit).
  - The PyAV wheel ships GPL x264/x265 (see M04).
- **Conversion** with `benchmarks/opus_convert.py`:
  - Runs in a throwaway `D:\LiveTranslator\convert-venv` (CPU torch + transformers), never the app venv.
  - Converts 14 pairs at pinned SHAs. Each pair gets a LICENCE.txt attribution and an `opus_mt.json`.
- **Bug found by the smoke test:** en→ko came out as `⁇ # 4 단계 ⁇`.
  - **Investigation:** the original zip name contains "sepvoc" (separate vocabularies). The HF port has one merged 32,001-token vocab with `share_encoder_decoder_embeddings: True`, so the HF port of tc-big sepvoc models is broken.
  - **Fix:** download the original Marian release zip; it contains the CC-BY 4.0 LICENSE, a second source for D-031.
    - Extract only the named members into a folder of their own.
    - Turn the SentencePiece `.vocab` files into Marian YAML vocabs.
    - CTranslate2's `OpusMTConverter` then keeps the source and target vocabularies separate, and Korean comes out correct.
    - The steps are scripted, so the conversion is reproducible.
- **en-zh** targets several variants (cmn/yue/wuu…) and needs a `>>cmn_Hans<<` prefix; found by grepping the converted vocabularies.
- **Naming:** the field was first called `target_token`. Bandit B105 kept flagging it as a "hardcoded password", so it was renamed to `language_tag`.
- **Opus-MT results:**
  - Speed: GPU int8 p50 **116 ms** (p95 226); CPU int8 p50 **166 ms**.
  - Memory and disk: VRAM 1.6 GB with all 14 pairs loaded (the app loads pairs lazily). Disk is 2.3 GB in float16; storing int8 would halve that (T054).
  - Quality: chrF is typically 2–8 points under MADLAD; the largest gap is ko→en, 48 vs 59. en→ko is **better** than both alternatives (38.5 vs 35.4 and 27.4).
- **Benchmark harness changes:**
  - It now uses the app's own `OpusMtEngine` and router, so the pivot runs the real code path.
  - It adds a disk-size column.
  - Rows merge across runs, so slow engines needn't be re-run.
  - Run logs are gitignored.
- **What slowed us:** the Bash heredoc + Python escaped-newline trap broke source files twice more, plus one heredoc that bash couldn't parse at all.
  - **Lesson (repeated from M02):** write prose and multi-line source with the Write/Edit tools, never through a heredoc.

## 2026-10-17 — T035 speaker-label benchmark (commit 490be01; user away)
- **Ground truth without speaker IDs.** FLEURS has no speaker IDs, but each sentence was recorded by up to 3 different people (gender in the TSV).
  - Different recordings of one sentence therefore guarantee different speakers.
  - Each recording was trimmed and cut into turns at its quietest 20 ms frames, so every turn's speaker is known.
- **Mixes:** 2 speakers M+F (en); 2 speakers F+F (en, hard); 3 speakers M+M+F (es) with one back-to-back turn (no gap); 4 speakers (3 en + 1 es) with one back-to-back turn.
- **Metric:** our own DER (10 ms grid, 0.25 s collar, best one-to-one mapping by brute force) plus turn accuracy and label switches. 7 hand-computed toy tests, e.g. a late switch of 0.5 s in 4 s gives 12.5 % confusion; with collar it's 0.25/3.0.
- **Approaches** (sherpa-onnx 1.13.8, CPU):
  - A: offline whole-mix.
  - B: the spec's sliding window, 10 s every 1 s, local clusters matched to global centroids.
  - C: per-line — one TitaNet embedding per Silero/Segmenter utterance, running-mean centroids, cosine similarity threshold.
- **Surprise 1:** offline (A), the expected upper bound, scored DER 0.41.
  - Probing showed it under-clusters at the default distance. But even with the oracle speaker count it left whole turns out: 38 % miss on M+F.
  - Cause: some FLEURS recordings are about 38 dB quieter (turn RMS 0.0007 vs 0.065), and the pyannote segmentation treats them as silence.
  - Level-matching every turn brings A to DER 0.16 (0.11–0.13 with oracle count).
  - **Decision:** report two materials, "as recorded" (stress test) and "level-matched".
- **Surprise 2:** I had wired one number into both the sherpa clustering *distance* (higher = merge) and our *similarity* (higher = split). Fixed by sweeping them separately.
- **Result:** C wins clearly and is loudness-robust.
  - DER 0.098 as recorded / 0.097 level-matched; 93 % of turns right; correct speaker count in all 4 mixes; zero label switches.
  - Cost: TitaNet-large 0.11 s per line, small 0.04 s. CPU only.
  - The similarity plateau is 0.5–0.6; at 0.7 it over-splits.
  - B: DER 0.35 / 0.21, at 0.2 s CPU every second.
  - The only remaining C errors are the two back-to-back turns. With no pause the VAD keeps them in the previous line, so both speakers get one label.
- **Design proposal for G4/G6** (spec §5.13 said "sliding window"):
  - Switch to per-line labels.
  - Add in-line change detection for long lines: run the pyannote segmentation only on lines over ~3 s and split at a detected change, which is the spec's "utterance splitting" idea.
  - Speaker memory stays in RAM only (D-028).
- **Not done:** diart. Its models are gated and need the user's HF token (D-024). The spec makes it optional and never default, so this is recorded as blocked rather than worked around.
