# MT benchmark (T033)

## Setup

- GPU: NVIDIA GeForce RTX 3060 (12288 MB)
- Corpus: FLEURS dev, the same 20 sentences in every language (parallel references)
- One sentence per call (live use); beam 4 for CTranslate2 engines; temperature 0 for Qwen
- chrF 0-100, higher is better. Opus-MT ja→ko pivots through English.
- Disk = model files on disk (Opus-MT: all 14 pairs, float16; int8 is applied at load).

## Quality (chrF)

| Engine | en→es | es→en | en→fr | en→de | en→ru | ru→en | en→ja | ja→en | en→ko | ko→en | en→zh | zh→en | ja→ko |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Opus-MT · GPU int8 | 54.0 | 58.2 | 68.5 | 62.5 | 56.8 | 60.0 | 29.6 | 48.6 | 38.5 | 48.1 | 33.9 | 50.4 | 24.2 |
| Opus-MT · CPU int8 | 54.4 | 58.1 | 69.3 | 63.6 | 56.2 | 59.4 | 29.0 | 48.2 | 38.7 | 47.2 | 33.7 | 51.5 | 26.5 |
| MADLAD-400 3B · GPU int8 | 54.3 | 61.4 | 72.0 | 64.9 | 62.0 | 63.5 | 32.3 | 56.0 | 35.4 | 59.1 | 35.3 | 56.6 | 28.3 |
| Qwen3-4B Q4_K_M · llama.cpp cuda | 53.1 | 62.7 | 63.7 | 55.7 | 57.7 | 62.1 | 34.6 | 52.1 | 27.4 | 55.0 | 35.5 | 58.0 | 27.4 |
| Qwen3-4B Q4_K_M · llama.cpp vulkan | 53.2 | 62.8 | 63.6 | 55.1 | 58.2 | 62.4 | 35.1 | 52.5 | 26.3 | 54.5 | 34.7 | 57.8 | 27.7 |

## Speed, memory, disk, licence

| Engine | Load s | VRAM MB | Disk MB | p50 ms | p95 ms | Licence | Error |
|---|---|---|---|---|---|---|---|
| Opus-MT · GPU int8 | 6.88 | 1635 | 2339 | 115.6 | 226.2 | CC-BY-4.0 / Apache-2.0 (D-031) | n/a |
| Opus-MT · CPU int8 | 6.29 | n/a | 2339 | 166.3 | 336.3 | CC-BY-4.0 / Apache-2.0 (D-031) | n/a |
| MADLAD-400 3B · GPU int8 | 4.38 | 3475 | 2839 | 1067.5 | 2106.3 | Apache-2.0 | n/a |
| Qwen3-4B Q4_K_M · llama.cpp cuda | 4.6 | 2855 | 3528 | 484.5 | 1008.7 | Apache-2.0 (model) / MIT (llama.cpp) | n/a |
| Qwen3-4B Q4_K_M · llama.cpp vulkan | 13.1 | 2769 | 2470 | 490.7 | 1066.5 | Apache-2.0 (model) / MIT (llama.cpp) | n/a |

## Sample output (sentence 1, ja→en)

- **Opus-MT · GPU int8** ja→en: And at the UN, we want to make a final decision about a fund to help countries affected by global warming to cope with its effects.
- **Opus-MT · CPU int8** ja→en: And at the UN, we want to make a final decision on a fund to help countries affected by global warming to cope with its effects.
- **MADLAD-400 3B · GPU int8** ja→en: In addition, the United Nations wants to finalize the decision on a fund to help countries affected by global warming cope with its effects.
- **Qwen3-4B Q4_K_M · llama.cpp cuda** ja→en: Furthermore, the United Nations aims to finally decide on establishing a fund to support countries affected by climate change as they address these impacts.
- **Qwen3-4B Q4_K_M · llama.cpp vulkan** ja→en: Moreover, the United Nations aims to finally decide on establishing a fund to support countries affected by climate change as they cope with its impacts.
