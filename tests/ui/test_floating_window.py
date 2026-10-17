"""T024 — floating window behaviour (pytest-qt on the real desktop; Windows-only parts noted).

Look and feel is judged by the user at gate G1; these tests pin down the behaviour:
store <-> window sync, pin/click-through on the native window, drag/resize/snap/lock,
Ctrl+wheel, chrome hover, and the style popover's controls.
"""

import sys

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent, QWheelEvent
from PySide6.QtWidgets import QApplication

from livetranslator.app.window_controller import WindowController
from livetranslator.core.state import (
    AppConfig,
    AppState,
    DisplayMode,
    Geometry,
    Source,
    WindowConfig,
)
from livetranslator.core.store import Store
from livetranslator.platform import win32
from livetranslator.theme.qss import window_qss
from livetranslator.theme.tokens import PAPER
from livetranslator.ui.floating_window import FloatingWindow, sources_summary
from livetranslator.ui.geometry import Rect

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="native window flags")

START = Geometry(x=2000, y=600, width=520, height=220, screen="Odyssey G95C")


@pytest.fixture
def setup(qtbot):
    store = Store(AppState(config=AppConfig(windows=(WindowConfig(id="w1", geometry=START),))))
    controller = WindowController(store)
    window = FloatingWindow(controller, "w1", lambda _wid: [])
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    return store, controller, window


def cfg(store: Store) -> WindowConfig:
    found = store.state.config.window("w1")
    assert found is not None
    return found


def geom(store: Store) -> Geometry:
    geometry = cfg(store).geometry
    assert geometry is not None
    return geometry


