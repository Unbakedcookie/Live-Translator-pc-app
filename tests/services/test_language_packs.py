"""T074 — language packs from the catalogue: grouping, order, installed state, removal."""

from pathlib import Path

from livetranslator.services.language_packs import language_packs, pair_of, remove_pack
from livetranslator.services.models import ModelEntry, UrlSource

SHA = "0" * 64


def pair(src: str, tgt: str, size: int = 150, licence: str = "Apache-2.0") -> ModelEntry:
    return ModelEntry(
        id=f"opus-mt-{src}-{tgt}",
        title=f"{src}-{tgt}",
        kind="translation",
        license=licence,
        size_mb=size,
        source=UrlSource(f"https://example.test/{src}-{tgt}.zip", SHA, "zip"),
        dest=f"opus-mt/{src}-{tgt}",
        marker="model.bin",
        languages=(src, tgt),
    )


def install(models: Path, entry: ModelEntry) -> None:
    folder = models / entry.dest
    folder.mkdir(parents=True)
    (folder / "model.bin").write_bytes(b"x")


CATALOG = {
    e.id: e
    for e in (
        pair("en", "pt", 233, "CC-BY-4.0"),
        pair("pt", "en", 156),
        pair("th", "en"),  # into English only
        pair("en", "de"),
        pair("de", "en"),
        pair("de", "fr"),  # not an English pair: no pack
    )
}
OTHER = ModelEntry(
    "qwen", "Qwen", "translation", "Apache-2.0", 2382, CATALOG["opus-mt-de-en"].source, "qwen3-4b"
)


def test_packs_group_both_directions_and_follow_the_app_order(tmp_path: Path):
    packs = language_packs({**CATALOG, "qwen": OTHER}, tmp_path, order=("pt", "de"))
    assert [p.code for p in packs] == ["pt", "de", "th"]  # given order first, then the rest
    pt = packs[0]
    assert [pair_of(e) for e in pt.entries] == [("pt", "en"), ("en", "pt")]  # into English first
    assert pt.size_mb == 389 and pt.licences == ("Apache-2.0", "CC-BY-4.0")
    assert pt.directions == (True, True) and packs[2].directions == (True, False)
    assert not pt.is_installed and not pt.is_partial


def test_installed_state_comes_from_the_models_folder(tmp_path: Path):
    install(tmp_path, CATALOG["opus-mt-pt-en"])
    pt = language_packs(CATALOG, tmp_path)[1]  # alphabetical: de, pt, th
    assert pt.code == "pt" and pt.is_partial
    assert [e.id for e in pt.missing] == ["opus-mt-en-pt"]
    install(tmp_path, CATALOG["opus-mt-en-pt"])
    assert language_packs(CATALOG, tmp_path)[1].is_installed


def test_remove_deletes_only_the_packs_folders(tmp_path: Path):
    for entry in CATALOG.values():
        install(tmp_path, entry)
    (tmp_path / "qwen3-4b").mkdir()
    pt = language_packs(CATALOG, tmp_path, order=("pt",))[0]
    assert sorted(remove_pack(pt, tmp_path)) == ["opus-mt-en-pt", "opus-mt-pt-en"]
    assert not (tmp_path / "opus-mt" / "pt-en").exists()
    assert (tmp_path / "opus-mt" / "de-en" / "model.bin").exists()
    assert (tmp_path / "qwen3-4b").exists()
    escaping = ModelEntry(
        "bad", "bad", "translation", "MIT", 1, OTHER.source, "opus-mt/../qwen3-4b", "x"
    )
    from livetranslator.services.language_packs import LanguagePack

    assert remove_pack(LanguagePack("xx", (escaping,), frozenset()), tmp_path) == []
    assert (tmp_path / "qwen3-4b").exists()  # a bad dest can't reach outside opus-mt/
