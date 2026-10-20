"""Settings → Speakers "Separate people talking over each other" (2026-10-20): the switch
downloads what's missing, then turns the feature on; game mode pauses it."""

from pathlib import Path

from PySide6.QtWidgets import QCheckBox

from livetranslator.app.separation_controller import SeparationController
from livetranslator.app.settings_controller import SettingsController
from livetranslator.app.window_controller import WindowController
from livetranslator.core.presets import effective
from livetranslator.core.state import AppConfig, AppState, WindowConfig
from livetranslator.core.store import Store
from livetranslator.services.models import DownloadError, ModelEntry, UrlSource
from livetranslator.services.speakers.separation import OVERLAP_ID, SEPARATION_ID
from livetranslator.ui.settings.context import SettingsContext
from livetranslator.ui.settings.speakers_page import SpeakersPage

SHA = "0" * 64


def entry(entry_id: str, dest: str, size: int) -> ModelEntry:
    return ModelEntry(
        id=entry_id,
        title=entry_id,
        kind="speakers",
        license="MIT",
        size_mb=size,
        source=UrlSource(f"https://example.test/{entry_id}", SHA),
        dest=dest,
        marker="model.onnx",
    )


CATALOG = {
    OVERLAP_ID: entry(OVERLAP_ID, "separation/overlap", 6),
    SEPARATION_ID: entry(SEPARATION_ID, "separation/convtasnet", 20),
}


class FakeManager:
    def __init__(self, models: Path, fail: bool = False) -> None:
        self.models, self.fail = models, fail
        self.downloaded: list[str] = []

    def is_installed(self, e: ModelEntry) -> bool:
        return (self.models / e.dest / e.marker).exists()

    def download(self, e: ModelEntry, progress, cancel) -> Path:
        if self.fail:
            raise DownloadError("Couldn't connect. Check the internet connection.")
        if progress is not None:
            progress((e.size_mb << 20) // 2, e.size_mb << 20)
        folder = self.models / e.dest
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "model.onnx").write_bytes(b"x")
        self.downloaded.append(e.id)
        return folder


def make(tmp_path: Path, catalog=CATALOG, fail: bool = False):
    store = Store(AppState(config=AppConfig(windows=(WindowConfig(id="a"),))))
    manager = FakeManager(tmp_path / "models", fail)
    controller = SeparationController(
        store,
        lambda: tmp_path / "models",
        catalog,
        lambda _d: manager,  # type: ignore[arg-type,return-value]
    )
    return store, controller, manager


def test_turning_it_on_downloads_then_switches_on(qtbot, tmp_path: Path):
    store, controller, manager = make(tmp_path)
    assert controller.available and not controller.installed
    assert controller.download_mb() == 26
    done: list[tuple[bool, str]] = []
    controller.finished.connect(lambda ok, msg: done.append((ok, msg)))
    assert controller.set_enabled(True)
    controller.wait()
    assert manager.downloaded == [OVERLAP_ID, SEPARATION_ID]
    qtbot.waitUntil(lambda: store.state.config.speakers.separate_overlaps, timeout=3000)
    assert controller.installed and done == [(True, "Ready.")]
    assert controller.set_enabled(False)
    assert not store.state.config.speakers.separate_overlaps
    assert controller.set_enabled(True)  # installed now: no download
    assert store.state.config.speakers.separate_overlaps and len(manager.downloaded) == 2


def test_not_downloadable_yet_or_failed_download_leaves_it_off(qtbot, tmp_path: Path):
    _, unavailable, _ = make(tmp_path, {OVERLAP_ID: CATALOG[OVERLAP_ID]})
    assert not unavailable.available and not unavailable.set_enabled(True)
    store, controller, _ = make(tmp_path, fail=True)
    done: list[tuple[bool, str]] = []
    controller.finished.connect(lambda ok, msg: done.append((ok, msg)))
    assert controller.set_enabled(True)
    controller.wait()
    qtbot.waitUntil(lambda: bool(done), timeout=3000)
    assert done == [(False, "Couldn't connect. Check the internet connection.")]
    assert not store.state.config.speakers.separate_overlaps and not controller.busy


def test_game_mode_pauses_it():
    on = AppConfig().model_copy(
        update={"speakers": AppConfig().speakers.model_copy(update={"separate_overlaps": True})}
    )
    assert effective(on).separate_overlaps and not effective(AppConfig()).separate_overlaps
    gaming = on.model_copy(
        update={"performance": on.performance.model_copy(update={"game_mode": True})}
    )
    assert not effective(gaming).separate_overlaps


def test_speakers_page_switch(qtbot, tmp_path: Path):
    store, controller, _ = make(tmp_path)
    ctx = SettingsContext(
        settings=SettingsController(store, lambda _s: None),
        windows=WindowController(store),
        models_dir=tmp_path / "models",
        log_dir=tmp_path / "logs",
        open_folder=lambda _p: None,
        separation=controller,
    )
    page = SpeakersPage(ctx)
    qtbot.addWidget(page)
    box, row = page.overlap, page.overlap_row
    assert isinstance(box, QCheckBox) and row is not None
    assert box.isEnabled() and not box.isChecked()
    assert "downloads 26 MB" in row.description.text()
    box.setChecked(True)  # the user ticks it
    controller.wait()
    qtbot.waitUntil(lambda: store.state.config.speakers.separate_overlaps, timeout=3000)
    page.refresh()
    assert box.isChecked() and "downloads" not in row.description.text()
    box.setChecked(False)
    assert not store.state.config.speakers.separate_overlaps

    _, unavailable, _ = make(tmp_path / "other", {OVERLAP_ID: CATALOG[OVERLAP_ID]})
    ctx.separation = unavailable
    later = SpeakersPage(ctx)
    qtbot.addWidget(later)
    assert later.overlap is not None and not later.overlap.isEnabled()
    assert later.overlap_row is not None
    assert "Not downloadable yet" in later.overlap_row.description.text()
