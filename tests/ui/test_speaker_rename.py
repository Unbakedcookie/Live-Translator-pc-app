"""T104 — click a speaker label in an overlay to rename that speaker for the session."""

import sys

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

from livetranslator.app.window_controller import WindowController
from livetranslator.core import actions as a
from livetranslator.core.chat_view import automatic_label, speaker_label
from livetranslator.core.state import AppConfig, AppState, Source, Utterance, WindowConfig
from livetranslator.core.store import Store

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="real overlay window")


def line(uid: str, speaker: str, text: str, start: float) -> a.AddUtterance:
    source = Source.ME if speaker == "me" else Source.OTHERS
    return a.AddUtterance(
        Utterance(
            id=uid,
            source=source,
            speaker_id=speaker,
            start=start,
            committed=text,
            language="en",
            is_final=True,
        )
    )


@pytest.fixture
def env(qtbot):
    from livetranslator.ui.floating_window import FloatingWindow

    store = Store(AppState(config=AppConfig(windows=(WindowConfig(id="w"),))))
    store.dispatch(line("u1", "voice:1", "first line", 1.0))
    store.dispatch(line("u2", "others", "someone unknown", 2.0))
    store.dispatch(line("u3", "voice:1", "second line", 3.0))
    window = FloatingWindow(WindowController(store), "w", lambda _id: [])
    qtbot.addWidget(window)
    window.resize(520, 260)
    window.show()
    qtbot.waitExposed(window)
    window.content.repaint()  # paints and records where labels are
    return store, window


def label_center(window, uid: str) -> QPoint:
    rect = next(r for r, u in window.content.label_hits if u == uid)
    return window.content.mapTo(window, rect.center().toPoint())


def test_labels_are_hit_tested_where_they_were_painted(env):
    _, window = env
    assert {uid for _, uid in window.content.label_hits} == {"u1", "u2", "u3"}
    assert window.renamable_label_at(label_center(window, "u1")) == "u1"
    assert window.renamable_label_at(label_center(window, "u2")) is None  # "Others"
    assert window.renamable_label_at(QPoint(window.width() - 5, 5)) is None


def test_click_rename_applies_to_every_line_of_that_speaker(env, qtbot):
    store, window = env
    QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=label_center(window, "u1"))
    popup = window.rename_popup
    assert popup is not None and popup.isVisible()
    assert popup.edit.text() == "Speaker 2" and popup.edit.placeholderText() == "Speaker 2"
    popup.edit.setText("Mika")
    QTest.keyClick(popup.edit, Qt.Key.Key_Return)
    assert store.state.session.speaker_names == {"voice:1": "Mika"}
    labels = {x.utterance_id: x.label for x in window.content.lines}
    assert labels == {"u1": "Mika", "u2": "Others", "u3": "Mika"}  # past lines too
    store.dispatch(line("u4", "voice:1", "a future line", 4.0))
    assert window.content.lines[-1].label == "Mika"


def test_empty_name_goes_back_to_automatic_and_esc_cancels(env, qtbot):
    store, window = env
    store.dispatch(a.RenameSpeaker("voice:1", "Mika"))
    window.open_rename("u3")
    popup = window.rename_popup
    assert popup is not None
    QTest.keyClick(popup.edit, Qt.Key.Key_Escape)
    assert store.state.session.speaker_names == {"voice:1": "Mika"}  # unchanged
    window.open_rename("u3")
    popup = window.rename_popup
    assert popup is not None
    popup.edit.clear()
    QTest.keyClick(popup.edit, Qt.Key.Key_Return)
    assert store.state.session.speaker_names == {}
    assert speaker_label(store.state, "voice:1") == "Speaker 2"


def test_a_drag_from_a_label_moves_the_window_instead(env, qtbot):
    store, window = env
    start = label_center(window, "u1")
    QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(window, start + QPoint(40, 0))
    QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=start + QPoint(40, 0))
    assert window.rename_popup is None
    assert store.state.session.speaker_names == {}


def test_automatic_labels():
    state = AppState()
    assert automatic_label(state, "voice:0") == "Speaker 1"
    assert automatic_label(state, "me") == "Me"
    assert automatic_label(state, "screen") == "Screen"
    assert automatic_label(state, "others") == "Others"
