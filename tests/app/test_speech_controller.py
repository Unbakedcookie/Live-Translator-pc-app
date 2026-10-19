"""T045/T046 — speech wiring: devices, mute, settings snapshot, echo filter (no hardware)."""

from livetranslator.app.speech_controller import SpeechController, asr_settings
from livetranslator.core import actions as a
from livetranslator.core.state import (
    AppConfig,
    AppState,
    AudioConfig,
    DeviceRef,
    PerformanceConfig,
    Source,
    StatusLevel,
    Utterance,
)
from livetranslator.core.store import Store
from livetranslator.services.asr.worker import ASRWorker
from livetranslator.services.audio.devices import AudioDevice, DeviceList
from tests.services.asr.test_worker import FakeVad

MIC = AudioDevice(1, "Microphone (Astro A50 Voice)", "Windows WASAPI", 1, 48000)
HEADSET = AudioDevice(2, "Headset (Astro A50 Game) [Loopback]", "Windows WASAPI", 2, 48000, True)
SPEAKERS = AudioDevice(3, "Speakers (Realtek) [Loopback]", "Windows WASAPI", 2, 48000, True)
DEVICES = DeviceList((MIC,), (HEADSET, SPEAKERS), MIC, SPEAKERS)


class FakeCapture:
    def __init__(self, device, ring, on_status) -> None:
        self.device, self.ring, self.on_status = device, ring, on_status
        self.running = False

    def start(self) -> None:
        self.running = True
        self.on_status(StatusLevel.OK, f"Listening to {self.device.ref.name}")

    def stop(self) -> None:
        self.running = False


class NullEngine:
    name = "null"
    is_loaded = True

    def load(self) -> None: ...

    def unload(self) -> None: ...

    def transcribe(self, audio, *, language=None, prompt=None, final=False):
        raise AssertionError("no audio is fed in these tests")


def make(config: AppConfig | None = None, devices=lambda: DEVICES):
    store = Store(AppState(config=config or AppConfig()))
    worker = ASRWorker(NullEngine(), store.dispatch, vad_factory=FakeVad)
    controller = SpeechController(store, worker, devices, FakeCapture)
    return store, controller


def fake(speech: SpeechController, source: Source) -> FakeCapture:
    capture = speech.captures[source]
    assert isinstance(capture, FakeCapture)
    return capture


def status(store: Store, source: str):
    return store.state.runtime.statuses[f"audio.{source}"]


def test_start_opens_default_devices(qtbot):
    store, speech = make()
    speech.start()
    try:
        assert speech.devices == {Source.ME: MIC, Source.OTHERS: SPEAKERS}
        assert fake(speech, Source.ME).running and fake(speech, Source.OTHERS).running
        assert set(speech.worker.streams) == {Source.ME, Source.OTHERS}
        assert status(store, "others").message == "Listening to Speakers (Realtek)"
    finally:
        speech.stop()
    assert speech.captures == {}


def test_saved_device_is_used_and_missing_one_falls_back(qtbot):
    config = AppConfig(
        audio=AudioConfig(
            output_device=DeviceRef(name="Headset (Astro A50 Game)"),
            mic_device=DeviceRef(name="USB Mic (gone)"),
        )
    )
    store, speech = make(config)
    speech.start()
    try:
        assert speech.devices[Source.OTHERS] == HEADSET
        assert speech.devices[Source.ME] == MIC  # saved mic is gone: Windows default
        warning = store.state.runtime.statuses["audio.me.device"]
        assert warning.level is StatusLevel.WARNING and "USB Mic (gone)" in warning.message
        assert "audio.others.device" not in store.state.runtime.statuses
    finally:
        speech.stop()


def test_mute_stops_the_mic_and_unmute_restarts_it(qtbot):
    store, speech = make()
    speech.start()
    try:
        mic = fake(speech, Source.ME)
        store.dispatch(a.UpdateConfigSection("audio", {"mic_enabled": False}))
        assert Source.ME not in speech.captures and not mic.running
        assert speech.worker.settings.enabled == frozenset({Source.OTHERS})
        assert status(store, "me").message == "Microphone muted."
        store.dispatch(a.UpdateConfigSection("audio", {"mic_enabled": True}))
        assert fake(speech, Source.ME).running
        assert speech.worker.settings.enabled == frozenset({Source.ME, Source.OTHERS})
        assert list(speech.worker.streams) == [Source.ME, Source.OTHERS]  # ring reused
    finally:
        speech.stop()


