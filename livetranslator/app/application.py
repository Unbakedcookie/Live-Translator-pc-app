"""Composition root: builds the store, persistence, controllers, hotkeys and windows (T024;
spec §6.1, §6.2). `run()` is what `python -m livetranslator` starts.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, cast

from loguru import logger
from PySide6.QtCore import QObject, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from livetranslator import APP_DISPLAY_NAME, APP_NAME, __version__
from livetranslator.app.lifecycle import Exporter, QuitFlow
from livetranslator.app.log import setup_logging
from livetranslator.app.paths import AppPaths, app_paths
from livetranslator.app.settings_controller import HOTKEY_TITLES, SettingsController
from livetranslator.app.speech_controller import SpeechController, line_audio_to
from livetranslator.app.translation_controller import TranslationController, target_languages
from livetranslator.app.tray import Tray
from livetranslator.app.window_controller import HOTKEY_ACTIONS, WindowController
from livetranslator.app.window_manager import WindowManager
from livetranslator.core import actions as a
from livetranslator.core.persistence import Persistence, load_config
from livetranslator.core.presets import effective
from livetranslator.core.state import AppConfig, AppState, SpeakerMode, StatusLevel
from livetranslator.core.store import Store
from livetranslator.services.asr.worker import STATUS_KEY as ASR_STATUS_KEY
from livetranslator.services.asr.worker import ASRWorker
from livetranslator.services.hotkeys import HotkeyService, valid_hotkey
from livetranslator.services.metrics import MetricsService, NvmlSampler
from livetranslator.services.mt.router import TranslationRouter
from livetranslator.services.speakers.worker import SpeakerWorker
from livetranslator.services.timings import Timings
from livetranslator.theme.fonts import bundled_font_files, register_fonts
from livetranslator.theme.icons import icon
from livetranslator.theme.tokens import DEFAULT_PALETTE_ID, PALETTES
from livetranslator.ui.dialogs import ask_export_before_quit, ask_save_path
from livetranslator.ui.settings.context import EngineRow, EngineSummary, SettingsContext

if TYPE_CHECKING:
    from livetranslator.services.asr.faster_whisper_engine import FasterWhisperEngine
    from livetranslator.services.mt.engines.opus_mt import Device, OpusMtEngine
    from livetranslator.ui.settings.settings_window import SettingsWindow
    from livetranslator.ui.transcript_window import TranscriptWindow

# Hotkey actions handled here rather than by the WindowController.
APP_HOTKEY_ACTIONS = ("open_settings",)
ALL_HOTKEY_ACTIONS = (*HOTKEY_ACTIONS, *APP_HOTKEY_ACTIONS)
WHERE = {"cuda": "Graphics card", "cpu": "Processor"}
STARTING = "Starting…"
NOT_AVAILABLE = "Not available"


class LiveTranslatorApp(QObject):
    def __init__(self, paths: AppPaths, quit_app: Callable[[], None], speech: bool = False) -> None:
        super().__init__()
        register_fonts(bundled_font_files())
        self.paths = paths
        loaded = load_config(paths.settings_file)
        self.store = Store(AppState(config=loaded.config), self)
        self.persistence = Persistence(self.store, paths.settings_file, parent=self)
        if loaded.notice:
            self.store.dispatch(a.SetStatus("settings.load", StatusLevel.WARNING, loaded.notice))
        self.controller = WindowController(self.store)
        self.settings = SettingsController(self.store, self._suspend_hotkeys, ALL_HOTKEY_ACTIONS)
        # Declared before any signal can reach _on_config_changed (adding the first window
        # below emits config_changed).
        self.demo: QObject | None = None  # `--demo` feed (T062)
        self.speech: SpeechController | None = None
        self.translation: TranslationController | None = None
        self.asr_engine: FasterWhisperEngine | None = None
        self.mt_engine: OpusMtEngine | None = None
        self.metrics: MetricsService | None = None
        self.settings_window: SettingsWindow | None = None
        self._pairs: tuple[tuple[str, str], ...] | None = None  # installed MT pairs, read once
        self._hotkeys_suspended = False
        self.hotkeys = HotkeyService(self)
        self.hotkeys.triggered.connect(self._on_hotkey)
        self.store.config_changed.connect(self._on_config_changed)
        self._register_hotkeys()
        if not self.store.state.config.windows:
            self.controller.add_window()
        self.tray: Tray | None = None
        self.transcript_window: TranscriptWindow | None = None
        self._quit_app = quit_app
        self.exporter = Exporter(self.store, ask_save_path)
        self.quit_flow = QuitFlow(
            self.store,
            self.exporter,
            lambda parent: ask_export_before_quit(parent, PALETTES[DEFAULT_PALETTE_ID]),
            self._quit_now,
            show_error=self._notify,
        )
        self.windows = WindowManager(
            self.store,
            self.controller,
            self.request_quit,
            self,
            on_last_closed=self._on_last_closed,
        )
        self.windows.settings_requested.connect(self.open_settings)
        self.windows.transcript_requested.connect(self.open_transcript)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = Tray(
                self.controller,
                self.request_quit,
                self.open_settings,
                parent=self,
                open_transcript=self.open_transcript,
            )
            self.tray.show()
        if speech:
            self._start_speech(self.models_dir())

    def _start_speech(self, models_dir: Path) -> None:
        from livetranslator.services.asr.faster_whisper_engine import FasterWhisperEngine
        from livetranslator.services.mt.engines.opus_mt import OpusMtEngine

        timings = Timings()
        self.mt_engine = OpusMtEngine(models_dir)
        self.translation = build_translation(self.store, self.mt_engine, timings)
        self.translation.start()
        self.asr_engine = FasterWhisperEngine(models_dir)
        self.speech = build_speech(self.store, models_dir, self.asr_engine, timings)
        self.speech.start()
        self.metrics = MetricsService(
            self.store,
            timings,
            NvmlSampler(),
            lambda utterance, state: target_languages(utterance.source, state.config),
            parent=self,
        )
        self.metrics.start()

    def _quit_now(self) -> None:
        """Qt 6 quits by asking every *visible* window to close and cancels the quit if one
        refuses. Settings and Transcript refuse (closing them only hides them), so they are
        hidden first; otherwise Quit silently did nothing while one was open."""
        for window in (self.settings_window, self.transcript_window):
            if window is not None:
                window.hide()
        self._quit_app()

    def _on_last_closed(self) -> None:
        """Spec §5.11: closing the last window doesn't quit while the tray icon is there."""
        if self.tray is None:
            self.request_quit()
            return
        self.tray.notify(
            f"{APP_DISPLAY_NAME} is still running. Use the tray icon to open a new window or quit."
        )

    def _notify(self, message: str) -> None:
        if self.tray is not None:
            self.tray.notify(message)
        else:
            logger.warning("notice not shown (no tray): {}", message)

    # ------------------------------------------------------------ quit + transcript (T063/T064)

    def request_quit(self) -> bool:
        """Every Quit goes through here: asks to export a non-empty conversation first."""
        return self.quit_flow.request_quit(None)

    def open_transcript(self) -> None:
        if self.transcript_window is None:
            from livetranslator.ui.transcript_window import TranscriptWindow

            self.transcript_window = TranscriptWindow(
                self.store,
                PALETTES[DEFAULT_PALETTE_ID],
                self.exporter.export,
                lambda: self.exporter.last_error,
            )
        self.transcript_window.bring_to_front()

    def models_dir(self) -> Path:
        configured = self.store.state.config.models_dir
        return Path(configured) if configured else self.paths.default_models_dir

    # ------------------------------------------------------------ settings (T072)

    def open_settings(self, page: str = "") -> None:
        if self.settings_window is None:
            from livetranslator.ui.settings.settings_window import SettingsWindow

            self.settings_window = SettingsWindow(self.settings_context())
        if page:
            self.settings_window.show_page(page)
        self.settings_window.bring_to_front()

    def settings_context(self) -> SettingsContext:
        speech = self.speech
        return SettingsContext(
            settings=self.settings,
            windows=self.controller,
            models_dir=self.models_dir(),
            log_dir=self.paths.log_dir,
            open_folder=open_folder,
            devices=speech.available_devices if speech is not None else None,
            level_db=speech.level_db if speech is not None else None,
            engines=self.engine_summary,
            hotkey_actions=ALL_HOTKEY_ACTIONS,
        )

    def engine_summary(self) -> EngineSummary:
        """What runs where, for Settings → Translation (read live; engines load in the
        background)."""
        if self.speech is None or self.asr_engine is None or self.mt_engine is None:
            return EngineSummary()
        from livetranslator.services.mt.engines.opus_mt import installed_pairs

        asr = self.asr_engine
        model = asr.model_used or "large-v3-turbo"
        asr_failed = self.store.state.runtime.statuses.get(ASR_STATUS_KEY)
        asr_where = WHERE.get(asr.device_used or "", STARTING)
        if asr.device_used is None and asr_failed and asr_failed.level is StatusLevel.ERROR:
            asr_where = NOT_AVAILABLE
        if self._pairs is None:
            try:
                self._pairs = tuple(sorted(installed_pairs(self.models_dir())))
            except (OSError, ValueError) as exc:  # damaged model folder: show none, don't crash
                logger.warning("listing translation models failed ({})", type(exc).__name__)
                self._pairs = ()
        speakers = self.speech.speakers
        labels_on = (
            speakers is not None
            and speakers.enabled
            and self.store.state.config.speakers.mode is not SpeakerMode.OFF
        )
        rows = (
            EngineRow("Speech recognition", f"Whisper {model}", asr_where),
            EngineRow("Translation", "Opus-MT", WHERE.get(self.mt_engine.device or "", STARTING)),
            EngineRow(
                "Speaker labels",
                "TitaNet voice fingerprints",
                WHERE["cpu"] if labels_on else "Off",
            ),
        )
        return EngineSummary(rows, self._pairs)

    # ------------------------------------------------------------ hotkeys

    def _on_hotkey(self, action: str) -> None:
        if action == "open_settings":
            self.open_settings()
        else:
            self.controller.handle_hotkey(action)

    def _suspend_hotkeys(self, suspended: bool) -> None:
        """Settings is recording a new shortcut: let every key through to it."""
        self._hotkeys_suspended = suspended
        if suspended:
            self.hotkeys.unregister_all()
        else:
            self._register_hotkeys()

    def _on_config_changed(self, section: str) -> None:
        if section in ("hotkeys", "all"):
            self._register_hotkeys()
        if self.translation is not None and section in ("performance", "all"):
            self.translation.translate_partials = partials_allowed(self.store.state.config)
        if self.mt_engine is not None and section in ("performance", "all"):
            device = effective(self.store.state.config).mt_device
            self.mt_engine.set_device(cast("Device", device))  # game mode → processor

    def _register_hotkeys(self) -> None:
        if self._hotkeys_suspended:
            return  # re-registered when recording ends
        bindings = self.store.state.config.hotkeys
        # Release everything first: when two actions swap keys, registering the first one
        # would otherwise collide with our own old registration of the second.
        self.hotkeys.unregister_all()
        for action in ALL_HOTKEY_ACTIONS:
            key = f"hotkey.{action}"
            combo = bindings.get(action)
            if combo is None:
                self.store.dispatch(a.ClearStatus(key))
                continue
            if self.hotkeys.register(action, combo):
                self.store.dispatch(a.ClearStatus(key))
                continue
            title = HOTKEY_TITLES[action]
            if valid_hotkey(combo):
                message = (
                    f"The shortcut {combo} ({title}) is taken by another app. "
                    "Pick a different one in Settings."
                )
            else:  # hand-edited or damaged settings file
                message = f"The saved shortcut for {title} isn't valid. Set it again in Settings."
            self.store.dispatch(a.SetStatus(key, StatusLevel.WARNING, message))

    def shutdown(self) -> None:
        if self.metrics is not None:
            self.metrics.stop()
        if self.speech is not None:
            self.speech.stop()
        if self.translation is not None:
            self.translation.stop()
        self.persistence.flush()
        self.hotkeys.close()
        self.windows.close_all()
        if self.settings_window is not None:
            self.settings_window.hide()
        if self.transcript_window is not None:
            self.transcript_window.hide()
        if self.tray is not None:
            self.tray.hide()
        logger.info("{} stopped", APP_DISPLAY_NAME)


