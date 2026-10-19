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
    # T074 catalogue, 2026-10-18: the app's other target languages, both ways. Revisions and
    # licences read from the HF API that day (cardData); the README says which multi-target
    # models need a >>tag<<.
    ("en", "pt"): (
        "opus-mt-tc-big-en-pt",
        "9f2863d807ecf91a374bdbecb8d01e402e90622e",
        "CC-BY-4.0",
        "",
    ),
    ("pt", "en"): (  # no pt-en model: the Romance-languages -> English one covers pt / pt_BR
        "opus-mt-ROMANCE-en",
        "e9ca9975e3972afd80732f08ce01d3a1339f47f8",
        "Apache-2.0",
        "",
    ),
    ("en", "it"): ("opus-mt-en-it", "be5a254d936f1a8c8da080406ca582a6615e6658", "Apache-2.0", ""),
    ("it", "en"): ("opus-mt-it-en", "42556a0848fc726f4d27399f20b19ff6f01afe11", "Apache-2.0", ""),
    ("en", "uk"): ("opus-mt-en-uk", "634fdc4b28bf0c8a1d4359cbbcfb29190a09dc0e", "Apache-2.0", ""),
    ("uk", "en"): ("opus-mt-uk-en", "1b9a2a0d1aa2a329d8476d2be5c7b0b27d5397b0", "Apache-2.0", ""),
    ("en", "pl"): (  # West Slavic multi-target: README requires >>id<<
        "opus-mt-en-zlw",
        "92ffd5aa936924688bd715b26d6bb75393082c03",
        "Apache-2.0",
        ">>pol<<",
    ),
    ("pl", "en"): ("opus-mt-pl-en", "7f2bb874fdfb6139f9842b91a9b75c4a6c93401c", "Apache-2.0", ""),
    ("en", "tr"): (
        "opus-mt-tc-big-en-tr",
        "e539fc16a8a1a0ea5950eb339b595bfcce990e90",
        "CC-BY-4.0",
        "",
    ),
    ("tr", "en"): ("opus-mt-tr-en", "19c65427cc2af5f191337d4899e0348c4af25902", "Apache-2.0", ""),
    ("en", "ar"): (  # Arabic varieties multi-target: README requires >>id<<
        "opus-mt-en-ar",
        "03087980e8ce753d64b3248ed0a912444545b840",
        "Apache-2.0",
        ">>ara<<",
    ),
    ("ar", "en"): ("opus-mt-ar-en", "c5b2a50db78d6be98ae207223f8d4f63bc7a0ff1", "Apache-2.0", ""),
    ("en", "hi"): ("opus-mt-en-hi", "75d7f7c9232b2891c7d65fe4ef635616c72be867", "Apache-2.0", ""),
    ("hi", "en"): ("opus-mt-hi-en", "a7d96a16729f812578bd55e7366147beda625d86", "Apache-2.0", ""),
    # Into English only: languages often heard in voice chat that aren't window targets.
    ("id", "en"): ("opus-mt-id-en", "9a7f1b0d0dfe0a92ba691030b01d6f23f966e7ec", "Apache-2.0", ""),
    ("vi", "en"): ("opus-mt-vi-en", "c8d2853e77f5fae31124d993e0b35176b1c8914e", "Apache-2.0", ""),
    # Vietnamese became a window language (user request 2026-10-18): the other direction too.
    ("en", "vi"): ("opus-mt-en-vi", "989c9fb9ec63987901022baf0182dcec3e149be6", "Apache-2.0", ""),
    ("th", "en"): ("opus-mt-th-en", "0fff80be1c3f40d6180efd59f566ece956ace689", "Apache-2.0", ""),
    ("nl", "en"): ("opus-mt-nl-en", "48af999f2c59b10c05ca6e008dcedc07677a9b15", "Apache-2.0", ""),
    ("sv", "en"): ("opus-mt-sv-en", "202cf6240046bd8b6d08c207ee751ffd630d7ba8", "Apache-2.0", ""),
    ("fi", "en"): ("opus-mt-fi-en", "c4d8fff0f8f00b637f0578666f35cdacef354778", "Apache-2.0", ""),
    ("da", "en"): ("opus-mt-da-en", "0960cff506758772cf23186b941305e0afeb43c5", "Apache-2.0", ""),
    ("no", "en"): (  # no Norwegian-only model: North Germanic -> English (da, nb, nn, sv...)
        "opus-mt-gmq-en",
        "82e9a0a21f1393f58f3a12dfee196adf058d1236",
        "Apache-2.0",
        "",
    ),
    ("ur", "en"): ("opus-mt-ur-en", "1425fec421641ff8b064596e77d42a2450d684c2", "Apache-2.0", ""),
    ("tl", "en"): ("opus-mt-tl-en", "8d2dee91f8b3fa48dda8ec06ee2af8f24970dcbc", "Apache-2.0", ""),
    ("cs", "en"): ("opus-mt-cs-en", "577d2053d249b476aefec9524a37ec945ccbd331", "Apache-2.0", ""),
    ("hu", "en"): ("opus-mt-hu-en", "cdf0ec884dc05cf435cef756dbf05a91c877f105", "Apache-2.0", ""),
    ("he", "en"): (
        "opus-mt-tc-big-he-en",
        "134c5a850dcaa763eec85bd1f4eb25112fecedbb",
        "CC-BY-4.0",
        "",
    ),
    ("el", "en"): (
        "opus-mt-tc-big-el-en",
        "a69108562775c6727edf3540346f9d8900b73634",
        "CC-BY-4.0",
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
