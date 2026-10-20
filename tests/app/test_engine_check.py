"""--engine-check (2026-10-19): WAV reading and the report, without real engines."""

import struct
from pathlib import Path

import numpy as np
import pytest

from livetranslator.__main__ import build_parser
from livetranslator.app.engine_check import read_wav


def wav_bytes(samples: bytes, fmt: int, bits: int, rate: int = 16_000, channels: int = 1):
    block = channels * bits // 8
    fmt_chunk = struct.pack("<HHIIHH", fmt, channels, rate, rate * block, block, bits)
    body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt_chunk)) + fmt_chunk
    body += b"LIST" + struct.pack("<I", 3) + b"abc\x00"  # odd chunk: padded to even
    body += b"data" + struct.pack("<I", len(samples)) + samples
    return b"RIFF" + struct.pack("<I", len(body)) + body


def test_reads_16_bit_and_float_wavs(tmp_path: Path):
    pcm = tmp_path / "pcm.wav"
    pcm.write_bytes(wav_bytes(struct.pack("<3h", 0, 16384, -32768), fmt=1, bits=16))
    assert read_wav(pcm).tolist() == [0.0, 0.5, -1.0]
    floats = tmp_path / "float.wav"
    floats.write_bytes(wav_bytes(np.array([0.25, -0.75], dtype="<f4").tobytes(), fmt=3, bits=32))
    assert read_wav(floats).tolist() == [0.25, -0.75]


def test_wrong_rate_or_channels_are_explained(tmp_path: Path):
    stereo = tmp_path / "stereo.wav"
    stereo.write_bytes(wav_bytes(b"\x00" * 8, fmt=1, bits=16, channels=2))
    with pytest.raises(ValueError, match="16 kHz mono"):
        read_wav(stereo)
    cd = tmp_path / "cd.wav"
    cd.write_bytes(wav_bytes(b"\x00" * 4, fmt=1, bits=16, rate=44_100))
    with pytest.raises(ValueError, match="44100"):
        read_wav(cd)
    junk = tmp_path / "junk.wav"
    junk.write_bytes(b"not audio")
    with pytest.raises(ValueError, match="not a WAV"):
        read_wav(junk)


def test_option_is_parsed():
    args = build_parser().parse_args(["--engine-check", "clip.wav"])
    assert args.engine_check == Path("clip.wav")


def test_a_failure_still_writes_the_report(tmp_path: Path, monkeypatch, capsys):
    from livetranslator.app import engine_check as check

    monkeypatch.setenv("LIVETRANSLATOR_HOME", str(tmp_path))
    assert check.engine_check(tmp_path / "missing.wav") == 1
    report = next(tmp_path.rglob(check.REPORT_FILE)).read_text(encoding="utf-8")
    assert report.startswith("FAILED: FileNotFoundError")
    assert "FAILED" in capsys.readouterr().out
