"""Settings → Audio (T072): which microphone and which speakers, with live level meters."""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtGui import QHideEvent, QShowEvent
from PySide6.QtWidgets import QCheckBox, QWidget

from livetranslator.core.state import DeviceRef, Source
from livetranslator.services.audio.devices import AudioDevice, DeviceList
from livetranslator.theme.tokens import SETTINGS
from livetranslator.ui.settings.context import SettingsContext
from livetranslator.ui.settings.level_meter import LevelMeter
from livetranslator.ui.settings.rows import SettingsPage, silently
from livetranslator.ui.widgets.choice_combo import ChoiceCombo

METER_INTERVAL_MS = 66  # ~15 updates a second: smooth enough, nearly free
WINDOWS_DEFAULT = "Windows default"


def device_choices(
    devices: tuple[AudioDevice, ...], saved: DeviceRef | None
) -> list[tuple[str, object]]:
    """Dropdown items: Windows default first, then each device once by its saved name. A
    saved device that is unplugged stays listed so the choice isn't silently lost."""
    items: list[tuple[str, object]] = [(WINDOWS_DEFAULT, None)]
    seen: set[DeviceRef] = set()
    for device in devices:
        ref = device.ref
        if ref not in seen:
            seen.add(ref)
            items.append((ref.name, ref))
    if saved is not None and saved not in seen:
        items.append((f"{saved.name} (not connected)", saved))
    return items


class AudioPage(SettingsPage):
    title_text = "Audio"
    icon_name = "speaker-high"

    def __init__(self, ctx: SettingsContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self.notice = self.intro("")
        self.notice.setVisible(False)

        me = self.section("Me — your microphone")
        self.mic = ChoiceCombo([(WINDOWS_DEFAULT, None)])
        self.mic.setFixedWidth(SETTINGS.control_width)
        self.mic.apply_palette(ctx.palette)
        self.mic.choice_changed.connect(lambda ref: ctx.settings.set_mic_device(ref))
        me.row("Microphone", "", self.mic)
        self.mic_on = QCheckBox()
        self.mic_on.toggled.connect(lambda on: ctx.settings.set_stream_enabled(mic=on))
        me.row("Listen to my microphone", "Off = Mute Me.", self.mic_on)
        self.mic_meter = LevelMeter(ctx.palette)
        me.row("Level", "Talk: the bar should move.", self.mic_meter)

        others = self.section("Others — what you hear")
        self.output = ChoiceCombo([(WINDOWS_DEFAULT, None)])
        self.output.setFixedWidth(SETTINGS.control_width)
        self.output.apply_palette(ctx.palette)
        self.output.choice_changed.connect(lambda ref: ctx.settings.set_output_device(ref))
        others.row(
            "Speakers or headphones",
            "The app listens to what this device plays (game chat, calls, videos).",
            self.output,
        )
        self.others_on = QCheckBox()
        self.others_on.toggled.connect(lambda on: ctx.settings.set_stream_enabled(others=on))
        others.row("Listen to what I hear", "Off = Mute Others.", self.others_on)
        self.others_meter = LevelMeter(ctx.palette)
        others.row("Level", "Play something: the bar should move.", self.others_meter)
        self.finish()

        self._timer = QTimer(self)
        self._timer.setInterval(METER_INTERVAL_MS)
        self._timer.timeout.connect(self.update_meters)
        self.reload_devices()

    def reload_devices(self) -> None:
        """Re-list devices (they can be plugged in or out while the window is open)."""
        devices: DeviceList | None = None
        message = ""
        if self._ctx.devices is None:
            message = "Speech is turned off in this session, so devices can't be listed."
        else:
            try:
                devices = self._ctx.devices()
            except Exception:  # PortAudio down: show it instead of crashing the window
                message = "Windows audio isn't available right now."
        self.notice.setText(message)
        self.notice.setVisible(bool(message))
        audio = self._ctx.settings.store.state.config.audio
        self.mic.set_items(
            device_choices(devices.inputs if devices else (), audio.mic_device), audio.mic_device
        )
        self.output.set_items(
            device_choices(devices.loopbacks if devices else (), audio.output_device),
            audio.output_device,
        )

    def refresh(self) -> None:
        audio = self._ctx.settings.store.state.config.audio
        self.mic.set_choice(audio.mic_device)
        self.output.set_choice(audio.output_device)
        silently(self.mic_on, lambda: self.mic_on.setChecked(audio.mic_enabled))
        silently(self.others_on, lambda: self.others_on.setChecked(audio.others_enabled))

    def update_meters(self) -> None:
        level = self._ctx.level_db
        self.mic_meter.set_level(level(Source.ME) if level else None)
        self.others_meter.set_level(level(Source.OTHERS) if level else None)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.reload_devices()
        self._timer.start()

    def hideEvent(self, event: QHideEvent) -> None:
        self._timer.stop()
        super().hideEvent(event)
