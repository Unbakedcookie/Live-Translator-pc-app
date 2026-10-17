"""T035 — speaker-label (diarization) benchmark on this PC (spec §5.13; D-029).

    python -m benchmarks.diar_bench

Test material is built from FLEURS dev with known ground truth: recordings of the SAME
sentence are by different people (FLEURS has up to 3 speakers per sentence, gender noted),
and each recording is cut into turns at its quietest points, so every turn's speaker is
known. Mixes: 2 speakers M+F, 2 speakers F+F (hard), 3 speakers incl. a back-to-back turn
with no pause, 4 speakers (3 en + 1 es).

Approaches (all sherpa-onnx on CPU: pyannote segmentation-3.0 MIT + NeMo TitaNet CC-BY-4.0):
  A offline   whole mix at once (upper bound; not usable live)
  B window    the spec's design: re-diarize the last 10 s every 1 s, match local clusters
              to running speaker centroids by embedding
  C per-line  one embedding per VAD utterance (our ASR segmenter), online centroid matching;
              a label is ready when the line ends
diart is not run: its pyannote models are gated (needs the user's HF token; D-024).
Results: benchmarks/results/diarization.md (+ .json).
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from benchmarks.asr_bench import MODELS_DIR, RESULTS
from benchmarks.corpus import FLEURS_REVISION, SPLIT, default_dest, extract_selected, read_wav
from benchmarks.diar_metrics import Segment, der, turn_accuracy
from benchmarks.harness import markdown_table, write_results
from livetranslator.services.asr.vad import FRAME, Segmenter, SileroVad, frame_energy

SR = 16_000
Audio = NDArray[np.float32]
DIAR_MODELS = MODELS_DIR / "diarization"
SEGMENTATION = DIAR_MODELS / "pyannote-segmentation-3-0" / "model.onnx"
EMBEDDINGS = {
    "titanet-large": DIAR_MODELS / "nemo_en_titanet_large.onnx",
    "titanet-small": DIAR_MODELS / "nemo_en_titanet_small.onnx",
}
MAX_SPEAKERS = 6  # spec §5.13 default


@dataclass(frozen=True)
class MixSpec:
    name: str
    speakers: tuple[tuple[str, int, int], ...]  # (FLEURS config, sentence id, recording no.)
    pattern: tuple[int, ...]  # speaker index per turn
    gaps: tuple[float, ...]  # silence before turn 2, 3, ... (0 = back-to-back)


MIXES: tuple[MixSpec, ...] = (
    MixSpec("2 speakers, en, M+F", (("en_us", 1544, 0), ("en_us", 1544, 1)), (0, 1, 0, 1),
            (0.7, 0.8, 0.6)),
    MixSpec("2 speakers, en, F+F", (("en_us", 1557, 0), ("en_us", 1557, 1)), (0, 1, 0, 1),
            (0.7, 0.8, 0.6)),
    MixSpec("3 speakers, es, M+M+F", (("es_419", 1551, 0), ("es_419", 1551, 1),
            ("es_419", 1551, 2)), (0, 1, 2, 0, 1, 2), (0.7, 0.8, 0.0, 0.7, 0.6)),
    MixSpec("4 speakers, 3 en + 1 es", (("en_us", 1544, 0), ("en_us", 1544, 1),
            ("en_us", 1544, 2), ("es_419", 1635, 1)), (0, 1, 2, 3, 0, 1, 2, 3),
            (0.7, 0.6, 0.8, 0.7, 0.6, 0.0, 0.7)),
)  # fmt: skip


@dataclass
class Mix:
    spec: MixSpec
    audio: Audio
    turns: list[Segment]  # reference (start, end, speaker)
    genders: list[str]


# ---------------------------------------------------------------- test material


def fleurs_dir() -> Path:
    return default_dest() / "hf-cache" / "datasets--google--fleurs" / "snapshots" / FLEURS_REVISION


def tsv_rows(cfg: str) -> dict[int, list[tuple[str, str]]]:
    """sentence id -> [(file name, gender)] sorted by file name."""
    rows: dict[int, list[tuple[str, str]]] = {}
    text = (fleurs_dir() / "data" / cfg / f"{SPLIT}.tsv").read_text(encoding="utf-8")
    for line in text.splitlines():
        fields = line.split("\t")
        if len(fields) >= 7 and fields[0].isdigit():
            rows.setdefault(int(fields[0]), []).append((fields[1], fields[6]))
    return {k: sorted(v) for k, v in rows.items()}


def rms_frames(audio: Audio, frame: int = 320) -> Audio:
    n = len(audio) // frame
    shaped = audio[: n * frame].reshape(n, frame).astype(np.float64)
    return np.sqrt((shaped**2).mean(axis=1)).astype(np.float32)


def trim_silence(audio: Audio, frame: int = 320) -> Audio:
    energy = rms_frames(audio, frame)
    loud = np.nonzero(energy > 0.1 * float(energy.max()))[0]
    if loud.size == 0:
        return audio
    return audio[max(loud[0] - 5, 0) * frame : (loud[-1] + 6) * frame]


def split_quietly(
    audio: Audio, pieces: int, frame: int = 320, search_s: float = 0.8
) -> list[Audio]:
    """Cut into `pieces` parts at the quietest 20 ms frame near each equal-length cut."""
    energy = rms_frames(audio, frame)
    window = int(search_s * SR / frame)
    cuts = [0]
    for j in range(1, pieces):
        ideal = len(energy) * j // pieces
        lo, hi = max(ideal - window, cuts[-1] + 1), min(ideal + window, len(energy) - 1)
        cuts.append(lo + int(np.argmin(energy[lo:hi])))
    cuts.append(len(energy))
    return [audio[a * frame : b * frame] for a, b in itertools.pairwise(cuts)]


def build_mix(spec: MixSpec, cache: Path) -> Mix:
    clips: list[Audio] = []
    genders: list[str] = []
    for cfg, sentence_id, index in spec.speakers:
        name, gender = tsv_rows(cfg)[sentence_id][index]
        target = cache / cfg / name.replace(".wav", "") / name
        if not target.exists():
            archive = fleurs_dir() / "data" / cfg / "audio" / f"{SPLIT}.tar.gz"
            extract_selected(archive, {name: target})
        clips.append(trim_silence(read_wav(target)))
        genders.append(gender)
    turns_per_speaker = [spec.pattern.count(i) for i in range(len(spec.speakers))]
    pieces = [split_quietly(c, n) for c, n in zip(clips, turns_per_speaker, strict=True)]
    used = [0] * len(spec.speakers)
    parts: list[Audio] = [np.zeros(SR, np.float32)]
    turns: list[Segment] = []
    t = 1.0
    for k, speaker in enumerate(spec.pattern):
        if k > 0:
            gap = spec.gaps[k - 1]
            parts.append(np.zeros(int(gap * SR), np.float32))
            t += gap
        piece = pieces[speaker][used[speaker]]
        used[speaker] += 1
        parts.append(piece)
        turns.append((t, t + len(piece) / SR, f"S{speaker + 1}"))
        t += len(piece) / SR
    parts.append(np.zeros(SR, np.float32))
    return Mix(spec, np.concatenate(parts), turns, genders)


# ---------------------------------------------------------------- engines


def embedding_extractor(model: Path) -> Any:
    import sherpa_onnx

    config = sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(model), num_threads=2)
    return sherpa_onnx.SpeakerEmbeddingExtractor(config)


def embed(extractor: Any, audio: Audio) -> Audio:
    stream = extractor.create_stream()
    stream.accept_waveform(SR, audio)
    stream.input_finished()
    vector = np.asarray(extractor.compute(stream), dtype=np.float32)
    return vector / (np.linalg.norm(vector) + 1e-9)


def offline_diarizer(embedding: Path, threshold: float) -> Any:
    import sherpa_onnx

    config = sherpa_onnx.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(
                model=str(SEGMENTATION)
            ),
            num_threads=2,
        ),
        embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(embedding), num_threads=2),
        clustering=sherpa_onnx.FastClusteringConfig(num_clusters=-1, threshold=threshold),
        min_duration_on=0.3,
        min_duration_off=0.5,
    )
    return sherpa_onnx.OfflineSpeakerDiarization(config)


def run_offline(sd: Any, audio: Audio) -> list[Segment]:
    result = sd.process(audio).sort_by_start_time()
    return [(float(s.start), float(s.end), str(s.speaker)) for s in result]


class Centroids:
    """Online speaker memory: running mean embedding per speaker (memory only, D-028)."""

    def __init__(self, threshold: float, max_speakers: int = MAX_SPEAKERS) -> None:
        self.threshold = threshold
        self.max_speakers = max_speakers
        self.sums: list[Audio] = []

    def assign(self, vector: Audio, weight: float = 1.0) -> str:
        if self.sums:
            means = [s / (np.linalg.norm(s) + 1e-9) for s in self.sums]
            sims = [float(np.dot(vector, m)) for m in means]
            best = int(np.argmax(sims))
            if sims[best] >= self.threshold or len(self.sums) >= self.max_speakers:
                self.sums[best] = (self.sums[best] + weight * vector).astype(np.float32)
                return str(best)
        self.sums.append((weight * vector).astype(np.float32))
        return str(len(self.sums) - 1)


def vad_utterances(audio: Audio) -> list[tuple[int, int]]:
    """Our ASR segmenter's utterances (Silero + Segmenter, state reset after each close)."""
    vad, segmenter = SileroVad(), Segmenter()
    spans: list[tuple[int, int]] = []
    start: int | None = None
    for i in range(len(audio) // FRAME):
        frame = audio[i * FRAME : (i + 1) * FRAME]
        for event in segmenter.push(vad(frame), frame_energy(frame)):
            if event.kind == "open":
                start = event.sample
            elif start is not None:
                spans.append((start, event.sample))
                start = None
                if event.reason == "silence":
                    vad.reset()
    for event in segmenter.flush():
        if start is not None:
            spans.append((start, event.sample))
    return spans


def run_per_line(extractor: Any, audio: Audio, threshold: float) -> tuple[list[Segment], float]:
    """Approach C. Returns hypothesis segments and mean embedding time per line (s)."""
    memory = Centroids(threshold)
    segments: list[Segment] = []
    times: list[float] = []
    for start, end in vad_utterances(audio):
        if end - start < int(0.3 * SR):
            continue
        t0 = time.perf_counter()
        vector = embed(extractor, audio[start:end])
        times.append(time.perf_counter() - t0)
        segments.append((start / SR, end / SR, memory.assign(vector, (end - start) / SR)))
    return segments, float(np.mean(times)) if times else 0.0


def run_window(
    sd: Any,
    extractor: Any,
    audio: Audio,
    threshold: float,
    window_s: float = 10.0,
    hop_s: float = 1.0,
) -> tuple[list[Segment], float]:
    """Approach B. Every hop, diarize the last `window_s` and label the newest hop's speech
    through the global centroid memory. Returns segments and compute time per hop (s)."""
    memory = Centroids(threshold)
    segments: list[Segment] = []
    times: list[float] = []
    hop = int(hop_s * SR)
    for end in range(hop, len(audio) + 1, hop):
        start = max(0, end - int(window_s * SR))
        t0 = time.perf_counter()
        local = run_offline(sd, audio[start:end])
        by_label: dict[str, list[tuple[float, float]]] = {}
        for s, e, label in local:
            by_label.setdefault(label, []).append((s, e))
        global_label: dict[str, str] = {}
        for label, spans in by_label.items():
            pieces = [audio[start + int(s * SR) : start + int(e * SR)] for s, e in spans]
            joined = np.concatenate(pieces) if pieces else np.zeros(0, np.float32)
            if len(joined) >= int(0.5 * SR):
                seconds = len(joined) / SR
                global_label[label] = memory.assign(embed(extractor, joined), seconds)
        times.append(time.perf_counter() - t0)
        hop_start = (end - hop) / SR - start / SR
        for s, e, label in local:
            lo, hi = max(s, hop_start), e
            if hi > lo and label in global_label:
                segments.append((start / SR + lo, start / SR + hi, global_label[label]))
    return segments, float(np.mean(times)) if times else 0.0


def label_switches(turns: Sequence[Segment], hyp: Sequence[Segment]) -> float:
    """Average number of label changes inside a reference turn (0 = stable)."""
    changes = 0
    for t_start, t_end, _ in turns:
        inside = [h[2] for h in sorted(hyp) if min(h[1], t_end) - max(h[0], t_start) > 0.2]
        changes += sum(1 for a, b in itertools.pairwise(inside) if a != b)
    return changes / len(turns) if turns else 0.0


def turn_labels(turns: Sequence[Segment], hyp: Sequence[Segment]) -> list[str | None]:
    """The hypothesis label covering most of each reference turn."""
    labels: list[str | None] = []
    for t_start, t_end, _ in turns:
        cover: dict[str, float] = {}
        for h_start, h_end, label in hyp:
            shared = min(h_end, t_end) - max(h_start, t_start)
            if shared > 0:
                cover[label] = cover.get(label, 0.0) + shared
        labels.append(max(cover, key=lambda k: cover[k]) if cover else None)
    return labels


# ---------------------------------------------------------------- run + report


@dataclass
class Row:
    material: str  # "as recorded" / "level-matched"
    approach: str
    embedding: str
    setting: str  # e.g. "similarity 0.6" (C), "distance 0.5" (A), "dist 0.5 / sim 0.6" (B)
    per_mix: dict[str, dict[str, float]] = field(default_factory=dict[str, dict[str, float]])
    compute_s: float = 0.0  # per line (C) / per hop (B) / per audio second (A)


def level_matched(mix: Mix, rms: float = 0.05) -> Mix:
    """Every turn scaled to the same loudness (about -26 dBFS). FLEURS recordings differ by up
    to ~38 dB, which is a stress test; this variant isolates who-is-who from loudness."""
    audio = mix.audio.copy()
    for start, end, _ in mix.turns:
        a, b = int(start * SR), int(end * SR)
        level = float(np.sqrt(np.mean(np.square(audio[a:b], dtype=np.float64))))
        if level > 0:
            audio[a:b] *= rms / level
    return Mix(mix.spec, audio.astype(np.float32), mix.turns, mix.genders)


def evaluate(mixes: Sequence[Mix], run: Callable[[Mix], tuple[list[Segment], float]]) -> Row:
    row = Row("", "", "", "")
    costs: list[float] = []
    for mix in mixes:
        hyp, cost = run(mix)
        costs.append(cost)
        result = der(mix.turns, hyp)
        accuracy, _ = turn_accuracy(mix.turns, turn_labels(mix.turns, hyp))
        row.per_mix[mix.spec.name] = {
            "der": result.der,
            "confusion": result.confusion,
            "miss": result.miss,
            "false_alarm": result.false_alarm,
            "turn_accuracy": accuracy,
            "speakers_found": float(len({h[2] for h in hyp})),
            "switches": label_switches(mix.turns, hyp),
        }
    row.compute_s = float(np.mean(costs)) if costs else 0.0
    return row


SIMILARITIES = (0.5, 0.6, 0.7)  # C/B: cosine similarity needed to join a known speaker
DISTANCES = (0.2, 0.5)  # A/B: sherpa FastClustering distance (higher = merges more)


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description="Speaker-label benchmark (T035).").parse_args(argv)
    cache = default_dest() / "diarization"
    recorded = [build_mix(spec, cache) for spec in MIXES]
    for mix in recorded:
        print(f"{mix.spec.name}: {len(mix.audio) / SR:.1f} s, genders {mix.genders}", flush=True)
    materials = {"as recorded": recorded, "level-matched": [level_matched(m) for m in recorded]}
    extractors = {name: embedding_extractor(path) for name, path in EMBEDDINGS.items()}
    large = EMBEDDINGS["titanet-large"]

    rows: list[Row] = []

    def add(row: Row, material: str, approach: str, embedding: str, setting: str) -> None:
        row.material, row.approach, row.embedding, row.setting = (
            material, approach, embedding, setting
        )  # fmt: skip
        rows.append(row)
        print(f"{material} | {approach} {embedding} {setting}: {summary(row)}", flush=True)

    for material, mixes in materials.items():
        for emb_name, extractor in extractors.items():
            for sim in SIMILARITIES:

                def per_line(
                    mix: Mix, ex: Any = extractor, sim: float = sim
                ) -> tuple[list[Segment], float]:
                    return run_per_line(ex, mix.audio, sim)

                add(
                    evaluate(mixes, per_line), material, "C per-line", emb_name, f"similarity {sim}"
                )
        for dist in DISTANCES:
            sd = offline_diarizer(large, dist)

            def offline(mix: Mix, sd: Any = sd) -> tuple[list[Segment], float]:
                t0 = time.perf_counter()
                hyp = run_offline(sd, mix.audio)
                return hyp, (time.perf_counter() - t0) / (len(mix.audio) / SR)

            add(
                evaluate(mixes, offline), material, "A offline", "titanet-large", f"distance {dist}"
            )
        sd = offline_diarizer(large, 0.5)

        def window(mix: Mix, sd: Any = sd) -> tuple[list[Segment], float]:
            return run_window(sd, extractors["titanet-large"], mix.audio, 0.6)

        add(evaluate(mixes, window), material, "B window 10s/1s", "titanet-large",
            "dist 0.5 / sim 0.6")  # fmt: skip
    report(recorded, rows)
    print(f"wrote {RESULTS / 'diarization.md'}")
    return 0