def test_device_listing_failure_is_reported(qtbot):
    def broken() -> DeviceList:
        raise OSError("PortAudio not initialised")

    store, speech = make(devices=broken)
    speech.start()
    try:
        assert status(store, "me").level is StatusLevel.ERROR
        assert speech.captures == {}
    finally:
        speech.stop()


def test_settings_snapshot_follows_config():
    config = AppConfig(
        my_language="ja",
        performance=PerformanceConfig(asr_update_interval_s=0.5, game_mode=True),
        audio=AudioConfig(others_enabled=False),
    )
    settings = asr_settings(config)
    assert settings.mic_languages == ("ja",)  # nothing chosen: the language you read
    assert settings.update_interval_s == 1.0  # game mode
    assert settings.enabled == frozenset({Source.ME})


def utt(uid: str, source: Source, text: str, start: float, final: bool = True) -> Utterance:
    return Utterance(
        id=uid,
        source=source,
        speaker_id="me" if source is Source.ME else "others",
        start=start,
        end=start + 2.0,
        committed=text,
        is_final=final,
    )


def test_echo_of_others_on_the_mic_is_removed_either_order(qtbot):
    store, _ = make()
    store.dispatch(a.AddUtterance(utt("o1", Source.OTHERS, "wait for me at the gate", 10.0)))
    store.dispatch(a.AddUtterance(utt("m1", Source.ME, "Wait for me at the gate!", 10.5, False)))
    store.dispatch(a.UpdateUtterance("m1", {"is_final": True}))
    assert store.state.session.utterance("m1") is None
    # Mic line finishes first, the loopback line second.
    store.dispatch(a.AddUtterance(utt("m2", Source.ME, "take the left path", 30.0)))
    store.dispatch(a.AddUtterance(utt("o2", Source.OTHERS, "take the left path", 30.2, False)))
    assert store.state.session.utterance("m2") is not None
    store.dispatch(a.UpdateUtterance("o2", {"is_final": True}))
    assert store.state.session.utterance("m2") is None
    # A genuinely different line from me stays.
    store.dispatch(a.AddUtterance(utt("m3", Source.ME, "sounds good, I'm ready", 30.5)))
    store.dispatch(a.UpdateUtterance("m3", {"end": 33.0}))
    assert store.state.session.utterance("m3") is not None


def test_speaker_worker_follows_settings_and_forgets_voices_with_the_session(qtbot):
    from livetranslator.core.state import SpeakerConfig, SpeakerMode
    from livetranslator.services.speakers.worker import SpeakerWorker
    from tests.services.speakers.test_worker import FakeEmbedder, job

    store = Store(AppState())
    speakers = SpeakerWorker(FakeEmbedder(), store.dispatch)
    worker = ASRWorker(NullEngine(), store.dispatch, vad_factory=FakeVad)
    speech = SpeechController(store, worker, lambda: DEVICES, FakeCapture, speakers=speakers)
    speech.start()
    try:
        speakers.handle(job("u1", 0))
        assert speakers.clusters.count == 1
        store.dispatch(a.UpdateConfigSection("speakers", {"mode": SpeakerMode.OFF}))
        assert not speakers.enabled
        assert store.state.config.speakers == SpeakerConfig(mode=SpeakerMode.OFF)
        store.dispatch(a.AddUtterance(utt("o1", Source.OTHERS, "hi", 1.0)))
        store.dispatch(a.ClearSession())
        assert speakers.clusters.count == 0  # voices never outlive the session (D-028)
    finally:
        speech.stop()


def test_i_speak_resolves_for_the_recogniser():
    from livetranslator.app.speech_controller import mic_languages

    def config(*chosen: str) -> AppConfig:
        return AppConfig(my_language="ja", audio=AudioConfig(mic_languages=chosen))

    assert mic_languages(config()) == ("ja",)  # nothing chosen: the language you read
    assert mic_languages(config("auto")) == ()  # detect any
    assert mic_languages(config("es", "en")) == ("es", "en")
