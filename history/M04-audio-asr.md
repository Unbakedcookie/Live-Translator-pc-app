# M04 — Audio capture + streaming ASR · history

## 2026-10-17 — pure-logic tasks pulled forward (user away; autonomous)
I did these while the GPU ran the M03 benchmarks and the desktop was in use by the verifier. Both depend only on finished tasks (T016, T013).

### T044 — LocalAgreement-n (`services/asr/local_agreement.py`)
- **How it works.** Every update feeds the hypothesis for the whole utterance buffer (Whisper re-decodes from the utterance start). Words that start before the last committed word's end, minus 80 ms of timestamp jitter, are skipped. A word is committed when the last n hypotheses agree on it at the same position.
- **Matching rule.** Agreement uses NFKC + casefold + no punctuation/whitespace, so "Hello," equals "hello". The newest hypothesis's spelling is kept.
- **Committed words are never revoked.** `finalize()` commits the final decode's remainder. Words are joined by concatenation because Whisper words carry their own leading spaces, which keeps CJK correct without spaces.
- **Bug caught by my own n=3 test:** while warming up (fewer than n hypotheses), the history update dropped older tails, so 3-way agreement never formed. Fix: re-base all tails and keep the newest n−1. n=2 (the default) was unaffected.
- **Lint:** E741 on a test constant named `I`, renamed to `W_I` with a targeted regex so the "I think" strings stayed intact.
- **Verification:** 8 scripted-hypothesis tests:
  - first update commits nothing;
  - common prefix, then skip-by-timestamp on re-decode;
  - revised word stays tentative;
  - punctuation/case agreement;
  - never revoke;
  - finalize + reset;
  - CJK join with punctuation-only token ignored;
  - n=3 warm-up.

### T046 — Echo duplicate filter (`core/chatlog.py`)
- **Rule.** A final "Me" line is an echo when an "Others" line overlaps it within ±window_s (an open line uses its start) and rapidfuzz `token_set_ratio` (default_process: case/punctuation-insensitive) ≥ min_ratio. Defaults are 4 s / 80 from EchoFilterConfig.
- **New dependency.** rapidfuzz 3.14.6 (MIT) is now a runtime dependency. The license gate passed: 20 runtime packages, 0 violations.
- **Verification:** 7 tests:
  - hand-computed Indel similarity "abcd" vs "abcdef" = 80.0, used for the exact-threshold case (dropped at 80, kept at 80.5);
  - overlapping + similar → dropped;
  - same text 6 s apart → kept;
  - overlapping but different → kept;
  - partial Me and Screen lines are never judged;
  - open Others line uses its start.
- D-010 still Unresolved: the thresholds get tuned with real audio in T045.

### T041 — Device enumeration (`services/audio/devices.py`)
- **What it does.** `list_devices()` returns WASAPI inputs, WASAPI loopbacks and both defaults, via PyAudioWPatch (Apache-2.0, now a runtime dependency; license file + classifier read, gate 21/0).
- **Matching** (`match()`): exact name + host API first, then the "stable" name (USB-port number like "(3- " and the " [Loopback]" suffix removed, casefolded), then the Windows default. A loopback is saved under its output device's own name, so the Settings choice "Headphones (A50 Game)" maps back to its loopback.
- **Real devices found on the user's PC** (the fixtures use these names):
  - Astro A50 with separate **Game** and **Voice** outputs (default output = A50 Voice), plus an A50 Mic.
  - NexiGo webcam mic; Steam Streaming virtual devices; Odyssey G95C HDMI audio; Realtek S/PDIF.
- **User benefit to point out:** if Discord outputs to A50 Voice and games to A50 Game, capturing the A50 Voice loopback gives Discord-only "Others" audio without game sound. That's a hardware stand-in for the post-MVP per-app capture.
- **Verification:** 7 Tier A matching tests:
  - stable name;
  - default follow;
  - exact wins;
  - replugged port "(4- A50 Mic)" → "(3- A50 Mic)";
  - missing → default / None;
  - loopback ref round trip;
  - exact preferred over a stable duplicate.
  - Plus a live listing smoke test on this PC: inputs and loopbacks present, flags consistent, both defaults found.
