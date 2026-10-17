"""The central store: single source of truth (T014; spec §6.3, §6.4).

- Holds the current AppState; only `reduce` produces new states.
- `dispatch` is thread-safe. On the store's own (main) thread the action is applied at once;
  from any other thread it is queued to the main thread, so reducers and signal handlers
  always run on the UI thread and widgets never see a half-applied state.
- Signals are narrow (one window, one utterance), so widgets only redraw what changed.
- Invalid actions never raise out of `dispatch`: they are logged (type only, never values,
  which may contain transcript text) and reported through `action_failed`.
"""

from __future__ import annotations

from loguru import logger
from PySide6.QtCore import QObject, Qt, QThread, Signal

from livetranslator.core.actions import Action
from livetranslator.core.reducers import Change, ChangeKind, reduce
from livetranslator.core.state import AppState


class Store(QObject):
    config_changed = Signal(str)  # section, "windows" or "all"
    window_changed = Signal(str)  # window id (added, removed or changed)
    utterance_added = Signal(str)
    utterance_updated = Signal(str)
    utterance_removed = Signal(str)
    session_cleared = Signal()
    speaker_changed = Signal(str)  # speaker id
    runtime_changed = Signal(str)  # "status:<key>", "metric:<name>", "all_hidden"
    action_failed = Signal(str)  # action type name

    _queued = Signal(object)

    def __init__(self, state: AppState | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._state = state if state is not None else AppState()
        self._queued.connect(self._apply, Qt.ConnectionType.QueuedConnection)

    @property
    def state(self) -> AppState:
        return self._state

    def dispatch(self, action: Action) -> None:
        """Apply `action` (now on the main thread, queued from any other thread)."""
        if QThread.currentThread() is self.thread():
            self._apply(action)
        else:
            self._queued.emit(action)

    def _apply(self, action: Action) -> None:
        try:
            self._state, changes = reduce(self._state, action)
        except ValueError as exc:
            # The message may echo rejected values (possibly transcript text): log the type only.
            logger.warning("action {} rejected ({})", type(action).__name__, type(exc).__name__)
            self.action_failed.emit(type(action).__name__)
            return
        for change in changes:
            self._emit(change)

    def _emit(self, change: Change) -> None:
        match change.kind:
            case ChangeKind.CONFIG:
                self.config_changed.emit(change.key)
            case ChangeKind.WINDOW:
                self.window_changed.emit(change.key)
            case ChangeKind.UTTERANCE_ADDED:
                self.utterance_added.emit(change.key)
            case ChangeKind.UTTERANCE_UPDATED:
                self.utterance_updated.emit(change.key)
            case ChangeKind.UTTERANCE_REMOVED:
                self.utterance_removed.emit(change.key)
            case ChangeKind.SESSION_CLEARED:
                self.session_cleared.emit()
            case ChangeKind.SPEAKER:
                self.speaker_changed.emit(change.key)
            case ChangeKind.RUNTIME:
                self.runtime_changed.emit(change.key)
