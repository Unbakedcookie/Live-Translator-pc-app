# Speaker-label benchmark (T035)

## Setup

- CPU only (sherpa-onnx 1.13.8, 2 threads): pyannote segmentation-3.0 (MIT) + NeMo TitaNet large/small (CC-BY-4.0). No graphics memory used.
- Mixes from FLEURS dev (CC-BY-4.0): different recordings of one sentence = different people; each recording cut into turns at its quietest points.
- 2 speakers, en, M+F: 25 s, 4 turns, genders MALE, FEMALE
- 2 speakers, en, F+F: 22 s, 4 turns, genders FEMALE, FEMALE
- 3 speakers, es, M+M+F: 20 s, 6 turns, genders MALE, MALE, FEMALE
- 4 speakers, 3 en + 1 es: 46 s, 8 turns, genders MALE, FEMALE, FEMALE, MALE
- DER with a 0.25 s collar (miss + false alarm + confusion). Turn accuracy = share of turns given the right speaker. Switches = label changes inside one turn.
- Compute: A = seconds per second of audio; B = seconds per 1 s hop; C = seconds per line (embedding only).
- Material: *as recorded* keeps FLEURS loudness (some speakers ~38 dB quieter: a stress test); *level-matched* scales every turn to about -26 dBFS.
- Settings: *similarity* = cosine similarity a line needs to join a known speaker (higher = more speakers); *distance* = sherpa clustering distance (higher = fewer).
- diart not run: its models are gated (needs your Hugging Face token, D-024).

## DER (lower is better)

| Material | Approach | Embedding | Setting | 2 speakers, en, M+F | 2 speakers, en, F+F | 3 speakers, es, M+M+F | 4 speakers, 3 en + 1 es | Mean | Compute s |
|---|---|---|---|---|---|---|---|---|---|
| as recorded | C per-line | titanet-large | similarity 0.5 | 0.0448 | 0.117 | 0.113 | 0.118 | 0.0983 | 0.123 |
| as recorded | C per-line | titanet-large | similarity 0.6 | 0.0448 | 0.117 | 0.113 | 0.118 | 0.0983 | 0.109 |
| as recorded | C per-line | titanet-large | similarity 0.7 | 0.118 | 0.34 | 0.242 | 0.156 | 0.214 | 0.114 |
| as recorded | C per-line | titanet-small | similarity 0.5 | 0.0448 | 0.117 | 0.113 | 0.202 | 0.119 | 0.047 |
| as recorded | C per-line | titanet-small | similarity 0.6 | 0.0448 | 0.117 | 0.113 | 0.202 | 0.119 | 0.0439 |
| as recorded | C per-line | titanet-small | similarity 0.7 | 0.0448 | 0.117 | 0.242 | 0.118 | 0.131 | 0.0424 |
| as recorded | A offline | titanet-large | distance 0.2 | 0.662 | 0.543 | 0.455 | 0.698 | 0.589 | 0.145 |
| as recorded | A offline | titanet-large | distance 0.5 | 0.383 | 0.519 | 0.325 | 0.409 | 0.409 | 0.144 |
| as recorded | B window 10s/1s | titanet-large | dist 0.5 / sim 0.6 | 0.427 | 0.53 | 0.0351 | 0.408 | 0.35 | 0.205 |
| level-matched | C per-line | titanet-large | similarity 0.5 | 0.0448 | 0.111 | 0.113 | 0.118 | 0.0967 | 0.116 |
| level-matched | C per-line | titanet-large | similarity 0.6 | 0.0448 | 0.111 | 0.113 | 0.118 | 0.0967 | 0.111 |
| level-matched | C per-line | titanet-large | similarity 0.7 | 0.118 | 0.111 | 0.242 | 0.156 | 0.157 | 0.118 |
| level-matched | C per-line | titanet-small | similarity 0.5 | 0.0448 | 0.111 | 0.113 | 0.118 | 0.0967 | 0.0455 |
| level-matched | C per-line | titanet-small | similarity 0.6 | 0.0448 | 0.111 | 0.113 | 0.118 | 0.0967 | 0.0419 |
| level-matched | C per-line | titanet-small | similarity 0.7 | 0.0448 | 0.111 | 0.242 | 0.19 | 0.147 | 0.0449 |
| level-matched | A offline | titanet-large | distance 0.2 | 0.356 | 0.503 | 0.408 | 0.501 | 0.442 | 0.172 |
| level-matched | A offline | titanet-large | distance 0.5 | 0.112 | 0.123 | 0.113 | 0.29 | 0.159 | 0.171 |
| level-matched | B window 10s/1s | titanet-large | dist 0.5 / sim 0.6 | 0.106 | 0.175 | 0.195 | 0.379 | 0.214 | 0.232 |

## Turn accuracy (speakers found, label switches per turn)

