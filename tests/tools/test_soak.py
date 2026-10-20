"""T112 soak tool: the pretend devices and the looping player."""

import numpy as np

from tools.soak import CHUNK, MIC, SPEAKERS, Player, fake_devices


def test_player_loops_with_pauses():
    clip = np.ones(CHUNK, dtype=np.float32)
    player = Player([clip], gap_s=CHUNK / 16_000)  # one chunk of silence after the clip
    chunks = [np.frombuffer(player.next_chunk(), dtype=np.float32) for _ in range(3)]
    assert chunks[0].tolist() == [1.0] * CHUNK
    assert chunks[1].tolist() == [0.0] * CHUNK
    assert chunks[2].tolist() == [1.0] * CHUNK  # back to the start


def test_fake_devices_match_the_saved_names():
    devices = fake_devices()
    assert devices.default_input is not None and devices.default_input.ref.name == MIC
    assert devices.default_loopback is not None
    assert devices.default_loopback.ref.name == SPEAKERS  # loopback suffix dropped
    assert devices.default_loopback.is_loopback and devices.default_input.sample_rate == 16_000
