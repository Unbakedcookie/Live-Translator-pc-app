# ASR benchmark (T032)

## Setup

- GPU: NVIDIA GeForce RTX 3060 (12288 MB, driver 610.74)
- Corpus: FLEURS dev, 20 sentences x 8 languages (benchmarks/README.md)
- faster-whisper, beam 5, no VAD, no conditioning on previous text, unless noted
- Error rates are pooled; lower is better. en=WER, es=WER, fr=WER, de=WER, ru=WER, ja=CER, ko=CER, zh=CER

## Quality — language given (how 'Me' runs)

| Config | en | es | fr | de | ru | ja | ko | zh |
|---|---|---|---|---|---|---|---|---|
| large-v3-turbo · GPU · float16 | 0.0548 | 0.0339 | 0.0685 | 0.0508 | 0.0723 | 0.0322 | 0.109 | 0.147 |
| large-v3-turbo · GPU · int8_float16 | 0.0592 | 0.0321 | 0.0704 | 0.053 | 0.0723 | 0.034 | 0.108 | 0.142 |
| small · GPU · int8_float16 | 0.0789 | 0.0499 | 0.122 | 0.113 | 0.122 | 0.143 | 0.117 | 0.295 |
| small · CPU · int8 | 0.0768 | 0.0481 | 0.148 | 0.113 | 0.0998 | 0.138 | 0.12 | 0.297 |

## Quality — language auto-detected (how 'Others' runs)

| Config | Lang-ID acc. | en | es | fr | de | ru | ja | ko | zh |
|---|---|---|---|---|---|---|---|---|---|
| large-v3-turbo · GPU · float16 | 1 | 0.0548 | 0.0339 | 0.0685 | 0.0508 | 0.0723 | 0.0322 | 0.109 | 0.147 |
| large-v3-turbo · GPU · int8_float16 | 1 | 0.0592 | 0.0321 | 0.0704 | 0.053 | 0.0723 | 0.034 | 0.108 | 0.142 |
| small · GPU · int8_float16 | 1 | 0.0789 | 0.0499 | 0.122 | 0.113 | 0.122 | 0.143 | 0.117 | 0.295 |

## Speed and memory

| Config | Load s | VRAM MB | Clip p50 ms | Clip p95 ms | 2 s buffer p50 ms | 5 s buffer p50 ms | 10 s buffer p50 ms |
|---|---|---|---|---|---|---|---|
| large-v3-turbo · GPU · float16 | 2.01 | 2164 | 458.6 | 638.9 | 314.4 | 347.4 | 403.1 |
| large-v3-turbo · GPU · int8_float16 | 4.64 | 1160 | 496.6 | 887.0 | 310.1 | 339.3 | 431.2 |
| small · GPU · int8_float16 | 1.26 | 425 | 481.1 | 876.3 | 151.7 | 253.1 | 323.7 |
| small · CPU · int8 | 1.51 | n/a | 3142.4 | 5446.0 | 2055.8 | 2153.0 | 2543.5 |

## Streaming load (fraction of GPU time busy; > 1.0 = can't keep up)

Growing 10 s buffer re-decoded every 0.5 s or 1.0 s with word timestamps.

| Config | 0.5s/beam1/1 stream | 0.5s/beam1/2 streams | 0.5s/beam5/1 stream | 0.5s/beam5/2 streams | 1.0s/beam1/1 stream | 1.0s/beam1/2 streams | 1.0s/beam5/1 stream | 1.0s/beam5/2 streams |
|---|---|---|---|---|---|---|---|---|
| large-v3-turbo · GPU · float16 | 0.627 | 1.25 | 0.724 | 1.45 | 0.314 | 0.628 | 0.364 | 0.728 |
| large-v3-turbo · GPU · int8_float16 | 0.603 | 1.21 | 0.691 | 1.38 | 0.291 | 0.582 | 0.35 | 0.701 |
| small · GPU · int8_float16 | 0.421 | 0.842 | 0.541 | 1.08 | 0.219 | 0.438 | 0.273 | 0.545 |

## Two streams: one model instance vs two (D-018)

| Config | 1 instance seq. s | 2 instances par. s | Speed-up |
|---|---|---|---|
| large-v3-turbo · GPU · float16 | 6.28 | 6.02 | 1.04 |
| large-v3-turbo · GPU · int8_float16 | 5.93 | 5.76 | 1.03 |
| small · GPU · int8_float16 | 4.34 | 4.77 | 0.909 |
