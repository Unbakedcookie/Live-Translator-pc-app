# M11 — MVP hardening + sign-off — narrative

## 2026-10-18 — T111 (part): logs never contain what was said or who said it
- Test `tests/app/test_log_privacy.py`: a real `LiveTranslatorApp` with DEBUG file logging, one full pass of the demo conversation (every line and its translations in 5 languages), a session rename, Discord member names, a screen-text capture (fake reader, real controller) and the transcript window opened. Then the log file is searched for every sentence, translation and name: **none found**, while a normal log line is present (so the search is not vacuous).
- First attempt hung: `demo_steps()` is endless by design (the demo loops); the test now uses one pass of `line_steps`.
- Still to do in T111: the per-failure recovery review (no CUDA, missing/corrupt model, device unplugged, OCR language missing, worker crash, Discord not running / token revoked).
