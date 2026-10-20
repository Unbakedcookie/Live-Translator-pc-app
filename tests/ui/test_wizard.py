"""T073 — the setup wizard, clicked through with a fake downloader and no audio devices."""

from pathlib import Path

from livetranslator.app.setup_controller import Machine, SetupController
from livetranslator.core.state import AppState
from livetranslator.core.store import Store
from livetranslator.theme.tokens import DEFAULT_PALETTE_ID, PALETTES
from livetranslator.ui.wizard.setup_wizard import SetupWizard
from tests.app.test_setup_controller import CATALOG, FakeManager


def make(qtbot, tmp_path: Path, manager: FakeManager | None = None):
    store = Store(AppState())
    fake = manager or FakeManager(tmp_path / "models")
    controller = SetupController(
        store,
        CATALOG,
        tmp_path / "models",
        Machine(cuda=True, vram_mb=12288),
        lambda _d: fake,  # type: ignore[arg-type,return-value]
    )
    wizard = SetupWizard(controller, PALETTES[DEFAULT_PALETTE_ID])
    qtbot.addWidget(wizard)
    wizard.show()
    return store, wizard


def test_click_through_downloads_and_saves(qtbot, tmp_path: Path):
    store, wizard = make(qtbot, tmp_path)
    done: list[int] = []
    wizard.completed.connect(lambda: done.append(1))
    assert wizard.step_label.text() == "Step 1 of 6" and not wizard.back.isVisible()
    wizard.next.click()  # -> languages
    wizard.languages.speak.set_choice("es")
    wizard.next.click()  # -> microphone and speakers (no devices in this test)
    assert wizard.stack.currentWidget() is wizard.audio
    wizard.next.click()  # -> what to download
    assert wizard.next.text() == "Download"
    assert sorted(wizard.downloads.language_boxes) == ["es", "ja"]
    assert wizard.downloads.language_boxes["es"].isChecked()  # common language pre-ticked
    assert wizard.downloads.smart.isChecked()  # 12 GB card: recommended
    assert "To download:" in wizard.downloads.summary.text()
    wizard.next.click()  # -> downloading
    qtbot.waitUntil(lambda: wizard.stack.currentWidget() is wizard.done, timeout=5000)
    assert wizard.next.text() == "Start"
    wizard.next.click()
    assert done == [1]
    config = store.state.config
    assert config.wizard_completed and config.audio.mic_languages == ("es",)
    assert (tmp_path / "models" / "opus-mt" / "es-en" / "model.bin").exists()


def test_pause_and_continue(qtbot, tmp_path: Path):
    blocking = FakeManager(tmp_path / "models", block=True)
    _, wizard = make(qtbot, tmp_path, blocking)
    for _ in range(4):
        wizard.next.click()
    assert wizard.stack.currentWidget() is wizard.downloading
    assert blocking.started.wait(5) and wizard.next.text() == "Pause"
    wizard.next.click()  # pause
    qtbot.waitUntil(lambda: wizard.next.text() == "Continue", timeout=5000)
    assert "Paused" in wizard.downloading.message.text() and wizard.back.isEnabled()


def test_everything_already_here_skips_the_download(qtbot, tmp_path: Path):
    store, wizard = make(qtbot, tmp_path)
    for entry in CATALOG.values():
        folder = tmp_path / "models" / entry.dest
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "model.bin").write_bytes(b"x")
    for _ in range(3):
        wizard.next.click()
    assert wizard.downloads.summary.text() == "Everything is already on this PC."
    wizard.next.click()
    assert wizard.stack.currentWidget() is wizard.done
    wizard.next.click()
    assert store.state.config.wizard_completed


def test_closing_early_means_quit(qtbot, tmp_path: Path):
    _, wizard = make(qtbot, tmp_path)
    left: list[int] = []
    wizard.abandoned.connect(lambda: left.append(1))
    wizard.close()
    assert left == [1]


def test_run_again_starts_from_the_current_settings(qtbot, tmp_path: Path):
    from livetranslator.app.setup_controller import SetupChoices
    from livetranslator.core.state import DeviceRef

    store = Store(AppState())
    controller = SetupController(
        store,
        CATALOG,
        tmp_path / "models",
        Machine(cuda=True, vram_mb=12288),
        lambda _d: FakeManager(tmp_path / "models"),  # type: ignore[arg-type,return-value]
    )
    saved = SetupChoices(
        my_language="ja", mic_languages=("es", "en"), mic_device=DeviceRef(name="Mic"), smart=False
    )
    wizard = SetupWizard(controller, PALETTES[DEFAULT_PALETTE_ID], choices=saved, first_run=False)
    qtbot.addWidget(wizard)
    assert wizard.languages.read.current_code() == "ja"
    assert wizard.languages.speak.current_choice() == "es"
    assert wizard.languages.also.codes() == ("en",)
    assert not wizard.downloads.smart.isChecked()  # the saved choice, not the recommendation
    left: list[int] = []
    wizard.abandoned.connect(lambda: left.append(1))
    wizard.close()
    assert left == []  # closing a later run doesn't quit the app


def test_settings_offer_to_run_setup_again(qtbot, tmp_path: Path):
    from PySide6.QtWidgets import QPushButton

    from livetranslator.app.settings_controller import SettingsController
    from livetranslator.app.window_controller import WindowController
    from livetranslator.ui.settings.advanced_page import AdvancedPage
    from livetranslator.ui.settings.context import SettingsContext

    store = Store(AppState())
    runs: list[int] = []
    ctx = SettingsContext(
        SettingsController(store),
        WindowController(store),
        tmp_path,
        tmp_path,
        lambda _p: None,
        run_setup=lambda: runs.append(1),
    )
    page = AdvancedPage(ctx)
    qtbot.addWidget(page)
    [button] = [b for b in page.findChildren(QPushButton) if b.text() == "Run setup"]
    button.click()
    assert runs == [1]


def test_nvidia_libraries_come_with_their_licence(qtbot, tmp_path: Path, monkeypatch):
    """D-026 (user OK 2026-10-19): downloaded from NVIDIA's own package, licence linked."""
    from PySide6.QtGui import QDesktopServices

    from livetranslator.app.setup_controller import NVIDIA_LICENSE_URL

    opened: list[str] = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url.toString()))
    _, wizard = make(qtbot, tmp_path)
    assert wizard.downloads.nvidia_licence is None  # libraries already loadable
    controller = SetupController(
        Store(AppState()),
        CATALOG,
        tmp_path / "models",
        Machine(cuda=True, vram_mb=12288, gpu_runtime=False),
        lambda _d: FakeManager(tmp_path / "models"),  # type: ignore[arg-type,return-value]
    )
    wizard = SetupWizard(controller, PALETTES[DEFAULT_PALETTE_ID])
    qtbot.addWidget(wizard)
    button = wizard.downloads.nvidia_licence
    assert button is not None
    button.click()
    assert opened == [NVIDIA_LICENSE_URL]
