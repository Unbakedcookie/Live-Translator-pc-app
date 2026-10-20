"""Spike: does separating overlapping talkers help speech recognition? (user request
2026-10-20: "can it not manage multiple people talking over each other?").

    python -m benchmarks.separation mix                 # build the two-talker mixtures
    <torch env> -m benchmarks.separation separate MODEL # split each mixture into 2 tracks
    python -m benchmarks.separation score MODEL ...     # Whisper on mixtures vs tracks
    python -m benchmarks.separation detect              # overlap detector: mixes vs singles

Mixtures come from the FLEURS benchmark clips (CC-BY-4.0, local measurement only, D-017):
sentence i in one language over sentence i+7 in another, both at the same loudness or the
second 6 dB quieter, fully overlapping or the second starting half-way, with or without
pink noise at 15 dB SNR (a stand-in for game sound). Per talker we score the Whisper
error rate (WER, CER for zh) against that talker's reference text:
- baseline: one transcript of the mixture (what the app does today);
- separated: one transcript per output track, tracks matched to talkers by lowest error.
"Both understood" = both talkers' error <= 30 %.

The separate step runs where PyTorch is installed (D:/LiveTranslator/convert-venv); mix and
score run in the app venv (faster-whisper on the GPU). Not part of the app.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass
from itertools import permutations
from pathlib import Path

import numpy as np

from benchmarks.corpus import load_corpus, read_wav

RATE = 16_000
OUT = Path(r"D:\LiveTranslator\bench-data\separation")
LANGUAGE_PAIRS = (("en", "en"), ("en", "es"), ("es", "fr"), ("en", "zh"))
PAIRS_PER_LANGUAGE = 6
PARTNER_OFFSET = 7  # sentence i talks over sentence i + 7
QUIETER_DB = -6.0
NOISE_SNR_DB = 15.0
UNDERSTOOD = 0.30
SEED = 20261020


@dataclass(frozen=True)
class Mix:
    id: str
    lang_a: str
    lang_b: str
    text_a: str
    text_b: str
    overlap: str  # "full" or "half"
    gain_b_db: float
    noise: bool
    seconds: float


def _rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(x)) + 1e-12))


def pink_noise(n: int, rng: np.random.Generator) -> np.ndarray:
    """1/f noise by shaping white noise in the frequency domain."""
    spectrum = np.fft.rfft(rng.standard_normal(n))
    freqs = np.arange(len(spectrum), dtype=np.float64)
    freqs[0] = 1.0
    noise = np.fft.irfft(spectrum / np.sqrt(freqs), n)
    return (noise / _rms(noise)).astype(np.float32)


def mix_two(
    a: np.ndarray, b: np.ndarray, overlap: str, gain_b_db: float, noise: bool, rng
) -> np.ndarray:
    a = a / _rms(a) * 0.1
    b = b / _rms(b) * 0.1 * 10 ** (gain_b_db / 20)
    start_b = 0 if overlap == "full" else len(a) // 2
    out = np.zeros(max(len(a), start_b + len(b)), dtype=np.float32)
    out[: len(a)] += a
    out[start_b : start_b + len(b)] += b
    if noise:
        out += pink_noise(len(out), rng) * _rms(out) * 10 ** (-NOISE_SNR_DB / 20)
    peak = float(np.max(np.abs(out)))
    return (out / peak * 0.9 if peak > 0.9 else out).astype(np.float32)


def write_wav(path: Path, audio: np.ndarray) -> None:
    pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype("<i2").tobytes()
    header = b"RIFF" + (36 + len(pcm)).to_bytes(4, "little") + b"WAVEfmt "
    header += (16).to_bytes(4, "little") + (1).to_bytes(2, "little") + (1).to_bytes(2, "little")
    header += RATE.to_bytes(4, "little") + (RATE * 2).to_bytes(4, "little")
    header += (2).to_bytes(2, "little") + (16).to_bytes(2, "little")
    path.write_bytes(header + b"data" + len(pcm).to_bytes(4, "little") + pcm)


def build_mixes(out: Path = OUT) -> list[Mix]:
    corpus = load_corpus()
    sentences = corpus.sentences
    rng = np.random.default_rng(SEED)
    (out / "mixes").mkdir(parents=True, exist_ok=True)
    mixes: list[Mix] = []
    for lang_a, lang_b in LANGUAGE_PAIRS:
        for i in range(PAIRS_PER_LANGUAGE):
            sa, sb = sentences[i], sentences[(i + PARTNER_OFFSET) % len(sentences)]
            a = read_wav(corpus.audio_path(sa, lang_a))
            b = read_wav(corpus.audio_path(sb, lang_b))
            for overlap in ("full", "half"):
                for gain in (0.0, QUIETER_DB):
                    for noise in (False, True):
                        sound = "n" if noise else "c"
                        mix_id = f"{lang_a}-{lang_b}-{i}-{overlap}-{int(-gain)}db-{sound}"
                        audio = mix_two(a, b, overlap, gain, noise, rng)
                        write_wav(out / "mixes" / f"{mix_id}.wav", audio)
                        mixes.append(
                            Mix(
                                mix_id,
                                lang_a,
                                lang_b,
                                sa.text[lang_a],
                                sb.text[lang_b],
                                overlap,
                                gain,
                                noise,
                                round(len(audio) / RATE, 2),
                            )
                        )
    (out / "mixes.json").write_text(
        json.dumps([asdict(m) for m in mixes], ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return mixes


def load_mixes(out: Path = OUT) -> list[Mix]:
    return [Mix(**m) for m in json.loads((out / "mixes.json").read_text(encoding="utf-8"))]


# ------------------------------------------------------------------ scoring


def best_assignment(errors: list[list[float]]) -> tuple[float, float]:
    """errors[track][talker] -> (error A, error B) of the track-to-talker matching with the
    lowest sum (2 talkers; any number of tracks >= 1)."""
    if len(errors) == 1:
        return errors[0][0], errors[0][1]
    pairs = [(errors[ta][0], errors[tb][1]) for ta, tb in permutations(range(len(errors)), 2)]
    return min(pairs, key=sum)


def summarize(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Mean errors and the share of mixtures where both talkers were understood, per
    condition (overlap x loudness x noise) and overall."""
    groups: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        sound = "noise" if row["noise"] else "clean"
        key = f"{row['overlap']} overlap, B {row['gain_b_db']:+.0f} dB, {sound}"
        groups.setdefault(key, []).append(row)
        groups.setdefault("all", []).append(row)
    table: list[dict[str, object]] = []
    for key, items in groups.items():
        entry: dict[str, object] = {"condition": key, "n": len(items)}
        for kind in ("base", "sep"):
            a = [float(r[f"{kind}_a"]) for r in items if f"{kind}_a" in r]  # type: ignore[arg-type]
            b = [float(r[f"{kind}_b"]) for r in items if f"{kind}_b" in r]  # type: ignore[arg-type]
            if a and b:
                entry[f"{kind} err A"] = round(float(np.mean(a)), 2)
                entry[f"{kind} err B"] = round(float(np.mean(b)), 2)
                both = sum(x <= UNDERSTOOD and y <= UNDERSTOOD for x, y in zip(a, b, strict=True))
                entry[f"{kind} both ok"] = f"{both / len(a):.0%}"
        table.append(entry)
    return table


