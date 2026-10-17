"""T013 — pure reducers (Tier A). Every expected state/change list is written out by hand."""

import pytest

from livetranslator.core import actions as a
from livetranslator.core.reducers import Change, ChangeKind, reduce
from livetranslator.core.state import (
    AppConfig,
    AppState,
    DisplayMode,
    Geometry,
    RuntimeStatus,
    SessionState,
    Source,
    StatusLevel,
    Utterance,
    WindowConfig,
    WindowStyle,
)

W = ChangeKind.WINDOW
C = ChangeKind.CONFIG


def state_with(*windows: WindowConfig) -> AppState:
    return AppState(config=AppConfig(windows=windows))


EN = WindowConfig(id="w-en", target_lang="en")
JA = WindowConfig(id="w-ja", target_lang="ja", sources=(Source.OTHERS,))


# ---------------------------------------------------------------- windows


def test_add_window():
    state, changes = reduce(state_with(EN), a.AddWindow(JA))
    assert state.config.windows == (EN, JA)
    assert changes == (Change(W, "w-ja"), Change(C, "windows"))


def test_add_duplicate_window_raises():
    with pytest.raises(ValueError, match="already exists"):
        reduce(state_with(EN), a.AddWindow(WindowConfig(id="w-en")))


def test_remove_window_and_unknown_is_noop():
    start = state_with(EN, JA)
    state, changes = reduce(start, a.RemoveWindow("w-en"))
    assert state.config.windows == (JA,)
    assert changes == (Change(W, "w-en"), Change(C, "windows"))
    same, none = reduce(state, a.RemoveWindow("ghost"))
    assert same is state
    assert none == ()


def test_update_window_fields():
    geometry = Geometry(x=100, y=900, width=520, height=220, screen=r"\\.\DISPLAY1")
    state, changes = reduce(
        state_with(EN, JA),
        a.UpdateWindow(
            "w-ja", {"pinned": False, "display": DisplayMode.BOTH, "geometry": geometry}
        ),
    )
    expected = WindowConfig(
        id="w-ja",
        target_lang="ja",
        sources=(Source.OTHERS,),
        display=DisplayMode.BOTH,
        geometry=geometry,
        pinned=False,
    )
    assert state.config.windows == (EN, expected)
    assert changes == (Change(W, "w-ja"), Change(C, "windows"))


def test_sources_are_deduplicated_and_ordered():
    state, _ = reduce(
        state_with(EN), a.UpdateWindow("w-en", {"sources": (Source.SCREEN, Source.ME, Source.ME)})
    )
    assert state.config.windows[0].sources == (Source.ME, Source.SCREEN)


def test_update_window_rejects_bad_values_and_fixed_fields():
    start = state_with(EN)
    with pytest.raises(ValueError, match="not a language code"):
        reduce(start, a.UpdateWindow("w-en", {"target_lang": "English"}))
    with pytest.raises(ValueError, match="can't be updated"):
        reduce(start, a.UpdateWindow("w-en", {"id": "other"}))
    with pytest.raises(ValueError, match="has no field"):
        reduce(start, a.UpdateWindow("w-en", {"colour": "red"}))
    with pytest.raises(ValueError):
        reduce(
            start, a.UpdateWindow("w-en", {"geometry": {"x": 0, "y": 0, "width": 10, "height": 10}})
        )


def test_unchanged_update_emits_nothing():
    start = state_with(EN)
    state, changes = reduce(start, a.UpdateWindow("w-en", {"pinned": True}))  # already True
    assert state is start
    assert changes == ()


def test_set_window_style_field():
    state, changes = reduce(
        state_with(EN, JA), a.UpdateWindowStyle("w-en", {"bg_opacity": 0.4, "palette_id": "neon"})
    )
    assert state.config.windows[0].style == WindowStyle(bg_opacity=0.4, palette_id="neon")
    assert state.config.windows[1] == JA
    assert changes == (Change(W, "w-en"), Change(C, "windows"))


