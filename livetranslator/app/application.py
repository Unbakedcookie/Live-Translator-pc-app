"""Composition root: builds the store, persistence, controllers, hotkeys and windows (T024;
spec §6.1, §6.2). `run()` is what `python -m livetranslator` starts.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

from loguru import logger
from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication

from livetranslator import APP_DISPLAY_NAME, APP_NAME, __version__
from livetranslator.app.log import setup_logging
from livetranslator.app.paths import AppPaths, app_paths
from livetranslator.app.speech_controller import SpeechController
from livetranslator.app.window_controller import HOTKEY_ACTIONS, WindowController
from livetranslator.app.window_manager import WindowManager
from livetranslator.core import actions as a
from livetranslator.core.persistence import Persistence, load_config
from livetranslator.core.state import AppState, StatusLevel
from livetranslator.core.store import Store
from livetranslator.services.asr.worker import ASRWorker
from livetranslator.services.hotkeys import HotkeyService
from livetranslator.theme.fonts import bundled_font_files, register_fonts

HOTKEY_LABELS = {
    "show_hide_all": "show/hide all windows",
    "click_through_all": "click-through",
    "pin_all": "pin all windows",
    "mute_me": "mute Me",
    "mute_others": "mute Others",
    "game_mode": "game mode",
}


class LiveTranslatorApp(QObject):
    def __init__(self, paths: AppPaths, quit_app: Callable[[], None], speech: bool = False) -> None:
        super().__init__()
        register_fonts(bundled_font_files())
        loaded = load_config(paths.settings_file)
        self.store = Store(AppState(config=loaded.config), self)
        self.persistence = Persistence(self.store, paths.settings_file, parent=self)
        if loaded.notice:
            self.store.dispatch(a.SetStatus("settings.load", StatusLevel.WARNING, loaded.notice))
        self.controller = WindowController(self.store)
        self.hotkeys = HotkeyService(self)
        self.hotkeys.triggered.connect(self.controller.handle_hotkey)
        self.store.config_changed.connect(self._on_config_changed)
        self._register_hotkeys()
        if not self.store.state.config.windows:
            self.controller.add_window()
        self.windows = WindowManager(self.store, self.controller, quit_app, self)
        self.demo: QObject | None = None  # `--demo` feed (T062)
        self.speech: SpeechController | None = None
        if speech:
            self.speech = build_speech(self.store, paths)
            self.speech.start()

    def _on_config_changed(self, section: str) -> None:
        if section in ("hotkeys", "all"):
            self._register_hotkeys()

    def _register_hotkeys(self) -> None:
        bindings = self.store.state.config.hotkeys
        for action in HOTKEY_ACTIONS:
            key = f"hotkey.{action}"
            combo = bindings.get(action)
            if combo is None:
                self.hotkeys.unregister(action)
                continue
            if self.hotkeys.register(action, combo):
                self.store.dispatch(a.ClearStatus(key))
            else:
                self.store.dispatch(
                    a.SetStatus(
                        key,
                        StatusLevel.WARNING,
                        f"The shortcut {combo} ({HOTKEY_LABELS[action]}) is taken by another "
                        "app. Pick a different one in Settings.",
                    )
                )

    def shutdown(self) -> None:
        if self.speech is not None:
            self.speech.stop()
        self.persistence.flush()
        self.hotkeys.close()
        self.windows.close_all()
        logger.info("{} stopped", APP_DISPLAY_NAME)


def build_speech(store: Store, paths: AppPaths) -> SpeechController:
    """Mic + loopback capture feeding faster-whisper (T045). Heavy imports stay lazy."""
    from livetranslator.services.asr.faster_whisper_engine import FasterWhisperEngine
    from livetranslator.services.audio.devices import list_devices

    configured = store.state.config.models_dir
    models_dir = Path(configured) if configured else paths.default_models_dir
    engine = FasterWhisperEngine(models_dir)
    worker = ASRWorker(engine, store.dispatch)
    return SpeechController(store, worker, list_devices)


def run(demo: bool = False, speech: bool = True) -> int:
    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_DISPLAY_NAME)
    app.setQuitOnLastWindowClosed(False)
    paths = app_paths()
    paths.ensure()
    setup_logging(paths.log_dir)
    logger.info("{} {} starting", APP_DISPLAY_NAME, __version__)
    live = LiveTranslatorApp(paths, app.quit, speech=speech and not demo)
    app.aboutToQuit.connect(live.shutdown)
    if demo:
        from livetranslator.app.demo import DemoFeed

        live.demo = DemoFeed(live.store, live)
        live.demo.start()
    return app.exec()
