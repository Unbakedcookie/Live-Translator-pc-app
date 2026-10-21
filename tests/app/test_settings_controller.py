"""T072 — settings intents and shortcut validation (Tier A)."""

from livetranslator.app.settings_controller import HOTKEY_TITLES, SettingsController, check_hotkey
from livetranslator.core.state import (
    DEFAULT_HOTKEYS,
    HOTKEY_ACTION_NAMES,
    AppState,
    DeviceRef,
    SpeakerMode,
)
from livetranslator.core.store import Store


def make() -> tuple[Store, SettingsController, list[bool]]:
    store = Store(AppState())
    suspended: list[bool] = []
    return store, SettingsController(store, suspended.append), suspended


def test_check_hotkey_normalises_and_accepts():
    assert check_hotkey({}, "lock_all", "ctrl+shift+l").keys == "Ctrl+Shift+L"
    assert check_hotkey({}, "lock_all", "F5").keys == "F5"  # function keys may stand alone
    # re-setting an action to its own combination is not a clash
    assert check_hotkey({"mute_me": "Ctrl+Alt+M"}, "mute_me", "Alt+Ctrl+M").keys == "Ctrl+Alt+M"


def test_check_hotkey_refuses_bad_and_taken_combinations():
    bare = check_hotkey({}, "lock_all", "L")
    assert bare.keys is None and "Ctrl, Alt, Shift or Win" in bare.error
    assert check_hotkey({}, "lock_all", "Ctrl+Nope").keys is None
    taken = check_hotkey({"mute_me": "Ctrl+Alt+M"}, "lock_all", "ctrl+ALT+m")
    assert taken.keys is None
    assert taken.error == "Ctrl+Alt+M is already used for “Mute Me (microphone)”."
    # a damaged saved entry elsewhere is skipped, not fatal
    assert check_hotkey({"pin_all": "???"}, "lock_all", "Ctrl+Alt+L").keys == "Ctrl+Alt+L"


def test_every_action_has_a_title():
    assert set(HOTKEY_TITLES) == set(HOTKEY_ACTION_NAMES)
    assert {"new_window", "lock_all", "open_settings"} <= set(HOTKEY_ACTION_NAMES)
    assert not {"new_window", "lock_all", "open_settings"} & set(DEFAULT_HOTKEYS)


def test_set_clear_and_reset_hotkeys():
    store, settings, _ = make()
    assert settings.set_hotkey("lock_all", "ctrl+shift+l").error == ""
    assert store.state.config.hotkeys["lock_all"] == "Ctrl+Shift+L"
    refused = settings.set_hotkey("new_window", "Ctrl+Shift+L")
    assert refused.error and "new_window" not in store.state.config.hotkeys
    settings.clear_hotkey("mute_me")
    assert "mute_me" not in store.state.config.hotkeys
    settings.reset_hotkeys()
    assert store.state.config.hotkeys == DEFAULT_HOTKEYS  # extras removed, defaults back


def test_suspend_is_forwarded():
    _, settings, suspended = make()
    settings.suspend_hotkeys(True)
    settings.suspend_hotkeys(False)
    assert suspended == [True, False]
    SettingsController(Store(AppState())).suspend_hotkeys(True)  # no hook: harmless


def test_general_audio_and_speaker_intents():
    store, settings, _ = make()
    settings.set_my_language("ja")
    mic = DeviceRef(name="USB Mic")
    settings.set_mic_device(mic)
    settings.set_output_device(None)
    settings.set_stream_enabled(mic=False)
    settings.set_stream_enabled()  # nothing given: no change
    config = store.state.config
    assert config.my_language == "ja"
    assert config.audio.mic_device == mic and config.audio.output_device is None
    assert not config.audio.mic_enabled and config.audio.others_enabled
    settings.set_speaker_mode(SpeakerMode.OFF)
    settings.set_max_speakers(4)
    settings.set_me_label("  Mika ")
    settings.set_me_label("   ")  # blank is ignored, the old label stays
    speakers = store.state.config.speakers
    assert (speakers.mode, speakers.max_speakers, speakers.me_label) == (SpeakerMode.OFF, 4, "Mika")


