"""T024 — window manager: create/destroy, placement, hide/minimize/show-all (pytest-qt)."""

import sys

import pytest
from PySide6.QtGui import QIcon

from livetranslator.app.window_controller import WindowController
from livetranslator.app.window_manager import WindowManager
from livetranslator.core import actions as a
from livetranslator.core.state import AppConfig, AppState, Away, Geometry, WindowConfig
from livetranslator.core.store import Store
from livetranslator.ui.geometry import default_placement
from livetranslator.ui.screens import monitors
from livetranslator.ui.taskbar_button import TaskbarButton


def geom(store: Store, window_id: str) -> Geometry:
    window = store.state.config.window(window_id)
    assert window is not None and window.geometry is not None
    return window.geometry


pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="real desktop windows")


@pytest.fixture
def env(qtbot):
    quits: list[int] = []
    store = Store(AppState(config=AppConfig(windows=(WindowConfig(id="a"),))))
    controller = WindowController(store)
    manager = WindowManager(store, controller, lambda: quits.append(1))
    yield store, controller, manager, quits
    manager.close_all()


def test_existing_window_is_created_and_placed(env):
    store, _, manager, _ = env
    assert list(manager.windows) == ["a"]
    expected = default_placement(monitors(), index=0)
    geometry = geom(store, "a")
    assert (geometry.x, geometry.y, geometry.width, geometry.height) == (
        expected.x,
        expected.y,
        expected.width,
        expected.height,
    )
    assert manager.windows["a"].isVisible()


def test_new_windows_cascade(env):
    store, controller, manager, _ = env
    new_id = controller.add_window()
    assert set(manager.windows) == {"a", new_id}
    second = default_placement(monitors(), index=1)
    assert geom(store, new_id).y == second.y


def test_offscreen_saved_window_is_pulled_back(qtbot):
    far = Geometry(x=20000, y=300, width=520, height=220, screen="Gone Monitor")
    store = Store(AppState(config=AppConfig(windows=(WindowConfig(id="x", geometry=far),))))
    manager = WindowManager(store, WindowController(store), lambda: None)
    try:
        g = geom(store, "x")
        work = next(m for m in monitors() if m.primary).work
        assert g.x + g.width <= work.right and g.x >= work.left
    finally:
        manager.close_all()


def test_remove_last_window_quits_without_a_tray(env):
    _, controller, manager, quits = env
    controller.remove_window("a")
    assert manager.windows == {}
    assert quits == [1]


def test_remove_last_window_calls_the_tray_hook_instead(qtbot):
    quits: list[int] = []
    closed: list[int] = []
    store = Store(AppState(config=AppConfig(windows=(WindowConfig(id="a"),))))
    controller = WindowController(store)
    manager = WindowManager(
        store, controller, lambda: quits.append(1), on_last_closed=lambda: closed.append(1)
    )
    controller.remove_window("a")
    assert manager.windows == {} and closed == [1] and quits == []


def test_hide_one_and_show_hide_all(env):
    store, controller, manager, _ = env
    b = controller.add_window()
    manager.hide_window("a")
    assert not manager.windows["a"].isVisible() and manager.windows[b].isVisible()
    store.dispatch(a.SetAllHidden(True))
    assert not any(w.isVisible() for w in manager.windows.values())
    store.dispatch(a.SetAllHidden(False))  # showing all also brings back the single hidden one
    assert all(w.isVisible() for w in manager.windows.values())
    assert store.state.runtime.away == {}


def test_minimize_puts_a_button_on_the_taskbar(qtbot):
    store = Store(AppState(config=AppConfig(windows=(WindowConfig(id="a"),))))
    controller = WindowController(store)
    taskbar = TaskbarButton("Live Translator", QIcon())
    manager = WindowManager(store, controller, lambda: None, taskbar=taskbar)
    b = controller.add_window()
    manager.windows["a"].minimize_requested.emit("a")
    assert not manager.windows["a"].isVisible() and manager.windows[b].isVisible()
    assert taskbar.on_taskbar
    manager.windows[b].minimize_requested.emit(b)
    assert not manager.windows[b].isVisible()
    taskbar.showNormal()  # what clicking the taskbar button does
    qtbot.waitUntil(lambda: all(w.isVisible() for w in manager.windows.values()))
    assert not taskbar.isVisible() and store.state.runtime.away == {}
    manager.windows["a"].minimize_requested.emit("a")
    controller.handle_hotkey("show_hide_all")  # Ctrl+Alt+H also brings it back
    assert manager.windows["a"].isVisible() and not taskbar.isVisible()
    manager.windows["a"].minimize_requested.emit("a")
    taskbar.close()  # the taskbar's "Close window" restores rather than quitting
    assert manager.windows["a"].isVisible() and not taskbar.isVisible()
    manager.windows["a"].minimize_requested.emit("a")
    manager.close_all()
    assert not taskbar.isVisible()


def test_hide_from_the_menu_says_how_to_get_it_back(env):
    store, _, manager, _ = env
    told: list[int] = []
    manager.window_hidden.connect(lambda: told.append(1))
    manager.windows["a"].hide_requested.emit("a")
    assert store.state.runtime.away == {"a": Away.HIDDEN} and told == [1]
