"""T032 — speech-recognition benchmark on this PC (spec §5.4, §8; D-004, D-005, D-015, D-018).

    python -m benchmarks.asr_bench [--configs turbo-fp16,turbo-int8,...] [--skip-auto]

For every config:
- quality: pooled WER/CER per language with the language forced (how "Me" runs) and
  auto-detected (how "Others" runs), plus language-ID accuracy;
- latency per clip, and for fixed 2 s / 5 s / 10 s buffers;
- a streaming simulation: re-decode a growing buffer every 0.5 s / 1.0 s up to 10 s with word
  timestamps (what LocalAgreement does) -> GPU busy fraction for one and for two streams;
- 1 vs 2 model instances serving two streams at once;
- load time and VRAM added.
Results: benchmarks/results/asr.md (+ asr.json with raw numbers).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from benchmarks.corpus import FLEURS_CONFIGS, Corpus, load_corpus, read_wav
from benchmarks.harness import VramMonitor, gpu_info, markdown_table, write_results
from benchmarks.metrics import LatencyStats, corpus_error_rate, uses_cer
from livetranslator.platform.cuda import add_cuda_dll_dirs

RESULTS = Path(__file__).resolve().parent / "results"
MODELS_DIR = Path(os.environ.get("LT_BENCH_DIR", r"D:\LiveTranslator\bench-data")) / "models"
SR = 16_000
BUFFER_SECONDS = (2, 5, 10)
STREAM_SECONDS = 10.0


@dataclass(frozen=True)
class AsrConfig:
    key: str
    label: str
    model: str
    device: str
    compute_type: str
    streaming: bool = True  # run the streaming / two-instance tests


CONFIGS: tuple[AsrConfig, ...] = (
    AsrConfig("turbo-fp16", "large-v3-turbo · GPU · float16", "large-v3-turbo", "cuda", "float16"),
    AsrConfig(
        "turbo-int8",
        "large-v3-turbo · GPU · int8_float16",
        "large-v3-turbo",
        "cuda",
        "int8_float16",
    ),
    AsrConfig("small-int8", "small · GPU · int8_float16", "small", "cuda", "int8_float16"),
    AsrConfig("small-cpu", "small · CPU · int8", "small", "cpu", "int8", streaming=False),
)


@dataclass
class ConfigResult:
    config: AsrConfig
    load_s: float = 0.0
    vram_mb: int | None = None
    forced: dict[str, float] = field(default_factory=dict[str, float])  # lang -> error rate
    auto: dict[str, float] = field(default_factory=dict[str, float])
    lid_accuracy: float | None = None
    clip_latency: LatencyStats | None = None
    buffer_p50_ms: dict[int, float] = field(default_factory=dict[int, float])
    streaming_busy: dict[str, float] = field(default_factory=dict[str, float])
    two_instances: dict[str, float] = field(default_factory=dict[str, float])


def transcribe(
    model: Any, audio: NDArray[np.float32], language: str | None, **kw: Any
) -> tuple[str, str]:
    segments, info = model.transcribe(
        audio,
        language=language,
        beam_size=kw.pop("beam_size", 5),
        vad_filter=False,
        condition_on_previous_text=False,
        **kw,
    )
    text = " ".join(s.text.strip() for s in segments)
    return text, str(info.language)


def quality(model: Any, corpus: Corpus, result: ConfigResult, skip_auto: bool) -> None:
    latencies: list[float] = []
    lid_hits = lid_total = 0
    for lang in FLEURS_CONFIGS:
        refs: list[str] = []
        forced_hyps: list[str] = []
        auto_hyps: list[str] = []
        for sentence in corpus.sentences:
            audio = read_wav(corpus.audio_path(sentence, lang))
            refs.append(sentence.text[lang])
            start = time.perf_counter()
            text, _ = transcribe(model, audio, lang)
            latencies.append(time.perf_counter() - start)
            forced_hyps.append(text)
            if not skip_auto:
                text, detected = transcribe(model, audio, None)
                auto_hyps.append(text)
                lid_total += 1
                lid_hits += detected == lang
        result.forced[lang] = corpus_error_rate(refs, forced_hyps, lang)
        if auto_hyps:
            result.auto[lang] = corpus_error_rate(refs, auto_hyps, lang)
        print(f"  {lang}: {result.forced[lang]:.3f}", flush=True)
    result.clip_latency = LatencyStats.from_seconds(latencies)
    if lid_total:
        result.lid_accuracy = lid_hits / lid_total


def long_audio(corpus: Corpus, seconds: float) -> NDArray[np.float32]:
    parts = [read_wav(corpus.audio_path(s, "en")) for s in corpus.sentences]
    joined = np.concatenate(parts)
    return joined[: int(seconds * SR)]


def buffer_latency(model: Any, corpus: Corpus, result: ConfigResult) -> None:
    audio = long_audio(corpus, max(BUFFER_SECONDS))
    for seconds in BUFFER_SECONDS:
        clip = audio[: seconds * SR]
        samples = []
        for _ in range(5):
            start = time.perf_counter()
            transcribe(model, clip, "en")
            samples.append(time.perf_counter() - start)
        result.buffer_p50_ms[seconds] = LatencyStats.from_seconds(samples).p50_ms


def streaming_cost(model: Any, audio: NDArray[np.float32], interval: float, beam: int) -> float:
    """Seconds of decoding needed for STREAM_SECONDS of speech re-decoded every `interval`."""
    total = 0.0
    t = interval
    while t <= STREAM_SECONDS + 1e-9:
        start = time.perf_counter()
        transcribe(model, audio[: int(t * SR)], "en", beam_size=beam, word_timestamps=True)
        total += time.perf_counter() - start
        t += interval
    return total


def streaming(model: Any, corpus: Corpus, result: ConfigResult) -> None:
    audio = long_audio(corpus, STREAM_SECONDS)
    for interval in (0.5, 1.0):
        for beam in (1, 5):
            busy = streaming_cost(model, audio, interval, beam) / STREAM_SECONDS
            # One GPU worker serving two streams needs twice the decoding time.
            result.streaming_busy[f"{interval}s/beam{beam}/1 stream"] = busy
            result.streaming_busy[f"{interval}s/beam{beam}/2 streams"] = 2 * busy


def two_instances(
    make_model: Callable[[], Any], model: Any, corpus: Corpus, result: ConfigResult
) -> None:
    """Wall time for two streams' work: one instance (sequential) vs two instances (threads)."""
    audio = long_audio(corpus, STREAM_SECONDS)

    def work(m: Any) -> None:
        streaming_cost(m, audio, 1.0, 1)

    start = time.perf_counter()
    work(model)
    work(model)
    sequential = time.perf_counter() - start
    second = make_model()
    threads = [threading.Thread(target=work, args=(m,)) for m in (model, second)]
    start = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    parallel = time.perf_counter() - start
    del second
    result.two_instances = {
        "one instance, sequential (s)": sequential,
        "two instances, parallel (s)": parallel,
        "speed-up": sequential / parallel,
    }