def summary(row: Row) -> str:
    ders = [m["der"] for m in row.per_mix.values()]
    accs = [m["turn_accuracy"] for m in row.per_mix.values()]
    return f"mean DER {np.mean(ders):.3f}, mean turn accuracy {np.mean(accs):.2f}"


def report(mixes: Sequence[Mix], rows: Sequence[Row]) -> None:
    names = [m.spec.name for m in mixes]
    setup = (
        "- CPU only (sherpa-onnx 1.13.8, 2 threads): pyannote segmentation-3.0 (MIT) + NeMo "
        "TitaNet large/small (CC-BY-4.0). No graphics memory used.\n"
        "- Mixes from FLEURS dev (CC-BY-4.0): different recordings of one sentence = different "
        "people; each recording cut into turns at its quietest points.\n"
        + "".join(
            f"- {m.spec.name}: {len(m.audio) / SR:.0f} s, {len(m.turns)} turns, "
            f"genders {', '.join(m.genders)}\n"
            for m in mixes
        )
        + "- DER with a 0.25 s collar (miss + false alarm + confusion). Turn accuracy = share "
        "of turns given the right speaker. Switches = label changes inside one turn.\n"
        "- Compute: A = seconds per second of audio; B = seconds per 1 s hop; C = seconds "
        "per line (embedding only).\n"
        "- Material: *as recorded* keeps FLEURS loudness (some speakers ~38 dB quieter: a "
        "stress test); *level-matched* scales every turn to about -26 dBFS.\n"
        "- Settings: *similarity* = cosine similarity a line needs to join a known speaker "
        "(higher = more speakers); *distance* = sherpa clustering distance (higher = fewer).\n"
        "- diart not run: its models are gated (needs your Hugging Face token, D-024).\n"
    )
    der_table = markdown_table(
        ["Material", "Approach", "Embedding", "Setting", *names, "Mean", "Compute s"],
        [
            [r.material, r.approach, r.embedding, r.setting,
             *(r.per_mix[n]["der"] for n in names),
             float(np.mean([r.per_mix[n]["der"] for n in names])), r.compute_s]
            for r in rows
        ],
    )  # fmt: skip
    acc_table = markdown_table(
        ["Material", "Approach", "Embedding", "Setting", *names],
        [
            [r.material, r.approach, r.embedding, r.setting,
             *(f"{r.per_mix[n]['turn_accuracy']:.2f} ({r.per_mix[n]['speakers_found']:.0f} spk, "
               f"{r.per_mix[n]['switches']:.1f} sw)" for n in names)]
            for r in rows
        ],
    )  # fmt: skip
    write_results(
        RESULTS / "diarization.md",
        "Speaker-label benchmark (T035)",
        [
            ("Setup", setup),
            ("DER (lower is better)", der_table),
            ("Turn accuracy (speakers found, label switches per turn)", acc_table),
        ],
    )
    raw = [r.__dict__ for r in rows]
    (RESULTS / "diarization.json").write_text(json.dumps(raw, indent=2), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