def mouse(window, kind: QEvent.Type, local: QPoint, buttons=Qt.MouseButton.LeftButton) -> None:
    button = Qt.MouseButton.LeftButton if kind != QEvent.Type.MouseMove else Qt.MouseButton.NoButton
    event = QMouseEvent(
        kind,
        QPointF(local),
        QPointF(window.mapToGlobal(local)),
        button,
        buttons,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(window, event)


def drag(window, start: QPoint, dx: int, dy: int) -> None:
    mouse(window, QEvent.Type.MouseButtonPress, start)
    end_global = window.mapToGlobal(start) + QPoint(dx, dy)
    mouse(window, QEvent.Type.MouseMove, window.mapFromGlobal(end_global))
    mouse(
        window,
        QEvent.Type.MouseButtonRelease,
        window.mapFromGlobal(end_global),
        Qt.MouseButton.NoButton,
    )


def test_window_reflects_config(setup):
    _, _, window = setup
    assert window.geometry().getRect() == (2000, 600, 520, 220)
    assert window.windowOpacity() == pytest.approx(1.0)
    assert win32.is_topmost(int(window.winId()))  # pinned by default
    assert window.chrome.sources.text() == "Me + Others"
    assert sources_summary((Source.OTHERS, Source.SCREEN)) == "Others + Screen"


def test_chrome_is_styled_from_the_first_palette(setup):
    # Regression (found in the G1 render check): the chrome only applied QSS on palette
    # *changes*, so a new window's strip fell back to native Windows styling.
    _, controller, window = setup
    assert window.chrome.styleSheet() == window_qss(window.palette_value)
    assert window.chrome.language.property("flat") is True
    controller.set_builtin_palette("w1", "paper")
    assert window.chrome.styleSheet() == window_qss(PAPER)


def test_pin_button_unpins_native_window(setup, qtbot):
    store, _, window = setup
    window.chrome.show()
    qtbot.mouseClick(window.chrome.pin, Qt.MouseButton.LeftButton)
    assert cfg(store).pinned is False
    assert not win32.is_topmost(int(window.winId()))
    qtbot.mouseClick(window.chrome.pin, Qt.MouseButton.LeftButton)
    assert cfg(store).pinned is True
    assert win32.is_topmost(int(window.winId()))


def test_click_through_and_opacity_follow_store(setup):
    _, controller, window = setup
    controller.set_click_through("w1", True)
    assert win32.is_click_through(int(window.winId()))
    controller.set_click_through("w1", False)
    assert not win32.is_click_through(int(window.winId()))
    controller.set_style("w1", window_opacity=0.5)
    assert window.windowOpacity() == pytest.approx(0.5, abs=0.01)


def test_drag_moves_and_commits_once(setup):
    store, _, window = setup
    changes: list[str] = []
    store.window_changed.connect(changes.append)
    drag(window, QPoint(260, 110), 40, 30)
    assert cfg(store).geometry == START.model_copy(update={"x": 2040, "y": 630})
    assert changes == ["w1"]  # one commit on release, not one per mouse move


def test_drag_snaps_to_screen_edge(setup):
    store, controller, window = setup
    controller.set_geometry("w1", Rect(30, 600, 520, 220), "")
    drag(window, QPoint(260, 110), -21, 0)  # x 30 -> 9, within 12 px of 0
    assert geom(store).x == 0


def test_resize_from_right_edge(setup):
    store, _, window = setup
    drag(window, QPoint(518, 110), 50, 0)
    geometry = geom(store)
    assert (geometry.x, geometry.width, geometry.height) == (2000, 570, 220)


def test_locked_window_does_not_move(setup):
    store, controller, window = setup
    controller.set_locked("w1", True)
    drag(window, QPoint(260, 110), 40, 30)
    assert cfg(store).geometry == START


def test_ctrl_wheel_changes_font_size(setup):
    store, _, window = setup
    for delta, expected in ((120, 17), (-120, 16), (-120, 15)):
        event = QWheelEvent(
            QPointF(100, 100),
            QPointF(window.mapToGlobal(QPoint(100, 100))),
            QPoint(0, 0),
            QPoint(0, delta),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.ControlModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )
        QApplication.sendEvent(window, event)
        assert cfg(store).style.font_size == expected


def test_chrome_appears_on_hover_and_hides_after_leaving(setup, qtbot):
    _, _, window = setup
    QApplication.sendEvent(window, QEvent(QEvent.Type.Enter))
    qtbot.waitUntil(lambda: window.chrome.isVisible(), timeout=1000)
    window._hide_timer.setInterval(10)
    QApplication.sendEvent(window, QEvent(QEvent.Type.Leave))
    # The real cursor is not over the test window, so the chrome fades out.
    qtbot.waitUntil(lambda: not window.chrome.isVisible(), timeout=2000)


def test_style_popover_controls_update_store(setup, qtbot):
    store, _, window = setup
    window.open_style_popover()
    popover = window.popover
    assert popover is not None and popover.isVisible()
    qtbot.mouseClick(popover.swatches.swatches["paper"], Qt.MouseButton.LeftButton)
    assert cfg(store).style.palette_id == "paper"
    popover.bg_opacity._slider.setValue(35)
    assert cfg(store).style.bg_opacity == pytest.approx(0.35)
    popover.both.setChecked(True)
    assert cfg(store).display is DisplayMode.BOTH
    popover.sources[Source.SCREEN].setChecked(True)
    assert cfg(store).sources == (Source.ME, Source.OTHERS, Source.SCREEN)
    for source in (Source.ME, Source.OTHERS, Source.SCREEN):
        popover.sources[source].setChecked(False)
    assert cfg(store).sources == (Source.SCREEN,)  # the last source can't be unticked
    assert popover.sources[Source.SCREEN].isChecked()
    popover.close()


def test_language_picker_and_close_button(setup, qtbot):
    store, _, window = setup
    window.chrome.language.activated.emit(window.chrome.language.findData("ja"))
    assert cfg(store).target_lang == "ja"
    window.chrome.show()
    qtbot.mouseClick(window.chrome.close_button, Qt.MouseButton.LeftButton)
    assert store.state.config.windows == ()


def _toasts() -> list:
    from livetranslator.ui.widgets.toast import Toast

    return [w for w in QApplication.topLevelWidgets() if isinstance(w, Toast) and w.isVisible()]


def test_click_through_shows_toast_and_arms_hover_hint(setup):
    # User feedback (G1): after turning click-through on, the controls vanished and it
    # wasn't clear how to get them back.
    _, controller, window = setup
    for toast in _toasts():
        toast.close()
    controller.set_click_through("w1", True)
    toasts = _toasts()
    assert [t.label.text() for t in toasts] == [
        "Click-through is on. Press Ctrl+Alt+T to turn it off."
    ]
    assert window._hint_timer.isActive()
    assert window.click_through_hint.text() == toasts[0].label.text()
    controller.set_click_through("w1", False)
    assert not window._hint_timer.isActive()
    assert not window.click_through_hint.isVisible()
    for toast in _toasts():
        toast.close()


def test_click_through_message_follows_remapped_shortcut(setup):
    from livetranslator.core import actions as a

    store, _, window = setup
    store.dispatch(a.SetHotkey("click_through_all", "Ctrl+Shift+K"))
    assert (
        window.click_through_message() == "Click-through is on. Press Ctrl+Shift+K to turn it off."
    )
    store.dispatch(a.SetHotkey("click_through_all", None))
    assert "Set a shortcut" in window.click_through_message()


def test_style_change_does_not_reraise_window(setup, monkeypatch):
    # Regression (G1 feedback): every setting change re-ran SetWindowPos(TOPMOST), which
    # pulled the overlay above its own open style popover.
    _, controller, window = setup
    calls: list[bool] = []
    monkeypatch.setattr(win32, "set_topmost", lambda hwnd, on: calls.append(on))
    window.open_style_popover()
    controller.set_style("w1", bg_opacity=0.4)
    controller.set_style("w1", shadow=True)
    assert calls == []
    controller.set_pinned("w1", False)
    assert calls == [False]
    assert window.popover is not None and window.popover.isVisible()
    window.popover.close()
