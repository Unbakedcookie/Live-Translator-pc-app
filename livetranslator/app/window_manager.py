"""Creates/destroys FloatingWindows as the store's window list changes (T024; spec §5.1).

Also places new windows (default bottom-centre placement, cascading), restores saved ones
onto existing monitors, and shows each window unless the store says it's put away (hide-all,
or one window hidden / minimized; runtime only). Minimized windows come back from a taskbar
button (`TaskbarButton`).
Closing the last window calls `on_last_closed`: with a tray icon (T071) the app keeps running
there; without a system tray it quits (spec §5.11).
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, Signal

from livetranslator.app.window_controller import WindowController
from livetranslator.core.state import Away
from livetranslator.core.store import Store
from livetranslator.ui.floating_window import FloatingWindow
from livetranslator.ui.geometry import Rect, default_placement, monitor_for, restore
from livetranslator.ui.screens import monitors, rect_from_qrect
from livetranslator.ui.taskbar_button import TaskbarButton


class WindowManager(QObject):
    settings_requested = Signal()  # a window's menu asked for Settings (T072)
    transcript_requested = Signal()  # ... or for the transcript (T063)
    screen_region_requested = Signal()  # ... or to translate a screen region (T083)
    window_hidden = Signal()  # "Hide this window": the tray says how to get it back

    def __init__(
        self,
        store: Store,
        controller: WindowController,
        quit_app: Callable[[], object],
        parent: QObject | None = None,
        on_last_closed: Callable[[], object] | None = None,
        taskbar: TaskbarButton | None = None,
    ) -> None:
        super().__init__(parent)
        self._store = store
        self._controller = controller
        self._quit_app = quit_app
        self._on_last_closed = on_last_closed or quit_app
        self.windows: dict[str, FloatingWindow] = {}
        self.taskbar = taskbar
        if taskbar is not None:
            taskbar.restore_requested.connect(controller.restore_minimized)
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
            window.close()
            window.deleteLater()
            if not self.windows:
                self._on_last_closed()

    def _create(self, window_id: str) -> None:
        window = FloatingWindow(self._controller, window_id, self.other_rects)
        window.hide_requested.connect(self.hide_window)
        window.minimize_requested.connect(self.minimize_window)
        window.new_window_requested.connect(self._controller.add_window)
        window.quit_requested.connect(self._quit_app)
        window.settings_requested.connect(self.settings_requested)
        window.transcript_requested.connect(self.transcript_requested)
        window.screen_region_requested.connect(self.screen_region_requested)
        self.windows[window_id] = window
        self._place(window_id, index=len(self.windows) - 1)
        if self._shown(window_id):
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
        self._controller.set_away(window_id, Away.HIDDEN)
        self.window_hidden.emit()

    def minimize_window(self, window_id: str) -> None:
        self._controller.set_away(window_id, Away.MINIMIZED)

    def _shown(self, window_id: str) -> bool:
        runtime = self._store.state.runtime
        return not runtime.all_hidden and window_id not in runtime.away

    def _on_runtime(self, key: str) -> None:
        if key not in ("all_hidden", "away"):
            return
        for window_id, window in self.windows.items():
            window.setVisible(self._shown(window_id))
        if self.taskbar is not None:
            self.taskbar.set_on_taskbar(Away.MINIMIZED in self._store.state.runtime.away.values())

    def close_all(self) -> None:
        if self.taskbar is not None:
            self.taskbar.set_on_taskbar(False)  # it refuses close events: Qt's quit would stop
        for window in self.windows.values():
            window.close()
