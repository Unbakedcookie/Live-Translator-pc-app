"""Composition root: builds the store, persistence, controllers, hotkeys and windows (T024;
spec §6.1, §6.2). `run()` is what `python -m livetranslator` starts.
"""

from __future__ import annotations

import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, cast

from loguru import logger
from PySide6.QtCore import QObject, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QWidget

from livetranslator import APP_DISPLAY_NAME, APP_NAME, __version__
from livetranslator.app.discord_controller import DiscordController
from livetranslator.app.language_controller import LanguageController
from livetranslator.app.lifecycle import Exporter, QuitFlow
from livetranslator.app.log import install_excepthook, setup_logging
from livetranslator.app.ocr_controller import OcrController
from livetranslator.app.paths import AppPaths, app_paths
from livetranslator.app.settings_controller import HOTKEY_TITLES, SettingsController
from livetranslator.app.single_instance import SingleInstance, ask_running_copy_to_show, server_name
from livetranslator.app.speech_controller import SpeechController, line_audio_to
from livetranslator.app.translation_controller import TranslationController, target_languages
from livetranslator.app.tray import Tray
from livetranslator.app.window_controller import HOTKEY_ACTIONS, WindowController
from livetranslator.app.window_manager import WindowManager
from livetranslator.core import actions as a
from livetranslator.core.languages import language
from livetranslator.core.persistence import Persistence, load_config
from livetranslator.core.presets import effective
from livetranslator.core.state import AppConfig, AppState, Source, SpeakerMode, StatusLevel
from livetranslator.core.store import Store
from livetranslator.platform.app_identity import register_app_identity, write_icon
from livetranslator.platform.win32 import APP_USER_MODEL_ID, set_app_user_model_id
from livetranslator.services.asr.worker import STATUS_KEY as ASR_STATUS_KEY
from livetranslator.services.asr.worker import ASRWorker
from livetranslator.services.errors import EngineError
from livetranslator.services.hotkeys import HotkeyService, valid_hotkey
from livetranslator.services.language_packs import rough_pairs
from livetranslator.services.metrics import MetricsService, NvmlSampler
from livetranslator.services.models import load_catalog
from livetranslator.services.mt.engines.qwen_llama import QwenLlamaEngine
from livetranslator.services.mt.engines.qwen_llama import installed as qwen_installed
from livetranslator.services.mt.router import TranslationRouter
from livetranslator.services.ocr.base import OcrEngine
from livetranslator.services.ocr.grab import Region, grab
from livetranslator.services.ocr.rapid_ocr import RapidOcrEngine
from livetranslator.services.speakers.discord_rpc import SpeakingTimeline
from livetranslator.services.speakers.worker import SpeakerWorker
from livetranslator.services.timings import Timings
from livetranslator.theme.fonts import bundled_font_files, register_fonts
from livetranslator.theme.icons import icon
from livetranslator.theme.tokens import DEFAULT_PALETTE_ID, PALETTES
from livetranslator.ui.dialogs import ask_export_before_quit, ask_save_path
from livetranslator.ui.geometry import Rect, beside, monitor_for
from livetranslator.ui.region_selector import RegionSelector
from livetranslator.ui.screens import monitors, place_beside
from livetranslator.ui.settings.context import EngineRow, EngineSummary, SettingsContext

# Screens are imported up front, not when first opened: a running app would otherwise load
# them from newer code on disk and mix versions (2026-10-18: Settings failed to open with an
# ImportError after an update).
from livetranslator.ui.settings.settings_window import SettingsWindow
from livetranslator.ui.taskbar_button import TaskbarButton
from livetranslator.ui.transcript_window import TranscriptWindow

if TYPE_CHECKING:
    from livetranslator.services.asr.faster_whisper_engine import FasterWhisperEngine
    from livetranslator.services.mt.engines.opus_mt import Device, OpusMtEngine