def run_config(config: AsrConfig, corpus: Corpus, skip_auto: bool) -> ConfigResult:
    from faster_whisper import WhisperModel

    result = ConfigResult(config)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    def make_model() -> Any:
        return WhisperModel(
            config.model,
            device=config.device,
            compute_type=config.compute_type,
            download_root=str(MODELS_DIR),
        )

    make_model()  # first call may download; don't count that as load time
    with VramMonitor() as vram:
        start = time.perf_counter()
        model = make_model()
        result.load_s = time.perf_counter() - start
        transcribe(model, long_audio(corpus, 2), "en")  # warm-up inside the VRAM window
        result.vram_mb = vram.peak_delta_mb if config.device == "cuda" else None
    print(f"{config.key}: loaded in {result.load_s:.1f}s, VRAM +{result.vram_mb} MB", flush=True)
    quality(model, corpus, result, skip_auto or config.device == "cpu")
    buffer_latency(model, corpus, result)
    if config.streaming:
        streaming(model, corpus, result)
        two_instances(make_model, model, corpus, result)
    del model
    return result


def report(results: list[ConfigResult]) -> None:
    gpu = gpu_info()
    langs = list(FLEURS_CONFIGS)
    unit = {lang: ("CER" if uses_cer(lang) else "WER") for lang in langs}
    setup = (
        f"- GPU: {gpu.name if gpu else 'n/a'} ({gpu.total_mb if gpu else '?'} MB, driver "
        f"{gpu.driver if gpu else '?'})\n"
        f"- Corpus: FLEURS dev, 20 sentences x {len(langs)} languages (benchmarks/README.md)\n"
        "- faster-whisper, beam 5, no VAD, no conditioning on previous text, unless noted\n"
        "- Error rates are pooled; lower is better. "
        + ", ".join(f"{lang}={unit[lang]}" for lang in langs)
        + "\n"
    )
    quality_rows = [[r.config.label, *(r.forced.get(lang) for lang in langs)] for r in results]
    auto_rows = [
        [r.config.label, r.lid_accuracy, *(r.auto.get(lang) for lang in langs)]
        for r in results
        if r.auto
    ]
    speed_rows = [
        [
            r.config.label,
            r.load_s,
            r.vram_mb,
            r.clip_latency.p50_ms if r.clip_latency else None,
            r.clip_latency.p95_ms if r.clip_latency else None,
            *(r.buffer_p50_ms.get(s) for s in BUFFER_SECONDS),
        ]
        for r in results
    ]
    stream_keys = sorted({k for r in results for k in r.streaming_busy})
    stream_rows = [
        [r.config.label, *(r.streaming_busy.get(k) for k in stream_keys)]
        for r in results
        if r.streaming_busy
    ]
    two_rows = [[r.config.label, *r.two_instances.values()] for r in results if r.two_instances]
    sections = [
        ("Setup", setup),
        (
            "Quality — language given (how 'Me' runs)",
            markdown_table(["Config", *langs], quality_rows),
        ),
        (
            "Quality — language auto-detected (how 'Others' runs)",
            markdown_table(["Config", "Lang-ID acc.", *langs], auto_rows),
        ),
        (
            "Speed and memory",
            markdown_table(
                [
                    "Config",
                    "Load s",
                    "VRAM MB",
                    "Clip p50 ms",
                    "Clip p95 ms",
                    *(f"{s} s buffer p50 ms" for s in BUFFER_SECONDS),
                ],
                speed_rows,
            ),
        ),
        (
            "Streaming load (fraction of GPU time busy; > 1.0 = can't keep up)",
            "Growing 10 s buffer re-decoded every 0.5 s or 1.0 s with word timestamps.\n\n"
            + markdown_table(["Config", *stream_keys], stream_rows),
        ),
        (
            "Two streams: one model instance vs two (D-018)",
            markdown_table(
                ["Config", "1 instance seq. s", "2 instances par. s", "Speed-up"], two_rows
            ),
        ),
    ]
    write_results(RESULTS / "asr.md", "ASR benchmark (T032)", sections)
    raw = [
        {**asdict(r), "clip_latency": asdict(r.clip_latency) if r.clip_latency else None}
        for r in results
    ]
    (RESULTS / "asr.json").write_text(json.dumps(raw, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    parser.add_argument("--configs", default=",".join(c.key for c in CONFIGS))
    parser.add_argument("--skip-auto", action="store_true")
    args = parser.parse_args(argv)
    add_cuda_dll_dirs()
    wanted = set(args.configs.split(","))
    corpus = load_corpus()
    results = [run_config(c, corpus, args.skip_auto) for c in CONFIGS if c.key in wanted]
    report(results)
    print(f"wrote {RESULTS / 'asr.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
