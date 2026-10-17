"""T024 — window manager: create/destroy, placement, hide/show-all (pytest-qt)."""

import sys

import pytest

from livetranslator.app.window_controller import WindowController
from livetranslator.app.window_manager import WindowManager
from livetranslator.core import actions as a
from livetranslator.core.state import AppConfig, AppState, Geometry, WindowConfig
from livetranslator.core.store import Store
from livetranslator.ui.geometry import default_placement
from livetranslator.ui.screens import monitors


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


def test_remove_last_window_quits_until_tray_exists(env):
    _, controller, manager, quits = env
    controller.remove_window("a")
    assert manager.windows == {}
    assert quits == [1]


def test_hide_one_and_show_hide_all(env):
    store, controller, manager, _ = env
    b = controller.add_window()
    manager.hide_window("a")
    assert not manager.windows["a"].isVisible() and manager.windows[b].isVisible()
    store.dispatch(a.SetAllHidden(True))
    assert not any(w.isVisible() for w in manager.windows.values())
    store.dispatch(a.SetAllHidden(False))  # showing all also brings back the single hidden one
    assert all(w.isVisible() for w in manager.windows.values())
    assert manager.hidden == set()
