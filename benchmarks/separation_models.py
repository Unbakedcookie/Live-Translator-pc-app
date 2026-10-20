"""Separation models for the overlap spike (benchmarks/separation.py). Runs in the PyTorch
environment (D:/LiveTranslator/convert-venv, with asteroid 0.7.0 installed --no-deps).

Only models whose licence was checked (2026-10-20) are listed:
- convtasnet-libri2mix-16k: JorisCos/ConvTasNet_Libri2Mix_sepclean_16k (Asteroid). Weights
  CC-BY-SA-4.0; trained on Libri2Mix sep_clean = LibriSpeech only (CC-BY-4.0), no WHAM noise.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import Any

import numpy as np

Separator = Callable[[np.ndarray], list[np.ndarray]]

MODELS = {"convtasnet-libri2mix-16k": "JorisCos/ConvTasNet_Libri2Mix_sepclean_16k"}


def load_separator(name: str) -> Separator:
    # Only installed in the PyTorch environment, not the app venv (which type-checks this).
    torch: Any = importlib.import_module("torch")
    ConvTasNet: Any = importlib.import_module("asteroid.models").ConvTasNet

    if name not in MODELS:
        raise SystemExit(f"unknown model {name!r}; licence-checked: {', '.join(MODELS)}")
    model = ConvTasNet.from_pretrained(MODELS[name])
    model.eval()
    torch.set_num_threads(max(1, (torch.get_num_threads() or 1)))

    def separate(audio: np.ndarray) -> list[np.ndarray]:
        with torch.inference_mode():
            out = model(torch.from_numpy(audio.astype(np.float32))[None, None, :])
        return [track.numpy() for track in out[0]]

    return separate
