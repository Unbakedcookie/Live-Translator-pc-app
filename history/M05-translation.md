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

## 2026-10-17 — T051 Opus-MT adapter + translation live in the app (commits 45af05c, ab3ad4d; user away)
- **`OpusMtEngine`:**
  - Discovers `<models>/opus-mt/<src>-<tgt>/` folders that have both model.bin and opus_mt.json. An interrupted download is ignored (tested).
  - Loads each pair lazily: CTranslate2 int8_float16 on GPU, int8 on CPU.
  - Prefixes the language tag where a pair needs one (en-zh).
  - Tests cover the contract errors, plus real translations when the models are on the PC: es, and the ja→ko pivot producing Hangul with no `⁇`.
- **App wiring (`build_translation`):**
  - Opus-MT is the *provisional* default until gate G4. It is the fastest option, the only one with a fast CPU path, and the smallest.
  - Partial lines are translated except in game mode, which meets the spec §5.5 rule (p50 < 150 ms).
  - The models were copied into this PC's app models folder (2.3 GB).
  - **Open (user decision at G4):** how other users get the models. Converted models must be hosted somewhere, e.g. our own HF repo with CC-BY attribution.
- **Statuses:** a missing pair or a failing engine now dispatches a plain-language "translation" status instead of only being logged (tested in test_fanout).
- **Bug caught by reading the code before running it:**
  - `_on_config_changed` read `self.translation`, but adding the first window emits config_changed before that attribute exists, so a first start would have raised AttributeError.
  - Fixed by declaring the attributes before any signal is connected.

## 2026-10-18 — Optional "smarter translation" with Qwen for Chinese (Mandarin follow-up)
- **Why:** the user wants Mandarin to work "VERY well"; on 16 casual/gaming Chinese lines Opus-MT garbled the slang (麦 → "wheat", 开黑 → "keep it dark", 副本 → "copy") while Qwen3-4B got them right (history/M03). G4 kept Opus-MT as the default, so this is an **option** the user decides on.
- **Engine** (`services/mt/engines/qwen_llama.py`): llama.cpp's Vulkan llama-server (MIT, 88 MB, no NVIDIA DLLs) as a hidden child process on 127.0.0.1 with a free port, loading Qwen3-4B-Instruct Q4_K_M (Apache-2.0, 2.4 GB). One chat request per line, temperature 0, with a prompt that asks to keep slang and gaming terms natural. Starting the server is its "warm-up" (the existing pre-load jobs start it while the person is still talking).
- **Never orphaned:** the server is put in a Windows job object with kill-on-close, so if the app crashes or is killed the server dies with it (it would otherwise keep 2.8 GB of graphics memory). Tested by hard-exiting a process that started it.
- **Routing:** `TranslationRouter(preferred=…)` tries Qwen first for pairs touching `engines.smart_languages`; if Qwen fails (server gone), the line falls back to Opus-MT instead of being lost.
- **Game mode turns it off** (preset `smart_translation=False`) and the app stops the server off the UI thread to free the memory; turning game mode off starts it again via re-warm.
- **Settings → Translation:** "Smarter translation → Chinese (Mandarin)" switch, shown only when the Qwen files are installed; the engines list shows "Smarter translation · Qwen3-4B (Chinese) · Graphics card / Starts with the first line / Off". **Default off** until the user decides.
- Installed on the user's PC: `%LOCALAPPDATA%\LiveTranslator\models\llama.cpp\vulkan` + `qwen3-4b\…gguf` (copied from the benchmark folder).
- **Verified:** unit tests (reply cleaning incl. "翻译：" prefix, not-installed paths, game mode off, preference + fallback + both-fail error, Settings switch both ways and hidden when not installed); real server: "你的麦有点吵…" → contains "mic", "…开黑…" → "8 PM", no "dark"; end to end through the real TranslationController: 谁有空帮我刷一下副本？ → "Who's free to help me clear the raid?" (4.8 s incl. server start), a Spanish line still via Opus-MT; crash test leaves no llama-server. Full suite 547 passed.

## 2026-10-18 — T054 model catalogue + ModelManager (Opus-MT entries pending hosting)
- `livetranslator/data/model_catalog.json` (shipped): Whisper turbo + small (HF, pinned commits, HF cache layout), TitaNet (GitHub release URL + SHA-256), Qwen3-4B GGUF (HF pinned, single file), llama.cpp Vulkan zip (URL + SHA-256, marker `llama-server.exe`). Each entry has licence, size, attribution. Opus-MT pairs are added once the converted models are hosted (G4 decision 5 — needs the user's HF repo).
- `services/models.py`: catalogue rules (licence on an allow-list, HF sources pin a 40-hex commit, URLs are HTTPS with a SHA-256, dest stays inside the models folder); `ModelManager` with installed checks, free-space check before downloading, HF via huggingface_hub (injected in tests), URL downloads to `.downloads/<name>.part` resumed with an HTTP Range after a cancel or drop, SHA-256 checked before anything moves into place (a wrong hash deletes the file), zips extracted to a temp folder, a single wrapper folder flattened, swapped in whole; `move_to` for a model-folder change (never overwrites).
- Tests (14): shipped catalogue valid; 5 rule violations rejected; download + progress; **resume** sends `Range: bytes=300000-` and completes; cancel keeps the partial and the next download resumes; wrong hash deletes; zip flatten + marker; not enough space refused before any request; HF calls; folder move. First run: the cancel test downloaded everything in one 1 MiB block (payload = block size) — test payload raised to 3 MiB.
- **Real downloads** through the manager into a scratch folder: TitaNet (97 MB, 3.9 s) and llama.cpp Vulkan (31 MB, 2.0 s) — both hashes match what GitHub serves; on the user's PC all five catalogue models report installed.
- Not yet: the wizard / Language Manager UI on top (T073/T074).
