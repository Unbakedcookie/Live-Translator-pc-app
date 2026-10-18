# ruff: noqa: RUF001  (real Chinese punctuation on purpose)
"""T083 — screen translation flow with a fake grabber and fake readers."""

import numpy as np

from livetranslator.app.ocr_controller import STATUS_KEY, OcrController, new_lines
from livetranslator.core.state import AppConfig, AppState, Source, StatusLevel, WindowConfig
from livetranslator.core.store import Store
from livetranslator.services.errors import UnsupportedLanguage
from livetranslator.services.ocr.base import OcrLine, OcrResult
from livetranslator.services.ocr.grab import Region

IMAGE = np.zeros((10, 10, 3), dtype=np.uint8)
REGION = Region(100, 200, 400, 120)


class Reader:
    def __init__(self, name: str, rows: list[str], fail: bool = False) -> None:
        self.name = name
        self.rows = rows
        self.fail = fail
        self.calls = 0

    def available_languages(self) -> set[str]:
        return {"zh", "en"}

    def recognize(self, image, language=None) -> OcrResult:
        self.calls += 1
        if self.fail:
            raise UnsupportedLanguage("no pack")
        return OcrResult(tuple(OcrLine(r, (0, i * 20, 100, 18)) for i, r in enumerate(self.rows)))


ONE_WINDOW = (WindowConfig(id="w"),)


def make(readers, windows=ONE_WINDOW):
    store = Store(AppState(config=AppConfig(windows=windows)))
    opened: list[Region] = []
    grabs: list[Region] = []

    def grab(region: Region):
        grabs.append(region)
        return IMAGE

    ctl = OcrController(store, readers, grab, opened.append, clock=lambda: 50.0)
    return store, ctl, opened, grabs


def screen_lines(store: Store) -> list[tuple[str, str | None]]:
    return [
        (u.text, u.language) for u in store.state.session.utterances if u.source is Source.SCREEN
    ]


def test_new_lines_skips_rows_already_shown():
    assert new_lines(["a  b", "C", "", "c", "d"], ["A B"]) == ["C", "d"]


def test_each_row_becomes_a_finished_screen_line_with_its_language():
    store, ctl, _, grabs = make(
        [Reader("rapid", ["队长：在桥那边集合", "Quest complete: return to town"])]
    )
    assert ctl.run(REGION) == 2
    assert grabs == [REGION]
    assert screen_lines(store) == [
        ("队长：在桥那边集合", "zh"),
        ("Quest complete: return to town", "en"),
    ]
    first = store.state.session.utterances[0]
    assert first.is_final and first.speaker_id == "screen"
    assert STATUS_KEY not in store.state.runtime.statuses  # done: busy message cleared


def test_recapture_adds_only_new_rows():
    reader = Reader("rapid", ["hello there friends", "see you at the gate"])
    store, ctl, _, _ = make([reader])
    ctl.run(REGION)
    reader.rows = ["see you at the gate", "on my way now"]  # chat scrolled by one row
    assert ctl.run(REGION) == 1
    assert [t for t, _ in screen_lines(store)][-1] == "on my way now"
    assert ctl.run(REGION) == 0
    assert store.state.runtime.statuses[STATUS_KEY].message == "No new text there."


def test_falls_back_to_the_next_reader():
    failing = Reader("rapid", [], fail=True)
    empty = Reader("windows", [])
    store, ctl, _, _ = make([failing, empty])
    assert ctl.run(REGION) == 0
    assert store.state.runtime.statuses[STATUS_KEY].message == "No text found there."
    failing = Reader("rapid", [], fail=True)
    good = Reader("windows", ["good game everyone"])
    store, ctl, _, _ = make([failing, good])
    assert ctl.run(REGION) == 1 and failing.calls == 1 and good.calls == 1


def test_grab_failure_is_reported():
    store = Store(AppState())

    def broken(region: Region):
        raise OSError("screen locked")

    ctl = OcrController(store, [Reader("rapid", ["x"])], broken, lambda r: None)
    assert ctl.run(REGION) == 0
    assert store.state.runtime.statuses[STATUS_KEY].level is StatusLevel.WARNING


def test_first_capture_opens_a_screen_window_and_recapture_needs_a_region(qtbot):
    store, ctl, opened, _ = make([Reader("rapid", [])])
    assert not ctl.recapture()
    assert "Pick a screen region" in store.state.runtime.statuses[STATUS_KEY].message
    ctl.capture(REGION)
    assert opened == [REGION] and ctl.last_region == REGION
    screen = (WindowConfig(id="s", sources=(Source.SCREEN,)),)
    _, ctl2, opened2, _ = make([Reader("rapid", [])], windows=screen)
    ctl2.capture(REGION)
    assert opened2 == []  # a window already shows Screen lines
    assert ctl2.recapture()
