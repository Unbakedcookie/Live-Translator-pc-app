# Overlapping talkers: detection + separation spike (2026-10-20)

User question: "can it not manage multiple people talking over each other? ... how much would voice separation add? could it be a feature you turn on?" Tooling: `benchmarks/separation.py` (mix / detect / separate / score), `benchmarks/separation_models.py`.

## Licences (checked before any model was run)

| Model | Use | Licence | Training data | Verdict |
|---|---|---|---|---|
| pyannote segmentation-3.0, ONNX by k2-fsa/sherpa-onnx (`sherpa-onnx-pyannote-segmentation-3-0`, 5.7 MB) | overlap detection | MIT (Copyright (c) 2022 CNRS; LICENSE file inside the release tarball, read 2026-10-20) | multi-corpus (AMI, DIHARD, Ego4D, …; per-dataset terms not checked, D-043) | Shippable with the MIT notice |
| JorisCos/ConvTasNet_Libri2Mix_sepclean_16k (5.07 M params, 20 MB ONNX) | separation | CC-BY-SA-4.0 (HF API tag) | Libri2Mix sep_clean = LibriSpeech only (CC-BY-4.0), no WHAM noise | Shippable as a separate download with attribution; the model file (and our ONNX export) stays CC-BY-SA; the app stays MIT (D-042, needs the user's OK: CC-BY-SA isn't on the allow-list yet) |
| Rejected | | WSJ0 (LDC) or WHAM!/WHAMR! (CC-BY-NC) training data: SpeechBrain sepformer-wsj02mix/whamr/wham16k, all `sep_noisy` models; sepformer-libri2mix (8 kHz, WSJ0-initialised recipe); MossFormer2 (undisclosed private data); TIGER (EchoSet sources undocumented); pyannote speech-separation-ami-1.0 (MIT + AMI CC-BY-4.0, but gated on HF: needs each user's login); GPL uploads | | |

Note: the fact-checker's first-ranked "MIT DPRNNTasNet-ks2_Libri2Mix_sepclean_16k" does not exist (HF API 401; the author's public models are all CC-BY-SA-4.0). Caught by checking the HF API before downloading.

## Test set

FLEURS dev clips (CC-BY-4.0, local only): 20 sentences × 8 languages with reference text. 192 two-talker mixtures: language pairs en+en, en+es, es+fr, en+zh (6 each), × full / half overlap × second talker 0 dB / −6 dB × clean / pink noise at 15 dB SNR. Plus 320 one-talker clips (160 clean + 160 with noise) for false alarms. Speech recognition: Whisper large-v3-turbo (the app's), language auto-detected, final-pass settings. Error = WER (CER for zh), capped at 1.0; "both ok" = both talkers ≤ 30 %.

## Overlap detection (pyannote segmentation-3.0 ONNX, CPU)

| | n | flagged (≥ 0.5 s of two-talker speech) |
|---|---|---|
| two talkers | 192 | **91 %** (full overlap 96/96; half overlap 79/96) |
| one talker | 320 | **0 %** |

Speed: 0.008 s of processor time per second of audio.

## Separation (ConvTasNet sep_clean 16k)

| Condition | n | today: error A / B | today: both ok | separated: error A / B | separated: both ok |
|---|---|---|---|---|---|
| full overlap, same level, clean | 24 | 0.65 / 0.46 | 0 % | 0.13 / 0.15 | 75 % |
| full overlap, same level, noise | 24 | 0.68 / 0.49 | 0 % | 0.15 / 0.18 | 75 % |
| full overlap, B −6 dB, clean | 24 | 0.41 / 0.73 | 0 % | 0.08 / 0.20 | 71 % |
| full overlap, B −6 dB, noise | 24 | 0.26 / 0.81 | 0 % | 0.10 / 0.23 | 62 % |
| half overlap, same level, clean | 24 | 0.87 / 0.51 | 0 % | 0.15 / 0.16 | 75 % |
| half overlap, same level, noise | 24 | 0.81 / 0.44 | 0 % | 0.17 / 0.14 | 71 % |
| half overlap, B −6 dB, clean | 24 | 0.62 / 0.66 | 0 % | 0.08 / 0.15 | 83 % |
| half overlap, B −6 dB, noise | 24 | 0.36 / 0.77 | 0 % | 0.10 / 0.17 | 62 % |
| **all** | 192 | **0.58 / 0.61** | **0 %** | **0.12 / 0.17** | **72 %** |

By language pair (both ok, today → separated): en+en 0 → 73 %, en+es 0 → 83 %, es+fr 0 → 62 %, en+zh 0 → 69 % (error 0.60/0.52 → 0.13/0.17).

## Cost

- Download: separation model 20 MB + overlap detector 5.7 MB.
- Graphics memory: none (both run on the processor through onnxruntime, already shipped).
- Lines without overlap: the detector only, ~0.008 s per second of audio.
- Overlapped lines: separation 0.18–0.24 s per second of audio on the processor (onnxruntime 1.31, 3/6/10 s lines: 525/1449/2324 ms), plus one extra recognition (~0.4 s on the GPU) and one extra translation. Roughly +1.5–2 s for a 6 s overlapped line.

## Caveats

- Test speech is read speech, like the model's training data (LibriSpeech). Discord audio (codec, game sound, a stream with music) will separate worse; the pink-noise rows are a mild stand-in only (62–75 %).
- 2 talkers only (the model outputs 2 tracks).
- Separation of a whole line; inside the app the split tracks also need their own timing/speaker labels.
