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
