"""Quality and latency metrics for the benchmarks (T031; spec §8, M03).

- ASR: WER for space-separated languages, CER for ja/zh/ko (no spaces), after normalising
  case, punctuation and whitespace, via jiwer.
- MT: chrF (sacrebleu), robust across scripts.
- Latency: p50/p95 with linear interpolation (numpy's default method).
"""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

import jiwer
import numpy as np
from sacrebleu.metrics.chrf import CHRF

CHARACTER_LANGUAGES = frozenset({"ja", "zh", "ko"})


def normalize(text: str) -> str:
    """Lowercase, drop punctuation and symbols (Unicode P* and S*), collapse whitespace."""
    kept = [
        " " if unicodedata.category(ch)[0] in "PS" else ch
        for ch in unicodedata.normalize("NFKC", text)
    ]
    return " ".join("".join(kept).lower().split())


def uses_cer(language: str) -> bool:
    return language in CHARACTER_LANGUAGES


def error_rate(reference: str, hypothesis: str, language: str) -> float:
    """WER, or CER for ja/zh/ko (spaces removed: they aren't part of those scripts)."""
    ref, hyp = normalize(reference), normalize(hypothesis)
    if uses_cer(language):
        ref, hyp = ref.replace(" ", ""), hyp.replace(" ", "")
        if not ref:
            return 0.0 if not hyp else 1.0
        return float(jiwer.cer(ref, hyp))
    if not ref:
        return 0.0 if not hyp else 1.0
    return float(jiwer.wer(ref, hyp))


def corpus_error_rate(references: Sequence[str], hypotheses: Sequence[str], language: str) -> float:
    """Pooled error rate (total edits / total reference units), not a mean of sentences."""
    refs = [normalize(r) for r in references]
    hyps = [normalize(h) for h in hypotheses]
    if uses_cer(language):
        refs = [r.replace(" ", "") for r in refs]
        hyps = [h.replace(" ", "") for h in hyps]
        return float(jiwer.cer(refs, hyps))
    return float(jiwer.wer(refs, hyps))


def chrf(hypotheses: Sequence[str], references: Sequence[str]) -> float:
    """Corpus chrF (0-100) with one reference per sentence."""
    return float(CHRF().corpus_score(list(hypotheses), [list(references)]).score)


@dataclass(frozen=True)
class LatencyStats:
    n: int
    p50_ms: float
    p95_ms: float
    mean_ms: float

    @classmethod
    def from_seconds(cls, samples: Sequence[float]) -> LatencyStats:
        if not samples:
            raise ValueError("no latency samples")
        ms = np.asarray(samples, dtype=np.float64) * 1000.0
        return cls(
            n=len(samples),
            p50_ms=float(np.percentile(ms, 50)),
            p95_ms=float(np.percentile(ms, 95)),
            mean_ms=float(ms.mean()),
        )
