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
| Smarter Qwen translation (if turned on) | on | off (frees ~2.8 GB) |
"""

from __future__ import annotations

from dataclasses import dataclass

from livetranslator.core.state import AppConfig


@dataclass(frozen=True)
class GameModePreset:
    min_asr_interval_s: float = 1.0
    translate_partials: bool = False
    mt_device: str = "cpu"
    smart_translation: bool = False  # Qwen needs ~2.8 GB of graphics memory: off while gaming


GAME_MODE = GameModePreset()
NORMAL_MT_DEVICE = "auto"  # graphics card when CUDA is available, else processor


@dataclass(frozen=True)
class Effective:
    asr_interval_s: float
    translate_partials: bool
    mt_device: str  # "auto" | "cpu"
    smart_languages: frozenset[str] = frozenset()  # lines to/from these use Qwen
    smart_fallback: bool = False  # Qwen for pairs with no installed model

    @property
    def smart_wanted(self) -> bool:
        """Qwen has a job (so its server should run)."""
        return bool(self.smart_languages) or self.smart_fallback


def effective(config: AppConfig, preset: GameModePreset = GAME_MODE) -> Effective:
    interval = config.performance.asr_update_interval_s
    smart = frozenset(config.engines.smart_languages)
    fallback = config.engines.smart_fallback
    if not config.performance.game_mode:
        return Effective(interval, True, NORMAL_MT_DEVICE, smart, fallback)
    allowed = preset.smart_translation
    return Effective(
        max(interval, preset.min_asr_interval_s),
        preset.translate_partials,
        preset.mt_device,
        smart if allowed else frozenset(),
        fallback and allowed,
    )
