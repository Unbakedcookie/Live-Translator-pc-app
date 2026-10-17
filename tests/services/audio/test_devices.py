"""T041 — device matching (Tier A, fixtures from this PC's real names) + live smoke listing."""

import sys

import pytest

from livetranslator.core.state import DeviceRef
from livetranslator.services.audio.devices import WASAPI, AudioDevice, match, stable_name

A50_MIC = AudioDevice(32, "Headset Microphone (3- A50 Mic)", WASAPI, 2, 48000)
WEBCAM = AudioDevice(31, "Microphone (NexiGo N60 FHD Webcam Audio)", WASAPI, 2, 48000)
A50_GAME_LOOP = AudioDevice(34, "Headphones (3- A50 Game) [Loopback]", WASAPI, 2, 48000, True)
A50_VOICE_LOOP = AudioDevice(
    36, "Headset Earphone (3- A50 Voice) [Loopback]", WASAPI, 2, 48000, True
)
INPUTS = [WEBCAM, A50_MIC]
LOOPS = [A50_GAME_LOOP, A50_VOICE_LOOP]


def test_stable_name():
    assert stable_name("Headset Microphone (3- A50 Mic)") == "headset microphone (a50 mic)"
    assert stable_name("Headset Microphone (12- A50 Mic)") == "headset microphone (a50 mic)"
    assert stable_name("Headphones (3- A50 Game) [Loopback]") == "headphones (a50 game)"
    assert stable_name("Microphone (NexiGo N60 FHD Webcam Audio)") == (
        "microphone (nexigo n60 fhd webcam audio)"
    )


def test_none_saved_follows_windows_default():
    assert match(None, INPUTS, A50_MIC) is A50_MIC


def test_exact_match_wins():
    saved = DeviceRef(name="Microphone (NexiGo N60 FHD Webcam Audio)", host_api=WASAPI)
    assert match(saved, INPUTS, A50_MIC) is WEBCAM


def test_replugged_usb_port_still_matches():
    saved = DeviceRef(name="Headset Microphone (4- A50 Mic)", host_api=WASAPI)
    assert match(saved, INPUTS, WEBCAM) is A50_MIC


def test_missing_device_falls_back_to_default():
    saved = DeviceRef(name="Yeti Stereo Microphone", host_api=WASAPI)
    assert match(saved, INPUTS, A50_MIC) is A50_MIC
    assert match(saved, INPUTS, None) is None


def test_loopback_saved_as_output_name_and_matched_back():
    assert A50_GAME_LOOP.ref == DeviceRef(name="Headphones (3- A50 Game)", host_api=WASAPI)
    assert match(A50_GAME_LOOP.ref, LOOPS, A50_VOICE_LOOP) is A50_GAME_LOOP


def test_exact_preferred_over_stable_duplicate():
    other_port = AudioDevice(40, "Headset Microphone (5- A50 Mic)", WASAPI, 2, 48000)
    saved = DeviceRef(name="Headset Microphone (5- A50 Mic)", host_api=WASAPI)
    assert match(saved, [A50_MIC, other_port], None) is other_port


@pytest.mark.skipif(sys.platform != "win32", reason="real WASAPI devices")
def test_live_listing_has_inputs_and_loopbacks():
    from livetranslator.services.audio.devices import list_devices

    devices = list_devices()
    assert devices.inputs and devices.loopbacks
    assert all(d.is_loopback and d.name.endswith("[Loopback]") for d in devices.loopbacks)
    assert all(not d.is_loopback for d in devices.inputs)
    assert devices.default_input is not None and devices.default_loopback is not None
