# M10 — Speaker identification (approval gate G6)

Goal: every line shows who said it, on day one. Spec: `project-spec.md` §5.13. Engine choice + Discord feasibility come from M03 (T035, T036, gate G4).

### T101 — Fusion + calibration logic · Tier A
- Files: `livetranslator/services/speakers/fusion.py`, `services/speakers/calibration.py`, `tests/services/speakers/test_fusion.py`, `test_calibration.py`
- Depends on: T013
- Acceptance: pure functions, hand-built timelines:
  - **Single speaker**: one Discord speaker covers ≥ 60 % → that name.
  - **Overlapping speakers**: the cluster-linked user wins the majority vote; otherwise the largest overlap wins.
  - **No Discord data**: the voice label (or its rename) is used.
  - **Unreliable input**: < 1 s or low confidence → "Others".
  - **Calibration**: median lag over 10 events (hand-computed, including outliers).

### T102 — Diarization engine adapter(s) + worker · Tier B (integration)
- Files: `services/speakers/base.py`, `services/speakers/sherpa_engine.py` (and `diart_engine.py` only if chosen at G4), `services/speakers/worker.py`, `tests/services/speakers/test_worker.py`
- Depends on: G4, T042
- Acceptance:
  - A fake engine checks the worker plumbing.
  - On the T035 3-speaker mix, DER is within 10 % of the M03 value and cluster ids stay stable across windows.
  - Embeddings are never written to disk (test scans the config/data dirs after a run).

### T103 — Discord RPC service · Tier B (integration)
- Files: `services/speakers/discord_rpc.py`, `services/speakers/token_store.py` (DPAPI), `tests/services/speakers/test_discord_rpc.py`, `test_token_store.py`
- Depends on: T036
- Acceptance:
  - Unit tests with a fake IPC transport cover: the authorize flow, channel follow on `VOICE_CHANNEL_SELECT`, SPEAKING events → timeline, and reconnect when Discord restarts.
  - DPAPI encrypt/decrypt round-trip; Disconnect deletes the token.
  - No secret in the repo (gitleaks).
  - Live: real Discord call names appear (if T036 succeeded).

### T104 — Speaker labels UI: rename, colours, Speakers settings, own-app setup guide · Tier B · (G6)
- Files: `livetranslator/ui/widgets/speaker_label.py`, `livetranslator/ui/settings/speakers_page.py`, `livetranslator/ui/discord_setup.py`, tests under `tests/ui/`
- Depends on: G1, G2, T072, T101
- Acceptance:
  - Clicking a label → inline rename; the change applies to past and future lines of that speaker for the session.
  - Speaker colours come from the palette ramp.
  - The Speakers page covers mode / connect / max speakers / "Me" label.
  - The guided own-app setup has a "Test connection" button.
  - Screenshots reviewed by the user (G6).

### T105 — Utterance splitting at speaker change + live test · Tier A + Tier B
- Files: `services/asr/vad.py` (extended), `tests/services/asr/test_speaker_split.py`, `history/M10-speakers.md` (evidence)
- Depends on: T043, T101, T102
- Acceptance:
  - Back-to-back speakers with no pause → 2 utterances, split within 300 ms of the true boundary (synthetic test).
  - Live: a 2–4 person Discord call or a multi-speaker video. Labels are correct on ≥ 80 % of lines in voice-only mode and ≥ 95 % with Discord (spec §8), or the gap is reported.