def open_folder(path: Path) -> None:
    """Show a folder in Explorer (created first, so the button never does nothing)."""
    path.mkdir(parents=True, exist_ok=True)
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def partials_allowed(config: AppConfig) -> bool:
    """Spec §5.5: translate partial lines (2x/s) only with a fast engine, never in game mode.
    Opus-MT measured p50 116 ms on GPU / 166 ms on CPU (benchmarks/results/mt.md)."""
    return effective(config).translate_partials


def build_translation(
    store: Store, engine: OpusMtEngine, timings: Timings | None = None
) -> TranslationController:
    """Opus-MT through the router (T051/T053; the G4 default). Game mode puts it on the
    processor (T092)."""
    engine.set_device(cast("Device", effective(store.state.config).mt_device))
    engine.load()  # picks the device only; each language pair loads on first use
    router = TranslationRouter([engine], timings=timings)
    return TranslationController(store, router, partials_allowed(store.state.config))


def build_speech(
    store: Store, models_dir: Path, engine: FasterWhisperEngine, timings: Timings | None = None
) -> SpeechController:
    """Mic + loopback capture feeding faster-whisper (T045). Heavy imports stay lazy."""
    from livetranslator.services.audio.devices import list_devices
    from livetranslator.services.speakers.sherpa_engine import SherpaEmbedder

    speakers = SpeakerWorker(SherpaEmbedder(models_dir), store.dispatch)
    worker = ASRWorker(
        engine, store.dispatch, on_line_audio=line_audio_to(speakers), timings=timings
    )
    return SpeechController(store, worker, list_devices, speakers=speakers)


def run(demo: bool = False, speech: bool = True) -> int:
    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_DISPLAY_NAME)
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(icon("translate", PALETTES[DEFAULT_PALETTE_ID], "accent"))  # dialogs too
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
