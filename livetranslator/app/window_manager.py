"""Creates/destroys FloatingWindows as the store's window list changes (T024; spec §5.1).

Also places new windows (default bottom-centre placement, cascading), restores saved ones
onto existing monitors, implements show/hide-all and per-window hide (runtime only).
Closing the last window calls `on_last_closed`: with a tray icon (T071) the app keeps running
there; without a system tray it quits (spec §5.11).
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject

from livetranslator.app.window_controller import WindowController
from livetranslator.core.store import Store
from livetranslator.ui.floating_window import FloatingWindow
from livetranslator.ui.geometry import Rect, default_placement, monitor_for, restore
from livetranslator.ui.screens import monitors, rect_from_qrect


class WindowManager(QObject):
    def __init__(
        self,
        store: Store,
        controller: WindowController,
        quit_app: Callable[[], None],
        parent: QObject | None = None,
        on_last_closed: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._store = store
        self._controller = controller
        self._quit_app = quit_app
        self._on_last_closed = on_last_closed or quit_app
        self.windows: dict[str, FloatingWindow] = {}
        self.hidden: set[str] = set()
        store.window_changed.connect(self._sync)
        store.runtime_changed.connect(self._on_runtime)
        for cfg in store.state.config.windows:
            self._create(cfg.id)

    # ------------------------------------------------------------ lifecycle

    def _sync(self, window_id: str) -> None:
        exists = self._store.state.config.window(window_id) is not None
        if exists and window_id not in self.windows:
            self._create(window_id)
        elif not exists and window_id in self.windows:
            window = self.windows.pop(window_id)
            self.hidden.discard(window_id)
            window.close()
            window.deleteLater()
            if not self.windows:
                self._on_last_closed()

    def _create(self, window_id: str) -> None:
        window = FloatingWindow(self._controller, window_id, self.other_rects)
        window.hide_requested.connect(self.hide_window)
        window.new_window_requested.connect(self._controller.add_window)
        window.quit_requested.connect(self._quit_app)
        self.windows[window_id] = window
        self._place(window_id, index=len(self.windows) - 1)
        if not self._store.state.runtime.all_hidden:
            window.show()

    def _place(self, window_id: str, index: int) -> None:
        cfg = self._store.state.config.window(window_id)
        screens = monitors()
        if cfg is None or not screens:
            return
        if cfg.geometry is None:
            rect = default_placement(screens, index=index)
            self._controller.set_geometry(window_id, rect, monitor_for(rect, screens).name)
            return
        saved = Rect(cfg.geometry.x, cfg.geometry.y, cfg.geometry.width, cfg.geometry.height)
        placed = restore(saved, cfg.geometry.screen, screens)
        if placed != saved:
            self._controller.set_geometry(window_id, placed, monitor_for(placed, screens).name)

    # ------------------------------------------------------------ visibility

    def other_rects(self, window_id: str) -> list[Rect]:
        return [
            rect_from_qrect(w.geometry())
            for wid, w in self.windows.items()
            if wid != window_id and w.isVisible()
        ]

    def hide_window(self, window_id: str) -> None:
        window = self.windows.get(window_id)
        if window is not None:
            window.hide()
            self.hidden.add(window_id)

    def _on_runtime(self, key: str) -> None:
        if key != "all_hidden":
            return
        hidden = self._store.state.runtime.all_hidden
        if not hidden:
            self.hidden.clear()
        for window in self.windows.values():
            window.setVisible(not hidden)

    def close_all(self) -> None:
        for window in self.windows.values():
            window.close()
