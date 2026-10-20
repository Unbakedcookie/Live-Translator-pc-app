"""T015 — settings persistence (Tier A, pytest-qt for the debounce)."""

import json
import os
from pathlib import Path

import pytest

from livetranslator.core import actions as a
from livetranslator.core import migrations
from livetranslator.core.migrations import MigrationError, NewerSchemaError, migrate
from livetranslator.core.persistence import Persistence, load_config, save_config
from livetranslator.core.state import (
    AppConfig,
    AppState,
    DeviceRef,
    Geometry,
    Source,
    StatusLevel,
    Utterance,
    WindowConfig,
    WindowStyle,
)
from livetranslator.core.store import Store

FULL = AppConfig(
    my_language="es",
    windows=(
        WindowConfig(
            id="w1",
            target_lang="ja",
            sources=(Source.OTHERS, Source.SCREEN),
            style=WindowStyle(
                palette_id="neon",
                bg_opacity=0.5,
                custom_seed="#3B82F6",
                custom_colors=(("bg", "#FFFFFF"), ("speaker_others_3", "#123456")),
            ),
            geometry=Geometry(x=-200, y=1200, width=600, height=240, screen=r"\\.\DISPLAY2"),
            pinned=False,
        ),
    ),
    hotkeys={"pin_all": "Ctrl+Shift+P"},
    models_dir=r"D:\LiveTranslator\models",
    wizard_completed=True,
).model_copy(
    update={
        "audio": AppConfig().audio.model_copy(update={"mic_device": DeviceRef(name="Mic (Yeti)")})
    }
)


def test_round_trip_is_exact(tmp_path: Path):
    path = tmp_path / "settings.json"
    save_config(path, FULL)
    assert load_config(path).config == FULL
    assert load_config(path).notice is None


def test_file_is_readable_json_with_version(tmp_path: Path):
    path = tmp_path / "settings.json"
    save_config(path, FULL)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["schema_version"] == 2
    assert data["windows"][0]["sources"] == ["others", "screen"]
    assert data["windows"][0]["geometry"]["screen"] == r"\\.\DISPLAY2"


def test_missing_file_gives_defaults(tmp_path: Path):
    result = load_config(tmp_path / "nope.json")
    assert result.config == AppConfig()
    assert result.notice is None


@pytest.mark.parametrize(
    "content",
    ["{not json", "[1, 2]", '{"windows": "lots"}', '{"schema_version": -3}', "\udcff"],
    ids=["syntax", "not-object", "bad-field", "bad-version", "bad-encoding"],
)
def test_corrupt_file_is_set_aside(tmp_path: Path, content: str):
    path = tmp_path / "settings.json"
    path.write_bytes(content.encode("utf-8", "surrogateescape"))
    result = load_config(path)
    assert result.config == AppConfig()
    assert not path.exists()
    kept = list(tmp_path.glob("settings.corrupt-*.json"))
    assert len(kept) == 1
    assert kept[0].read_bytes() == content.encode("utf-8", "surrogateescape")
    assert result.notice is not None
    assert kept[0].name in result.notice


def test_newer_schema_is_set_aside_not_overwritten(tmp_path: Path):
    path = tmp_path / "settings.json"
    path.write_text('{"schema_version": 99}', encoding="utf-8")
    result = load_config(path)
    assert result.config == AppConfig()
    assert len(list(tmp_path.glob("settings.newer-version-*.json"))) == 1
    assert "newer version" in (result.notice or "")


def test_unversioned_v0_file_migrates_to_v1(tmp_path: Path):
    path = tmp_path / "settings.json"
    path.write_text('{"my_language": "fr", "lock_layout": true}', encoding="utf-8")
    config = load_config(path).config
    assert config == AppConfig(my_language="fr", lock_layout=True)
    assert config.schema_version == 2


