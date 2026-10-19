"""T074 — packing converted models for Hugging Face and writing the catalogue entries."""

import json
import zipfile
from pathlib import Path

import pytest

from livetranslator.services.models import UrlSource, load_catalog
from tools.model_hosting import MANIFEST, catalog_entries, pack, write_catalog

COMMIT = "a" * 40
REPO = "someone/live-translator-models"


def converted(root: Path, name: str, licence: str = "Apache-2.0", tag: str = "") -> Path:
    folder = root / name
    folder.mkdir(parents=True)
    for file in ("model.bin", "config.json", "source.spm", "target.spm", "shared_vocabulary.json"):
        (folder / file).write_bytes(f"{name}:{file}".encode())
    (folder / "LICENCE.txt").write_text("credit", encoding="utf-8")
    meta = {"repo": f"Helsinki-NLP/opus-mt-{name}", "revision": "b" * 40, "licence": licence}
    (folder / "opus_mt.json").write_text(json.dumps({**meta, "language_tag": tag}), "utf-8")
    return folder


def test_pack_is_reproducible_and_lists_licences(tmp_path: Path):
    source = tmp_path / "converted"
    converted(source, "en-pl", tag=">>pol<<")
    converted(source, "pt-en", licence="CC-BY-4.0")
    (source / "xx-yy.tmp").mkdir()  # a half-finished conversion is skipped
    pairs = pack(source, tmp_path / "a")
    again = pack(source, tmp_path / "b")
    assert [p["sha256"] for p in pairs] == [p["sha256"] for p in again]  # same input, same hash
    assert [(p["src"], p["tgt"], p["licence"]) for p in pairs] == [
        ("en", "pl", "Apache-2.0"),
        ("pt", "en", "CC-BY-4.0"),
    ]
    assert pairs[0]["language_tag"] == ">>pol<<"
    with zipfile.ZipFile(tmp_path / "a" / "opus-mt-en-pl.zip") as zf:
        assert "model.bin" in zf.namelist() and "LICENCE.txt" in zf.namelist()
    card = (tmp_path / "a" / "README.md").read_text(encoding="utf-8")
    assert "University of Helsinki" in card and "CC-BY-4.0" in card and "opus-mt-pt-en.zip" in card
    assert json.loads((tmp_path / "a" / MANIFEST).read_text(encoding="utf-8")) == pairs


def test_a_folder_missing_files_is_refused(tmp_path: Path):
    folder = converted(tmp_path / "converted", "en-it")
    (folder / "target.spm").unlink()
    with pytest.raises(ValueError, match=r"target\.spm"):
        pack(tmp_path / "converted", tmp_path / "staging")


def test_catalogue_entries_are_pinned_and_pass_the_apps_checks(tmp_path: Path):
    converted(tmp_path / "converted", "en-pl")
    pairs = pack(tmp_path / "converted", tmp_path / "staging")
    catalogue = tmp_path / "catalog.json"
    old_pair = {"id": "old", "dest": "opus-mt/xx-en"}
    keep = {
        "id": "keep",
        "title": "Kept",
        "kind": "runtime",
        "license": "MIT",
        "size_mb": 1,
        "source": {"type": "url", "url": "https://example.test/x", "sha256": "c" * 64},
        "dest": "x",
    }
    catalogue.write_text(json.dumps({"schema": 1, "models": [keep, old_pair]}), "utf-8")
    write_catalog(catalog_entries(pairs, REPO, COMMIT), catalogue)
    loaded = load_catalog(catalogue)  # the app's own validation (licence, https, sha256)
    assert sorted(loaded) == ["keep", "opus-mt-en-pl"]  # old pair entries replaced
    entry = loaded["opus-mt-en-pl"]
    assert entry.title == "Translation: English to Polish"
    assert isinstance(entry.source, UrlSource)
    assert entry.source.url == f"https://huggingface.co/{REPO}/resolve/{COMMIT}/opus-mt-en-pl.zip"
    assert entry.source.sha256 == pairs[0]["sha256"] and entry.source.archive == "zip"
    assert (entry.dest, entry.marker) == ("opus-mt/en-pl", "model.bin")
    assert entry.languages == ("en", "pl")


def test_rough_pairs_carry_their_quality_into_the_catalogue(tmp_path: Path):
    converted(tmp_path / "converted", "en-hi")
    converted(tmp_path / "converted", "en-it")
    pairs = pack(tmp_path / "converted", tmp_path / "staging")
    assert [p["quality"] for p in pairs] == ["rough", ""]
    catalogue = tmp_path / "catalog.json"
    catalogue.write_text(json.dumps({"schema": 1, "models": []}), "utf-8")
    write_catalog(catalog_entries(pairs, REPO, COMMIT), catalogue)
    loaded = load_catalog(catalogue)
    assert loaded["opus-mt-en-hi"].quality == "rough" and loaded["opus-mt-en-it"].quality == ""
