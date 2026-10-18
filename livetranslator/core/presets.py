"""Game mode preset (T092; spec §5.10; values decided at G4 on 2026-10-17, see
benchmarks/results/summary.md "Recommendation").

Game mode never rewrites the user's settings: it is applied on top of them when the effective
values are computed. Turning it off therefore restores exactly what the user had (their own
refresh interval survives any number of toggles).

| Setting | Normal | Game mode |
|---|---|---|
| Speech refresh interval | user's value (default 0.5 s) | at least 1.0 s |
| Translate unfinished lines (twice a second) | yes | no (finished lines only) |
| Translation runs on | graphics card if there is one | processor (0 graphics memory) |
"""

from __future__ import annotations

from dataclasses import dataclass

from livetranslator.core.state import AppConfig


@dataclass(frozen=True)
class GameModePreset:
    min_asr_interval_s: float = 1.0
    translate_partials: bool = False
    mt_device: str = "cpu"


GAME_MODE = GameModePreset()
NORMAL_MT_DEVICE = "auto"  # graphics card when CUDA is available, else processor


@dataclass(frozen=True)
class Effective:
    asr_interval_s: float
    translate_partials: bool
    mt_device: str  # "auto" | "cpu"


def effective(config: AppConfig, preset: GameModePreset = GAME_MODE) -> Effective:
    interval = config.performance.asr_update_interval_s
    if not config.performance.game_mode:
        return Effective(interval, True, NORMAL_MT_DEVICE)
    return Effective(
        max(interval, preset.min_asr_interval_s),
        preset.translate_partials,
        preset.mt_device,
    )
