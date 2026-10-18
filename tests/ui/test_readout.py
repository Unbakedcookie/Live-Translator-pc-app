"""T093 — readout text (hand-written expectations) and the strip inside an overlay."""

import sys

import pytest

from livetranslator.app.window_controller import WindowController
from livetranslator.core import actions as a
from livetranslator.core.state import AppConfig, AppState, WindowConfig
from livetranslator.core.store import Store
from livetranslator.ui.readout import readout_text

FULL = {
    "gpu_util_pct": 37.0,
    "vram_used_mb": 4198.0,
    "vram_total_mb": 12288.0,
    "asr_p50_ms": 290.0,
    "mt_p50_ms": 76.0,
    "lag_p50_ms": 978.0,
}


def test_full_readout():
    assert readout_text(FULL, game_mode=False) == (
        "GPU 37 % · VRAM 4.1 / 12.0 GB · Speech 290 ms · Translate 76 ms · Lag 0.98 s"
    )
    assert readout_text(FULL, game_mode=True).startswith("Game mode · GPU 37 %")


def test_missing_values_say_n_a():
    assert readout_text({}, game_mode=False) == (
        "GPU n/a · VRAM n/a · Speech n/a · Translate n/a · Lag n/a"
    )
    only_used = {"vram_used_mb": 100.0}  # total unknown: the pair is n/a
    assert "VRAM n/a" in readout_text(only_used, game_mode=False)


@pytest.mark.skipif(sys.platform != "win32", reason="real overlay window")
def test_strip_follows_the_setting_and_metrics(qtbot):
    from livetranslator.ui.floating_window import FloatingWindow

    store = Store(AppState(config=AppConfig(windows=(WindowConfig(id="w"),))))
    window = FloatingWindow(WindowController(store), "w", lambda _id: [])
    qtbot.addWidget(window)
    window.resize(520, 220)
    window.show()
    assert not window.readout.isVisible()
    assert window.content.height() == 220
    store.dispatch(a.UpdateConfigSection("performance", {"show_readout": True}))
    assert window.readout.isVisible()
    assert window.content.height() == 220 - window.readout.height()  # chat makes room
    store.dispatch(a.SetMetric("asr_p50_ms", 300.0))
    assert "Speech 300 ms" in window.readout.text()
    store.dispatch(a.UpdateConfigSection("performance", {"game_mode": True}))
    assert window.readout.text().startswith("Game mode")
    store.dispatch(a.UpdateConfigSection("performance", {"show_readout": False}))
    assert not window.readout.isVisible() and window.content.height() == 220


@pytest.mark.skipif(sys.platform != "win32", reason="real overlay window")
def test_problem_line_appears_above_the_readout(qtbot):
    from livetranslator.core.state import StatusLevel
    from livetranslator.ui.floating_window import FloatingWindow

    store = Store(AppState(config=AppConfig(windows=(WindowConfig(id="w"),))))
    window = FloatingWindow(WindowController(store), "w", lambda _id: [])
    qtbot.addWidget(window)
    window.resize(520, 220)
    window.show()
    assert not window.status_strip.isVisible() and window.content.height() == 220
    store.dispatch(a.SetStatus("audio.me", StatusLevel.WARNING, "No microphone found."))
    assert window.status_strip.isVisible()
    assert window.status_strip.text.text() == "No microphone found."
    status_h = window.status_strip.height()
    assert window.content.height() == 220 - status_h
    store.dispatch(a.UpdateConfigSection("performance", {"show_readout": True}))
    assert window.status_strip.geometry().bottom() < window.readout.geometry().top()
    store.dispatch(a.ClearStatus("audio.me"))
    assert not window.status_strip.isVisible()
    assert window.content.height() == 220 - window.readout.height()
