"""T063 — transcript window lists, searches, copies and exports (pytest-qt)."""

from pathlib import Path

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QWidget

from livetranslator.core import actions as a
from livetranslator.core.export import transcript_lines
from livetranslator.core.state import AppState, Source, Utterance
from livetranslator.core.store import Store
from livetranslator.theme.tokens import DEFAULT_PALETTE_ID, PALETTES
from livetranslator.ui.transcript_window import EMPTY, NO_MATCH, TranscriptWindow, transcript_html

PALETTE = PALETTES[DEFAULT_PALETTE_ID]


def line(uid: str, start: float, text: str, speaker: str = "voice:0", **extra) -> a.AddUtterance:
    source = Source.ME if speaker == "me" else Source.OTHERS
    return a.AddUtterance(
        Utterance(
            id=uid,
            source=source,
            speaker_id=speaker,
            start=start,
            committed=text,
            is_final=True,
            **extra,
        )
    )


def make(qtbot, export=None):
    store = Store(AppState())
    calls: list[QWidget] = []

    def fake_export(parent: QWidget) -> Path | None:
        calls.append(parent)
        return export

    window = TranscriptWindow(store, PALETTE, fake_export, lambda: "Couldn't save there.")
    qtbot.addWidget(window)
    window.bring_to_front()
    return store, window, calls


def test_empty_then_lines_arrive(qtbot):
    store, window, _ = make(qtbot)
    assert EMPTY in window.view.toPlainText()
    assert not window.copy.isEnabled() and not window.export_button.isEnabled()
    store.dispatch(
        line(
            "u1",
            1.0,
            "hola",
            language="es",
            translations={"en": "hi"},
            translated_from={"en": "hola"},
        )
    )
    store.dispatch(line("u2", 3.0, "hi there", speaker="me", language="en"))
    qtbot.waitUntil(lambda: len(window.shown) == 2, timeout=2000)
    text = window.view.toPlainText()
    assert "Speaker 1" in text and "hola" in text and "English: hi" in text and "Me" in text
    assert window.count.text() == "2 lines" and window.export_button.isEnabled()


def test_search_filters_and_copy_takes_what_is_shown(qtbot):
    store, window, _ = make(qtbot)
    store.dispatch(line("u1", 1.0, "hola amigos"))
    store.dispatch(line("u2", 2.0, "good game"))
    window.redraw()
    window.search.setText("GAME")
    assert [x.utterance_id for x in window.shown] == ["u2"]
    assert window.count.text() == "1 of 2 lines"
    window.copy_shown()
    assert QGuiApplication.clipboard().text() == "[00:01] Speaker 1\ngood game"
    assert window.status.text() == "Copied 1 line."
    window.search.setText("nothing like this")
    assert NO_MATCH in window.view.toPlainText() and not window.copy.isEnabled()


def test_export_button_reports_where_it_saved(qtbot, tmp_path: Path):
    target = tmp_path / "chat.txt"
    store, window, calls = make(qtbot, export=target)
    store.dispatch(line("u1", 1.0, "hola"))
    window.redraw()
    window.export_button.click()
    assert calls == [window] and window.status.text() == f"Saved to {target}"
    _, failing, _ = make(qtbot, export=None)
    failing._on_export()
    assert failing.status.text() == "Couldn't save there."


def test_html_escapes_text_and_colours_speakers():
    store = Store(AppState())
    store.dispatch(line("u1", 1.0, "<b>not bold</b> & co"))
    store.dispatch(line("u2", 2.0, "yo", speaker="me"))
    html = transcript_html(transcript_lines(store.state), PALETTE)
    assert "&lt;b&gt;not bold&lt;/b&gt; &amp; co" in html
    assert PALETTE.speaker_color(0) in html and PALETTE.speaker_me in html


def test_close_hides_and_clear_session_empties(qtbot):
    store, window, _ = make(qtbot)
    store.dispatch(line("u1", 1.0, "hola"))
    window.redraw()
    window.close()
    assert not window.isVisible()
    store.dispatch(a.ClearSession())
    window.bring_to_front()  # redraws on open
    assert EMPTY in window.view.toPlainText()
