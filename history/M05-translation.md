# M05 — Translation pipeline + model management · history

## 2026-10-17 — T052 pulled forward (user away; autonomous)
### T052 — Router + pivot + cache (`services/mt/router.py`, `services/mt/cache.py`)
- **Router.**
  - Engines are tried in preference order (the G4 winner first).
  - src == tgt (after reducing "zh-TW" → "zh") is a passthrough with no engine call.
  - If no engine supports a pair directly, it pivots src → en → tgt, and the two legs may use different engines.
  - Otherwise it raises UnsupportedLanguage; `supports()` reports this without raising.
- **Cache.** A thread-safe OrderedDict LRU with 1000 entries by default, keyed by (engine, src, tgt, text). Each pivot leg is cached separately, so a repeated line costs nothing.
- **Verification:** 9 tests with fake engines: preferred engine first, ja→ko pivot, mixed-engine pivot, passthrough with zero calls, unsupported, cache hit avoids the call (hits 1 / misses 1), LRU order with maxsize 3, default size 1000, base_language.

### License finding that shapes M05 (fact-checker, 2026-10-17; DATA_TRACKER D-031)
- **Argos packages can't ship.** Argos Translate `.argosmodel` weights have **no licence** (only Argos code is MIT/CC0) and are trained partly on WikiMatrix (CC-BY-SA). They stay a benchmark proxy only.
- **What ships instead.** If an Opus-MT-style engine wins G4, the app ships **Helsinki-NLP Opus-MT** converted to CTranslate2 by us, each pair with its upstream licence: Apache-2.0 for most, CC-BY-4.0 for en→de, ru→en, zh→en and `opus-mt-tc-big-en-ko`. en→ja is `opus-mt-en-jap`.

### T053 — Fan-out + MT worker (`services/mt/worker.py`, `app/translation_controller.py`)
- **Targets.** The set of `target_lang` over the windows whose sources include the utterance's source, so each language is translated once however many windows use it.
- **Source language.** The detected language, or `my_language` for Me when detection is missing. Others with no language is skipped.
- **When lines are sent.** Finals are always translated. Partials only when `translate_partials` is on, throttled to ≤ 2/s per line.
- **Worker.** `TranslationWorker` is a thread + queue. `is_current` drops jobs whose text has moved on, both before and after translating, so a slow engine never paints stale text. EngineError is logged by type only (privacy) and doesn't crash. `run_pending()` processes jobs synchronously for deterministic tests.
- **Bugs found by the tests:**
  1. **Feedback loop.** SetTranslation emits `utterance_updated`, and the controller re-submitted the same final line, giving 6 jobs instead of 2. It only stopped because the cache returned identical text, so the store emitted no further change. Fix: remember the last submitted (text, is_final) per line and skip unchanged ones. A regression test was added.
  2. My test expected en→en to be "translated". The router correctly passes it through unchanged, so the test now uses a French Screen line, plus a separate passthrough test.
  3. My own edit misplaced a `finally:` (SyntaxError at collection). Fixed.
  4. A first draft of the controller had a meaningless `or True` condition and a speculative helper. Both were caught on re-reading and removed before testing.
- **Verification:** 10 tests:
  - targets/source-language rules;
  - fan-out {en, ja} once each, written into `translations`;
  - partials ignored when off;
  - throttle (updates every 100 ms for 1 s → jobs at t = 0, 0.5, 1.0, and only the newest is current, so 1 engine call);
  - final bypasses the throttle;
  - unknown source skipped;
  - engine error survives;
  - real worker thread → result arrives through the queued dispatch;
  - same-language passthrough with 0 engine calls;
  - no re-trigger.
