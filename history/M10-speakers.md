# M10 — Speaker identification (gate G6) — narrative

## 2026-10-17 — T101 fusion + calibration, T102 per-line voice labels (commit 8885086; user away)

### Context
- T035 measured that per-line fingerprints beat the spec's sliding-window plan: DER 0.10 vs 0.35, 93 % of turns right, robust to big loudness differences.
- The engine (sherpa-onnx) was already the spec's recommendation, so T102 went ahead with the per-line design before G4. It is listed as question 4 on the G4 sheet and is easy to change: only the worker's job source would differ.

### T101 (Tier A)
- `fusion.py` implements the spec §5.13 rules as pure functions:
  - one Discord user covering ≥ 60 % of the line wins, and the line's voice cluster gets a vote for that user;
  - when several users overlap, the cluster's vote majority decides; otherwise the largest overlap;
  - with no Discord data, the voice label is used;
  - lines under 1 s, or with low confidence, become "others".
  - The vote table is passed in and a new one is returned; nothing is mutated.
- `calibration.py`: each SPEAKING_START is paired with the nearest VAD onset within 2 s, and the lag is the median over the first 10 pairs (at least 3 needed).
- 11 tests on hand-built timelines, e.g. 2.5 s of 4 s is 62.5 %, so the single speaker wins. The calibration test includes outliers of +1.8 s and −1.5 s plus one unpaired start; the expected median is 0.3.

### T102
- **`VoiceClusters`:** duration-weighted running sums with a similarity threshold of 0.55 (inside the T035 plateau of 0.5–0.6) and at most 6 speakers. `peek` serves partial lines and never learns or creates a speaker.
  - **Test bug caught by re-checking my own arithmetic:** the first "weighted mean" test would also have passed with an unweighted mean (a 60° voice joins either way). It now uses 70°, which joins only without weighting: 4.5° centroid → cos 65.5° = 0.41.
- **`SherpaEmbedder`:** TitaNet-large on CPU, 2 threads, model in `<models>/speakers/`.
- **`SpeakerWorker`:**
  - Runs on its own thread.
  - A partial line is embedded once it has ≥ 1.5 s of audio; it is labelled only if it matches a known voice, otherwise it keeps the neutral label.
  - The final line assigns (learns), fuses, and dispatches `UpdateUtterance(speaker_id)`.
  - A load failure turns labels off with a plain-language status.
  - The session reset forgets every voice (D-028).
- **ASR worker hook:** `on_line_audio(id, audio, start, end, final)`, for the Others stream only and never the mic. It keeps the ASR module independent of speakers.
- **Licence gate:** sherpa-onnx 1.13.8's metadata is free text, so an override (D-029) was added after reading the wheel's `licenses/LICENSE`, which is Apache-2.0. The gate passes 42 packages.

### Verification
- **Tier A / unit tests:** clusters (5), worker with a fake embedder (7: stable labels, peek-only partials, short lines, OFF mode, Discord name + vote teaching, load failure, reset, thread), the ASR hook (one early + one final hand-over, Others only), and the controller (settings follow, voices cleared with the session).
- **Real model on the T035 3-speaker mix:** DER within 10 % of the M03 value of 0.113. The tmp app dirs are byte-for-byte unchanged afterwards, so no fingerprint was written.
- **Live Tier B:**
  - Setup: scratch profile, mic muted. The level-matched 2-speaker (en M+F) and 3-speaker (es M+M+F) mixes were played through the default output and captured by the loopback.
  - All 10 lines got the right speaker. The English pair alternated Speaker 1/2; the Spanish trio became Speakers 3/4/5 and stayed consistent on their second turns.
  - The only miss is the known back-to-back turn (es S3 → S1 with no pause), which was merged into one line. That is T105's job.

### Not done / open
- **T103 Discord RPC:** blocked on T036, which needs the user's own Discord application (5-step setup approved in Phase 1).
- **T104 label UI:** rename by clicking a label, plus the Speakers settings page.
- **T105:** split a line at a speaker change.
- **Live test:** a real Discord call with 2–4 people.
