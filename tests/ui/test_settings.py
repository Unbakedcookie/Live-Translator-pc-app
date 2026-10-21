"""T072 — Settings window: every control reads from and writes to the store (pytest-qt)."""

from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from livetranslator.app.settings_controller import SettingsController
from livetranslator.app.window_controller import WindowController
from livetranslator.core import actions as a
from livetranslator.core.state import (
    AppConfig,
    AppState,
    DeviceRef,
    Source,
    SpeakerMode,
    StatusLevel,
    WindowConfig,
)
from livetranslator.core.store import Store
from livetranslator.services.audio.devices import AudioDevice, DeviceList
from livetranslator.ui.settings.advanced_page import AdvancedPage
from livetranslator.ui.settings.audio_page import WINDOWS_DEFAULT, AudioPage, device_choices
from livetranslator.ui.settings.context import EngineRow, EngineSummary, SettingsContext
from livetranslator.ui.settings.general_page import GeneralPage
from livetranslator.ui.settings.hotkey_box import NOT_SET, PROMPT, UNUSABLE, HotkeyBox
from livetranslator.ui.settings.hotkeys_page import HotkeysPage
from livetranslator.ui.settings.performance_page import PerformancePage
from livetranslator.ui.settings.rows import SettingRow, SettingsPage
from livetranslator.ui.settings.settings_window import SettingsWindow
from livetranslator.ui.settings.speakers_page import SpeakersPage
from livetranslator.ui.settings.translation_page import TranslationPage
from livetranslator.ui.settings.windows_page import (
    WindowsPage,
    window_description,
    window_title,
)

MIC = AudioDevice(1, "USB Mic", "Windows WASAPI", 1, 48000)
HEADSET = AudioDevice(2, "Headset (A50)", "Windows WASAPI", 2, 48000)
LOOP = AudioDevice(3, "Headset (A50) [Loopback]", "Windows WASAPI", 2, 48000, is_loopback=True)
DEVICES = DeviceList((MIC, HEADSET), (LOOP,), MIC, LOOP)
ACTIONS = ("show_hide_all", "mute_me", "lock_all", "new_window", "open_settings")


class Env:
    def __init__(
        self,
        qtbot,
        tmp_path: Path,
        devices: DeviceList | None = DEVICES,
        levels=None,
        engines=None,
    ):
        self.store = Store(AppState(config=AppConfig(windows=(WindowConfig(id="a"),))))
        self.suspended: list[bool] = []
        self.opened: list[Path] = []
        self.settings = SettingsController(self.store, self.suspended.append)
        self.windows = WindowController(self.store)
        ctx = SettingsContext(
            settings=self.settings,
            windows=self.windows,
            models_dir=tmp_path / "models",
            log_dir=tmp_path / "logs",
            open_folder=self.opened.append,
            devices=(lambda: devices) if devices is not None else None,
            level_db=levels,
            engines=engines,
            hotkey_actions=ACTIONS,
        )
        self.window = SettingsWindow(ctx)
        qtbot.addWidget(self.window)
        self.window.show()  # hidden Settings skips refreshes (showEvent re-reads)

    def page[T: SettingsPage](self, kind: type[T]) -> T:
        self.window.show_page(kind.title_text)
        page = self.window.pages[kind.title_text]
        assert isinstance(page, kind)
        return page


@pytest.fixture
def env(qtbot, tmp_path: Path) -> Env:
    return Env(qtbot, tmp_path)


def test_window_has_its_pages_in_order(env: Env):
    assert list(env.window.pages) == [
        "General",
        "Audio",
        "Speakers",
        "Windows",
        "Translation",
        "Languages",  # T074
        "Hotkeys",
        "Performance",
        "Advanced",
        "About",  # T113
    ]
    env.window.show_page("Hotkeys")
    assert env.window.stack.currentWidget() is env.window.pages["Hotkeys"]
    assert env.window.nav.currentRow() == 6


def test_close_only_hides_and_reopens(env: Env, qtbot):
    env.window.bring_to_front()
    qtbot.waitExposed(env.window)
    env.window.close()
    assert not env.window.isVisible()
    env.window.bring_to_front()
    assert env.window.isVisible()


