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
