"""Convert the speech-separation model to ONNX for the optional "separate people talking over
each other" setting (D-042; benchmarks/results/separation.md).

    <PyTorch env> -m tools.export_separation D:/LiveTranslator/hf-staging

Runs where PyTorch + asteroid are installed (D:/LiveTranslator/convert-venv; asteroid 0.7.0
`--no-deps` plus soundfile, scipy, onnx). Writes `separation-convtasnet/` into the staging
folder: `model.onnx`, `LICENCE.txt` (CC-BY-SA-4.0, the weights' licence: our ONNX export is
an adaptation and keeps it) and `NOTICE.txt` (credit + what we changed). `tools.model_hosting
pack` then zips it with the translation packs. Build tool, not part of the app.
"""

from __future__ import annotations

import argparse
import importlib
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = "JorisCos/ConvTasNet_Libri2Mix_sepclean_16k"
REVISION = "e1ef95ab7a037950f3a606b9a56760cf94701d3d"
FOLDER = "separation-convtasnet"
LICENCE = ROOT / "licenses" / "CC-BY-SA-4.0.txt"
SAMPLE_S = 10
NOTICE = f"""Speech separation model for Live Translator

Model: ConvTasNet trained on Libri2Mix sep_clean, 16 kHz (Asteroid), by Joris Cosentino,
https://huggingface.co/{UPSTREAM} (revision {REVISION}).
Licence: Creative Commons Attribution-ShareAlike 4.0 International (CC-BY-SA-4.0), see
LICENCE.txt. Training data: Libri2Mix sep_clean, built from LibriSpeech (Panayotov et al.,
CC-BY-4.0).

Changes: the PyTorch weights were exported unchanged to ONNX (opset 17) by Live Translator
(tools/export_separation.py). This ONNX file is an adaptation and is shared under the same
CC-BY-SA-4.0 licence. Live Translator itself is MIT-licensed and only downloads this file.
"""


def export(staging: Path) -> Path:
    torch: Any = importlib.import_module("torch")
    hub: Any = importlib.import_module("huggingface_hub")
    conv_tasnet: Any = importlib.import_module("asteroid.models").ConvTasNet

    weights = hub.hf_hub_download(UPSTREAM, "pytorch_model.bin", revision=REVISION)
    model = conv_tasnet.from_pretrained(weights).eval()
    out = staging / FOLDER
    out.mkdir(parents=True, exist_ok=True)
    sample = torch.zeros(1, 1, SAMPLE_S * 16_000)
    torch.onnx.export(
        model,
        sample,
        str(out / "model.onnx"),
        input_names=["mix"],
        output_names=["tracks"],
        dynamic_axes={"mix": {2: "samples"}, "tracks": {2: "samples"}},
        opset_version=17,
        dynamo=False,
    )
    shutil.copyfile(LICENCE, out / "LICENCE.txt")
    (out / "NOTICE.txt").write_text(NOTICE, encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export the separation model to ONNX")
    parser.add_argument("staging", type=Path)
    args = parser.parse_args(argv)
    out = export(args.staging)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
