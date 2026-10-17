"""T031 — benchmark metrics and corpus helpers (Tier A, hand-computed)."""

import io
import tarfile
import wave
from pathlib import Path

import numpy as np
import pytest

from benchmarks.corpus import (
    FleursRow,
    extract_selected,
    first_recording,
    parse_tsv,
    read_wav,
    shared_sentence_ids,
)
from benchmarks.metrics import (
    LatencyStats,
    chrf,
    corpus_error_rate,
    error_rate,
    normalize,
)


def test_normalize():
    assert normalize("Hello, World!  It's 'Number One'.") == "hello world it s number one"
    assert normalize("場にふさわしい敬意を払い、尊厳。") == "場にふさわしい敬意を払い 尊厳"


def test_wer_hand_computed():
    # ref 6 words; hyp substitutes sat->sit and deletes one "the": 2 edits / 6 = 0.3333
    assert error_rate("The cat sat on the mat.", "the cat sit on mat", "en") == pytest.approx(2 / 6)
    assert error_rate("Hola, ¿qué tal?", "hola qué tal", "es") == 0.0


def test_cer_for_japanese_hand_computed():
    # 5 characters, one substitution (は -> わ): 1/5
    assert error_rate("こんにちは。", "こんにちわ", "ja") == pytest.approx(0.2)
    assert error_rate("你好 世界", "你好世界", "zh") == 0.0  # spaces aren't part of the script


def test_corpus_rate_is_pooled():
    # sentence 1: 0 edits / 2 words; sentence 2: 1 edit / 1 word -> pooled 1/3 (mean would be 0.5)
    assert corpus_error_rate(["a b", "c"], ["a b", "d"], "en") == pytest.approx(1 / 3)


def test_chrf_bounds():
    assert chrf(["the same sentence"], ["the same sentence"]) == pytest.approx(100.0)
    assert chrf(["xyz"], ["abc"]) == pytest.approx(0.0)


def test_latency_percentiles_hand_computed():
    # ms = 10..50; p50 = 30; p95 index 0.95*4 = 3.8 -> 40 + 0.8*10 = 48; mean 30
    stats = LatencyStats.from_seconds([0.010, 0.020, 0.030, 0.040, 0.050])
    assert (stats.n, stats.p50_ms, stats.p95_ms, stats.mean_ms) == pytest.approx((5, 30, 48, 30))
    with pytest.raises(ValueError):
        LatencyStats.from_seconds([])


TSV = (
    "1590\tb.wav\tThe main beer.\tthe main beer\tt h e\t12345\tMALE\n"
    "1590\ta.wav\tThe main beer.\tthe main beer\tt h e\t12000\tFEMALE\n"
    "1516\tc.wav\tBe respectful.\tbe respectful\tb e\t9000\tMALE\n"
)


def test_parse_tsv_and_selection():
    rows = parse_tsv(TSV)
    assert rows[0] == FleursRow(1590, "b.wav", "The main beer.")
    assert first_recording(rows, 1590).file_name == "a.wav"
    by_lang = {
        "en": rows,
        "ja": [
            FleursRow(1516, "x.wav", "..."),
            FleursRow(1590, "y.wav", "..."),
            FleursRow(7, "z.wav", "..."),
        ],
    }
    assert shared_sentence_ids(by_lang, 5) == [1516, 1590]
    assert shared_sentence_ids(by_lang, 1) == [1516]


def _tar_with(tmp_path: Path, members: dict[str, bytes]) -> Path:
    path = tmp_path / "audio.tar.gz"
    with tarfile.open(path, "w:gz") as tar:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return path


def test_extract_only_wanted_and_never_outside(tmp_path: Path):
    archive = _tar_with(
        tmp_path,
        {"dev/a.wav": b"AAA", "dev/skip.wav": b"SSS", "../../evil.wav": b"EVIL"},
    )
    out = tmp_path / "out"
    written = extract_selected(archive, {"a.wav": out / "en" / "1.wav", "evil.wav": out / "x.wav"})
    assert written == {"a.wav", "evil.wav"}
    assert (out / "en" / "1.wav").read_bytes() == b"AAA"
    assert (out / "x.wav").read_bytes() == b"EVIL"  # written only where WE said
    assert not (tmp_path.parent / "evil.wav").exists()
    assert not (out / "en" / "skip.wav").exists()


def test_read_wav_scales_int16(tmp_path: Path):
    path = tmp_path / "t.wav"
    samples = np.array([0, 16384, -32768, 32767], dtype="<i2")
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(samples.tobytes())
    audio = read_wav(path)
    assert audio.dtype == np.float32
    assert audio.tolist() == pytest.approx([0.0, 0.5, -1.0, 32767 / 32768])
    stereo = tmp_path / "s.wav"
    with wave.open(str(stereo), "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00\x00\x00")
    with pytest.raises(ValueError, match="expected 16 kHz mono"):
        read_wav(stereo)


def _float_wav(path: Path, values: list[float], rate: int = 16000) -> None:
    """Hand-built FLEURS-style WAV: format 3 (IEEE float), 18-byte fmt chunk (cbSize = 0)."""
    import struct

    data = np.asarray(values, dtype="<f4").tobytes()
    fmt = struct.pack("<HHIIHHH", 3, 1, rate, rate * 4, 4, 32, 0)
    body = (
        b"WAVE"
        + b"fmt "
        + struct.pack("<I", len(fmt))
        + fmt
        + b"data"
        + struct.pack("<I", len(data))
        + data
    )
    path.write_bytes(b"RIFF" + struct.pack("<I", len(body)) + body)


def test_read_wav_float32_like_fleurs(tmp_path: Path):
    path = tmp_path / "f.wav"
    _float_wav(path, [0.25, -0.5, 1.0])
    audio = read_wav(path)
    assert audio.dtype == np.float32
    assert audio.tolist() == [0.25, -0.5, 1.0]
    _float_wav(path, [0.0], rate=48000)
    with pytest.raises(ValueError, match="expected 16 kHz mono"):
        read_wav(path)


def test_read_real_fleurs_clip_if_present():
    from benchmarks.corpus import default_dest

    clip = default_dest() / "fleurs" / "en" / "1510.wav"
    if not clip.exists():
        pytest.skip("benchmark corpus not downloaded")
    audio = read_wav(clip)
    assert 1.0 < len(audio) / 16000 < 30.0
    assert float(np.abs(audio).max()) <= 1.0