def test_general_language_and_folders(env: Env):
    page = env.page(GeneralPage)
    page.language.language_changed.emit("de")
    assert env.store.state.config.my_language == "de"
    env.store.dispatch(a.SetMyLanguage("ja"))
    assert page.language.current_code() == "ja"
    buttons = [b for b in page.findChildren(QPushButton) if b.text() == "Open folder"]
    for button in buttons:
        button.click()
    assert [p.name for p in env.opened] == ["models", "logs"]


def test_device_choices_keep_an_unplugged_saved_device():
    saved = DeviceRef(name="Old Mic")
    items = device_choices((MIC, MIC), saved)
    assert items == [
        (WINDOWS_DEFAULT, None),
        ("USB Mic", MIC.ref),
        ("Old Mic (not connected)", saved),
    ]
    loops = device_choices((LOOP,), LOOP.ref)
    assert loops[1] == ("Headset (A50)", DeviceRef(name="Headset (A50)"))  # no [Loopback]


def test_audio_page_devices_toggles_and_meters(qtbot, tmp_path: Path):
    levels = {Source.ME: None, Source.OTHERS: -30.0}
    env = Env(qtbot, tmp_path, levels=lambda source: levels[source])
    page = env.page(AudioPage)
    assert [page.mic.itemText(i) for i in range(page.mic.count())] == [
        WINDOWS_DEFAULT,
        "USB Mic",
        "Headset (A50)",
    ]
    page.mic.choice_changed.emit(MIC.ref)
    page.output.choice_changed.emit(LOOP.ref)
    page.mic_on.setChecked(False)
    audio = env.store.state.config.audio
    assert audio.mic_device == MIC.ref and audio.output_device == LOOP.ref
    assert not audio.mic_enabled
    assert page.mic.current_choice() == MIC.ref
    env.store.dispatch(a.UpdateConfigSection("audio", {"others_enabled": False}))
    assert not page.others_on.isChecked()
    page.update_meters()
    assert (page.mic_meter.active, page.mic_meter.fraction) == (False, 0.0)
    assert (page.others_meter.active, page.others_meter.fraction) == (True, 0.5)
    assert not page.notice.isVisibleTo(page)


def test_audio_page_without_speech_says_so(qtbot, tmp_path: Path):
    env = Env(qtbot, tmp_path, devices=None)
    page = env.page(AudioPage)
    assert page.notice.isVisibleTo(page) and "turned off" in page.notice.text()
    assert page.mic.count() == 1  # Windows default only
    page.update_meters()
    assert not page.others_meter.active


def test_audio_page_survives_a_broken_device_list(qtbot, tmp_path: Path):
    def broken() -> DeviceList:
        raise OSError("PortAudio down")

    env = Env(qtbot, tmp_path)
    page = env.page(AudioPage)
    page._ctx.devices = broken
    page.reload_devices()
    assert "isn't available" in page.notice.text()


def test_speakers_page(env: Env):
    page = env.page(SpeakersPage)
    page.mode.choice_changed.emit(SpeakerMode.OFF)
    page.max_speakers.setValue(4)
    page.me_label.setText("Mika")
    page.me_label.editingFinished.emit()
    speakers = env.store.state.config.speakers
    assert (speakers.mode, speakers.max_speakers, speakers.me_label) == (SpeakerMode.OFF, 4, "Mika")
    env.store.dispatch(a.UpdateConfigSection("speakers", {"mode": SpeakerMode.VOICE}))
    assert page.mode.current_choice() == SpeakerMode.AUTO  # shown as "by voice"


def test_windows_page_lists_locks_adds_and_closes(env: Env):
    page = env.page(WindowsPage)
    assert page.list is not None
    page.lock_all.setChecked(True)
    assert all(w.locked for w in env.store.state.config.windows)
    new = next(b for b in page.findChildren(QPushButton) if b.text() == "New window")
    new.click()
    assert len(env.store.state.config.windows) == 2
    closes = [b for b in page.list.findChildren(QPushButton) if b.text() == "Close"]
    assert len(closes) == 2  # list rebuilt from the store
    assert not page.lock_all.isChecked()  # the new window isn't locked
    closes[0].click()
    assert [w.id for w in env.store.state.config.windows] != ["a"]
    assert len(env.store.state.config.windows) == 1