def test_migration_chain(monkeypatch: pytest.MonkeyPatch):
    # A hypothetical v1 -> v2 rename, to check the mechanism chains steps in order.
    def v1_to_v2(data: dict) -> dict:
        data = dict(data)
        data["language"] = data.pop("my_language")
        data["schema_version"] = 2
        return data

    monkeypatch.setitem(migrations.MIGRATIONS, 1, v1_to_v2)
    assert migrate({"my_language": "de"}, target=2) == {"language": "de", "schema_version": 2}
    with pytest.raises(NewerSchemaError):
        migrate({"schema_version": 3}, target=2)
    with pytest.raises(MigrationError, match="no migration"):
        migrate({"schema_version": 2}, target=4)


def test_atomic_write_keeps_old_file_on_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "settings.json"
    save_config(path, AppConfig(my_language="en"))
    original = path.read_bytes()

    def boom(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        save_config(path, AppConfig(my_language="ja"))
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]  # temp file cleaned up


@pytest.fixture
def store(qapp) -> Store:
    return Store(AppState(config=AppConfig(windows=(WindowConfig(id="w1"),))))


def test_debounce_writes_once(qtbot, store: Store, tmp_path: Path):
    path = tmp_path / "settings.json"
    persistence = Persistence(store, path, debounce_ms=100)
    saves: list[int] = []
    persistence.saved.connect(lambda: saves.append(1))
    for opacity in (0.1, 0.2, 0.3, 0.4, 0.5):
        store.dispatch(a.UpdateWindowStyle("w1", {"bg_opacity": opacity}))
    assert not path.exists()
    with qtbot.waitSignal(persistence.saved, timeout=2000):
        pass
    qtbot.wait(250)  # longer than the debounce: no second write may follow
    assert saves == [1]
    assert load_config(path).config.windows[0].style.bg_opacity == 0.5


def test_session_and_runtime_never_written(qtbot, store: Store, tmp_path: Path):
    path = tmp_path / "settings.json"
    persistence = Persistence(store, path, debounce_ms=50)
    store.dispatch(
        a.AddUtterance(
            Utterance(
                id="u1", source=Source.OTHERS, speaker_id="voice:1", start=0.0, committed="secreto"
            )
        )
    )
    store.dispatch(a.RenameSpeaker("voice:1", "Mika"))
    store.dispatch(a.SetStatus("audio", StatusLevel.WARNING, "Mic missing"))
    store.dispatch(a.SetMyLanguage("es"))
    with qtbot.waitSignal(persistence.saved, timeout=2000):
        pass
    text = path.read_text(encoding="utf-8")
    for leaked in ("secreto", "Mika", "voice:1", "Mic missing", "utterances", "statuses"):
        assert leaked not in text


def test_flush_saves_pending_change_now(qtbot, store: Store, tmp_path: Path):
    path = tmp_path / "settings.json"
    persistence = Persistence(store, path, debounce_ms=10_000)
    store.dispatch(a.SetLockLayout(True))
    assert persistence.pending
    persistence.flush()
    assert not persistence.pending
    assert load_config(path).config.lock_layout is True


def test_save_failure_sets_status_then_clears(qtbot, store: Store, tmp_path: Path):
    blocker = tmp_path / "file-not-dir"
    blocker.write_text("x", encoding="utf-8")
    persistence = Persistence(store, blocker / "settings.json", debounce_ms=10)
    persistence.save()
    status = store.state.runtime.statuses["settings"]
    assert status.level is StatusLevel.WARNING
    persistence._path = tmp_path / "ok" / "settings.json"
    persistence.save()
    assert "settings" not in store.state.runtime.statuses


def test_v1_file_drops_the_overlay_mica_option(tmp_path: Path):
    # Schema v2 (G1 feedback): Mica can't render on layered overlay windows.
    path = tmp_path / "settings.json"
    path.write_text(
        '{"schema_version": 1, "windows": [{"id": "w1", "style": {"mica": true, "shadow": true}}]}',
        encoding="utf-8",
    )
    config = load_config(path).config
    assert config.schema_version == 2
    assert config.windows[0].style.shadow is True
