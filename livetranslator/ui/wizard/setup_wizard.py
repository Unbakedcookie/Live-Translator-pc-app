"""The first-run setup wizard (T073; spec §5.9; gate G3).

Welcome + privacy → languages → microphone and speakers (live meters) → what to download
(sizes, free space, model folder) → download (one progress bar, pause / continue) → done.
Built from the Settings building blocks so it looks like the rest of the app. It only shows
and collects choices: planning, downloading and saving are the SetupController's job.
Closing it before the end quits the app (nothing works without the speech model); the
downloads continue where they stopped next time.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QHideEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from livetranslator import APP_DISPLAY_NAME
from livetranslator.app.level_probe import LevelProbe
from livetranslator.app.settings_controller import mic_choice, mic_languages_for
from livetranslator.app.setup_controller import (
    SetupChoices,
    SetupController,
    SetupPlan,
    preticked,
)
from livetranslator.core.languages import language
from livetranslator.core.state import DEFAULT_HOTKEYS, Source
from livetranslator.services.language_packs import LanguagePack
from livetranslator.theme.icons import icon
from livetranslator.theme.qss import settings_qss, window_qss
from livetranslator.theme.tokens import SETTINGS, SPACE, Palette
from livetranslator.ui.language_manager import pack_description, size_text
from livetranslator.ui.session import session_ending
from livetranslator.ui.settings.audio_page import device_choices
from livetranslator.ui.settings.general_page import also_items, speak_items
from livetranslator.ui.settings.level_meter import LevelMeter
from livetranslator.ui.settings.rows import SettingsPage, note
from livetranslator.ui.widgets.choice_combo import ChoiceCombo
from livetranslator.ui.widgets.language_picker import LanguagePicker

METER_MS = 66
PROGRESS_STEPS = 1000


class WelcomePage(SettingsPage):
    title_text = f"Welcome to {APP_DISPLAY_NAME}"

    def __init__(self) -> None:
        super().__init__()
        self.intro(
            "Live Translator shows what you and the people you talk to are saying, translated, "
            "in small windows over your game. It can also translate text on your screen."
        )
        privacy = self.section("Your privacy")
        privacy.row(
            "Everything runs on this PC",
            "Nothing anyone says is sent over the internet. Conversations are kept in memory "
            "only and are gone when the app closes, unless you export them. Logs never "
            "contain what anyone said.",
        )
        privacy.row(
            "The only downloads are the models",
            "The next steps pick your languages and devices, then download the speech and "
            "translation models once. You can pause and continue.",
        )
        self.finish()


class LanguagesStep(SettingsPage):
    title_text = "Your languages"

    def __init__(self, palette: Palette, choices: SetupChoices) -> None:
        super().__init__()
        first, also = mic_choice(choices.mic_languages)
        self.read = LanguagePicker(choices.my_language)
        self.read.setFixedWidth(SETTINGS.control_width)
        self.read.apply_palette(palette)
        self.speak = ChoiceCombo(speak_items(), first)
        self.speak.setFixedWidth(SETTINGS.control_width)
        self.speak.apply_palette(palette)
        self.also = ChoiceCombo(also_items(), also)
        self.also.setFixedWidth(SETTINGS.control_width)
        self.also.apply_palette(palette)
        section = self.section()
        section.row(
            "Translate into", "The language you read. Windows translate into it.", self.read
        )
        section.row(
            "I speak",
            "What your microphone hears. If it's not the language above, your own lines are "
            "translated too, so you can check what you said.",
            self.speak,
        )
        self.also_row = section.row(
            "I also speak",
            "If you switch between two languages, each line is checked against both.",
            self.also,
        )
        self.also_row.setEnabled(first != "auto")
        self.speak.choice_changed.connect(lambda c: self.also_row.setEnabled(str(c) != "auto"))
        self.intro("You can change all of this later in Settings.")
        self.finish()

    def apply(self, choices: SetupChoices) -> None:
        choices.my_language = self.read.current_code()
        choices.mic_languages = mic_languages_for(
            str(self.speak.current_choice()),
            str(self.also.current_choice() or ""),
            choices.my_language,
        )


class AudioStep(SettingsPage):
    title_text = "Microphone and speakers"

    def __init__(
        self, palette: Palette, probe: LevelProbe | None, choices: SetupChoices | None = None
    ) -> None:
        super().__init__()
        self._probe = probe
        self._saved = choices or SetupChoices()
        self.intro(
            "Talk into your microphone and play something on your speakers: the bars should "
            'move. "Windows default" follows whatever Windows uses.'
        )
        section = self.section()
        self.mic = ChoiceCombo([("Windows default", None)])
        self.out = ChoiceCombo([("Windows default", None)])
        self.meters: dict[Source, LevelMeter] = {}
        for source, combo, title, text in (
            (Source.ME, self.mic, "Microphone", "What you say."),
            (Source.OTHERS, self.out, "Speakers or headphones", "What the others say."),
        ):
            combo.setFixedWidth(SETTINGS.control_width)
            combo.apply_palette(palette)
            meter = LevelMeter(palette)
            self.meters[source] = meter
            box = QWidget()
            column = QVBoxLayout(box)
            column.setContentsMargins(0, 0, 0, 0)
            column.setSpacing(SPACE.xs)
            column.addWidget(combo)
            column.addWidget(meter, 0, Qt.AlignmentFlag.AlignRight)
            section.row(title, text, box)
            combo.choice_changed.connect(lambda ref, s=source: self._use(s, ref))
        self.problem = note("")
        self.problem.setObjectName("SettingsError")
        self.problem.hide()
        self.body.addWidget(self.problem)
        self.finish()
        self._timer = QTimer(self)
        self._timer.setInterval(METER_MS)
        self._timer.timeout.connect(self._update_meters)

    def start(self) -> None:
        if self._probe is None:
            return
        try:
            devices = self._probe.devices()
        except Exception:  # Windows audio not available: say so, let setup go on
            self.problem.setText(
                "Windows audio isn't available right now; you can pick "
                "devices later in Settings → Audio."
            )
            self.problem.show()
            return
        mic, out = self._saved.mic_device, self._saved.output_device
        self.mic.set_items(device_choices(devices.inputs, mic), mic)
        self.out.set_items(device_choices(devices.loopbacks, out), out)
        self._use(Source.ME, mic)
        self._use(Source.OTHERS, out)
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        if self._probe is not None:
            self._probe.stop()

    def _use(self, source: Source, ref: object) -> None:
        if self._probe is not None:
            try:
                self._probe.use(source, ref if ref is not None else None)  # type: ignore[arg-type]
            except Exception:  # a device that can't open: its meter just stays empty
                return

    def _update_meters(self) -> None:
        if self._probe is None:
            return
        for source, meter in self.meters.items():
            meter.set_level(self._probe.level_db(source))

    def apply(self, choices: SetupChoices) -> None:
        mic, out = self.mic.current_choice(), self.out.current_choice()
        choices.mic_device = mic if mic is not None else None  # type: ignore[assignment]
        choices.output_device = out if out is not None else None  # type: ignore[assignment]


class DownloadsStep(SettingsPage):
    title_text = "What to download"
    changed = Signal()

    def __init__(
        self, palette: Palette, controller: SetupController, choices: SetupChoices | None = None
    ) -> None:
        super().__init__()
        self._palette = palette
        self._controller = controller
        machine = controller.machine
        needed = self.section("Needed")
        speech = (
            "Large model for your NVIDIA graphics card: fast and accurate."
            if machine.cuda
            else "Small model that runs on the processor (no NVIDIA graphics card found)."
        )
        if machine.cuda and not machine.gpu_runtime:
            speech = speech.removesuffix(".") + (
                ", with NVIDIA's graphics libraries (downloaded from NVIDIA's own packages, "
                "under NVIDIA's licence)."
            )
        self.speech_row = needed.row("Speech recognition", speech)
        self.speakers_row = needed.row(
            "Speaker labels", "Tells voices apart so each line shows who said it."
        )
        smart = self.section("Smarter translation")
        self.smart = QCheckBox()
        self.smart.setChecked(choices.smart if choices is not None else machine.smart_recommended)
        self.smart.toggled.connect(lambda _on: self.changed.emit())
        smart.row(
            "Qwen translator",
            "Much better with slang and gaming talk, and covers languages you haven't "
            "downloaded. Needs about 3 GB of graphics memory, so it pauses in game mode."
            + ("" if machine.smart_recommended else " Not recommended for this graphics card."),
            self.smart,
        )
        self.language_section = self.section("Languages (each to and from English)")
        self.language_boxes: dict[str, QCheckBox] = {}
        self.no_languages = note(
            "Language downloads arrive in an update. Until then the Qwen translator above "
            "translates other languages, and the languages already on this PC keep working."
        )
        self.body.addWidget(self.no_languages)
        folder = self.section("Where to keep them")
        change = QPushButton("Change…")
        change.clicked.connect(self._pick_folder)
        self.folder_row = folder.row("Model folder", "", change)
        self.summary = note("")
        self.body.addWidget(self.summary)
        self.finish()
        self.models_dir: Path | None = None

    def load_packs(self, packs: list[LanguagePack], ticked: set[str]) -> None:
        for box in self.language_boxes.values():
            box.setParent(None)
        self.language_boxes.clear()
        for pack in packs:
            box = QCheckBox()
            box.setChecked(pack.code in ticked or pack.is_installed)
            box.toggled.connect(lambda _on: self.changed.emit())
            self.language_section.row(language(pack.code).label, pack_description(pack), box)
            self.language_boxes[pack.code] = box
        self.language_section.setVisible(bool(packs))
        self.no_languages.setVisible(not packs)

    def show_plan(self, plan: SetupPlan, folder: Path, sizes: dict[str, int]) -> None:
        self.speech_row.set_description(
            self.speech_row.description.text().split(" · ")[0] + f" · {size_text(sizes['speech'])}"
        )
        self.speakers_row.set_description(
            self.speakers_row.description.text().split(" · ")[0]
            + f" · {size_text(sizes['speakers'])}"
        )
        self.folder_row.set_description(str(folder))
        free = size_text(plan.free_mb)
        if not plan.entries:
            self.summary.setText("Everything is already on this PC.")
        elif plan.fits:
            self.summary.setText(f"To download: {size_text(plan.size_mb)} ({free} free).")
        else:
            self.summary.setText(
                f"To download: {size_text(plan.size_mb)}, but only {free} is free on that "
                "drive. Pick another folder or untick something."
            )

    def _pick_folder(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Where to keep the models")
        if chosen:
            self.models_dir = Path(chosen)
            self.changed.emit()

    def apply(self, choices: SetupChoices) -> None:
        choices.smart = self.smart.isChecked()
        choices.languages = {code for code, box in self.language_boxes.items() if box.isChecked()}
        if self.models_dir is not None:
            choices.models_dir = self.models_dir


class DownloadingStep(SettingsPage):
    title_text = "Downloading"

    def __init__(self) -> None:
        super().__init__()
        self.intro("This can take a while. You can pause and continue; nothing is lost.")
        self.bar = QProgressBar()
        self.bar.setObjectName("LanguageProgress")
        self.bar.setRange(0, PROGRESS_STEPS)
        self.body.addWidget(self.bar)
        self.current = note("")
        self.body.addWidget(self.current)
        self.message = note("")
        self.body.addWidget(self.message)
        self.finish()

    def on_progress(self, done: int, total: int, title: str) -> None:
        self.bar.setValue(int(PROGRESS_STEPS * done / total) if total else PROGRESS_STEPS)
        self.bar.setFormat(f"{done >> 20} / {total >> 20} MB")
        self.current.setText(title)

    def show_message(self, text: str, error: bool = False) -> None:
        self.message.setObjectName("SettingsError" if error else "SettingsNote")
        self.message.style().unpolish(self.message)
        self.message.style().polish(self.message)
        self.message.setText(text)


class DonePage(SettingsPage):
    title_text = "All set"

    def __init__(self) -> None:
        super().__init__()
        self.intro("Your first window opens when you click Start. A few things worth knowing:")
        tips = self.section()
        tips.row("Hide or show the windows", DEFAULT_HOTKEYS["show_hide_all"])
        tips.row("Translate text on your screen", DEFAULT_HOTKEYS["ocr_region"])
        tips.row("Game mode (lighter while you play)", DEFAULT_HOTKEYS["game_mode"])
        tips.row(
            "Everything else",
            "Right-click a window, or click the Live Translator icon by the clock. Shortcuts "
            "can be changed in Settings → Hotkeys.",
        )
        self.finish()


class SetupWizard(QWidget):
    completed = Signal()  # choices saved: the app starts speech and opens a window
    abandoned = Signal()  # closed before the end: the app quits

    def __init__(
        self,
        controller: SetupController,
        palette: Palette,
        probe_factory: Callable[[], LevelProbe | None] | None = None,
        parent: QWidget | None = None,
        choices: SetupChoices | None = None,
        first_run: bool = True,
    ) -> None:
        super().__init__(parent, Qt.WindowType.Window)
        self._controller = controller
        self.first_run = first_run  # closing a first run quits the app; later runs just close
        again = choices is not None
        self.choices = choices or SetupChoices()
        self.setObjectName("SettingsRoot")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setWindowTitle("Setup")
        self.setWindowIcon(icon("translate", palette, "accent"))
        self.setStyleSheet(window_qss(palette) + settings_qss(palette))
        self.resize(SETTINGS.width, SETTINGS.height)
        probe = probe_factory() if probe_factory is not None else None
        self.welcome = WelcomePage()
        self.languages = LanguagesStep(palette, self.choices)
        self.audio = AudioStep(palette, probe, self.choices)
        self.downloads = DownloadsStep(palette, controller, self.choices if again else None)
        self.downloading = DownloadingStep()
        self.done = DonePage()
        self.steps: list[SettingsPage] = [
            self.welcome,
            self.languages,
            self.audio,
            self.downloads,
            self.downloading,
            self.done,
        ]
        self.stack = QStackedWidget(self)
        for step in self.steps:
            self.stack.addWidget(step)
        self.step_label = QLabel(self)
        self.step_label.setObjectName("SettingsNote")
        self.back = QPushButton("Back")
        self.next = QPushButton("Next")
        self.next.setDefault(True)
        footer = QHBoxLayout()
        footer.setContentsMargins(SPACE.xl, SPACE.md, SPACE.xl, SPACE.xl)
        footer.addWidget(self.step_label)
        footer.addStretch(1)
        footer.addWidget(self.back)
        footer.addWidget(self.next)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.stack, 1)
        layout.addLayout(footer)
        self.back.clicked.connect(lambda: self.go(self.stack.currentIndex() - 1))
        self.next.clicked.connect(self._on_next)
        self.downloads.changed.connect(self._replan)
        controller.progress.connect(self.downloading.on_progress)
        controller.finished.connect(self._on_downloaded)
        self._finished = False
        self.go(0)

    # ------------------------------------------------------------ navigation

    def go(self, index: int) -> None:
        index = max(0, min(index, len(self.steps) - 1))
        leaving = self.stack.currentWidget()
        if leaving is self.audio and index != self.steps.index(self.audio):
            self.audio.stop()
        self.stack.setCurrentIndex(index)
        step = self.steps[index]
        if step is self.audio:
            self.audio.start()
        if step is self.downloads:
            self._load_downloads()
        self.step_label.setText(f"Step {index + 1} of {len(self.steps)}")
        self.back.setVisible(index > 0 and step is not self.done)
        self.back.setEnabled(step is not self.downloading or not self._controller.busy)
        self.next.setEnabled(True)
        self.next.setText(
            {
                self.downloads: "Download",
                self.downloading: "Pause",
                self.done: "Start",
            }.get(step, "Next")
        )
        if step is self.downloading:
            self._start_download()

    def _on_next(self) -> None:
        step = self.stack.currentWidget()
        index = self.stack.currentIndex()
        if step is self.languages:
            self.languages.apply(self.choices)
        elif step is self.audio:
            self.audio.apply(self.choices)
        elif step is self.downloads:
            self.downloads.apply(self.choices)
            if not self._controller.plan(self.choices).entries:
                self.go(self.steps.index(self.done))  # nothing to fetch
                return
        elif step is self.downloading:
            if self._controller.busy:
                self._controller.cancel()  # "Pause"
            else:
                self._start_download()  # "Continue"
            return
        elif step is self.done:
            self._finish()
            return
        self.go(index + 1)

    # ------------------------------------------------------------ downloads

    def _load_downloads(self) -> None:
        self.downloads.apply(self.choices)  # keep a folder chosen earlier
        packs = self._controller.packs(self.choices)
        if not self.downloads.language_boxes and packs:
            ticked = preticked(self.choices.my_language, [p.code for p in packs])
            self.downloads.load_packs(packs, ticked)
        elif not packs:
            self.downloads.load_packs([], set())
        self._replan()

    def _replan(self) -> None:
        self.downloads.apply(self.choices)
        plan = self._controller.plan(self.choices)
        wanted = self._controller.wanted(self.choices)
        sizes = {"speech": 0, "speakers": 0}
        for entry in wanted:
            if entry.kind in ("speech", "gpu-runtime"):  # NVIDIA's libraries belong to speech
                sizes["speech"] += entry.size_mb
            elif entry.kind == "speakers":
                sizes["speakers"] += entry.size_mb
        self.downloads.show_plan(plan, self._controller.models_dir(self.choices), sizes)
        self.next.setEnabled(plan.fits)

    def _start_download(self) -> None:
        if self._controller.download(self.choices):
            self.next.setText("Pause")
            self.back.setEnabled(False)
            self.downloading.show_message("")

    def _on_downloaded(self, ok: bool, message: str) -> None:
        if ok:
            self.go(self.steps.index(self.done))
            return
        self.downloading.show_message(message, error="Paused" not in message)
        self.next.setText("Continue")
        self.back.setEnabled(True)

    # ------------------------------------------------------------ the end

    def _finish(self) -> None:
        self._controller.apply(self.choices)
        self._finished = True
        self.audio.stop()
        self.completed.emit()
        self.close()

    def hideEvent(self, event: QHideEvent) -> None:
        self.audio.stop()
        super().hideEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._finished and not session_ending():
            self._controller.cancel()
            if self.first_run:
                self.abandoned.emit()
        self.audio.stop()
        event.accept()
