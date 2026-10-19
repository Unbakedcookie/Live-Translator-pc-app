"""Host the converted Opus-MT translation models on Hugging Face (T074; G4 decision 5).

Build-time tool, not part of the app. Three steps:

    python -m tools.model_hosting pack     <converted dir> <staging dir>
    python -m tools.model_hosting publish  <staging dir> <user>/live-translator-models
    python -m tools.model_hosting catalog  <staging dir> <user>/live-translator-models <commit>

- `pack`: one zip per pair (`opus-mt-<src>-<tgt>.zip`, stored, fixed timestamps so the same
  files always give the same SHA-256), a `manifest.json` (pair, bytes, sha256, licence,
  upstream) and the repo's README model card with every model's licence and credit.
- `publish`: uploads the staging folder (the user is logged in with `hf auth login`; this
  tool never sees the token) and prints the commit it landed in.
- `catalog`: writes the pairs into `livetranslator/data/model_catalog.json` as URL sources
  pinned to that commit with their SHA-256, so the app's downloader (resume, cancel, hash
  check, safe unzip) fetches them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path
from typing import Any

from livetranslator.core.languages import language
from livetranslator.services.models import CATALOG_FILE

ZIP_TIME = (2026, 1, 1, 0, 0, 0)  # fixed: identical input -> identical zip -> identical hash
MANIFEST = "manifest.json"
REQUIRED = ("model.bin", "config.json", "source.spm", "target.spm", "opus_mt.json", "LICENCE.txt")
LICENCES = {"cc-by-4.0": "CC-BY-4.0", "apache-2.0": "Apache-2.0"}
MIB = 1 << 20
# Spot check 2026-10-19 (D:/LiveTranslator/check_pairs.py, D-039): garbled or loose on
# game-chat lines; Qwen translates these first while it's on.
ROUGH_PAIRS = frozenset({("en", "hi"), ("hi", "en"), ("ur", "en")})


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(MIB), b""):
            digest.update(block)
    return digest.hexdigest()


def pair_name(folder: Path) -> tuple[str, str]:
    src, _, tgt = folder.name.partition("-")
    return src, tgt


def pack_pair(folder: Path, out_dir: Path) -> dict[str, Any]:
    missing = [name for name in REQUIRED if not (folder / name).is_file()]
    if missing:
        raise ValueError(f"{folder.name}: missing {', '.join(missing)}")
    src, tgt = pair_name(folder)
    meta = json.loads((folder / "opus_mt.json").read_text(encoding="utf-8"))
    licence = LICENCES.get(str(meta["licence"]).lower(), str(meta["licence"]))
    archive = out_dir / f"opus-mt-{src}-{tgt}.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as zf:
        for path in sorted(p for p in folder.iterdir() if p.is_file()):
            info = zipfile.ZipInfo(path.name, date_time=ZIP_TIME)
            info.external_attr = 0o644 << 16
            with path.open("rb") as data, zf.open(info, "w") as dest:
                while block := data.read(MIB):
                    dest.write(block)
    return {
        "src": src,
        "tgt": tgt,
        "file": archive.name,
        "bytes": archive.stat().st_size,
        "sha256": _sha256(archive),
        "licence": licence,
        "upstream": str(meta["repo"]),
        "revision": str(meta["revision"]),
        "language_tag": str(meta.get("language_tag", "")),
        "quality": "rough" if (src, tgt) in ROUGH_PAIRS else "",
    }


def model_card(pairs: list[dict[str, Any]]) -> str:
    rows = "\n".join(
        f"| {p['src']} → {p['tgt']} | `{p['file']}` | {p['bytes'] // MIB} MB | {p['licence']} "
        f"| {p['upstream']} @ `{p['revision'][:12]}` |"
        for p in pairs
    )
    return (
        "---\nlicense: other\nlicense_name: mixed-apache-2.0-and-cc-by-4.0\n"
        "tags:\n- translation\n- ctranslate2\n- opus-mt\n---\n\n"
        "# Live Translator translation models\n\n"
        "Helsinki-NLP OPUS-MT models converted to CTranslate2 (float16 weights, otherwise "
        "unchanged) for the Live Translator desktop app, which downloads them from here at "
        "pinned commits with SHA-256 checks.\n\n"
        "Each zip holds one translation direction: the CTranslate2 model, the SentencePiece "
        "models, `opus_mt.json` (upstream repo, revision, licence, target-language tag) and "
        "`LICENCE.txt`.\n\n"
        "## Licences and credit\n\n"
        "All models are by the **Language Technology Research Group at the University of "
        "Helsinki** ([OPUS-MT](https://github.com/Helsinki-NLP/Opus-MT), "
        "[Tiedemann & Thottingal 2020](https://aclanthology.org/2020.eamt-1.61/)). Each keeps "
        "its own licence, listed below; CC-BY-4.0 models require this attribution and the "
        "note that they were converted.\n\n"
        "| Direction | File | Size | Licence | Upstream (Hugging Face) |\n"
        "|---|---|---|---|---|\n"
        f"{rows}\n"
    )


def pack(source: Path, staging: Path) -> list[dict[str, Any]]:
    staging.mkdir(parents=True, exist_ok=True)
    pairs: list[dict[str, Any]] = []
    for folder in sorted(p for p in source.iterdir() if p.is_dir() and "-" in p.name):
        if folder.name.endswith(".tmp"):
            continue
        pairs.append(pack_pair(folder, staging))
        print(f"packed {folder.name}: {pairs[-1]['bytes'] // MIB} MB", flush=True)
    (staging / MANIFEST).write_text(json.dumps(pairs, indent=2) + "\n", encoding="utf-8")
    (staging / "README.md").write_text(model_card(pairs), encoding="utf-8")
    return pairs


def publish(staging: Path, repo: str) -> str:
    from huggingface_hub import HfApi

    api = HfApi()
    api.create_repo(repo, repo_type="model", exist_ok=True)
    info = api.upload_folder(
        repo_id=repo,
        repo_type="model",
        folder_path=str(staging),
        allow_patterns=["*.zip", MANIFEST, "README.md"],
        commit_message="Live Translator translation models (OPUS-MT, CTranslate2)",
    )
    commit = str(info.oid)
    print(f"published to https://huggingface.co/{repo} at commit {commit}", flush=True)
    return commit


def catalog_entries(pairs: list[dict[str, Any]], repo: str, commit: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for p in pairs:
        src, tgt = p["src"], p["tgt"]
        entries.append(
            {
                "id": f"opus-mt-{src}-{tgt}",
                "title": f"Translation: {language(src).english} to {language(tgt).english}",
                "kind": "translation",
                "license": p["licence"],
                "size_mb": -(-p["bytes"] // MIB),  # rounded up
                "source": {
                    "type": "url",
                    "url": f"https://huggingface.co/{repo}/resolve/{commit}/{p['file']}",
                    "sha256": p["sha256"],
                    "archive": "zip",
                },
                "dest": f"opus-mt/{src}-{tgt}",
                "marker": "model.bin",
                "languages": [src, tgt],
                **({"quality": p["quality"]} if p.get("quality") else {}),
                "attribution": (
                    f"Helsinki-NLP/{p['upstream'].rsplit('/', 1)[-1]} by Helsinki-NLP / OPUS-MT "
                    f"({p['licence']}), converted to CTranslate2 by Live Translator"
                ),
            }
        )
    return entries


def write_catalog(entries: list[dict[str, Any]], path: Path = CATALOG_FILE) -> None:
    """Replace the catalogue's Opus-MT pair entries, keep everything else."""
    data = json.loads(path.read_text(encoding="utf-8"))
    kept = [m for m in data["models"] if not str(m.get("dest", "")).startswith("opus-mt/")]
    data["models"] = kept + entries
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Host Opus-MT models on Hugging Face (T074)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_pack = sub.add_parser("pack")
    p_pack.add_argument("source", type=Path)
    p_pack.add_argument("staging", type=Path)
    p_pub = sub.add_parser("publish")
    p_pub.add_argument("staging", type=Path)
    p_pub.add_argument("repo")
    p_cat = sub.add_parser("catalog")
    p_cat.add_argument("staging", type=Path)
    p_cat.add_argument("repo")
    p_cat.add_argument("commit")
    args = parser.parse_args(argv)
    if args.cmd == "pack":
        pack(args.source, args.staging)
    elif args.cmd == "publish":
        commit = publish(args.staging, args.repo)
        pairs = json.loads((args.staging / MANIFEST).read_text(encoding="utf-8"))
        write_catalog(catalog_entries(pairs, args.repo, commit))
    else:
        pairs = json.loads((args.staging / MANIFEST).read_text(encoding="utf-8"))
        write_catalog(catalog_entries(pairs, args.repo, args.commit))
    return 0


if __name__ == "__main__":
    sys.exit(main())
