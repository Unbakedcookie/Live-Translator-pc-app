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

## 2026-10-17 — T105 split a line at a speaker change (commit c804cb7; user away)
- **Problem:** two people talking back-to-back with no pause land in one VAD line, so both get one label. This was the only remaining T035/T102 error.
- **Attempts, measured on the real T035 lines (level-matched and as recorded):**
  1. **pyannote segmentation run on the line alone** (sherpa offline pipeline): it found neither of the 2 changes.
  2. **1.5 s window fingerprints compared with the line's first window:** changes scored a minimum similarity of 0.06–0.08, but single-speaker lines dipped to 0.30 or lower.
  3. **Left-half vs right-half averaged windows:** changes 0.10 / 0.50 / 0.22; single-speaker lines as low as 0.17.
     - Attempts 2 and 3 overlap, so either would cause false splits. They also cost up to 1.1 s of CPU per line.
  4. **Windows matched against the speakers already known (`peek`):**
     - Single-speaker lines never showed two different known speakers. Real patterns: `000000000?`, `???????`, `??000?`, `2?22`.
     - Both changes did: `11111?????22` (known→known) and `???000` (new voice→known).
     - This works because in a conversation the people who interrupt have usually spoken before. **Chosen.**
- **Rule (pure, `change.py`):**
  - Runs of window labels. A known run needs ≥ 2 windows; an unclear ("new voice") run needs ≥ 3.
  - The first adjacent pair of solid runs with different labels (not both unclear) marks the change, estimated between the two runs' window centres.
  - The estimate is then snapped to the nearest gap between recognised words (within 0.8 s).
  - Only lines ≥ 3 s are checked, and only once at least one voice is known.
- **My own test expectation was wrong once:**
  - I expected `11111?????22` to split halfway to speaker 2's run (4.25 s).
  - The code splits where speaker 1 stops being recognised (3.0 s), because the unclear stretch is a run of its own.
  - The real line's true change was at 3.42 s, so the code's choice is the better one. The test was fixed, with that reasoning.
- **Plumbing:**
  - The ASR worker's hand-over became a `LineAudio` record that also carries the final line's timed words (`LocalAgreement.committed_words`) and its language.
  - On a change, the speaker worker splits the text by word midpoints:
    - the first part keeps the id and gets its own text, end time and label;
    - the second part becomes `<id>-2` and gets its own label.
  - Both parts teach their voices.
  - TranslationController re-translates the shortened first line on its own, because its text snapshot changed.
- **Verification:**
  - Tier A: 15 tests for runs, single-speaker patterns from T035, both change kinds, short-run noise, word snapping and window geometry.
  - Synthetic worker test: speaker A 2.5 s, then B 2.5 s; a fake embedder using the window's mean angle (like a real model, a mostly-B window sounds like B). The split lands at 2.475 s against a true 2.5 s, within 300 ms ✓.
  - No split for a long single-speaker line, with no words, or with no known voices.
- **Real audio** (real faster-whisper + TitaNet + store, T035 mixes fed in real time, `split_e2e.py` in the scratchpad):
  - Both back-to-back turns were split.
    - es 3-speaker: 10.50 s vs true 10.36 s (**140 ms**).
    - en 4-speaker: 34.62 s vs true 34.22 s (**400 ms**). The recogniser blurred words across the seam ("…efficiently. Them inv"), so the nearest word gap came late.
  - **Every line in both mixes now has the right speaker.**
- **Open:**
  - The 400 ms case misses spec §8's 300 ms on real audio, though the synthetic acceptance passes. A finer local search around the estimate could tighten it later.
  - Live test with a real multi-person call.
