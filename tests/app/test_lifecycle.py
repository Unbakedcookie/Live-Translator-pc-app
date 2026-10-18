"""T063/T064 — export writes only when asked; quit asks first when there's a conversation."""

from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import QWidget

from livetranslator.app.lifecycle import Exporter, QuitFlow, suggested_name, write_text_atomic
from livetranslator.core import actions as a
from livetranslator.core.state import AppState, Source, Utterance
from livetranslator.core.store import Store
from livetranslator.ui.dialogs import QuitChoice

NOW = datetime(2026, 10, 18, 1, 30)


def store_with_line() -> Store:
    store = Store(AppState())
    store.dispatch(
        a.AddUtterance(
            Utterance(
                id="u1",
                source=Source.OTHERS,
                speaker_id="voice:0",
                start=1.0,
                committed="hola",
                language="es",
                is_final=True,
            )
        )
    )
    return store


class Fakes:
    def __init__(self, answer: QuitChoice, path: Path | None) -> None:
        self.answer = answer
        self.path = path
        self.asked_paths: list[Path] = []
        self.asked_quit = 0
        self.quits = 0
        self.errors: list[str] = []

    def ask_path(self, _parent: QWidget | None, suggested: Path) -> Path | None:
        self.asked_paths.append(suggested)
        return self.path

    def ask_quit(self, _parent: QWidget | None) -> QuitChoice:
        self.asked_quit += 1
        return self.answer

    def quit(self) -> None:
        self.quits += 1


def flow(store: Store, fakes: Fakes, folder: Path) -> QuitFlow:
    exporter = Exporter(store, fakes.ask_path, clock=lambda: NOW, folder=lambda: folder)
    return QuitFlow(store, exporter, fakes.ask_quit, fakes.quit, fakes.errors.append)


def test_empty_log_quits_without_asking(tmp_path: Path):
    fakes = Fakes(QuitChoice.CANCEL, None)
    assert flow(Store(AppState()), fakes, tmp_path).request_quit()
    assert fakes.quits == 1 and fakes.asked_quit == 0


def test_cancel_keeps_running(tmp_path: Path):
    fakes = Fakes(QuitChoice.CANCEL, None)
    assert not flow(store_with_line(), fakes, tmp_path).request_quit()
    assert fakes.quits == 0 and fakes.asked_quit == 1 and fakes.asked_paths == []


def test_close_without_saving_quits_and_writes_nothing(tmp_path: Path):
    fakes = Fakes(QuitChoice.DISCARD, None)
    assert flow(store_with_line(), fakes, tmp_path).request_quit()
    assert fakes.quits == 1 and list(tmp_path.iterdir()) == []


def test_export_then_quit(tmp_path: Path):
    target = tmp_path / "chat.txt"
    fakes = Fakes(QuitChoice.EXPORT, target)
    assert flow(store_with_line(), fakes, tmp_path).request_quit()
    assert fakes.quits == 1
    assert fakes.asked_paths == [tmp_path / "Live Translator 2026-10-18 0130.txt"]
    assert "hola" in target.read_text(encoding="utf-8")
    assert [p.name for p in tmp_path.iterdir()] == ["chat.txt"]  # no temp file left


def test_export_cancelled_in_the_save_dialog_stays_open(tmp_path: Path):
    fakes = Fakes(QuitChoice.EXPORT, None)
    assert not flow(store_with_line(), fakes, tmp_path).request_quit()
    assert fakes.quits == 0 and fakes.errors == []


def test_export_failure_is_reported_and_stays_open(tmp_path: Path):
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    fakes = Fakes(QuitChoice.EXPORT, blocker / "chat.txt")  # parent is a file: can't write
    assert not flow(store_with_line(), fakes, tmp_path).request_quit()
    assert fakes.quits == 0 and len(fakes.errors) == 1
    assert fakes.errors[0].startswith("Couldn't save there")


def test_json_export_by_extension(tmp_path: Path):
    target = tmp_path / "chat.json"
    exporter = Exporter(store_with_line(), lambda _p, _s: target, clock=lambda: NOW)
    assert exporter.export() == target
    assert target.read_text(encoding="utf-8").startswith('{\n  "app": "Live Translator"')


def test_second_quit_while_asking_is_ignored(tmp_path: Path):
    store = store_with_line()
    fakes = Fakes(QuitChoice.CANCEL, None)
    quit_flow: QuitFlow | None = None

    def ask_again(_parent: QWidget | None) -> QuitChoice:
        assert quit_flow is not None
        assert not quit_flow.request_quit()  # e.g. tray Quit clicked while the dialog is open
        return QuitChoice.DISCARD

    exporter = Exporter(store, fakes.ask_path, clock=lambda: NOW)
    quit_flow = QuitFlow(store, exporter, ask_again, fakes.quit)
    assert quit_flow.request_quit()
    assert fakes.quits == 1


def test_helpers(tmp_path: Path):
    assert suggested_name(NOW) == "Live Translator 2026-10-18 0130.txt"
    path = tmp_path / "deep" / "a.txt"
    write_text_atomic(path, "line\n")
    assert path.read_bytes() == b"line\n"  # LF on Windows too
