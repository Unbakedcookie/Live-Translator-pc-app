"""T014 — store: thread-safe dispatch and narrow signals (Tier A, pytest-qt)."""

import threading

import pytest
from PySide6.QtCore import QThread

from livetranslator.core import actions as a
from livetranslator.core.state import AppConfig, AppState, Source, Utterance, WindowConfig
from livetranslator.core.store import Store

SIGNALS = (
    "config_changed",
    "window_changed",
    "utterance_added",
    "utterance_updated",
    "utterance_removed",
    "session_cleared",
    "speaker_changed",
    "runtime_changed",
    "action_failed",
)


class Recorder:
    """Records every store signal as (signal name, args...) in emission order."""

    def __init__(self, store: Store) -> None:
        self.events: list[tuple] = []
        self.threads: list[QThread] = []
        for name in SIGNALS:
            getattr(store, name).connect(lambda *args, n=name: self._record(n, *args))

    def _record(self, name: str, *args) -> None:
        self.events.append((name, *args))
        self.threads.append(QThread.currentThread())


@pytest.fixture
def store(qapp) -> Store:
    return Store(AppState(config=AppConfig(windows=(WindowConfig(id="w1"), WindowConfig(id="w2")))))


def utt(uid: str) -> Utterance:
    return Utterance(id=uid, source=Source.OTHERS, speaker_id="others", start=0.0, committed=uid)


def test_main_thread_dispatch_is_immediate_and_narrow(store: Store):
    rec = Recorder(store)
    store.dispatch(a.UpdateWindowStyle("w2", {"shadow": True}))
    assert store.state.config.windows[1].style.shadow is True
    # A style change touches one window (+ persisted config), nothing in the chat log.
    assert rec.events == [("window_changed", "w2"), ("config_changed", "windows")]


def test_noop_emits_nothing(store: Store):
    rec = Recorder(store)
    store.dispatch(a.UpdateWindow("w1", {"pinned": True}))
    assert rec.events == []


def test_session_signals(store: Store):
    rec = Recorder(store)
    store.dispatch(a.AddUtterance(utt("u1")))
    store.dispatch(a.SetTranslation("u1", "en", "hi"))
    store.dispatch(a.RenameSpeaker("voice:1", "Mika"))
    store.dispatch(a.RemoveUtterance("u1"))
    store.dispatch(a.ClearSession())
    assert rec.events == [
        ("utterance_added", "u1"),
        ("utterance_updated", "u1"),
        ("speaker_changed", "voice:1"),
        ("utterance_removed", "u1"),
        ("session_cleared",),
    ]


def test_invalid_action_is_reported_not_raised(store: Store):
    rec = Recorder(store)
    before = store.state
    store.dispatch(a.UpdateWindowStyle("w1", {"bg_opacity": 7.0}))
    assert store.state is before
    assert rec.events == [("action_failed", "UpdateWindowStyle")]


def test_worker_thread_dispatch_runs_on_main_thread(qtbot, store: Store):
    rec = Recorder(store)
    worker_thread_ids: list[int] = []

    def worker() -> None:
        worker_thread_ids.append(threading.get_ident())
        store.dispatch(a.AddUtterance(utt("from-worker")))

    with qtbot.waitSignal(store.utterance_added, timeout=2000):
        t = threading.Thread(target=worker)
        t.start()
        t.join()
        # Queued: nothing is applied until the main thread's event loop runs.
        assert store.state.session.utterances == ()
    assert [u.id for u in store.state.session.utterances] == ["from-worker"]
    assert rec.events == [("utterance_added", "from-worker")]
    assert rec.threads == [store.thread()]
    assert worker_thread_ids[0] != threading.get_ident()


def test_many_threads_keep_per_thread_order(qtbot, store: Store):
    def worker(prefix: str) -> None:
        for i in range(100):
            store.dispatch(a.AddUtterance(utt(f"{prefix}-{i}")))

    threads = [threading.Thread(target=worker, args=(p,)) for p in ("me", "others")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    qtbot.waitUntil(lambda: len(store.state.session.utterances) == 200, timeout=5000)
    ids = [u.id for u in store.state.session.utterances]
    for prefix in ("me", "others"):
        assert [i for i in ids if i.startswith(prefix)] == [f"{prefix}-{n}" for n in range(100)]
