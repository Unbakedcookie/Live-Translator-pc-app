# M09 — Game mode + performance readout

Spec: §5.10, §8.

### T091 — Metrics service · Tier A
- Files: `livetranslator/services/metrics.py`, `tests/services/test_metrics.py`
- Depends on: T014
- Acceptance: rolling p50/p95 over the last N samples is correct (hand-computed). NVML unavailable → metrics show "n/a" without error. Sampled at 1 Hz into `runtime`.

### T092 — Game mode presets · Tier A
- Files: `livetranslator/core/presets.py`, `tests/core/test_presets.py`
- Depends on: G4, T045, T053
- Acceptance: toggling applies/restores the exact preset values from the M03 summary. User overrides survive a toggle round-trip.

### T093 — Readout UI (footer strip + mini HUD) · Tier B
- Files: `livetranslator/ui/hud.py`, `tests/ui/test_hud.py`
- Depends on: G1, T091
- Acceptance: the values update live. Screenshot reviewed by the user. Measured: game mode meets the §8 budget with a game running (or the gap is reported).
