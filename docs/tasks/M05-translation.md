# M05 — Translation pipeline + model management

Goal: final (and optionally partial) utterances translated into every needed target language. Models download and verify. Spec: §5.5, §5.9 (ModelManager part).

### T051 — Engine adapters (chosen at G4) · Tier B (integration)
- Files: `livetranslator/services/mt/engines/*.py`, `tests/services/mt/test_engines.py`
- Depends on: T016, G4
- Acceptance: each adapter implements `TranslationEngine`. Integration: 5 fixed sentences per default pair produce non-empty output with chrF near the M03 values. `unload()` frees VRAM (NVML before/after).

### T052 — Router + pivot + cache · Tier A
- Files: `services/mt/router.py`, `services/mt/cache.py`, `tests/services/mt/test_router.py`
- Depends on: T016
- Acceptance (with fake engines): direct pair chosen when available; ja→ko pivots via en when needed; src == tgt → passthrough; cache hit avoids an engine call; LRU evicts the oldest at 1 000.

### T053 — Fan-out + MT worker · Tier A
- Files: `services/mt/worker.py`, `livetranslator/app/translation_controller.py`, `tests/services/mt/test_fanout.py`
- Depends on: T014, T052
- Acceptance: windows {en: Others, ja: Me+Others, en: Screen} + an OTHERS utterance → targets {en, ja}, each translated once. Partial throttle ≤ 2/s (fake clock). Results dispatched into `Utterance.translations`.

### T054 — Model catalog + ModelManager · Tier A
- Files: `livetranslator/services/models.py`, `livetranslator/data/model_catalog.json`, `tests/services/test_models.py`
- Depends on: T011, G4
- Acceptance: catalog schema validated (each entry has a license, and every license is on the allow-list; HF entries pin a commit revision). Language packs include their Noto font entries. HF files are fetched via **huggingface_hub** (mocked in tests); fonts/other files via HTTPS. Download to temp → SHA-256 check → atomic move (local HTTP server fixture). A wrong hash → file deleted + error. Resume from a partial file. Free-space check. A model-folder change moves files.