def test_performance_advanced_and_reset():
    store, settings, _ = make()
    settings.set_game_mode(True)
    settings.set_asr_interval(0.8000001)
    settings.set_echo_filter(window_s=10.0, min_ratio=90.0)
    settings.set_vad(threshold=0.6, end_silence_ms=700, max_utterance_s=20.0)
    config = store.state.config
    assert config.performance.game_mode and config.performance.asr_update_interval_s == 0.8
    assert (config.echo_filter.window_s, config.echo_filter.min_ratio) == (10.0, 90.0)
    assert (config.vad.threshold, config.vad.end_silence_ms, config.vad.max_utterance_s) == (
        0.6,
        700,
        20.0,
    )
    settings.reset_advanced()
    config = store.state.config
    assert config.vad.threshold == 0.5 and config.vad.end_silence_ms == 500
    assert config.echo_filter.window_s == 4.0 and config.performance.asr_update_interval_s == 0.5
    assert config.performance.game_mode  # game mode isn't an "advanced" setting


def test_lock_all_windows_intent():
    from livetranslator.app.window_controller import WindowController

    store, settings, _ = make()
    windows = WindowController(store)
    windows.add_window()
    windows.add_window()
    settings.set_all_locked(True)
    assert all(w.locked for w in store.state.config.windows)
    windows.handle_hotkey("lock_all")  # the hotkey toggles back
    assert not any(w.locked for w in store.state.config.windows)
    windows.handle_hotkey("new_window")
    assert len(store.state.config.windows) == 3


def test_only_active_actions_clash():
    """Review fix: a default kept for an unbuilt feature (OCR) must not block a combination."""
    hotkeys = {"ocr_region": "Ctrl+Alt+O", "mute_me": "Ctrl+Alt+M"}
    active = ("mute_me", "new_window")
    assert check_hotkey(hotkeys, "new_window", "Ctrl+Alt+O", active).keys == "Ctrl+Alt+O"
    assert check_hotkey(hotkeys, "new_window", "Ctrl+Alt+M", active).keys is None
    store = Store(AppState())
    settings = SettingsController(store, active_hotkeys=active)
    assert settings.set_hotkey("new_window", "Ctrl+Alt+O").error == ""


def test_smart_language_toggle():
    store, settings, _ = make()
    settings.set_smart_language("zh", True)
    settings.set_smart_language("ja", True)
    assert store.state.config.engines.smart_languages == ("ja", "zh")
    settings.set_smart_language("ja", False)
    settings.set_smart_language("ko", False)  # not on: no change
    assert store.state.config.engines.smart_languages == ("zh",)


def test_mic_language_choices_round_trip():
    from livetranslator.app.settings_controller import mic_choice, mic_languages_for

    cases = [
        (("same", ()), ()),
        (("same", ("es",)), ("en", "es")),
        (("same", ("en",)), ()),  # "also" = the same language: nothing extra
        (("auto", ("es",)), ("auto",)),
        (("ja", ("",)), ("ja",)),
        (("ja", ("en",)), ("ja", "en")),
        (("ja", ("en", "", "en", "zh", "vi")), ("ja", "en", "zh", "vi")),  # blanks, repeats
        (("ja", ("en", "zh", "vi", "ko")), ("ja", "en", "zh", "vi")),  # at most 4
    ]
    for (first, also), saved in cases:
        assert mic_languages_for(first, also, "en") == saved, (first, also)
    assert mic_choice(()) == ("same", ())
    assert mic_choice(("auto",)) == ("auto", ())
    assert mic_choice(("ja", "en", "zh")) == ("ja", ("en", "zh"))
    assert mic_choice(("ja",)) == ("ja", ())


def test_mic_languages_are_validated():
    import pytest
    from pydantic import ValidationError

    from livetranslator.core.state import AudioConfig

    assert AudioConfig(mic_languages=("auto",)).mic_languages == ("auto",)
    for bad in (("en", "en"), ("en", "es", "ja", "ko", "vi"), ("auto", "en"), ("English",)):
        with pytest.raises(ValidationError):
            AudioConfig(mic_languages=bad)


def test_others_language_choices_round_trip():
    """2026-10-20 "Others speak": detect any (default) or up to 4 languages."""
    from livetranslator.app.settings_controller import others_choice, others_languages_for

    assert others_languages_for("auto", ("es",)) == ()
    assert others_languages_for("zh", ()) == ("zh",)
    assert others_languages_for("zh", ("en", "", "zh", "ja", "ko", "vi")) == (
        "zh",
        "en",
        "ja",
        "ko",
    )
    assert others_choice(()) == ("auto", (), True)
    assert others_choice(("zh", "en"), False) == ("zh", ("en",), False)
