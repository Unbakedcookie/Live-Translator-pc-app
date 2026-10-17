"""T033 — translation benchmark on this PC (spec §5.5, §8; D-004, D-005, D-019, D-031).

    python -m benchmarks.mt_models          # download engines first (~7 GB)
    python -m benchmarks.mt_bench [--engines opus-gpu,opus-cpu,madlad,qwen-cuda,qwen-vulkan]

Each engine is loaded alone (VRAM delta measured), then translates the 20 FLEURS sentences
for every pair it supports, one sentence per call as in live use. Scores: corpus chrF against
the other language's FLEURS text; latency p50/p95 per sentence.
Results: benchmarks/results/mt.md (+ mt.json). Engines not re-run keep their previous rows.
Opus-MT models come from `benchmarks/opus_convert.py` (D-031; Argos is not shippable).
"""

from __future__ import annotations

import argparse
import json
import socket
import subprocess  # nosec B404 - launches the pinned llama-server binary we downloaded
import sys
import time
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from benchmarks.asr_bench import MODELS_DIR, RESULTS
from benchmarks.corpus import load_corpus
from benchmarks.harness import VramMonitor, gpu_info, markdown_table, write_results
from benchmarks.metrics import LatencyStats, chrf
from benchmarks.mt_models import llama_dir, madlad_dir, qwen_path
from livetranslator.core.languages import language
from livetranslator.platform.cuda import add_cuda_dll_dirs
from livetranslator.services.mt.engines.opus_mt import OpusMtEngine
from livetranslator.services.mt.router import TranslationRouter

PAIRS: tuple[tuple[str, str], ...] = (
    ("en", "es"),
    ("es", "en"),
    ("en", "fr"),
    ("en", "de"),
    ("en", "ru"),
    ("ru", "en"),
    ("en", "ja"),
    ("ja", "en"),
    ("en", "ko"),
    ("ko", "en"),
    ("en", "zh"),
    ("zh", "en"),
    ("ja", "ko"),  # no direct Opus-MT model: pivots through English
)


class Engine:
    name = ""
    license = ""

    def load(self) -> None: ...

    def unload(self) -> None: ...

    def supports(self, src: str, tgt: str) -> bool:
        return True

    def translate(self, text: str, src: str, tgt: str) -> str:
        raise NotImplementedError

    def disk_mb(self) -> int | None:
        return None


def folder_mb(path: Path) -> int:
    files = [path] if path.is_file() else [f for f in path.rglob("*") if f.is_file()]
    return round(sum(f.stat().st_size for f in files) / 2**20)


class OpusEngine(Engine):
    """The app's Opus-MT adapter (T051) behind the app's router, so pivots are real."""

    license = "CC-BY-4.0 / Apache-2.0 (D-031)"

    def __init__(self, device: str) -> None:
        self.name = f"Opus-MT · {'GPU int8' if device == 'cuda' else 'CPU int8'}"
        self._device: Any = device
        self._engine: OpusMtEngine | None = None
        self._router: TranslationRouter | None = None

    def disk_mb(self) -> int:
        return folder_mb(MODELS_DIR / "opus-mt")

    def load(self) -> None:
        self._engine = OpusMtEngine(MODELS_DIR, device=self._device)
        self._engine.load()
        self._router = TranslationRouter([self._engine])
        for src, tgt in PAIRS:  # load every pair inside the VRAM window
            if self._router.supports(src, tgt):
                self._router.translate("Hello.", src, tgt)

    def unload(self) -> None:
        if self._engine is not None:
            self._engine.unload()
        self._engine = self._router = None

    def supports(self, src: str, tgt: str) -> bool:
        return self._router is not None and self._router.supports(src, tgt)

    def translate(self, text: str, src: str, tgt: str) -> str:
        assert self._router is not None  # nosec B101 - load() ran
        return self._router.translate(text, src, tgt)