def score(models: list[str], out: Path = OUT, limit: int | None = None) -> int:
    from benchmarks.metrics import error_rate
    from livetranslator.services.asr.faster_whisper_engine import FasterWhisperEngine
    from tests.real_models import REAL_MODELS

    mixes = load_mixes(out)[:limit]
    engine = FasterWhisperEngine(REAL_MODELS)
    engine.load()

    def transcribe(path: Path) -> str:
        audio = read_wav(path)
        if _rms(audio) < 1e-4:
            return ""
        return engine.transcribe(audio, final=True).text.strip()

    def errors(text: str, mix: Mix) -> list[float]:
        return [
            min(1.0, error_rate(mix.text_a, text, mix.lang_a)),
            min(1.0, error_rate(mix.text_b, text, mix.lang_b)),
        ]

    for model in models:
        rows: list[dict[str, object]] = []
        timings = json.loads((out / "tracks" / model / "timings.json").read_text(encoding="utf-8"))
        for mix in mixes:
            row: dict[str, object] = asdict(mix)
            base = errors(transcribe(out / "mixes" / f"{mix.id}.wav"), mix)
            row["base_a"], row["base_b"] = base
            tracks = sorted((out / "tracks" / model).glob(f"{mix.id}_*.wav"))
            per_track = [errors(transcribe(t), mix) for t in tracks]
            row["sep_a"], row["sep_b"] = best_assignment(per_track)
            rows.append(row)
        table = summarize(rows)
        rtf = float(np.mean([t["seconds_taken"] / t["seconds_audio"] for t in timings.values()]))
        report = {
            "model": model,
            "separation_seconds_per_audio_second": round(rtf, 3),
            "summary": table,
            "rows": rows,
        }
        path = out / f"score-{model}.json"
        path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n{model}: separation {rtf:.3f} s per second of audio (see timings device)")
        for entry in table:
            print(entry)
    engine.unload()
    return 0


