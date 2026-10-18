"""T062 — what a window shows for each utterance (Tier A, hand-written expectations)."""

from livetranslator.core.chat_view import (
    ChatLineData,
    chat_line,
    language_tag,
    speaker_label,
    speaker_ramp_indexes,
    visible_lines,
)
from livetranslator.core.state import (
    AppConfig,
    AppState,
    DisplayMode,
    SessionState,
    Source,
    SpeakerConfig,
    Utterance,
    WindowConfig,
    WindowStyle,
)

EN = WindowConfig(id="w", target_lang="en", sources=(Source.ME, Source.OTHERS))
EN_BOTH = EN.model_copy(update={"display": DisplayMode.BOTH})


def utt(uid: str, speaker: str = "voice:0", source: Source = Source.OTHERS, **kw) -> Utterance:
    return Utterance(id=uid, source=source, speaker_id=speaker, start=0.0, **kw)


def state_with(*utterances: Utterance, my_language: str = "en", **session) -> AppState:
    return AppState(
        config=AppConfig(my_language=my_language, windows=(EN,)),
        session=SessionState(utterances=utterances, **session),
    )


def line(u: Utterance, window: WindowConfig = EN, state: AppState | None = None) -> ChatLineData:
    state = state or state_with(u)
    return chat_line(u, window, state, speaker_ramp_indexes(state.session))


def test_same_language_partial_shows_committed_and_tentative():
    u = utt("u", committed="we should", tentative="go left", language="en")
    assert line(u) == ChatLineData("u", "Speaker 1", 0, "we should", "go left", None)


def test_same_language_final_is_all_stable():
    u = utt("u", committed="we should go left", language="en", is_final=True)
    assert line(u) == ChatLineData("u", "Speaker 1", 0, "we should go left", "", None)


def test_mic_without_detected_language_uses_my_language():
    u = utt("u", "me", Source.ME, committed="hello", is_final=True)
    assert line(u).stable == "hello"  # my_language "en" == target: no translation needed
    de = state_with(u, my_language="de")
    assert line(u, state=de) == ChatLineData("u", "Me", "me", "", "hello", None, "DE→EN")  # pending


def test_pending_translation_shows_the_original_as_changing():
    u = utt("u", committed="hola amigos", language="es", is_final=True)
    assert line(u, EN_BOTH) == ChatLineData("u", "Speaker 1", 0, "", "hola amigos", None, "ES→EN")


def test_current_translation_of_a_final_line_is_stable():
    u = utt(
        "u",
        committed="hola amigos",
        language="es",
        is_final=True,
        translations={"en": "hi friends"},
        translated_from={"en": "hola amigos"},
    )
    assert line(u) == ChatLineData("u", "Speaker 1", 0, "hi friends", "", None, "ES→EN")
    assert line(u, EN_BOTH).original == "hola amigos"


def test_stale_or_partial_translation_is_shown_as_changing():
    stale = utt(
        "u",
        committed="hola amigos",
        language="es",
        is_final=True,
        translations={"en": "hi"},
        translated_from={"en": "hola"},  # made from an earlier partial
    )
    assert line(stale) == ChatLineData("u", "Speaker 1", 0, "", "hi", None, "ES→EN")
    partial = utt(
        "u",
        committed="hola",
        language="es",
        translations={"en": "hi"},
        translated_from={"en": "hola"},
    )
    assert line(partial, EN_BOTH) == ChatLineData("u", "Speaker 1", 0, "", "hi", "hola", "ES→EN")


def test_speaker_labels():
    state = AppState(
        config=AppConfig(speakers=SpeakerConfig(me_label="Sam")),
        session=SessionState(speaker_names={"voice:1": "Rin", "discord:42": "Mika"}),
    )
    assert speaker_label(state, "me") == "Sam"
    assert speaker_label(state, "screen") == "Screen"
    assert speaker_label(state, "voice:0") == "Speaker 1"
    assert speaker_label(state, "voice:1") == "Rin"  # session rename wins
    assert speaker_label(state, "discord:42") == "Mika"
    assert speaker_label(state, "discord:7") == "Others"  # name not known yet
    assert speaker_label(state, "others") == "Others"


def test_ramp_numbers_other_speakers_by_first_appearance():
    session = SessionState(
        utterances=(
            utt("1", "voice:3"),
            utt("2", "me", Source.ME),
            utt("3", "discord:9"),
            utt("4", "voice:3"),
            utt("5", "screen", Source.SCREEN),
        )
    )
    assert speaker_ramp_indexes(session) == {"voice:3": 0, "discord:9": 1}


def test_visible_lines_filters_sources_and_keeps_the_newest():
    lines = [utt(f"o{i}", committed=f"line {i}", language="en") for i in range(5)]
    screen = utt("s", "screen", Source.SCREEN, committed="menu", language="en")
    blank = utt("b", committed="  ", language="en")
    state = state_with(*lines[:3], screen, blank, *lines[3:])
    shown = visible_lines(state, EN, limit=3)
    assert [x.utterance_id for x in shown] == ["o2", "o3", "o4"]  # no screen, no blank


def test_language_tag():
    """User request 2026-10-18: show which languages a line is translated between."""
    assert language_tag("zh", "en") == "ZH→EN"
    assert language_tag("zh-TW", "en") == "ZH→EN"
    assert language_tag("en", "en") == ""  # nothing to translate
    assert language_tag(None, "en") == ""  # language not known yet
    same = utt("u", committed="hello", language="en", is_final=True)
    assert line(same).tag == ""
    unknown = utt("u", committed="hola")  # Others, language not detected yet
    assert line(unknown).tag == ""


def test_language_tag_can_be_turned_off_per_window():
    u = utt("u", committed="hola", language="es", is_final=True)
    quiet = WindowConfig(id="w", target_lang="en", style=WindowStyle(show_languages=False))
    assert line(u, quiet).tag == ""