class MadladEngine(Engine):
    """MADLAD-400 3B (T5) via CTranslate2; target chosen with a '<2xx>' prefix token."""

    name = "MADLAD-400 3B · GPU int8"
    license = "Apache-2.0"

    def disk_mb(self) -> int:
        return folder_mb(madlad_dir())

    def __init__(self) -> None:
        self._translator: Any = None
        self._sp: Any = None

    def load(self) -> None:
        import ctranslate2
        import sentencepiece

        folder = madlad_dir()
        self._translator = ctranslate2.Translator(
            str(folder), device="cuda", compute_type="int8_float16"
        )
        self._sp = sentencepiece.SentencePieceProcessor(model_file=str(folder / "spiece.model"))

    def unload(self) -> None:
        self._translator = None

    def translate(self, text: str, src: str, tgt: str) -> str:
        tokens = [*self._sp.encode(f"<2{tgt}> {text}", out_type=str), "</s>"]
        result = self._translator.translate_batch([tokens], beam_size=4, max_decoding_length=256)
        return str(self._sp.decode(result[0].hypotheses[0]))


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class LlamaServerEngine(Engine):
    """Qwen3-4B-Instruct (Q4_K_M GGUF) behind llama.cpp's llama-server on localhost."""

    license = "Apache-2.0 (model) / MIT (llama.cpp)"

    def disk_mb(self) -> int:
        return folder_mb(qwen_path()) + folder_mb(llama_dir(self._build))

    def __init__(self, build: str) -> None:
        self.name = f"Qwen3-4B Q4_K_M · llama.cpp {build}"
        self._build = build
        self._proc: subprocess.Popen[bytes] | None = None
        self._port = 0

    def load(self) -> None:
        folder = llama_dir(self._build)
        self._port = _free_port()
        log = (RESULTS / f"llama-server-{self._build}.log").open("wb")
        self._proc = subprocess.Popen(  # nosec B603 - fixed binary + arguments
            [
                str(folder / "llama-server.exe"),
                "-m",
                str(qwen_path()),
                "-ngl",
                "99",
                "-c",
                "2048",
                "--host",
                "127.0.0.1",
                "--port",
                str(self._port),
            ],
            cwd=folder,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        deadline = time.time() + 180
        while time.time() < deadline:
            if self._proc.poll() is not None:
                raise RuntimeError(f"llama-server exited with {self._proc.returncode}")
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self._port}/health") as r:  # nosec B310
                    if r.status == 200:
                        return
            except OSError:
                time.sleep(0.5)
        raise RuntimeError("llama-server did not become ready")

    def unload(self) -> None:
        if self._proc is not None:
            self._proc.terminate()
            self._proc.wait(timeout=30)
            self._proc = None

    def translate(self, text: str, src: str, tgt: str) -> str:
        system = (
            f"Translate the user's message from {language(src).english} to "
            f"{language(tgt).english}. Reply with the translation only."
        )
        body = json.dumps(
            {
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": text},
                ],
                "temperature": 0,
                "max_tokens": 256,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"http://127.0.0.1:{self._port}/v1/chat/completions",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request) as r:  # nosec B310 - localhost server we started
            reply = json.load(r)
        return str(reply["choices"][0]["message"]["content"]).strip()


ENGINES: dict[str, Callable[[], Engine]] = {
    "opus-gpu": lambda: OpusEngine("cuda"),
    "opus-cpu": lambda: OpusEngine("cpu"),
    "madlad": MadladEngine,
    "qwen-cuda": lambda: LlamaServerEngine("cuda"),
    "qwen-vulkan": lambda: LlamaServerEngine("vulkan"),
}


@dataclass
class EngineResult:
    key: str
    name: str
    license: str
    load_s: float = 0.0
    vram_mb: int | None = None
    disk_mb: int | None = None
    chrf: dict[str, float] = field(default_factory=dict[str, float])
    latency: LatencyStats | None = None
    error: str | None = None
    samples: dict[str, list[str]] = field(default_factory=dict[str, list[str]])


