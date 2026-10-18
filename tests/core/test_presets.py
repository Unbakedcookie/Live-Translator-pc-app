"""T092 — game mode is applied on top of the user's settings and undone exactly (Tier A)."""

from livetranslator.core.presets import GAME_MODE, Effective, effective
from livetranslator.core.state import AppConfig, PerformanceConfig


def config(interval: float, game: bool) -> AppConfig:
    return AppConfig(performance=PerformanceConfig(asr_update_interval_s=interval, game_mode=game))


def test_preset_values_match_the_g4_decision():
    assert (GAME_MODE.min_asr_interval_s, GAME_MODE.translate_partials, GAME_MODE.mt_device) == (
        1.0,
        False,
        "cpu",
    )


def test_normal_mode_uses_the_users_values():
    assert effective(config(0.5, False)) == Effective(0.5, True, "auto")
    assert effective(config(0.7, False)) == Effective(0.7, True, "auto")


def test_game_mode_applies_the_preset():
    assert effective(config(0.5, True)) == Effective(1.0, False, "cpu")
    assert effective(config(1.5, True)) == Effective(1.5, False, "cpu")  # slower stays slower


def test_round_trip_keeps_the_users_override():
    mine = config(0.7, False)
    on = mine.model_copy(
        update={"performance": mine.performance.model_copy(update={"game_mode": True})}
    )
    off = on.model_copy(
        update={"performance": on.performance.model_copy(update={"game_mode": False})}
    )
    assert effective(on).asr_interval_s == 1.0
    assert off == mine and effective(off) == Effective(0.7, True, "auto")
