"""Language packs for the Language Manager (T074; spec §5.9).

A pack is everything that translates one language to and from English: the catalogue's
Opus-MT entries (`dest` = "opus-mt/<src>-<tgt>") with that language on one side. Pairs between
two other languages pivot through English (router, T052), so English packs are all a user
needs. Some languages only have the "into English" half (e.g. Thai): voice chat in them still
gets translated for you, but a window can't translate *into* them without Qwen.

Installed state is read from the models folder (a pair counts once its `model.bin` is there),
so pairs converted by hand before the catalogue existed show as installed too.
"""

from __future__ import annotations

import shutil
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from livetranslator.services.models import ModelEntry

OPUS_PREFIX = "opus-mt/"
PIVOT = "en"


@dataclass(frozen=True)
class LanguagePack:
    code: str
    entries: tuple[ModelEntry, ...]  # the pair entries with this language on one side
    installed: frozenset[str]  # ids of the entries whose files are present

    @property
    def size_mb(self) -> int:
        return sum(e.size_mb for e in self.entries)

    @property
    def missing(self) -> tuple[ModelEntry, ...]:
        return tuple(e for e in self.entries if e.id not in self.installed)

    @property
    def is_installed(self) -> bool:
        return not self.missing

    @property
    def is_partial(self) -> bool:
        return bool(self.installed) and bool(self.missing)

    @property
    def directions(self) -> tuple[bool, bool]:
        """(into English, out of English) offered by this pack."""
        pairs = {pair_of(e) for e in self.entries}
        return (self.code, PIVOT) in pairs, (PIVOT, self.code) in pairs

    @property
    def rough(self) -> bool:
        return any(e.quality == "rough" for e in self.entries)

    @property
    def licences(self) -> tuple[str, ...]:
        return tuple(sorted({e.license for e in self.entries}))


def pair_of(entry: ModelEntry) -> tuple[str, str]:
    src, _, tgt = entry.dest.removeprefix(OPUS_PREFIX).partition("-")
    return src, tgt


def rough_pairs(catalog: Mapping[str, ModelEntry]) -> frozenset[tuple[str, str]]:
    """Pairs whose model is usable but weak: Qwen goes first for them while it's on."""
    return frozenset(
        pair_of(e) for e in catalog.values() if is_pair_entry(e) and e.quality == "rough"
    )


def is_pair_entry(entry: ModelEntry) -> bool:
    return entry.kind == "translation" and entry.dest.startswith(OPUS_PREFIX)


def pair_installed(models_dir: Path, entry: ModelEntry) -> bool:
    return (models_dir / entry.dest / (entry.marker or "model.bin")).is_file()


def language_packs(
    catalog: Mapping[str, ModelEntry], models_dir: Path, order: Iterable[str] = ()
) -> list[LanguagePack]:
    """One pack per non-English language in the catalogue's pairs. `order` (e.g. the app's
    language list) comes first, the rest follow alphabetically by code."""
    by_code: dict[str, list[ModelEntry]] = {}
    for entry in catalog.values():
        if not is_pair_entry(entry):
            continue
        src, tgt = pair_of(entry)
        if PIVOT not in (src, tgt) or src == tgt:
            continue  # only X <-> English pairs make packs
        code = tgt if src == PIVOT else src
        by_code.setdefault(code, []).append(entry)
    ranked = [c for c in order if c in by_code]
    ranked += sorted(c for c in by_code if c not in ranked)
    packs = []
    for code in ranked:
        entries = tuple(sorted(by_code[code], key=lambda e: pair_of(e) != (code, PIVOT)))
        installed = frozenset(e.id for e in entries if pair_installed(models_dir, e))
        packs.append(LanguagePack(code, entries, installed))
    return packs


def remove_pack(pack: LanguagePack, models_dir: Path) -> list[str]:
    """Delete the pack's pair folders. Returns the ids removed. Only folders under
    <models>/opus-mt/ are ever touched."""
    root = (models_dir / OPUS_PREFIX).resolve()
    removed = []
    for entry in pack.entries:
        folder = (models_dir / entry.dest).resolve()
        if not folder.is_relative_to(root) or folder == root:
            continue  # never outside the translation models folder
        if folder.exists():
            shutil.rmtree(folder)
            removed.append(entry.id)
    return removed