def test_style_validation():
    start = state_with(EN)
    with pytest.raises(ValueError):
        reduce(start, a.UpdateWindowStyle("w-en", {"bg_opacity": 1.5}))
    with pytest.raises(ValueError):
        reduce(start, a.UpdateWindowStyle("w-en", {"window_opacity": 0.1}))  # min 0.30
    with pytest.raises(ValueError, match="custom_seed"):
        reduce(start, a.UpdateWindowStyle("w-en", {"custom_seed": "blue"}))
    state, _ = reduce(start, a.UpdateWindowStyle("w-en", {"custom_seed": "#3b82f6"}))
    assert state.config.windows[0].style.custom_seed == "#3B82F6"


def test_update_all_windows_pins_only_changed_ones():
    unpinned = JA.model_copy(update={"pinned": False})
    state, changes = reduce(state_with(EN, unpinned), a.UpdateAllWindows({"pinned": True}))
    assert [w.pinned for w in state.config.windows] == [True, True]
    assert changes == (Change(W, "w-ja"), Change(C, "windows"))


# ---------------------------------------------------------------- config sections


def test_set_my_language_and_section_update():
    state, changes = reduce(AppState(), a.SetMyLanguage("es"))
    assert state.config.my_language == "es"
    assert changes == (Change(C, "my_language"),)
    state, changes = reduce(state, a.UpdateConfigSection("echo_filter", {"window_s": 6.0}))
    assert state.config.echo_filter.window_s == 6.0
    assert state.config.echo_filter.min_ratio == 80.0
    assert changes == (Change(C, "echo_filter"),)
    with pytest.raises(ValueError):
        reduce(state, a.UpdateConfigSection("speakers", {"discord_app_id": "not-digits"}))


def test_hotkeys():
    state, changes = reduce(AppState(), a.SetHotkey("pin_all", "Ctrl+Shift+P"))
    assert state.config.hotkeys["pin_all"] == "Ctrl+Shift+P"
    assert changes == (Change(C, "hotkeys"),)
    state, _ = reduce(state, a.SetHotkey("game_mode", None))
    assert "game_mode" not in state.config.hotkeys
    with pytest.raises(ValueError, match="unknown hotkey"):
        reduce(state, a.SetHotkey("launch_rockets", "Ctrl+R"))


def test_replace_config_reports_all_windows():
    start = state_with(EN, JA)
    new = AppConfig(windows=(WindowConfig(id="w-new"),), my_language="de")
    state, changes = reduce(start, a.ReplaceConfig(new))
    assert state.config == new
    assert changes == (
        Change(C, "all"),
        Change(W, "w-en"),
        Change(W, "w-ja"),
        Change(W, "w-new"),
    )


# ---------------------------------------------------------------- session


def utt(uid: str, **kw) -> Utterance:
    return Utterance(
        id=uid, source=kw.pop("source", Source.OTHERS), speaker_id="others", start=1.0, **kw
    )


def test_utterance_partial_to_final():
    state, changes = reduce(AppState(), a.AddUtterance(utt("u1", tentative="hola")))
    assert changes == (Change(ChangeKind.UTTERANCE_ADDED, "u1"),)
    state, changes = reduce(
        state, a.UpdateUtterance("u1", {"committed": "hola", "tentative": "cómo"})
    )
    assert state.session.utterances[0].text == "hola cómo"
    assert changes == (Change(ChangeKind.UTTERANCE_UPDATED, "u1"),)
    state, _ = reduce(
        state,
        a.UpdateUtterance(
            "u1", {"committed": "hola, ¿cómo estás?", "tentative": "", "is_final": True, "end": 2.5}
        ),
    )
    assert state.session.utterances == (
        utt("u1", committed="hola, ¿cómo estás?", is_final=True, end=2.5),
    )


def test_translations_and_fixed_fields():
    state, _ = reduce(AppState(), a.AddUtterance(utt("u1", committed="hola")))
    state, changes = reduce(state, a.SetTranslation("u1", "en", "hello"))
    state, _ = reduce(state, a.SetTranslation("u1", "ja", "こんにちは"))
    assert state.session.utterances[0].translations == {"en": "hello", "ja": "こんにちは"}
    assert changes == (Change(ChangeKind.UTTERANCE_UPDATED, "u1"),)
    _, none = reduce(state, a.SetTranslation("u1", "en", "hello"))
    assert none == ()
    with pytest.raises(ValueError, match="can't be updated"):
        reduce(state, a.UpdateUtterance("u1", {"source": Source.ME}))


