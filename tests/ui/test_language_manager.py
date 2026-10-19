"""T074 — Settings → Languages page: rows, download with progress, remove with a warning."""

from pathlib import Path

import pytest

from livetranslator.app.language_controller import LanguageController
from livetranslator.app.settings_controller import SettingsController
from livetranslator.app.window_controller import WindowController
from livetranslator.core.state import AppConfig, AppState, WindowConfig
from livetranslator.core.store import Store
from livetranslator.ui import language_manager
from livetranslator.ui.language_manager import LanguagesPage, pack_description, size_text
from livetranslator.ui.settings.context import SettingsContext
from tests.app.test_language_controller import CATALOG, FakeManager, pair


def make_page(qtbot, tmp_path: Path, catalog=CATALOG, **config):
    store = Store(AppState(config=AppConfig(windows=(WindowConfig(id="w"),), **config)))
    fake = FakeManager(tmp_path)
    controller = LanguageController(store, lambda: tmp_path, catalog, lambda _d: fake)
    ctx = SettingsContext(
        settings=SettingsController(store),
        windows=WindowController(store),
        models_dir=tmp_path,
        log_dir=tmp_path,
        open_folder=lambda _p: None,
        languages=controller,
    )
    page = LanguagesPage(ctx)
    qtbot.addWidget(page)
    return page, controller


def test_sizes_and_descriptions():
    assert size_text(389) == "389 MB" and size_text(2382) == "2.3 GB"
    from livetranslator.services.language_packs import LanguagePack

    th = LanguagePack("th", (pair("th", "en", 150),), frozenset())
    assert pack_description(th).startswith("Into English only")
    pt = LanguagePack("pt", (pair("pt", "en"), pair("en", "pt")), frozenset({"opus-mt-pt-en"}))
    assert "partly downloaded, 2 MB to go" in pack_description(pt)


def test_download_then_remove(qtbot, tmp_path: Path):
    page, _ = make_page(qtbot, tmp_path)
    assert list(page.rows) == ["pt", "ja"]
    row, control = page.rows["pt"]
    assert row.title.text() == "Portuguese · Português"
    assert row.description.text() == "To and from English · 4 MB · Apache-2.0"
    assert control.button.text() == "Download"
    control.button.click()
    qtbot.waitUntil(lambda: control.button.text() == "Remove", timeout=5000)
    assert control.status.text() == "Installed" and not control.progress.isVisibleTo(page)
    assert page.message.text() == "Portuguese is ready."
    control.button.click()  # not in use: removed without asking
    assert control.button.text() == "Download"
    assert page.message.text() == "Portuguese removed."


def test_removing_a_language_in_use_asks_first(qtbot, tmp_path: Path, monkeypatch):
    page, _ = make_page(qtbot, tmp_path, my_language="pt")
    _row, control = page.rows["pt"]
    control.button.click()
    qtbot.waitUntil(lambda: control.button.text() == "Remove", timeout=5000)
    asked: list[list[str]] = []

    def keep(_parent, _palette, _name, reasons) -> bool:
        asked.append(reasons)
        return False

    monkeypatch.setattr(language_manager, "confirm_remove_language", keep)
    control.button.click()
    assert asked == [["it's your language"]] and control.button.text() == "Remove"


def test_no_catalogue_entries_shows_a_plain_note(qtbot, tmp_path: Path):
    page, _ = make_page(qtbot, tmp_path, catalog={})
    assert page.rows == {} and "aren't available" in page.empty.text()


@pytest.mark.parametrize("code", ["pt", "ja"])
def test_one_download_at_a_time_disables_the_other_rows(qtbot, tmp_path: Path, code: str):
    page, controller = make_page(qtbot, tmp_path)
    blocking = FakeManager(tmp_path, block=True)
    controller._make_manager = lambda _d: blocking  # pyright: ignore[reportPrivateUsage]
    other = "ja" if code == "pt" else "pt"
    page.rows[code][1].button.click()
    assert blocking.started.wait(5)
    assert page.rows[code][1].button.text() == "Cancel"
    assert not page.rows[other][1].button.isEnabled()
    page.rows[code][1].button.click()  # cancel
    qtbot.waitUntil(lambda: page.rows[other][1].button.isEnabled(), timeout=5000)
    assert "Paused" in page.message.text()
