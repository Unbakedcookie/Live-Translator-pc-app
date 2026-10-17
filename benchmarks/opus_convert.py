"""T033 — download Helsinki-NLP Opus-MT models at pinned revisions and convert them to
CTranslate2 (D-031: shipped instead of Argos).

Build-time tool, NOT part of the app. Needs torch + transformers, so it runs in a separate
throwaway venv (never the app's .venv):

    D:\\LiveTranslator\\convert-venv\\Scripts\\python.exe benchmarks/opus_convert.py

Output: <bench-data>/models/opus-mt/<src>-<tgt>/ with the CTranslate2 model (float16
weights; int8 is chosen at load time), source.spm, target.spm and a LICENCE.txt naming the
upstream repo, revision and licence (CC-BY needs attribution + "converted" note).
Licences and SHAs: fact-checker 2026-10-17 (DATA_TRACKER D-031).
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

OUT = Path(os.environ.get("LT_BENCH_DIR", r"D:\LiveTranslator\bench-data")) / "models" / "opus-mt"

# (src, tgt): (repo, revision, licence, target-language tag such as ">>cmn_Hans<<" or "")
MODELS: dict[tuple[str, str], tuple[str, str, str, str]] = {
    ("en", "es"): ("opus-mt-en-es", "5bc4493d463cf000c1f0b50f8d56886a392ed4ab", "CC-BY-4.0", ""),
    ("es", "en"): ("opus-mt-es-en", "c96e2c5399ebfae4fc43d9669556b9afa74bb69d", "CC-BY-4.0", ""),
    ("en", "fr"): ("opus-mt-en-fr", "dd7f6540a7a48a7f4db59e5c0b9c42c8eea67f18", "CC-BY-4.0", ""),
    ("fr", "en"): ("opus-mt-fr-en", "c4aed37b318c763fd177aa449b44e3b783cc6c02", "CC-BY-4.0", ""),
    ("en", "de"): ("opus-mt-en-de", "6183067f769a302e3861815543b9f312c71b0ca4", "CC-BY-4.0", ""),
    ("de", "en"): ("opus-mt-de-en", "1a922f3b32a8e809e17a47d4b32142d8105924e5", "CC-BY-4.0", ""),
    ("en", "ru"): ("opus-mt-en-ru", "bb09c99d180016eac6819df3dae68edb1690fdee", "CC-BY-4.0", ""),
    ("ru", "en"): ("opus-mt-ru-en", "fbd6dc73284f95536648512cc21d57f19191961a", "CC-BY-4.0", ""),
    ("en", "zh"): (
        "opus-mt-en-zh",
        "408d9bc410a388e1d9aef112a2daba955b945255",
        "CC-BY-4.0",
        ">>cmn_Hans<<",  # multi-target (cmn/yue/wuu...): ask for Simplified Mandarin
    ),
    ("zh", "en"): ("opus-mt-zh-en", "cf109095479db38d6df799875e34039d4938aaa6", "CC-BY-4.0", ""),
    ("ja", "en"): ("opus-mt-ja-en", "0770961a39ba6bd66305b149c3f4110bcafca2e6", "CC-BY-4.0", ""),
    ("ko", "en"): ("opus-mt-ko-en", "e42d1f41b66194e6d10512f8a27bebc1f4f5097e", "CC-BY-4.0", ""),
    ("en", "ja"): (
        "opus-tatoeba-en-ja",
        "3a282648cb991174f3c423e376aff3a13e5edaaf",
        "Apache-2.0",
        "",
    ),
}
# The Hugging Face port of tc-big en-ko is broken: the original is a "sepvoc" model (separate
# source/target vocabularies) but the HF port merged them, so it emits "⁇" garbage. It is
# converted from the original MarianNMT release instead (licence file inside: CC-BY 4.0).
MARIAN_RELEASES: dict[tuple[str, str], tuple[str, str]] = {
    ("en", "ko"): (
        "https://object.pouta.csc.fi/Tatoeba-MT-models/eng-kor/"
        "opusTCv20210807-sepvoc_transformer-big_2022-07-28.zip",
        "opusTCv20210807-sepvoc.spm32k-spm32k",
    ),
}
DOWNLOADS = OUT.parent.parent / "downloads"
# Licence note: the HF API says Apache-2.0 for most of these, the OPUS-MT project README says
# CC-BY 4.0 for all models; we follow the stricter one and attribute everything (D-031).


def convert(src: str, tgt: str) -> Path:
    import ctranslate2
    from huggingface_hub import snapshot_download

    name, revision, licence, tag = MODELS[(src, tgt)]
    repo = f"Helsinki-NLP/{name}"
    target = OUT / f"{src}-{tgt}"
    if (target / "model.bin").exists():
        print(f"{src}-{tgt}: already converted", flush=True)
        return target
    local = Path(snapshot_download(repo, revision=revision))
    tmp = target.with_name(target.name + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    ctranslate2.converters.TransformersConverter(str(local)).convert(
        str(tmp), quantization="float16"
    )
    for spm in ("source.spm", "target.spm"):
        shutil.copy2(local / spm, tmp / spm)
    (tmp / "LICENCE.txt").write_text(
        f"{repo} (revision {revision}) by Helsinki-NLP / OPUS-MT, licence {licence}.\n"
        "https://huggingface.co/" + repo + "\n"
        "Converted to CTranslate2 (float16) by Live Translator; weights otherwise unchanged.\n",
        encoding="utf-8",
    )
    (tmp / "opus_mt.json").write_text(
        json.dumps({"repo": repo, "revision": revision, "licence": licence, "language_tag": tag}),
        encoding="utf-8",
    )
    shutil.rmtree(target, ignore_errors=True)
    tmp.rename(target)
    print(f"{src}-{tgt}: converted from {repo}@{revision[:8]}", flush=True)
    return target


def convert_marian(src: str, tgt: str) -> Path:
    """Convert an original MarianNMT release zip (separate vocabularies kept)."""
    import urllib.request
    import zipfile

    import ctranslate2
    import yaml

    url, stem = MARIAN_RELEASES[(src, tgt)]
    target = OUT / f"{src}-{tgt}"
    if (target / "model.bin").exists():
        print(f"{src}-{tgt}: already converted", flush=True)
        return target
    work = DOWNLOADS / f"{src}-{tgt}-marian"  # its own folder: the zip is untrusted data
    work.mkdir(parents=True, exist_ok=True)
    archive = work.with_suffix(".zip")
    if not archive.exists():
        urllib.request.urlretrieve(url, archive)  # nosec B310 - fixed https URL
    npz = f"{stem}.transformer-big.model1.npz.best-perplexity.npz"
    names = ["LICENSE", "source.spm", "target.spm", npz, f"{stem}.src.vocab", f"{stem}.trg.vocab"]
    with zipfile.ZipFile(archive) as z:
        for name in names:  # only these members, written to paths we choose
            with z.open(name) as packed, (work / name).open("wb") as out:
                shutil.copyfileobj(packed, out)
    vocabs = []
    for side in ("src", "trg"):
        lines = (work / f"{stem}.{side}.vocab").read_text(encoding="utf-8").splitlines()
        mapping = {line.split("\t")[0]: i for i, line in enumerate(lines)}
        (work / f"{side}.vocab.yml").write_text(
            yaml.safe_dump(mapping, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )
        vocabs.append(f"{side}.vocab.yml")
    (work / "decoder.yml").write_text(
        yaml.safe_dump({"relative-paths": True, "models": [npz], "vocabs": vocabs}),
        encoding="utf-8",
    )
    tmp = target.with_name(target.name + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    ctranslate2.converters.OpusMTConverter(str(work)).convert(str(tmp), quantization="float16")
    for spm in ("source.spm", "target.spm"):
        shutil.copy2(work / spm, tmp / spm)
    (tmp / "LICENCE.txt").write_text(
        f"Helsinki-NLP OPUS-MT {src}-{tgt} original MarianNMT release, licence CC-BY-4.0 "
        f"(LICENSE in the release).\n{url}\n"
        "Converted to CTranslate2 (float16) by Live Translator; weights otherwise unchanged.\n",
        encoding="utf-8",
    )
    (tmp / "opus_mt.json").write_text(
        json.dumps({"repo": url, "revision": stem, "licence": "CC-BY-4.0", "language_tag": ""}),
        encoding="utf-8",
    )
    shutil.rmtree(target, ignore_errors=True)
    tmp.rename(target)
    print(f"{src}-{tgt}: converted from the original Marian release", flush=True)
    return target


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    failed = []
    for src, tgt in MARIAN_RELEASES:
        try:
            convert_marian(src, tgt)
        except Exception as exc:
            print(f"{src}-{tgt}: FAILED {type(exc).__name__}: {exc}", flush=True)
            failed.append(f"{src}-{tgt}")
    for src, tgt in MODELS:
        try:
            convert(src, tgt)
        except Exception as exc:
            print(f"{src}-{tgt}: FAILED {type(exc).__name__}: {exc}", flush=True)
            failed.append(f"{src}-{tgt}")
    print("failed:", failed or "none")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