def test_original_state_is_not_mutated():
    start, _ = reduce(AppState(), a.AddUtterance(utt("u1", committed="hola")))
    reduce(start, a.SetTranslation("u1", "en", "hello"))
    assert start.session.utterances[0].translations == {}


def test_updates_to_missing_utterance_are_ignored():
    start = AppState()
    assert reduce(start, a.UpdateUtterance("gone", {"committed": "x"})) == (start, ())
    assert reduce(start, a.SetTranslation("gone", "en", "x")) == (start, ())
    assert reduce(start, a.RemoveUtterance("gone")) == (start, ())


def test_remove_and_clear_session():
    state, _ = reduce(AppState(), a.AddUtterance(utt("u1")))
    state, _ = reduce(state, a.AddUtterance(utt("u2", source=Source.ME)))
    state, changes = reduce(state, a.RemoveUtterance("u2"))  # e.g. echo filter
    assert [u.id for u in state.session.utterances] == ["u1"]
    assert changes == (Change(ChangeKind.UTTERANCE_REMOVED, "u2"),)
    state, _ = reduce(state, a.RenameSpeaker("voice:1", "Mika"))
    state, changes = reduce(state, a.ClearSession())
    assert state.session == SessionState()
    assert changes == (Change(ChangeKind.SESSION_CLEARED),)
    assert reduce(state, a.ClearSession()) == (state, ())


def test_rename_speaker():
    state, changes = reduce(AppState(), a.RenameSpeaker("voice:1", "  Mika "))
    assert state.session.speaker_names == {"voice:1": "Mika"}
    assert changes == (Change(ChangeKind.SPEAKER, "voice:1"),)
    state, changes = reduce(state, a.RenameSpeaker("voice:1", None))
    assert state.session.speaker_names == {}
    assert changes == (Change(ChangeKind.SPEAKER, "voice:1"),)


def test_duplicate_utterance_raises():
    state, _ = reduce(AppState(), a.AddUtterance(utt("u1")))
    with pytest.raises(ValueError, match="already exists"):
        reduce(state, a.AddUtterance(utt("u1")))


# ---------------------------------------------------------------- runtime + batch


def test_runtime_status_metric_hidden():
    state, changes = reduce(
        AppState(), a.SetStatus("audio.me", StatusLevel.WARNING, "Mic not found")
    )
    assert state.runtime.statuses == {
        "audio.me": RuntimeStatus(level=StatusLevel.WARNING, message="Mic not found")
    }
    assert changes == (Change(ChangeKind.RUNTIME, "status:audio.me"),)
    state, changes = reduce(state, a.ClearStatus("audio.me"))
    assert state.runtime.statuses == {}
    state, changes = reduce(state, a.SetMetric("asr_p50_ms", 412.0))
    assert state.runtime.metrics == {"asr_p50_ms": 412.0}
    assert changes == (Change(ChangeKind.RUNTIME, "metric:asr_p50_ms"),)
    state, changes = reduce(state, a.SetAllHidden(True))
    assert state.runtime.all_hidden
    assert changes == (Change(ChangeKind.RUNTIME, "all_hidden"),)


def test_batch_merges_changes_and_is_atomic():
    state, changes = reduce(
        state_with(EN),
        a.Batch(
            (
                a.UpdateWindow("w-en", {"pinned": False}),
                a.UpdateWindowStyle("w-en", {"shadow": True}),
            )
        ),
    )
    assert state.config.windows[0].pinned is False
    assert state.config.windows[0].style.shadow is True
    assert changes == (Change(W, "w-en"), Change(C, "windows"))
    start = state_with(EN)
    with pytest.raises(ValueError):
        reduce(start, a.Batch((a.SetMyLanguage("fr"), a.SetMyLanguage("French"))))
    assert start.config.my_language == "en"


def test_config_rejects_duplicate_window_ids():
    with pytest.raises(ValueError, match="duplicate window ids"):
        AppConfig(windows=(EN, WindowConfig(id="w-en")))
