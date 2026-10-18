# Engine defaults — gate G4 decision sheet (T034)

Measured on this PC (RTX 3060 12 GB). Details: `asr.md`, `mt.md`, `diarization.md`. The Discord
name spike (T036) needs your own Discord app and is still pending.

## Speech recognition (ASR)

| Option | Quality (error rate, lower is better) | Speed per update | Graphics memory |
|---|---|---|---|
| **large-v3-turbo, GPU int8 (recommended)** | 3–7 % words (en/es/fr/de/ru); 3–15 % characters (ja/ko/zh) | ~0.3 s | 1.2 GB |
| small, GPU int8 (game-mode option) | 5–12 % words; 12–30 % characters | ~0.15–0.3 s | 0.4 GB |
| small, CPU (no NVIDIA GPU) | similar to small GPU | ~2–2.5 s | none |

- One model serves both "Me" and "Others". Running two model copies gave no speed-up (1.03×).
- Updating twice a second (0.5 s) fits one person talking. With both streams busy the app
  automatically updates each one less often (measured: 2 streams × 0.5 s needs 120 % of the GPU).
- Live check in the app: en 5.4 %, es 3.7 %, de 1.0 %, ja 4.6 %, zh 17.7 % (zh sometimes
  comes out in Traditional characters).

## Translation (MT)

| Option | Quality (chrF, higher is better; mean of 13 directions) | Speed per sentence | Graphics memory | Notes |
|---|---|---|---|---|
| **Opus-MT, GPU (recommended default)** | 48.7 | **0.12 s** | ~0.1 GB per language pair in use | Fast enough to translate lines *while* people talk. Same quality on CPU (0.17 s). |
| MADLAD-400 3B, GPU | **52.4** | 1.07 s | 3.5 GB | Best quality, clearly better for ko/ja/zh → en (e.g. ko→en 59 vs 48). Too slow for live partial lines. |
| Qwen3-4B (llama.cpp), GPU | 49.6 | 0.49 s | 2.8 GB | Best en→ja; no NVIDIA DLLs needed with the Vulkan build. |

Licences: all three are shippable (Opus-MT CC-BY-4.0 with attribution, MADLAD Apache-2.0,
Qwen Apache-2.0). Argos was dropped: its models have no licence (D-031).

## Speaker labels ("Speaker 1", "Speaker 2" … on the Others stream)

| Option | Mistakes (DER, lower is better) | Turns labelled right | Cost |
|---|---|---|---|
| **Per line (recommended)**: one voice fingerprint per spoken line, matched to the speakers heard so far | 0.10 | 93 % (all mistakes = two people talking with no pause) | 0.1 s CPU per line, no graphics memory |
| Sliding window (the spec's original plan) | 0.35 (0.21 with equal volumes) | 66–86 % | 0.2 s CPU every second |
| Whole recording at once (not possible live) | 0.41 (0.16 with equal volumes) | 60–90 % | — |

Tested on mixes of 2–4 real voices (incl. two women, and very quiet speakers). Voice
fingerprints are kept in memory only, never saved. The "two people with no pause" case gets
an extra check on long lines (planned in T102).

## Recommendation

| Mode | Speech | Translation |
|---|---|---|
| **Normal** | turbo GPU, 0.5 s updates | **Opus-MT** for everything (partials + finals) |
| **Game mode** | turbo GPU, 1.0 s updates (or small if VRAM is tight) | Opus-MT on **CPU** (0 graphics memory) |
| **No NVIDIA GPU** | small on CPU (finals only, ~2 s) | Opus-MT on CPU |
| *Optional "best quality"* | — | Opus-MT for live partials, **MADLAD re-translates each final line** (+3.5 GB, ~1 s later) |

## Decisions (G4 approved 2026-10-17: all defaults, 1a 2a 3a 4a 5a)

1. Default translation engine: **Opus-MT** (GPU; CPU when no NVIDIA GPU or in game mode).
2. "Best quality" mode is offered, **off by default**: MADLAD re-translates final lines.
3. Game mode keeps **turbo**, with 1.0 s updates and no partial translation.
4. Speaker labels: **per line** (T102), with the back-to-back split (T105).
5. The converted Opus-MT models will be published in a Hugging Face repo under the user's
   account, with CC-BY credits and a "converted to CTranslate2" note (T054).

## Questions for you (answer by number; defaults in bold)

1. Default translation engine: **a) Opus-MT** · b) MADLAD · c) Qwen
2. Offer the optional "best quality" mode (MADLAD for final lines)? **a) yes, off by default** · b) no
3. Game mode speech model: **a) turbo with slower updates** · b) small model
4. Speaker labels: **a) per line (recommended)** · b) sliding window as originally planned
5. Sharing the app: other people need the converted Opus-MT models (2.3 GB, or ~1.1 GB at
   int8). OK to publish them in a Hugging Face repo under your account, with the required
   CC-BY credits? **a) yes** · b) find another way