def run_engine(key: str) -> EngineResult:
    engine = ENGINES[key]()
    result = EngineResult(key, engine.name, engine.license, disk_mb=engine.disk_mb())
    corpus = load_corpus()
    try:
        with VramMonitor() as vram:
            start = time.perf_counter()
            engine.load()
            result.load_s = time.perf_counter() - start
            engine.translate("Hello, how are you?", "en", "es")  # warm-up inside the window
        result.vram_mb = None if key.endswith("cpu") else vram.peak_delta_mb
        latencies: list[float] = []
        for src, tgt in PAIRS:
            if not engine.supports(src, tgt):
                continue
            hyps: list[str] = []
            refs: list[str] = []
            for sentence in corpus.sentences:
                start = time.perf_counter()
                hyps.append(engine.translate(sentence.text[src], src, tgt))
                latencies.append(time.perf_counter() - start)
                refs.append(sentence.text[tgt])
            pair = f"{src}→{tgt}"
            result.chrf[pair] = chrf(hyps, refs)
            result.samples[pair] = hyps[:2]
            print(f"  {key} {pair}: chrF {result.chrf[pair]:.1f}", flush=True)
        result.latency = LatencyStats.from_seconds(latencies)
    except Exception as exc:  # record and continue with the next engine
        result.error = f"{type(exc).__name__}: {exc}"
        print(f"  {key} failed: {result.error}", flush=True)
    finally:
        engine.unload()
    return result


def merged_rows(
    results: list[EngineResult], previous: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Rows of this run replace the same engine's previous row; others are kept (dropped
    engines such as the old Argos rows disappear). Ordered like ENGINES."""
    fresh = {
        r.key: {**r.__dict__, "latency": r.latency.__dict__ if r.latency else None} for r in results
    }
    rows = {row["key"]: row for row in previous if row.get("key") in ENGINES}
    rows.update(fresh)
    return [rows[key] for key in ENGINES if key in rows]


def report(results: list[EngineResult]) -> None:
    raw_path = RESULTS / "mt.json"
    previous: list[dict[str, Any]] = (
        json.loads(raw_path.read_text(encoding="utf-8")) if raw_path.exists() else []
    )
    rows = merged_rows(results, previous)
    gpu = gpu_info()
    pairs = [f"{s}→{t}" for s, t in PAIRS]
    setup = (
        f"- GPU: {gpu.name if gpu else 'n/a'} ({gpu.total_mb if gpu else '?'} MB)\n"
        "- Corpus: FLEURS dev, the same 20 sentences in every language (parallel references)\n"
        "- One sentence per call (live use); beam 4 for CTranslate2 engines; temperature 0 for "
        "Qwen\n"
        "- chrF 0-100, higher is better. Opus-MT ja→ko pivots through English.\n"
        "- Disk = model files on disk (Opus-MT: all 14 pairs, float16; int8 is applied at "
        "load).\n"
    )

    def latency(row: dict[str, Any], key: str) -> float | None:
        stats = row.get("latency")
        return stats[key] if stats else None

    quality = markdown_table(
        ["Engine", *pairs], [[row["name"], *(row["chrf"].get(p) for p in pairs)] for row in rows]
    )
    speed = markdown_table(
        ["Engine", "Load s", "VRAM MB", "Disk MB", "p50 ms", "p95 ms", "Licence", "Error"],
        [
            [
                row["name"],
                row["load_s"],
                row["vram_mb"],
                row.get("disk_mb"),
                latency(row, "p50_ms"),
                latency(row, "p95_ms"),
                row["license"],
                row["error"],
            ]
            for row in rows
        ],
    )
    samples = "\n".join(
        f"- **{row['name']}** ja→en: {row['samples'].get('ja→en', ['n/a'])[0]}" for row in rows
    )
    write_results(
        RESULTS / "mt.md",
        "MT benchmark (T033)",
        [
            ("Setup", setup),
            ("Quality (chrF)", quality),
            ("Speed, memory, disk, licence", speed),
            ("Sample output (sentence 1, ja→en)", samples + "\n"),
        ],
    )
    raw_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Translation benchmark (T033).")
    parser.add_argument("--engines", default=",".join(ENGINES))
    args = parser.parse_args(argv)
    add_cuda_dll_dirs()
    RESULTS.mkdir(parents=True, exist_ok=True)
    results = [run_engine(key) for key in args.engines.split(",")]
    report(results)
    print(f"wrote {RESULTS / 'mt.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
