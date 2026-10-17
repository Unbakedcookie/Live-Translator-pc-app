"""Download the translation engines under test (T033). Everything goes under
<bench-data>/models and is pinned to a release or revision so results are reproducible.

    python -m benchmarks.mt_models [--only argos,madlad,qwen,llama-cuda,llama-vulkan]

Licences (checked 2026-10-17, see DATA_TRACKER):
- MADLAD-400 3B ct2 int8 (Nextcloud-AI): Apache-2.0.
- Qwen3-4B-Instruct-2507 GGUF (unsloth): Apache-2.0.
- llama.cpp server builds: MIT. The CUDA build's cudart zip holds NVIDIA runtime DLLs (D-026).
- Argos Translate packages: NO licence file inside; README only credits data sources
  (OPUS, CCAligned, WikiMatrix...). Benchmark only until reviewed (D-031).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from benchmarks.corpus import default_dest

MODELS = default_dest() / "models"

ARGOS_INDEX = "https://raw.githubusercontent.com/argosopentech/argospm-index/main/index.json"
MADLAD_REPO = "Nextcloud-AI/madlad400-3b-mt-ct2-int8"
MADLAD_REVISION = "aa32bbdeba7880eff2096ec044cb155a340a9400"
QWEN_REPO = "unsloth/Qwen3-4B-Instruct-2507-GGUF"
QWEN_REVISION = "a06e946bb6b655725eafa393f4a9745d460374c9"
QWEN_FILE = "Qwen3-4B-Instruct-2507-Q4_K_M.gguf"
LLAMA_TAG = "b11714"
LLAMA_BUILDS: dict[str, list[str]] = {
    "cuda": [
        f"llama-{LLAMA_TAG}-bin-win-cuda-12.4-x64.zip",
        "cudart-llama-bin-win-cuda-12.4-x64.zip",
    ],
    "vulkan": [f"llama-{LLAMA_TAG}-bin-win-vulkan-x64.zip"],
}
ARGOS_LANGS = ("es", "fr", "de", "ru", "ja", "ko", "zh")


def safe_extract(archive: Path, dest: Path, skip: tuple[str, ...] = ()) -> None:
    """Extract a zip, refusing members that would land outside `dest`."""
    root = dest.resolve()
    with zipfile.ZipFile(archive) as zf:
        for member in zf.infolist():
            if member.is_dir() or any(part in member.filename for part in skip):
                continue
            target = (root / member.filename).resolve()
            if not target.is_relative_to(root):
                raise ValueError(f"{archive.name}: unsafe member {member.filename!r}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, target.open("wb") as out:
                shutil.copyfileobj(src, out)


USER_AGENT = "LiveTranslator-bench/0.1"  # argos-net.com answers 403 to Python-urllib


def _open(url: str) -> Any:
    if not url.startswith("https://"):
        raise ValueError(f"refusing non-https URL {url!r}")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    return urllib.request.urlopen(request)  # nosec B310 - https checked above


def _download(url: str, target: Path) -> Path:
    if target.exists():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    with _open(url) as response, partial.open("wb") as out:
        shutil.copyfileobj(response, out)
    partial.replace(target)
    return target


def argos_dir(src: str, tgt: str) -> Path:
    return MODELS / "argos" / f"{src}_{tgt}"


def fetch_argos() -> dict[str, str]:
    """English <-> each other language, highest package version. Returns pair -> version."""
    with _open(ARGOS_INDEX) as response:
        index = json.load(response)
    wanted = {(lang, "en") for lang in ARGOS_LANGS} | {("en", lang) for lang in ARGOS_LANGS}
    best: dict[tuple[str, str], dict[str, object]] = {}
    for pkg in index:
        pair = (pkg["from_code"], pkg["to_code"])
        if pair in wanted:
            current = best.get(pair)
            version = tuple(int(x) for x in str(pkg["package_version"]).split("."))
            if current is None or version > tuple(
                int(x) for x in str(current["package_version"]).split(".")
            ):
                best[pair] = pkg
    versions: dict[str, str] = {}
    for (src, tgt), pkg in sorted(best.items()):
        out = argos_dir(src, tgt)
        if not (out / "model" / "model.bin").exists():
            links = pkg["links"]
            assert isinstance(links, list)  # nosec B101 - index format
            archive = _download(str(links[0]), MODELS / "argos" / f"{src}_{tgt}.argosmodel")
            tmp = MODELS / "argos" / f"_{src}_{tgt}"
            safe_extract(archive, tmp, skip=("/stanza/",))
            inner = next(p for p in tmp.iterdir() if p.is_dir())
            shutil.rmtree(out, ignore_errors=True)
            inner.replace(out)
            shutil.rmtree(tmp, ignore_errors=True)
        versions[f"{src}-{tgt}"] = str(pkg["package_version"])
        print(f"argos {src}-{tgt} v{pkg['package_version']}", flush=True)
    return versions


def madlad_dir() -> Path:
    return MODELS / "madlad400-3b-ct2-int8"


def fetch_madlad() -> Path:
    from huggingface_hub import snapshot_download

    return Path(snapshot_download(MADLAD_REPO, revision=MADLAD_REVISION, local_dir=madlad_dir()))


def qwen_path() -> Path:
    return MODELS / "qwen3-4b" / QWEN_FILE


def fetch_qwen() -> Path:
    from huggingface_hub import hf_hub_download

    return Path(
        hf_hub_download(QWEN_REPO, QWEN_FILE, revision=QWEN_REVISION, local_dir=qwen_path().parent)
    )


def llama_dir(build: str) -> Path:
    return MODELS / "llama.cpp" / f"{LLAMA_TAG}-{build}"


def fetch_llama(build: str) -> Path:
    out = llama_dir(build)
    if (out / "llama-server.exe").exists():
        return out
    base = f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_TAG}"
    for name in LLAMA_BUILDS[build]:
        archive = _download(f"{base}/{name}", MODELS / "llama.cpp" / "_downloads" / name)
        safe_extract(archive, out)
    if not (out / "llama-server.exe").exists():
        found = next(out.rglob("llama-server.exe"), None)
        if found is None:
            raise RuntimeError(f"llama-server.exe not found in the {build} build")
        for item in found.parent.iterdir():
            item.replace(out / item.name)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download the MT engines under test.")
    parser.add_argument("--only", default="argos,madlad,qwen,llama-cuda,llama-vulkan")
    args = parser.parse_args(argv)
    wanted = set(args.only.split(","))
    if "argos" in wanted:
        fetch_argos()
    if "madlad" in wanted:
        print("madlad:", fetch_madlad(), flush=True)
    if "qwen" in wanted:
        print("qwen:", fetch_qwen(), flush=True)
    for build in ("cuda", "vulkan"):
        if f"llama-{build}" in wanted:
            print(f"llama {build}:", fetch_llama(build), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