| Material | Approach | Embedding | Setting | 2 speakers, en, M+F | 2 speakers, en, F+F | 3 speakers, es, M+M+F | 4 speakers, 3 en + 1 es |
|---|---|---|---|---|---|---|---|
| as recorded | C per-line | titanet-large | similarity 0.5 | 1.00 (2 spk, 0.0 sw) | 1.00 (2 spk, 0.0 sw) | 0.83 (3 spk, 0.0 sw) | 0.88 (4 spk, 0.0 sw) |
| as recorded | C per-line | titanet-large | similarity 0.6 | 1.00 (2 spk, 0.0 sw) | 1.00 (2 spk, 0.0 sw) | 0.83 (3 spk, 0.0 sw) | 0.88 (4 spk, 0.0 sw) |
| as recorded | C per-line | titanet-large | similarity 0.7 | 1.00 (3 spk, 0.2 sw) | 0.75 (3 spk, 0.0 sw) | 0.67 (4 spk, 0.0 sw) | 0.88 (5 spk, 0.1 sw) |
| as recorded | C per-line | titanet-small | similarity 0.5 | 1.00 (2 spk, 0.0 sw) | 1.00 (2 spk, 0.0 sw) | 0.83 (3 spk, 0.0 sw) | 0.75 (3 spk, 0.0 sw) |
| as recorded | C per-line | titanet-small | similarity 0.6 | 1.00 (2 spk, 0.0 sw) | 1.00 (2 spk, 0.0 sw) | 0.83 (3 spk, 0.0 sw) | 0.75 (3 spk, 0.0 sw) |
| as recorded | C per-line | titanet-small | similarity 0.7 | 1.00 (2 spk, 0.0 sw) | 1.00 (2 spk, 0.0 sw) | 0.67 (4 spk, 0.0 sw) | 0.88 (4 spk, 0.0 sw) |
| as recorded | A offline | titanet-large | distance 0.2 | 0.50 (3 spk, 0.0 sw) | 0.50 (2 spk, 0.2 sw) | 0.50 (3 spk, 0.0 sw) | 0.25 (4 spk, 0.0 sw) |
| as recorded | A offline | titanet-large | distance 0.5 | 0.75 (2 spk, 0.0 sw) | 0.50 (1 spk, 0.0 sw) | 0.67 (2 spk, 0.0 sw) | 0.50 (2 spk, 0.0 sw) |
| as recorded | B window 10s/1s | titanet-large | dist 0.5 / sim 0.6 | 0.50 (1 spk, 0.0 sw) | 0.50 (1 spk, 0.0 sw) | 1.00 (3 spk, 0.0 sw) | 0.62 (4 spk, 0.4 sw) |
| level-matched | C per-line | titanet-large | similarity 0.5 | 1.00 (2 spk, 0.0 sw) | 1.00 (2 spk, 0.0 sw) | 0.83 (3 spk, 0.0 sw) | 0.88 (4 spk, 0.0 sw) |
| level-matched | C per-line | titanet-large | similarity 0.6 | 1.00 (2 spk, 0.0 sw) | 1.00 (2 spk, 0.0 sw) | 0.83 (3 spk, 0.0 sw) | 0.88 (4 spk, 0.0 sw) |
| level-matched | C per-line | titanet-large | similarity 0.7 | 1.00 (3 spk, 0.2 sw) | 1.00 (2 spk, 0.0 sw) | 0.67 (4 spk, 0.0 sw) | 0.88 (5 spk, 0.1 sw) |
| level-matched | C per-line | titanet-small | similarity 0.5 | 1.00 (2 spk, 0.0 sw) | 1.00 (2 spk, 0.0 sw) | 0.83 (3 spk, 0.0 sw) | 0.88 (4 spk, 0.0 sw) |
| level-matched | C per-line | titanet-small | similarity 0.6 | 1.00 (2 spk, 0.0 sw) | 1.00 (2 spk, 0.0 sw) | 0.83 (3 spk, 0.0 sw) | 0.88 (4 spk, 0.0 sw) |
| level-matched | C per-line | titanet-small | similarity 0.7 | 1.00 (2 spk, 0.0 sw) | 1.00 (2 spk, 0.0 sw) | 0.67 (4 spk, 0.0 sw) | 0.75 (5 spk, 0.0 sw) |
| level-matched | A offline | titanet-large | distance 0.2 | 0.75 (3 spk, 0.0 sw) | 0.50 (5 spk, 0.2 sw) | 0.50 (5 spk, 0.0 sw) | 0.50 (7 spk, 0.1 sw) |
| level-matched | A offline | titanet-large | distance 0.5 | 1.00 (2 spk, 0.0 sw) | 1.00 (2 spk, 0.2 sw) | 0.83 (3 spk, 0.2 sw) | 0.75 (7 spk, 0.4 sw) |
| level-matched | B window 10s/1s | titanet-large | dist 0.5 / sim 0.6 | 1.00 (2 spk, 0.0 sw) | 1.00 (2 spk, 0.2 sw) | 0.83 (3 spk, 0.2 sw) | 0.62 (5 spk, 0.1 sw) |
