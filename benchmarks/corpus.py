"""FLEURS benchmark corpus (T031; DATA_TRACKER D-017).

FLEURS (google/fleurs, CC-BY-4.0, not gated) reads the same sentences aloud in many languages,
and the sentence id is shared across languages. So one small download gives both ASR clips
with references and a parallel text set for MT in every language pair.

Data lives OUTSIDE the repo (default D:\\LiveTranslator\\bench-data, or LT_BENCH_DIR) and is
never shipped. Archives are treated as untrusted: only the selected .wav files are read, and
output paths are built by us, never taken from archive member names.

    python -m benchmarks.corpus [--dest DIR] [--n 20]
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import struct
import sys
import tarfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import numpy as np
from numpy.typing import NDArray

FLEURS_REPO = "google/fleurs"
FLEURS_REVISION = "70bb2e84b976b7e960aa89f1c648e09c59f894dd"  # pinned 2026-10-17
FLEURS_LICENSE = "CC-BY-4.0"
SPLIT = "dev"
FLEURS_CONFIGS: dict[str, str] = {
    "en": "en_us",
    "es": "es_419",
    "fr": "fr_fr",
    "de": "de_de",
    "ru": "ru_ru",
    "ja": "ja_jp",
    "ko": "ko_kr",
    "zh": "cmn_hans_cn",
}
DEFAULT_SENTENCES = 20
SAMPLE_RATE = 16_000


def default_dest() -> Path:
    return Path(os.environ.get("LT_BENCH_DIR", r"D:\LiveTranslator\bench-data"))


@dataclass(frozen=True)
class FleursRow:
    sentence_id: int
    file_name: str
    raw: str  # original transcription with case and punctuation (our reference)


def parse_tsv(text: str) -> list[FleursRow]:
    """FLEURS TSV: id, file_name, raw_transcription, transcription, chars, num_samples, gender."""
    rows: list[FleursRow] = []
    reader = csv.reader(io.StringIO(text), delimiter="\t", quoting=csv.QUOTE_NONE)
    for fields in reader:
        if len(fields) < 3 or not fields[0].isdigit():
            continue
        rows.append(FleursRow(int(fields[0]), fields[1], fields[2]))
    return rows


def shared_sentence_ids(rows_by_lang: Mapping[str, Sequence[FleursRow]], n: int) -> list[int]:
    """The n smallest sentence ids present in every language (deterministic)."""
    id_sets = [{r.sentence_id for r in rows} for rows in rows_by_lang.values()]
    if not id_sets:
        return []
    return sorted(set.intersection(*id_sets))[:n]


def first_recording(rows: Sequence[FleursRow], sentence_id: int) -> FleursRow:
    """FLEURS has several speakers per sentence; take the lowest file name for determinism."""
    return min((r for r in rows if r.sentence_id == sentence_id), key=lambda r: r.file_name)


def extract_selected(archive: Path, wanted: Mapping[str, Path]) -> set[str]:
    """Copy only archive members whose base name is a key of `wanted` to the mapped path.

    Member paths never decide where data is written, so '../' or absolute names in a hostile
    archive can't escape. Returns the base names actually written.
    """
    written: set[str] = set()
    with tarfile.open(archive, "r:*") as tar:
        for member in tar:
            if not member.isfile():
                continue
            name = PurePosixPath(member.name).name
            target = wanted.get(name)
            if target is None or name in written:
                continue
            source = tar.extractfile(member)
            if source is None:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read())
            written.add(name)
    return written


WAVE_FORMAT_PCM = 1
WAVE_FORMAT_IEEE_FLOAT = 3


def read_wav(path: Path) -> NDArray[np.float32]:
    """16 kHz mono WAV, 16-bit PCM or 32-bit float -> float32 in [-1, 1].

    FLEURS ships 32-bit float WAVs (format 3, 18-byte fmt chunk), which the stdlib `wave`
    module can't read, so this walks the RIFF chunks itself.
    """
    data = path.read_bytes()
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError(f"{path.name}: not a RIFF/WAVE file")
    fmt: tuple[int, int, int, int] | None = None
    samples: bytes | None = None
    pos = 12
    while pos + 8 <= len(data):
        chunk_id = data[pos : pos + 4]
        size = struct.unpack_from("<I", data, pos + 4)[0]
        body = data[pos + 8 : pos + 8 + size]
        if chunk_id == b"fmt ":
            tag, channels, rate = struct.unpack_from("<HHI", body, 0)
            bits = struct.unpack_from("<H", body, 14)[0]
            fmt = (tag, channels, rate, bits)
        elif chunk_id == b"data":
            samples = body
        pos += 8 + size + (size & 1)  # chunks are word-aligned
    if fmt is None or samples is None:
        raise ValueError(f"{path.name}: missing fmt or data chunk")
    tag, channels, rate, bits = fmt
    if rate != SAMPLE_RATE or channels != 1:
        raise ValueError(f"{path.name}: expected 16 kHz mono, got {rate} Hz, {channels} ch")
    if tag == WAVE_FORMAT_PCM and bits == 16:
        return (np.frombuffer(samples, dtype="<i2").astype(np.float32) / 32768.0).astype(np.float32)
    if tag == WAVE_FORMAT_IEEE_FLOAT and bits == 32:
        return np.frombuffer(samples, dtype="<f4").astype(np.float32)
    raise ValueError(f"{path.name}: unsupported WAV format {tag} / {bits}-bit")


@dataclass(frozen=True)
class Sentence:
    sentence_id: int
    text: dict[str, str]  # language -> reference text
    audio: dict[str, str]  # language -> wav path relative to the corpus root


@dataclass(frozen=True)
class Corpus:
    root: Path
    sentences: tuple[Sentence, ...]

    def audio_path(self, sentence: Sentence, language: str) -> Path:
        return self.root / sentence.audio[language]


def load_corpus(root: Path | None = None) -> Corpus:
    root = root or default_dest()
    data = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    sentences = tuple(
        Sentence(int(s["id"]), dict(s["text"]), dict(s["audio"])) for s in data["sentences"]
    )
    return Corpus(root, sentences)


def build_corpus(dest: Path, n: int = DEFAULT_SENTENCES) -> Path:
    from huggingface_hub import hf_hub_download

    cache = dest / "hf-cache"

    def fetch(path_in_repo: str) -> Path:
        return Path(
            hf_hub_download(
                FLEURS_REPO,
                path_in_repo,
                repo_type="dataset",
                revision=FLEURS_REVISION,
                cache_dir=cache,
            )
        )

    rows_by_lang = {
        lang: parse_tsv(fetch(f"data/{cfg}/{SPLIT}.tsv").read_text(encoding="utf-8"))
        for lang, cfg in FLEURS_CONFIGS.items()
    }
    ids = shared_sentence_ids(rows_by_lang, n)
    if len(ids) < n:
        raise RuntimeError(f"only {len(ids)} sentences are shared by all languages")

    texts: dict[int, dict[str, str]] = {i: {} for i in ids}
    audio: dict[int, dict[str, str]] = {i: {} for i in ids}
    for lang, cfg in FLEURS_CONFIGS.items():
        wanted: dict[str, Path] = {}
        for sentence_id in ids:
            row = first_recording(rows_by_lang[lang], sentence_id)
            relative = f"fleurs/{lang}/{sentence_id}.wav"
            texts[sentence_id][lang] = row.raw
            audio[sentence_id][lang] = relative
            wanted[row.file_name] = dest / relative
        missing = set(wanted) - extract_selected(fetch(f"data/{cfg}/audio/{SPLIT}.tar.gz"), wanted)
        if missing:
            raise RuntimeError(f"{lang}: {len(missing)} selected clips not found in the archive")
        print(f"{lang}: {len(wanted)} clips")

    manifest = dest / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "source": FLEURS_REPO,
                "revision": FLEURS_REVISION,
                "license": FLEURS_LICENSE,
                "split": SPLIT,
                "sentences": [{"id": i, "text": texts[i], "audio": audio[i]} for i in ids],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download the FLEURS benchmark subset.")
    parser.add_argument("--dest", type=Path, default=default_dest())
    parser.add_argument("--n", type=int, default=DEFAULT_SENTENCES)
    args = parser.parse_args(argv)
    print(f"wrote {build_corpus(args.dest, args.n)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
