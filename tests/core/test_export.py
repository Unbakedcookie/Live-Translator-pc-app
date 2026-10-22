"""T063 — transcript formats equal hand-written expected files (Tier A)."""

import json
from datetime import datetime
from pathlib import Path

from livetranslator import __version__
from livetranslator.core.export import (
    format_offset,
    transcript_json,
    transcript_lines,
    transcript_txt,
)
from livetranslator.core.state import AppState, SessionState, Source, Utterance

DATA = Path(__file__).parent / "data"
EXPORTED_AT = datetime(2026, 10, 18, 1, 30)


def session() -> AppState:
    """Three spoken lines plus an empty one; Speaker 2 renamed "Mika"; one stale translation."""
    utterances = (
        Utterance(id="u0", source=Source.OTHERS, speaker_id="voice:0", start=99.0),  # empty
        Utterance(
            id="u1",
            source=Source.OTHERS,
            speaker_id="voice:0",
            start=100.0,
            end=102.5,
            committed="こんにちは、元気ですか",
            language="ja",
            is_final=True,
            translations={"en": "Hello, how are you?"},
            translated_from={"en": "こんにちは、元気ですか"},
        ),
        Utterance(
            id="u2",
            source=Source.ME,
            speaker_id="me",
            start=104.2,
            end=105.0,
            committed="I'm good, thanks",
            language="en",
            is_final=True,
            translations={
                "ja": "元気です、ありがとう",
                "es": "Estoy bien, gracias",
                "de": "Mir geht",
            },
            translated_from={"ja": "I'm good, thanks", "es": "I'm good, thanks", "de": "I'm good"},
        ),
        Utterance(
            id="u3",
            source=Source.OTHERS,
            speaker_id="voice:1",
            start=3765.0,
            committed="Vamos",
            tentative="a jugar",
            language="es",
        ),
    )
    return AppState(session=SessionState(utterances=utterances, speaker_names={"voice:1": "Mika"}))


def test_txt_matches_the_hand_written_file():
    expected = (DATA / "transcript_expected.txt").read_text(encoding="utf-8")
    assert transcript_txt(session(), EXPORTED_AT) == expected


def test_json_matches_the_hand_written_file():
    expected = json.loads((DATA / "transcript_expected.json").read_text(encoding="utf-8"))
    expected["version"] = __version__  # the app's own version, written at export time
    produced = transcript_json(session(), EXPORTED_AT)
    assert json.loads(produced) == expected
    assert "こんにちは" in produced  # written as UTF-8 text, not \u escapes


def test_offsets():
    assert format_offset(0) == "00:00"
    assert format_offset(4.9) == "00:04"
    assert format_offset(59 * 60 + 59) == "59:59"
    assert format_offset(3600) == "1:00:00"
    assert format_offset(3665) == "1:01:05"
    assert format_offset(-2) == "00:00"


def test_search_covers_speaker_text_and_translations():
    lines = transcript_lines(session())
    assert [x.utterance_id for x in lines] == ["u1", "u2", "u3"]
    assert [x.utterance_id for x in lines if x.matches("HOW ARE")] == ["u1"]
    assert [x.utterance_id for x in lines if x.matches("mika")] == ["u3"]
    assert [x.utterance_id for x in lines if x.matches("gracias")] == ["u2"]
    assert [x.utterance_id for x in lines if x.matches("Mir geht")] == []  # stale: not shown
    assert len([x for x in lines if x.matches("  ")]) == 3


def test_empty_session():
    assert transcript_lines(AppState()) == []
    assert transcript_txt(AppState(), EXPORTED_AT) == (
        "Live Translator transcript\nExported 2026-10-18 01:30\n"
    )
    assert json.loads(transcript_json(AppState(), EXPORTED_AT))["utterances"] == []
