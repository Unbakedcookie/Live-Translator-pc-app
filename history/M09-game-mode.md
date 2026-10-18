# M09 — Game mode + performance readout — narrative

## 2026-10-18 — T091 metrics service, T092 game-mode preset (user asleep)

### Design
- **Timings** (`services/timings.py`, Qt-free): workers record durations ("asr" around each Whisper decode, "mt" around real engine work, "lag" from the service); last 50 per kind; nearest-rank p50/p95.
- **Lag** (speech end → finished line on screen): `MetricsService` watches utterance updates; a line counts once it is final and every needed translation is current (`line_done`), measured against `Utterance.end` on the same monotonic clock the ASR worker uses. Measured once per line.
- **GPU** (`NvmlSampler`): utilisation + memory of GPU 0; per-process memory from `nvmlDeviceGetComputeRunningProcesses` when Windows reports it (WDDM usually doesn't → absent). Any NVML failure → no GPU metrics, logged once, never raised.
- **Service:** 1 Hz `Batch` of `SetMetric`s into `runtime.metrics` (ms / MB / %); a metric that can't be measured is absent (the readout will show n/a).
- **New runtime dependency nvidia-ml-py** (BSD-3-Clause, read the `pynvml.py` header in the wheel; licence gate passes via classifier; DATA_TRACKER register row updated). `nvml.dll` comes with the NVIDIA driver.
- **Game mode preset** (`core/presets.py`, G4 values): refresh ≥ 1.0 s, no partial translation, Opus-MT on the **processor**. Applied on top of the user's settings when computing effective values, never written into them, so turning game mode off restores the user's own interval exactly. `OpusMtEngine.set_device` switches under the translate lock (a line being translated finishes first; the next never sees a half-switched engine). Before T092 the MT-on-CPU part of the G4 decision wasn't implemented.

### Bug found by the live run
- First live run showed **"mt p50 = 0 ms"**: the worker timed every job, including same-language passthroughs (English line → English window) and cache hits. Timing moved into the router around actual engine calls. Regression test added.

### Verification
- **Tier A:** percentiles (1..4 → p50 2; 20..1 → p50 10, p95 19; 3 values → p95 = max), window, `timed` skips failures, 8 threads × 500 records; fake NVML (values, once-only init, failure → None without retry storm, sample failure, per-process memory missing/other pid); tick rounding (VRAM 4096.4 → 4096, app 300.6 → 301, asr p50 200 / p95 400, mt 116); no GPU → only timings; `line_done` (partial, missing, stale, complete); lag measured once (0.9 s) and not re-measured on later edits; presets (normal, game, slower user value kept, round trip); Opus device switch (before load, after load drops pairs, no-op keeps them); router times only real engine work.
- **Live (real app, scratch profile, mic muted, Spanish/English clips through the speakers):** GPU %, VRAM used/total sampled each second; ASR p50 ≈ 290 ms; MT GPU p50 65–86 ms with the first call per pair ≈ 0.94 s (model load); lag 0.86–0.98 s; the game-mode hotkey switched the engine to `cpu` within the same second; first line after the switch 2.15 s (CPU model load). Numbers recorded in D-015.

### Open
- T093 readout UI (footer strip / HUD) + measurement with a game running.
- Pre-loading likely language pairs would remove the ~0.94 s first-line cost (and the 2 s after switching to game mode).

## 2026-10-18 — T093 readout strip

- Chose the **footer strip** (spec offers strip or standalone HUD): one small secondary-colour line under the chat of each overlay, e.g. `GPU 28 % · VRAM 3.3 / 12.0 GB · Speech 310 ms · Translate 77 ms · Lag 0.96 s`, prefixed "Game mode" when on. Missing values say "n/a". The chat area shrinks to make room; the "New lines" pill sits above the strip; the strip ignores the mouse so dragging still works.
- Toggle: Settings → Performance → "Show performance readout" (`PerformanceConfig.show_readout`, already in the saved config).
- Game-mode description in Settings now also says translation runs on the processor (true since T092).
- **Verification:** `readout_text` against hand-written strings (full, game mode, all n/a, half-known VRAM); overlay test (hidden by default, appears with the setting, chat height shrinks by the strip, follows metrics and game mode, hides again); Settings toggle both ways. **Tier B:** real app, speech on, Spanish clip through the speakers → screenshot shows live values under the translated line.
- **Not done (needs the user):** the spec's "game mode meets the §8 budget with a game running" measurement. Without a game: lag 0.96 s (budget 1.5 s).

## 2026-10-18 — Pre-loading translation models (follow-up to the T091 numbers)

- **Problem (measured):** the first line of each language pair waited ~0.94 s for its model, and the first line after switching to game mode took 2.15 s (CPU load).
- **Design:** loading everything would cost ~2 GB of graphics memory, so it's targeted:
  - at start: my language → the languages of windows that show Me;
  - as soon as a line's language is known (a partial, seconds before the final): that language → its targets — this runs even when partial translation is off, which is exactly game mode;
  - after the engine moves device (game mode on/off): every pair that was in use, again.
  - `WarmJob`s go through the translation worker's own queue, so a load never races a translation; `router.warm` loads each pivot leg and skips passthrough/unsupported/engines without `warm`; once per pair.
- **Verification:** tests for router legs, controller (start, partial-off warm, once per pair, rewarm), engine (needs installed + loaded). Live: slowest translation 943 → ~320 ms; first line after switching to game mode 2.15 → 0.95 s; normal first line 0.97 s (now dominated by the final speech decode).
