"""T074 — Language Manager actions: download with progress, cancel, remove, in-use warning."""

import threading
from pathlib import Path

from livetranslator.app.language_controller import LanguageController
from livetranslator.core.state import AppConfig, AppState, WindowConfig
from livetranslator.core.store import Store
from livetranslator.services.models import DownloadCancelled, DownloadError, ModelEntry, UrlSource

SHA = "0" * 64


def pair(src: str, tgt: str, size: int = 2) -> ModelEntry:
    return ModelEntry(
        id=f"opus-mt-{src}-{tgt}",
        title=f"{src}-{tgt}",
        kind="translation",
        license="Apache-2.0",
        size_mb=size,
        source=UrlSource(f"https://example.test/{src}-{tgt}.zip", SHA, "zip"),
        dest=f"opus-mt/{src}-{tgt}",
        marker="model.bin",
        languages=(src, tgt),
    )


CATALOG = {e.id: e for e in (pair("pt", "en"), pair("en", "pt"), pair("en", "ja"))}


class FakeManager:
    """Writes the pair's model.bin in two progress steps; can fail or wait to be cancelled."""

    def __init__(self, models: Path, fail: str = "", block: bool = False) -> None:
        self.models, self.fail, self.block = models, fail, block
        self.started = threading.Event()

    def download(self, entry: ModelEntry, progress, cancel) -> Path:
        self.started.set()
        if self.block:
            while not cancel.is_set():
                cancel.wait(0.01)
            raise DownloadCancelled("paused")
        if self.fail and entry.id == self.fail:
            raise DownloadError("Couldn't connect. Check the internet connection.")
        half = (entry.size_mb << 20) // 2
        progress(half, entry.size_mb << 20)
        folder = self.models / entry.dest
        folder.mkdir(parents=True)
        (folder / "model.bin").write_bytes(b"x")
        progress(half * 2, entry.size_mb << 20)
        return folder


def make(qtbot, tmp_path: Path, manager: FakeManager | None = None, **config):
    store = Store(AppState(config=AppConfig(windows=(WindowConfig(id="w"),), **config)))
    fake = manager or FakeManager(tmp_path)
    changed: list[int] = []
    ctl = LanguageController(
        store, lambda: tmp_path, CATALOG, lambda _d: fake, on_changed=lambda: changed.append(1)
    )
    events: list[tuple] = []
    ctl.progress.connect(lambda code, done, total: events.append(("p", code, done, total)))
    ctl.finished.connect(lambda code, ok, msg: events.append(("f", code, ok, msg)))
    return ctl, events, changed, fake


def test_install_downloads_both_directions_with_whole_pack_progress(qtbot, tmp_path: Path):
    ctl, events, changed, _ = make(qtbot, tmp_path)
    assert [p.code for p in ctl.packs()] == ["pt", "ja"]  # app language order
    assert ctl.install("pt")
    qtbot.waitUntil(lambda: any(e[0] == "f" for e in events), timeout=5000)
    progress = [(done, total) for kind, _c, done, total in (e for e in events if e[0] == "p")]
    total = 4 << 20  # two 2 MB pairs
    assert progress[-1] == (total, total) and all(t == total for _, t in progress)
    assert [d for d, _ in progress] == sorted(d for d, _ in progress)  # never goes backwards
    assert events[-1] == ("f", "pt", True, "Portuguese is ready.")
    pack = ctl.pack("pt")
    assert pack is not None and pack.is_installed and changed
    assert not ctl.install("pt")  # nothing missing


def test_a_failed_pair_reports_and_keeps_what_landed(qtbot, tmp_path: Path):
    ctl, events, changed, _ = make(qtbot, tmp_path, FakeManager(tmp_path, fail="opus-mt-en-pt"))
    ctl.install("pt")
    qtbot.waitUntil(lambda: any(e[0] == "f" for e in events), timeout=5000)
    assert events[-1] == ("f", "pt", False, "Couldn't connect. Check the internet connection.")
    pack = ctl.pack("pt")
    assert pack is not None and pack.is_partial and changed  # pt -> en arrived


def test_cancel_pauses_and_only_one_download_at_a_time(qtbot, tmp_path: Path):
    blocking = FakeManager(tmp_path, block=True)
    ctl, events, _, _ = make(qtbot, tmp_path, blocking)
    assert ctl.install("pt")
    assert blocking.started.wait(5)
    assert not ctl.install("ja")  # busy
    ctl.cancel()
    qtbot.waitUntil(lambda: any(e[0] == "f" for e in events), timeout=5000)
    assert events[-1][2] is False and "Paused" in events[-1][3]
    assert ctl.busy is None


def test_remove_and_the_in_use_warning(qtbot, tmp_path: Path):
    ctl, events, changed, _ = make(qtbot, tmp_path, my_language="pt")
    store_windows = ctl._store.state.config.windows  # one window, translating into "en"
    assert store_windows[0].target_lang == "en"
    assert ctl.in_use("pt") == ["it's your language"]
    assert ctl.in_use("ja") == []
    ctl.install("pt")
    qtbot.waitUntil(lambda: any(e[0] == "f" for e in events), timeout=5000)
    changed.clear()
    assert sorted(ctl.remove("pt")) == ["opus-mt-en-pt", "opus-mt-pt-en"]
    assert changed == [1]
    pack = ctl.pack("pt")
    assert pack is not None and not pack.installed
