"""T062 — TranslationView inside the floating window (pytest-qt; look reviewed at G2)."""

import sys

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication

from livetranslator.app.demo import SCRIPT, DemoFeed, line_steps
from livetranslator.app.window_controller import WindowController
from livetranslator.core import actions as a
from livetranslator.core.state import (
    AppConfig,
    AppState,
    Geometry,
    Source,
    Utterance,
    WindowConfig,
)
from livetranslator.core.store import Store
from livetranslator.ui.floating_window import FloatingWindow
from livetranslator.ui.translation_view import MAX_LINES

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="native window flags")

GEOMETRY = Geometry(x=2000, y=600, width=420, height=160)


@pytest.fixture
def setup(qtbot):
    window_cfg = WindowConfig(id="w1", geometry=GEOMETRY, sources=(Source.ME, Source.OTHERS))
    store = Store(AppState(config=AppConfig(windows=(window_cfg,))))
    window = FloatingWindow(WindowController(store), "w1", lambda _wid: [])
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    return store, window


def add(store: Store, uid: str, text: str = "a fairly ordinary line of chat", **kw) -> None:
    store.dispatch(
        a.AddUtterance(
            Utterance(
                id=uid,
                source=kw.pop("source", Source.OTHERS),
                speaker_id=kw.pop("speaker_id", "voice:0"),
                start=0.0,
                committed=text,
                language="en",
                is_final=True,
                **kw,
            )
        )
    )


def wheel(window, notches: int, ctrl: bool = False) -> None:
    event = QWheelEvent(
        QPointF(50, 50),
        QPointF(window.mapToGlobal(QPoint(50, 50))),
        QPoint(0, 0),
        QPoint(0, 120 * notches),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.ControlModifier if ctrl else Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(window, event)


def test_lines_follow_the_store_and_window_sources(setup):
    store, window = setup
    view = window.content
    assert view.lines == []
    add(store, "u1", "hello there")
    add(store, "s1", "menu text", source=Source.SCREEN, speaker_id="screen")
    assert [line.utterance_id for line in view.lines] == ["u1"]  # Screen isn't shown here
    store.dispatch(a.UpdateWindow("w1", {"sources": (Source.SCREEN,)}))
    assert [line.utterance_id for line in view.lines] == ["s1"]
    store.dispatch(a.ClearSession())
    assert view.lines == []


def test_partial_update_relayouts_only_that_line(setup):
    store, window = setup
    view = window.content
    add(store, "u1", "first line")
    store.dispatch(
        a.AddUtterance(
            Utterance(id="u2", source=Source.OTHERS, speaker_id="voice:1", start=1.0, language="en")
        )
    )
    store.dispatch(a.UpdateUtterance("u2", {"tentative": "grow"}))
    first_rows = view.rows_for(view.lines[0])
    store.dispatch(a.UpdateUtterance("u2", {"committed": "grow", "tentative": "ing"}))
    assert view.rows_for(view.lines[0]) is first_rows  # cached, not re-measured
    assert view.lines[1].stable == "grow" and view.lines[1].changing == "ing"


def test_scroll_back_keeps_position_and_shows_new_lines_pill(setup, qtbot):
    store, window = setup
    view = window.content
    for i in range(12):
        add(store, f"u{i}")
    assert view.max_offset() > 0 and view.offset == 0
    wheel(window, 1)  # plain wheel scrolls towards older lines
    scrolled = view.offset
    assert scrolled == pytest.approx(min(view.wheel_step(), view.max_offset()))
    before = view.content_height()
    add(store, "new")
    # What the user was reading stays put: the offset grew by the added height.
    assert view.offset == pytest.approx(scrolled + view.content_height() - before)
    assert view.unread and window.new_lines.isVisible()
    qtbot.mouseClick(window.new_lines, Qt.MouseButton.LeftButton)
    assert view.offset == 0 and not view.unread and not window.new_lines.isVisible()
    wheel(window, 1)
    wheel(window, -5)  # back down to the bottom clears it too
    assert view.offset == 0 and not view.unread


def test_ctrl_wheel_still_changes_font_size_not_scroll(setup):
    store, window = setup
    for i in range(12):
        add(store, f"u{i}")
    size = store.state.config.windows[0].style.font_size
    wheel(window, 1, ctrl=True)
    assert store.state.config.windows[0].style.font_size == size + 1
    assert window.content.offset == 0


def test_at_most_max_lines_are_kept(setup):
    store, window = setup
    for i in range(MAX_LINES + 5):
        add(store, f"u{i}", "x")
    assert len(window.content.lines) == MAX_LINES
    assert window.content.lines[0].utterance_id == "u5"


def test_demo_line_plays_partials_then_final_then_translations():
    steps = [action for _, action in line_steps(SCRIPT[2], "d", 0.0)]
    assert isinstance(steps[0], a.AddUtterance)
    finals = [s for s in steps if isinstance(s, a.UpdateUtterance) and s.fields.get("is_final")]
    assert len(finals) == 1
    translations = [s for s in steps if isinstance(s, a.SetTranslation)]
    assert {t.language for t in translations} == set(SCRIPT[2].translations)
    assert all(t.source_text == SCRIPT[2].text for t in translations)
    assert steps.index(finals[0]) < steps.index(translations[0])


def test_demo_feed_fills_the_window(setup, qtbot):
    store, window = setup
    feed = DemoFeed(store)
    feed.start()
    qtbot.waitUntil(lambda: len(window.content.lines) >= 2, timeout=10000)
    feed.stop()
    assert store.state.session.speaker_names == {"discord:demo-mika": "Mika"}
