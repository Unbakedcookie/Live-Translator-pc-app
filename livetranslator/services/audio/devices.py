"""Audio device discovery and matching (T041; spec §5.3).

"Me" = a WASAPI input (microphone). "Others" = the WASAPI *loopback* of an output device
(what you hear through it). Devices are saved by name + host API, never by index (indices
change). Matching a saved device: exact name + host API, then the "stable" name, then the
Windows default. The stable name ignores the USB-port number Windows inserts into some names
("Headset Microphone (3- A50 Mic)" vs "(4- A50 Mic)" after replugging) and the
" [Loopback]" suffix, so an output device and its loopback compare equal.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from livetranslator.core.state import DeviceRef

WASAPI = "Windows WASAPI"
LOOPBACK_SUFFIX = " [Loopback]"
_USB_PORT = re.compile(r"\(\d+- ")


@dataclass(frozen=True)
class AudioDevice:
    index: int
    name: str
    host_api: str
    channels: int
    sample_rate: int
    is_loopback: bool = False

    @property
    def ref(self) -> DeviceRef:
        """What gets saved: the output device's own name for loopbacks (no suffix)."""
        name = self.name.removesuffix(LOOPBACK_SUFFIX) if self.is_loopback else self.name
        return DeviceRef(name=name, host_api=self.host_api)


@dataclass(frozen=True)
class DeviceList:
    inputs: tuple[AudioDevice, ...]
    loopbacks: tuple[AudioDevice, ...]
    default_input: AudioDevice | None
    default_loopback: AudioDevice | None


def stable_name(name: str) -> str:
    name = name.removesuffix(LOOPBACK_SUFFIX)
    name = _USB_PORT.sub("(", name)
    return " ".join(name.split()).casefold()


def match(
    saved: DeviceRef | None, devices: Sequence[AudioDevice], default: AudioDevice | None
) -> AudioDevice | None:
    """The device to open for a saved choice (None saved = follow the Windows default)."""
    if saved is None:
        return default
    for device in devices:
        if device.ref == saved:
            return device
    wanted = stable_name(saved.name)
    for device in devices:
        if stable_name(device.name) == wanted:
            return device
    return default


def _device(info: dict[str, Any], host_api: str) -> AudioDevice:
    loopback = bool(info.get("isLoopbackDevice", False))
    return AudioDevice(
        index=int(info["index"]),
        name=str(info["name"]),
        host_api=host_api,
        channels=int(info["maxInputChannels"]),
        sample_rate=int(info["defaultSampleRate"]),
        is_loopback=loopback,
    )


def list_devices() -> DeviceList:
    """WASAPI inputs and loopbacks via PyAudioWPatch (Windows only)."""
    import pyaudiowpatch as pa

    audio = pa.PyAudio()
    try:
        wasapi = audio.get_host_api_info_by_type(pa.paWASAPI)
        host_api = str(wasapi["name"])
        inputs: list[AudioDevice] = []
        loopbacks: list[AudioDevice] = []
        for i in range(audio.get_device_count()):
            info = audio.get_device_info_by_index(i)
            if info["hostApi"] != wasapi["index"] or int(info["maxInputChannels"]) < 1:
                continue
            device = _device(info, host_api)
            (loopbacks if device.is_loopback else inputs).append(device)
        default_input = next(
            (d for d in inputs if d.index == int(wasapi["defaultInputDevice"])), None
        )
        try:
            default_loopback: AudioDevice | None = _device(
                audio.get_default_wasapi_loopback(), host_api
            )
        except (OSError, LookupError):
            default_loopback = None
        return DeviceList(tuple(inputs), tuple(loopbacks), default_input, default_loopback)
    finally:
        audio.terminate()