# Hotkey actions handled here rather than by the WindowController.
APP_HOTKEY_ACTIONS = ("open_settings", "ocr_region", "ocr_recapture")
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
        self.smart_engine: QwenLlamaEngine | None = None  # optional Qwen (Mandarin follow-up)
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
        self.single_instance: SingleInstance | None = None
        self.region_selector: RegionSelector | None = None
        self.discord = DiscordController(self.store, paths.config_dir, parent=self)
        self.catalog = load_catalog()
        self.languages = LanguageController(
            self.store, self.models_dir, self.catalog, on_changed=self._on_languages_changed
        )
        self.ocr = OcrController(self.store, ocr_engines(), grab, self._open_screen_window)
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
            taskbar=TaskbarButton(
                APP_DISPLAY_NAME, icon("translate", PALETTES[DEFAULT_PALETTE_ID], "accent")
            ),
        )
        self._told_how_to_unhide = False
        self.windows.window_hidden.connect(self._on_window_hidden)
        self.windows.settings_requested.connect(self.open_settings)
        self.windows.transcript_requested.connect(self.open_transcript)
        self.windows.screen_region_requested.connect(self.select_screen_region)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = Tray(
                self.controller,
                self.request_quit,
                self.open_settings,
                parent=self,
                open_transcript=self.open_transcript,
                select_region=self.select_screen_region,
            )
            self.tray.show()
        if speech:
            self._start_speech(self.models_dir())

    def _start_speech(self, models_dir: Path) -> None:
        from livetranslator.services.asr.faster_whisper_engine import FasterWhisperEngine
        from livetranslator.services.mt.engines.opus_mt import OpusMtEngine

        timings = Timings()
        self.mt_engine = OpusMtEngine(models_dir)
        self.smart_engine = QwenLlamaEngine(models_dir) if qwen_installed(models_dir) else None
        self.translation = build_translation(
            self.store, self.mt_engine, timings, self.smart_engine, rough_pairs(self.catalog)
        )
        self.translation.start()
        self.asr_engine = FasterWhisperEngine(models_dir)
        self.speech = build_speech(
            self.store, models_dir, self.asr_engine, timings, self.discord.timeline
        )
        self.speech.start()
        self.discord.apply()  # Discord names, if the user set up their own Discord app
        self.metrics = MetricsService(
            self.store,
            timings,
            NvmlSampler(),
            lambda utterance, state: target_languages(utterance.source, state.config),
            parent=self,
        )
        self.metrics.start()
        self._apply_smart_translation()  # Qwen up before the first line needs it

    def _quit_now(self) -> None:
        """Qt 6 quits by asking every *visible* window to close and cancels the quit if one
        refuses. Settings and Transcript refuse (closing them only hides them), so they are
        hidden first; otherwise Quit silently did nothing while one was open."""
        for window in (self.settings_window, self.transcript_window, self.windows.taskbar):
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

    def show_everything(self) -> None:
        """The app was started again while running: bring every window back (or open one if
        all were closed)."""
        if not self.store.state.config.windows:
            self.controller.add_window()
        self.store.dispatch(a.SetAllHidden(False))

    def _on_window_hidden(self) -> None:
        """Once per run: say where a hidden window comes back from (it has no taskbar button)."""
        if self._told_how_to_unhide:
            return
        self._told_how_to_unhide = True
        shortcut = self.store.state.config.hotkeys.get("show_hide_all")
        how = f" or press {shortcut}" if shortcut else ""
        self._notify(
            f"Window hidden. Click the {APP_DISPLAY_NAME} icon by the clock{how} to show it."
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
            self.transcript_window = TranscriptWindow(
                self.store,
                PALETTES[DEFAULT_PALETTE_ID],
                self.exporter.export,
                lambda: self.exporter.last_error,
            )
            self._place_beside_overlay(self.transcript_window)
        self.transcript_window.bring_to_front()

    def _place_beside_overlay(self, window: QWidget) -> None:
        """First opening: next to the first visible overlay rather than centred over it, so
        the translations stay readable while settings change."""
        overlays = [w for w in self.windows.windows.values() if w.isVisible()]
        if overlays:
            place_beside(window, overlays[0])

    def _on_languages_changed(self) -> None:
        """A language was downloaded or removed (T074): the engine re-reads its pairs; new
        ones load on first use."""
        self._pairs = None
        if self.mt_engine is not None:
            self.mt_engine.rescan(self.models_dir())

    def models_dir(self) -> Path:
        configured = self.store.state.config.models_dir
        return Path(configured) if configured else self.paths.default_models_dir

    # ------------------------------------------------------------ settings (T072)

    def open_settings(self, page: str = "") -> None:
        if self.settings_window is None:
            self.settings_window = SettingsWindow(self.settings_context())
            self._place_beside_overlay(self.settings_window)
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
            smart_translation=qwen_installed(self.models_dir()),
            discord=self.discord,
            languages=self.languages,
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
        smart = self.smart_engine
        if smart is not None:
            now = effective(self.store.state.config)
            where = (
                WHERE["cuda"]
                if smart.is_loaded
                else ("Starts with the first line" if now.smart_wanted else "Off")
            )
            jobs = sorted(language(c).english for c in now.smart_languages)
            if now.smart_fallback:
                jobs.append("languages without their own model")
            names = ", ".join(jobs) or "nothing"
            rows = (*rows, EngineRow("Smarter translation", f"Qwen3-4B ({names})", where))
        return EngineSummary(rows, self._pairs)

    # ------------------------------------------------------------ hotkeys

    def _on_hotkey(self, action: str) -> None:
        if action == "open_settings":
            self.open_settings()
        elif action == "ocr_region":
            self.select_screen_region()
        elif action == "ocr_recapture":
            self.ocr.recapture()
        else:
            self.controller.handle_hotkey(action)

    # ------------------------------------------------------------ screen translation (T083)

    def select_screen_region(self) -> None:
        if self.region_selector is None:
            self.region_selector = RegionSelector(PALETTES[DEFAULT_PALETTE_ID], parent=self)
            self.region_selector.selected.connect(self.ocr.capture)
        self.region_selector.start()

    def _open_screen_window(self, region: Region) -> None:
        """First capture with no window showing Screen lines: one opens beside the region."""
        window_id = self.controller.add_window()
        self.controller.set_sources(window_id, (Source.SCREEN,))
        screens = monitors()
        if screens:
            rect = beside(Rect(region.x, region.y, region.width, region.height), screens)
            self.controller.set_geometry(window_id, rect, monitor_for(rect, screens).name)

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
            if self.mt_engine.set_device(cast("Device", device)) and self.translation:
                self.translation.rewarm()  # game mode moved it: reload what was in use
        if self.smart_engine is not None and section in ("performance", "engines", "all"):
            self._apply_smart_translation()

    def _apply_smart_translation(self) -> None:
        """Start Qwen when it's wanted, stop it (freeing ~2.8 GB) when it isn't, e.g. in game
        mode. Stopping runs off the UI thread: it waits for a line being translated."""
        engine = self.smart_engine
        if engine is None:
            return
        if effective(self.store.state.config).smart_wanted:
            if not engine.is_loaded:
                # Up front, off the UI thread: started on the first line it cost ~3 s plus a
                # ~10 s first request (measured 2026-10-18), and fallback languages can't be
                # known in advance.
                threading.Thread(target=self._start_smart, name="qwen-start", daemon=True).start()
        elif engine.is_loaded:
            threading.Thread(target=engine.unload, name="qwen-stop", daemon=True).start()

    def _start_smart(self) -> None:
        engine = self.smart_engine
        if engine is None:
            return
        try:
            engine.load()
        except EngineError as exc:  # lines fall back to Opus-MT / stay untranslated
            logger.warning("starting Qwen failed ({})", type(exc).__name__)

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
        self.discord.stop()
        if self.speech is not None:
            self.speech.stop()
        if self.translation is not None:
            self.translation.stop()
        if self.smart_engine is not None:
            self.smart_engine.unload()  # never leave a llama-server process behind
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


def ocr_engines() -> list[OcrEngine]:
    """Screen readers in order (T083): RapidOCR reads Chinese, Japanese and Latin text with no
    language setting; Windows OCR covers whatever packs the user installed (e.g. Korean)."""
    engines: list[OcrEngine] = [RapidOcrEngine()]
    if sys.platform == "win32":
        from livetranslator.services.ocr.windows_ocr import WindowsOcrEngine

        engines.append(WindowsOcrEngine())
    return engines


def open_folder(path: Path) -> None:
    """Show a folder in Explorer (created first, so the button never does nothing)."""
    path.mkdir(parents=True, exist_ok=True)
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def partials_allowed(config: AppConfig) -> bool:
    """Spec §5.5: translate partial lines (2x/s) only with a fast engine, never in game mode.
    Opus-MT measured p50 116 ms on GPU / 166 ms on CPU (benchmarks/results/mt.md)."""
    return effective(config).translate_partials


def build_translation(
    store: Store,
    engine: OpusMtEngine,
    timings: Timings | None = None,
    smart: QwenLlamaEngine | None = None,
    rough: frozenset[tuple[str, str]] = frozenset(),
) -> TranslationController:
    """Opus-MT through the router (T051/T053; the G4 default). Game mode puts it on the
    processor (T092). With `smart` (Qwen, when installed), lines from or into the languages
    in Settings → Translation go to it first, falling back to Opus-MT if it fails."""
    engine.set_device(cast("Device", effective(store.state.config).mt_device))
    engine.load()  # picks the device only; each language pair loads on first use

    def preferred(src: str, tgt: str) -> QwenLlamaEngine | None:
        now = effective(store.state.config)
        if smart is None:
            return None
        if src in now.smart_languages or tgt in now.smart_languages:
            return smart
        # A weak downloaded model (e.g. Hindi, D-039) mustn't make lines worse than Qwen did.
        return smart if now.smart_fallback and (src, tgt) in rough else None

    def fallback(src: str, tgt: str) -> QwenLlamaEngine | None:
        wanted = effective(store.state.config).smart_fallback
        return smart if smart is not None and wanted else None

    router = TranslationRouter([engine], timings=timings, preferred=preferred, fallback=fallback)
    return TranslationController(store, router, partials_allowed(store.state.config))


def build_speech(
    store: Store,
    models_dir: Path,
    engine: FasterWhisperEngine,
    timings: Timings | None = None,
    discord: SpeakingTimeline | None = None,
) -> SpeechController:
    """Mic + loopback capture feeding faster-whisper (T045). Heavy imports stay lazy."""
    from livetranslator.services.audio.devices import list_devices
    from livetranslator.services.speakers.sherpa_engine import SherpaEmbedder

    speakers = SpeakerWorker(
        SherpaEmbedder(models_dir),
        store.dispatch,
        discord_intervals=discord.intervals if discord is not None else None,
    )
    worker = ASRWorker(
        engine, store.dispatch, on_line_audio=line_audio_to(speakers), timings=timings
    )
    return SpeechController(store, worker, list_devices, speakers=speakers)


def run(demo: bool = False, speech: bool = True) -> int:
    set_app_user_model_id()  # our own taskbar name/icon (before any window exists)
    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_DISPLAY_NAME)
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(icon("translate", PALETTES[DEFAULT_PALETTE_ID], "accent"))  # dialogs too
    paths = app_paths()
    paths.ensure()
    setup_logging(paths.log_dir)
    install_excepthook()
    if not register_app_identity(  # notifications say "Live Translator", not the raw id
        APP_USER_MODEL_ID, APP_DISPLAY_NAME, write_icon(app.windowIcon(), paths.data_dir)
    ):
        logger.warning("registering the app's notification name failed")
    instance_name = server_name(APP_NAME)
    if not demo and ask_running_copy_to_show(instance_name):
        logger.info("already running: asked that copy to show its windows")
        return 0
    logger.info("{} {} starting", APP_DISPLAY_NAME, __version__)
    live = LiveTranslatorApp(paths, app.quit, speech=speech and not demo)
    if not demo:
        live.single_instance = SingleInstance(instance_name, live.show_everything, live)
    app.aboutToQuit.connect(live.shutdown)
    if demo:
        from livetranslator.app.demo import DemoFeed

        live.demo = DemoFeed(live.store, live)
        live.demo.start()
    return app.exec()
