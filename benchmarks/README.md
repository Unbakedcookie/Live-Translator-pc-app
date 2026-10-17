# Benchmarks (M03, dev only)

Measure speech-recognition, translation and speaker-diarization engines on this PC (RTX 3060 12 GB) before choosing defaults (gate G4, spec §8). Nothing here ships with the app.

## Setup
```
.venv/Scripts/python.exe -m pip install -r requirements-bench.txt
.venv/Scripts/python.exe -m benchmarks.corpus            # ~1.4 GB download, once
```
- **Data:** goes to `D:\LiveTranslator\bench-data`, or `LT_BENCH_DIR` if set. It's outside the repo and never committed.
- **Corpus:** 20 FLEURS sentences (dev split) that exist in all 8 languages: en, es, fr, de, ru, ja, ko, zh.
  - ASR uses each language's clip and its transcript.
  - MT uses the same sentence across languages as parallel references.
- **Dataset:** `google/fleurs` at pinned revision `70bb2e84…894dd`, licensed **CC-BY-4.0**. It's used here only for local measurement (DATA_TRACKER D-017). Credit FLEURS if results are ever published.

## Metrics (`benchmarks/metrics.py`)
- **ASR:** WER after normalising case, punctuation and whitespace; CER for ja/zh/ko. Corpus rates are pooled (total edits ÷ total reference units).
- **MT:** corpus chrF (sacrebleu).
- **Latency:** p50/p95 in ms. Warm-up calls are excluded.
- **VRAM:** NVML device-wide used memory. The peak minus the baseline is what the engine adds, so close games and other GPU apps while benchmarking.

## Results
`benchmarks/results/*.md` (committed): `asr.md`, `mt.md`, `diarization.md`, `discord_rpc.md`, `summary.md`.

## Engines under test
Each benchmark task installs its engine packages into the venv and records the exact versions and licenses in its results file. Some engines need conflicting dependencies (diart pins numpy < 2); those run in a separate throwaway venv (T035).
