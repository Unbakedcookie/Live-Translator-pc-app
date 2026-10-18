# M11 — MVP hardening + sign-off — narrative

## 2026-10-18 — T111 (part): logs never contain what was said or who said it
- Test `tests/app/test_log_privacy.py`: a real `LiveTranslatorApp` with DEBUG file logging, one full pass of the demo conversation (every line and its translations in 5 languages), a session rename, Discord member names, a screen-text capture (fake reader, real controller) and the transcript window opened. Then the log file is searched for every sentence, translation and name: **none found**, while a normal log line is present (so the search is not vacuous).
- First attempt hung: `demo_steps()` is endless by design (the demo loops); the test now uses one pass of `line_steps`.
- Still to do in T111: the per-failure recovery review (no CUDA, missing/corrupt model, device unplugged, OCR language missing, worker crash, Discord not running / token revoked).

## 2026-10-18 — T111 (part): failure paths in the speech and translation workers
- Reviewed against spec §9. Gaps found and fixed:
  - **Speech worker crash outside a decode** (e.g. a bug in the voice-activity step) ended the thread silently: speech just stopped. Now it restarts once ("Speech recognition hit an error and restarted.", half-finished lines dropped, streams reset to "now"), and a second crash ends with an ERROR status.
  - **Decodes failing every time** (e.g. the GPU driver crashed) only logged warnings — the user saw nothing. Now 5 failures in a row raise "Speech recognition keeps failing…", cleared automatically when decoding works again.
  - **Real bug found while testing that:** a failed partial decode left the job "not yet decoded", so the worker picked it again immediately, forever — a **100 % CPU retry loop** whenever decoding is broken (the test hung, which is how it showed). A failed partial now counts as tried until the next update interval.
  - **CPU fallback was silent.** After loading, the status now says when speech runs on the processor (no NVIDIA card, or the card failed: "…runs on the processor with a smaller model (slower, a little less accurate)").
  - **Translation worker:** an unexpected (non-engine) error ended its thread; now it's logged, reported for that line, and the worker carries on. (The speaker worker already did this.)
- Tests: restart-once-then-error with a broken VAD step (exactly 2 attempts), failing decodes reported then cleared, ready-status wording for GPU / no GPU / failed GPU, translation keeps going after a buggy line. Suite 600.
- Still to review: model missing/corrupt → offer re-download (needs the wizard/Language Manager UI), device unplugged (capture already retries with a status — to re-verify live), OCR language missing (RapidOCR fallback done), Discord not running / token revoked (client retries; AUTHENTICATE failure → refresh → new prompt).