def test_window_titles_and_descriptions():
    cfg = WindowConfig(id="x", target_lang="ja", click_through=True)
    assert window_title(1, cfg) == "Window 2 — Japanese"
    assert window_description(cfg) == "Shows Me + Others · on top, click-through"
    named = WindowConfig(id="y", title="Raid", sources=(), pinned=False)
    assert window_title(0, named) == "Raid — English"
    assert window_description(named) == "Shows nothing"


def test_translation_page_shows_engines_and_pairs(qtbot, tmp_path: Path):
    summary = EngineSummary(
        (EngineRow("Speech recognition", "Whisper large-v3-turbo", "Graphics card"),),
        (("ja", "en"), ("en", "es")),
    )
    env = Env(qtbot, tmp_path, engines=lambda: summary)
    page = env.page(TranslationPage)
    page.refresh()
    assert page.pairs.description.text() == "English → Spanish, Japanese → English"
    assert "Whisper large-v3-turbo" in [r.description.text() for r in page.findChildren(SettingRow)]


def key_event(vk: int, key: Qt.Key, mods: Qt.KeyboardModifier) -> QKeyEvent:
    return QKeyEvent(QEvent.Type.KeyPress, key, mods, 0, vk, 0)


def test_hotkey_box_records_a_combination(qtbot):
    box = HotkeyBox(None)
    qtbot.addWidget(box)
    got: list[str] = []
    rec: list[bool] = []
    box.captured.connect(got.append)
    box.recording.connect(rec.append)
    assert box.text() == NOT_SET
    box.click()
    assert box.is_recording and box.text() == PROMPT and rec == [True]
    ctrl_shift = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier
    QApplication.sendEvent(box, key_event(0x11, Qt.Key.Key_Control, ctrl_shift))
    assert box.text() == "Ctrl+Shift+"  # live feedback while only modifiers are held
    QApplication.sendEvent(box, key_event(0x4C, Qt.Key.Key_L, ctrl_shift))
    assert got == ["Ctrl+Shift+L"] and rec == [True, False] and not box.is_recording
    box.click()
    QApplication.sendEvent(box, key_event(0x1B, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
    assert got == ["Ctrl+Shift+L"] and not box.is_recording  # Esc cancels


def test_hotkeys_page_rows_set_refuse_clear_and_reset(env: Env):
    page = env.page(HotkeysPage)
    assert list(page.controls) == [
        "show_hide_all",
        "lock_all",
        "new_window",
        "mute_me",
        "open_settings",
    ]  # spec order, only actions this build can do
    box = page.controls["lock_all"].box
    assert box.text() == NOT_SET and not page.controls["lock_all"].clear.isVisibleTo(page)
    box.click()
    assert env.suspended == [True]
    box.captured.emit("Ctrl+Shift+L")
    box.stop()
    assert env.suspended == [True, False]
    assert env.store.state.config.hotkeys["lock_all"] == "Ctrl+Shift+L"
    assert box.text() == "Ctrl+Shift+L"
    page.controls["new_window"].box.captured.emit("Ctrl+Shift+L")
    assert "new_window" not in env.store.state.config.hotkeys
    assert "already used" in page.rows["new_window"].description.text()
    page.controls["lock_all"].clear.click()
    assert "lock_all" not in env.store.state.config.hotkeys
    assert page.rows["new_window"].description.text() == ""  # stale refusal cleared
    env.store.dispatch(a.SetStatus("hotkey.mute_me", StatusLevel.WARNING, "taken"))
    assert "Another program" in page.rows["mute_me"].description.text()
    reset = next(b for b in page.findChildren(QPushButton) if b.text().startswith("Restore"))
    reset.click()
    assert env.store.state.config.hotkeys["mute_me"] == "Ctrl+Alt+M"


def test_performance_page(env: Env):
    page = env.page(PerformancePage)
    page.interval.setValue(800)
    assert env.store.state.config.performance.asr_update_interval_s == 0.8
    page.game_mode.setChecked(True)
    assert env.store.state.config.performance.game_mode
    assert "1000 ms for now" in page.interval_row.description.text()
    page.interval.setValue(1500)
    assert "for now" not in page.interval_row.description.text()


def test_advanced_page(env: Env):
    page = env.page(AdvancedPage)
    page.threshold.setValue(60)
    page.silence.setValue(700)
    page.longest.setValue(20)
    page.echo_window.setValue(10)
    page.echo_ratio.setValue(90)
    config = env.store.state.config
    assert (config.vad.threshold, config.vad.end_silence_ms, config.vad.max_utterance_s) == (
        0.6,
        700,
        20.0,
    )
    assert (config.echo_filter.window_s, config.echo_filter.min_ratio) == (10.0, 90.0)
    reset = next(b for b in page.findChildren(QPushButton) if b.text() == "Restore defaults")
    reset.click()
    assert env.store.state.config.vad.threshold == 0.5
    assert page.threshold.value() == 50  # the page re-read the store


def test_hotkey_box_unusable_key_and_hide_stop(qtbot):
    box = HotkeyBox("Ctrl+Alt+H")
    qtbot.addWidget(box)
    box.show()
    rec: list[bool] = []
    box.recording.connect(rec.append)
    box.click()
    QApplication.sendEvent(
        box, key_event(0x6B, Qt.Key.Key_Plus, Qt.KeyboardModifier.KeypadModifier)
    )
    assert box.text() == UNUSABLE and box.is_recording  # keeps listening
    box.hide()  # page switched / window closed
    assert not box.is_recording and rec == [True, False] and box.text() == "Ctrl+Alt+H"


def test_speakers_page_blank_name_and_one_voice(env: Env):
    page = env.page(SpeakersPage)
    page.me_label.setText("   ")
    page.me_label.editingFinished.emit()
    assert env.store.state.config.speakers.me_label == "Me" and page.me_label.text() == "Me"
    env.store.dispatch(a.UpdateConfigSection("speakers", {"max_speakers": 1}))
    env.window.show()
    page.refresh()
    assert page.max_speakers.value() == 1


def test_hotkeys_page_flags_a_damaged_saved_shortcut(env: Env):
    env.store.dispatch(a.SetHotkey("mute_me", "Ctrl+Foo"))
    env.store.dispatch(a.SetStatus("hotkey.mute_me", StatusLevel.WARNING, "bad"))
    page = env.page(HotkeysPage)
    env.window.show()
    page.refresh()
    assert "isn't valid" in page.rows["mute_me"].description.text()


def test_performance_readout_toggle(env: Env):
    page = env.page(PerformancePage)
    page.readout.setChecked(True)
    assert env.store.state.config.performance.show_readout
    env.store.dispatch(a.UpdateConfigSection("performance", {"show_readout": False}))
    assert not page.readout.isChecked()


def test_translation_page_chinese_switch_only_when_installed(qtbot, tmp_path: Path):
    env = Env(qtbot, tmp_path)
    assert env.page(TranslationPage).chinese is None  # Qwen not installed: no dead switch
    env.window._ctx.smart_translation = True
    page = TranslationPage(env.window._ctx)
    qtbot.addWidget(page)
    assert page.chinese is not None
    page.chinese.setChecked(True)
    assert env.store.state.config.engines.smart_languages == ("zh",)
    env.store.dispatch(a.UpdateConfigSection("engines", {"smart_languages": ()}))
    page.refresh()
    assert not page.chinese.isChecked()
    assert page.fallback is not None and page.fallback.isChecked()  # on by default
    page.fallback.setChecked(False)
    assert not env.store.state.config.engines.smart_fallback
    env.store.dispatch(a.UpdateConfigSection("engines", {"smart_fallback": True}))
    page.refresh()
    assert page.fallback.isChecked()


def test_general_page_chinese_script(env: Env):
    page = env.page(GeneralPage)
    assert page.chinese.current_choice() == "simplified"
    page.chinese.choice_changed.emit("traditional")
    assert env.store.state.config.engines.chinese_script == "traditional"
    env.store.dispatch(a.UpdateConfigSection("engines", {"chinese_script": "simplified"}))
    assert page.chinese.current_choice() == "simplified"


def test_general_page_i_speak_is_separate_from_translate_into(env: Env):
    """User request 2026-10-18: speak Spanish to practise, read English translations."""
    page = env.page(GeneralPage)
    assert page.speak.current_choice() == "same" and page.also.codes() == ()
    page.speak.set_choice("es")
    page.speak.choice_changed.emit("es")
    assert env.store.state.config.audio.mic_languages == ("es",)
    assert env.store.state.config.my_language == "en"  # still read in English
    boxes = page.also.boxes
    assert [b.isVisibleTo(page) for b in boxes] == [True, False, False]  # one empty picker
    boxes[0].set_choice("en")
    boxes[0].choice_changed.emit("en")
    assert env.store.state.config.audio.mic_languages == ("es", "en")
    assert [b.isVisibleTo(page) for b in boxes] == [True, True, False]
    boxes[1].set_choice("vi")
    boxes[1].choice_changed.emit("vi")
    boxes[2].set_choice("zh")
    boxes[2].choice_changed.emit("zh")
    assert env.store.state.config.audio.mic_languages == ("es", "en", "vi", "zh")
    boxes[0].set_choice("")  # emptying one closes the gap
    boxes[0].choice_changed.emit("")
    assert env.store.state.config.audio.mic_languages == ("es", "vi", "zh")
    assert page.also.codes() == ("vi", "zh")
    assert [b.isVisibleTo(page) for b in boxes] == [True, True, True]
    page.speak.set_choice("auto")
    page.speak.choice_changed.emit("auto")
    assert env.store.state.config.audio.mic_languages == ("auto",)
    assert not page.also_row.isEnabled()  # "any language" already covers a second one
    env.store.dispatch(a.UpdateConfigSection("audio", {"mic_languages": ()}))
    assert page.speak.current_choice() == "same" and page.also_row.isEnabled()


def test_about_page_lists_the_licences(env: Env):
    from livetranslator.ui.about import AboutPage, licenses_dir

    page = env.page(AboutPage)
    assert page.package_count > 50
    texts = [label.text() for label in page.findChildren(QLabel)]
    assert any("GNU Lesser General Public License" in t for t in texts)
    assert any(t.startswith("PySide6") for t in texts)
    assert any(t.startswith("MIT License") for t in texts)  # the app's own (2026-10-19)
    assert "Listening to others" in texts  # D-011 notice
    assert (licenses_dir() / "LGPL-3.0.txt").is_file()
    buttons = [b for b in page.findChildren(QPushButton) if b.text() == "Open folder"]
    buttons[0].click()
    assert env.opened[-1] == licenses_dir()


def test_general_page_others_speak(env: Env):
    """User request 2026-10-20: universal detection, or "I know they speak Chinese, I don't
    know what else" (Chinese + Anything else), or exactly the room's languages."""
    from livetranslator.ui.settings.general_page import ANYTHING

    page = env.page(GeneralPage)
    audio = lambda: env.store.state.config.audio  # noqa: E731
    assert page.others.current_choice() == "auto" and not page.others_also_row.isEnabled()
    page.others.set_choice("zh")
    page.others.choice_changed.emit("zh")
    assert audio().others_languages == ("zh",) and audio().others_anything_else
    assert page.others_also_row.isEnabled()
    boxes = page.others_also.boxes
    assert boxes[0].current_choice() == ANYTHING  # the safe default: anything else too
    assert [b.isVisibleTo(page) for b in boxes] == [True, False, False]  # nothing after it
    boxes[0].set_choice("en")  # exactly Chinese and English
    boxes[0].choice_changed.emit("en")
    assert audio().others_languages == ("zh", "en") and not audio().others_anything_else
    assert [b.isVisibleTo(page) for b in boxes] == [True, True, False]
    boxes[1].set_choice(ANYTHING)  # Chinese, English, and anything else
    boxes[1].choice_changed.emit(ANYTHING)
    assert audio().others_languages == ("zh", "en") and audio().others_anything_else
    boxes[0].set_choice("")  # emptying a box closes the gap: Chinese + anything else
    boxes[0].choice_changed.emit("")
    assert audio().others_languages == ("zh",) and audio().others_anything_else
    assert boxes[0].current_choice() == ANYTHING
    boxes[0].set_choice("")  # and "Nothing else" there now means only Chinese
    boxes[0].choice_changed.emit("")
    assert audio().others_languages == ("zh",) and not audio().others_anything_else
    page.others.set_choice("auto")
    page.others.choice_changed.emit("auto")
    assert audio().others_languages == () and not page.others_also_row.isEnabled()