# ------------------------------------------------------------------ overlap detection

SEGMENTATION = Path(
    r"D:\LiveTranslator\bench-data\downloads\pyannote-seg"
    r"\sherpa-onnx-pyannote-segmentation-3-0\model.onnx"
)  # pyannote segmentation-3.0 (MIT), ONNX by k2-fsa/sherpa-onnx
WINDOW = 160_000  # 10 s, the model's window
FRAME_S = 270 / RATE  # receptive-field shift
OVERLAP_CLASSES = (4, 5, 6)  # powerset {0,1}, {0,2}, {1,2}
FLAG_S = 0.5  # a line counts as overlapped with at least this much two-talker speech


def overlap_seconds(session, audio: np.ndarray) -> float:
    total = 0.0
    for start in range(0, max(len(audio), 1), WINDOW):
        chunk = audio[start : start + WINDOW]
        if len(chunk) < RATE // 2:
            break
        x = np.zeros((1, 1, WINDOW), dtype=np.float32)
        x[0, 0, : len(chunk)] = chunk
        classes = session.run(None, {"x": x})[0][0].argmax(axis=-1)
        frames = int(np.isin(classes, OVERLAP_CLASSES)[: int(len(chunk) / 270)].sum())
        total += frames * FRAME_S
    return total


def detect(out: Path = OUT) -> int:
    import onnxruntime as ort

    session = ort.InferenceSession(str(SEGMENTATION), providers=["CPUExecutionProvider"])
    rng = np.random.default_rng(SEED + 1)
    results: dict[str, list[float]] = {"two talkers": [], "one talker": []}
    started = time.perf_counter()
    audio_s = 0.0
    for mix in load_mixes(out):
        audio = read_wav(out / "mixes" / f"{mix.id}.wav")
        audio_s += len(audio) / RATE
        results["two talkers"].append(overlap_seconds(session, audio))
    corpus = load_corpus()
    for sentence in corpus.sentences:
        for language in sentence.audio:
            clip = read_wav(corpus.audio_path(sentence, language))
            clip = clip / _rms(clip) * 0.1
            for noise in (False, True):
                audio = clip
                if noise:
                    audio = clip + pink_noise(len(clip), rng) * 0.1 * 10 ** (-NOISE_SNR_DB / 20)
                audio_s += len(audio) / RATE
                results["one talker"].append(overlap_seconds(session, audio.astype(np.float32)))
    taken = time.perf_counter() - started
    summary = {
        name: {
            "n": len(values),
            "flagged": f"{sum(v >= FLAG_S for v in values) / len(values):.0%}",
            "mean overlap s": round(float(np.mean(values)), 2),
        }
        for name, values in results.items()
    }
    summary["speed"] = {"cpu seconds per audio second": round(taken / audio_s, 4)}
    (out / "detect.json").write_text(json.dumps({"summary": summary, **results}, indent=1))
    for name, entry in summary.items():
        print(name, entry)
    return 0


# ------------------------------------------------------------------ separation


def separate(model: str, out: Path = OUT, limit: int | None = None) -> int:
    from benchmarks.separation_models import load_separator

    separator = load_separator(model)
    folder = out / "tracks" / model
    folder.mkdir(parents=True, exist_ok=True)
    timings: dict[str, dict[str, float]] = {}
    for mix in load_mixes(out)[:limit]:
        audio = read_wav(out / "mixes" / f"{mix.id}.wav")
        started = time.perf_counter()
        tracks = separator(audio)
        taken = time.perf_counter() - started
        for n, track in enumerate(tracks):
            peak = float(np.max(np.abs(track))) or 1.0
            write_wav(folder / f"{mix.id}_{n}.wav", track / peak * 0.9)
        timings[mix.id] = {"seconds_taken": taken, "seconds_audio": len(audio) / RATE}
        print(f"{mix.id}: {taken:.2f} s", flush=True)
    (folder / "timings.json").write_text(json.dumps(timings, indent=1), encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Speech separation spike")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("mix")
    sub.add_parser("detect")
    sep = sub.add_parser("separate")
    sep.add_argument("model")
    sep.add_argument("--limit", type=int)
    sc = sub.add_parser("score")
    sc.add_argument("models", nargs="+")
    sc.add_argument("--limit", type=int)
    args = parser.parse_args(argv)
    if args.command == "mix":
        print(f"{len(build_mixes())} mixtures in {OUT / 'mixes'}")
        return 0
    if args.command == "detect":
        return detect()
    if args.command == "separate":
        return separate(args.model, limit=args.limit)
    return score(args.models, limit=args.limit)


if __name__ == "__main__":
    sys.exit(main())
