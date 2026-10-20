"""Model catalogue and downloads (T054; spec §5.9).

The catalogue (`livetranslator/data/model_catalog.json`, shipped with the app) lists every
downloadable model with its licence, size and a pinned source:

- `hf`: a Hugging Face repo at a **pinned commit** (never "main"), fetched with
  huggingface_hub (resumable, cached, no token for public repos). `files` limits it to some
  files; without it the whole snapshot is fetched (Whisper's layout).
- `url`: a plain HTTPS file with its SHA-256. It downloads to `<name>.part` (resumed with an
  HTTP Range request after a cancel or a dropped connection), is checked, then moved into
  place. A `zip` is extracted into a temporary folder first and swapped in whole.

A wrong hash deletes the file and reports it; nothing half-verified is ever left where the
engines look. Every licence must be on `ALLOWED_LICENSES` (the app must stay shareable).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import threading
import urllib.request
import zipfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from livetranslator import __version__

CATALOG_FILE = Path(__file__).resolve().parents[1] / "data" / "model_catalog.json"
ALLOWED_LICENSES = frozenset(
    {"MIT", "Apache-2.0", "BSD-3-Clause", "CC-BY-4.0", "FunASR-Model-License-1.1", "CC-BY-SA-4.0"}
)
# NVIDIA's cuBLAS/cuDNN (D-026): never shipped with the app. The setup wizard downloads
# NVIDIA's own PyPI packages straight to the user's PC, so only this kind may carry it.
GPU_RUNTIME = "gpu-runtime"
VENDOR_RUNTIME_LICENSES = frozenset({"LicenseRef-NVIDIA-Proprietary"})
CHUNK = 1 << 20
USER_AGENT = (
    f"LiveTranslator/{__version__} (+https://github.com/Unbakedcookie/Live-Translator-pc-app)"
)
_REVISION = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

Progress = Callable[[int, int], None]  # (bytes done, bytes total; 0 = unknown)


class CatalogError(ValueError):
    pass


class DownloadError(RuntimeError):
    """Something the user can act on (no space, bad file, no connection)."""


class DownloadCancelled(DownloadError):
    pass


@dataclass(frozen=True)
class HfSource:
    repo: str
    revision: str
    files: tuple[str, ...] = ()  # empty = whole snapshot


@dataclass(frozen=True)
class UrlSource:
    url: str
    sha256: str
    archive: str = ""  # "" = single file, "zip" = extract


@dataclass(frozen=True)
class RemoteFile:
    name: str  # file name inside the model folder
    url: str
    sha256: str
    size: int  # bytes (progress across files)


@dataclass(frozen=True)
class FilesSource:
    """Several HTTPS files that together make one model folder (e.g. a Whisper model from
    its Hugging Face repo, file by file at a pinned commit): resumable, cancellable and
    checked like a URL source, no Hugging Face cache layout (T073)."""

    files: tuple[RemoteFile, ...]


@dataclass(frozen=True)
class ModelEntry:
    id: str
    title: str
    kind: str  # "speech", "translation", "speakers", "runtime"
    license: str
    size_mb: int
    source: HfSource | UrlSource | FilesSource
    dest: str  # where it lives under the models folder ("" = Hugging Face cache layout)
    marker: str = ""  # a file under dest that proves it's installed
    languages: tuple[str, ...] = ()
    attribution: str = ""
    quality: str = ""  # "rough": usable, but Qwen does better while it's on (T074)


# ---------------------------------------------------------------- catalogue


def _entry(raw: Mapping[str, Any]) -> ModelEntry:
    entry_id = str(raw["id"])
    licence = str(raw["license"])
    vendor_runtime = str(raw["kind"]) == GPU_RUNTIME and licence in VENDOR_RUNTIME_LICENSES
    if licence not in ALLOWED_LICENSES and not vendor_runtime:
        raise CatalogError(f"{entry_id}: licence {licence!r} isn't allowed in a shareable app")
    src = raw["source"]
    source: HfSource | UrlSource | FilesSource
    if src["type"] == "hf":
        revision = str(src["revision"])
        if not _REVISION.match(revision):
            raise CatalogError(
                f"{entry_id}: Hugging Face sources must pin a commit, not {revision!r}"
            )
        source = HfSource(str(src["repo"]), revision, tuple(src.get("files", ())))
    elif src["type"] == "url":
        url, digest = str(src["url"]), str(src["sha256"]).lower()
        if not url.startswith("https://"):
            raise CatalogError(f"{entry_id}: downloads must use HTTPS")
        if not _SHA256.match(digest):
            raise CatalogError(f"{entry_id}: a URL source needs its SHA-256")
        source = UrlSource(url, digest, str(src.get("archive", "")))
    elif src["type"] == "files":
        files = []
        for item in src["files"]:
            url, digest, name = str(item["url"]), str(item["sha256"]).lower(), str(item["name"])
            if not url.startswith("https://"):
                raise CatalogError(f"{entry_id}: downloads must use HTTPS")
            if not _SHA256.match(digest):
                raise CatalogError(f"{entry_id}: every file needs its SHA-256")
            if "/" in name or "\\" in name or name in ("", ".", ".."):
                raise CatalogError(f"{entry_id}: file names can't contain folders")
            files.append(RemoteFile(name, url, digest, int(item["size"])))
        if not files:
            raise CatalogError(f"{entry_id}: a files source needs files")
        source = FilesSource(tuple(files))
    else:
        raise CatalogError(f"{entry_id}: unknown source type {src['type']!r}")
    dest = str(raw.get("dest", ""))
    if Path(dest).is_absolute() or ".." in Path(dest).parts:
        raise CatalogError(f"{entry_id}: dest must stay inside the models folder")
    return ModelEntry(
        id=entry_id,
        title=str(raw["title"]),
        kind=str(raw["kind"]),
        license=licence,
        size_mb=int(raw["size_mb"]),
        source=source,
        dest=dest,
        marker=str(raw.get("marker", "")),
        languages=tuple(raw.get("languages", ())),
        attribution=str(raw.get("attribution", "")),
        quality=str(raw.get("quality", "")),
    )


def load_catalog(path: Path = CATALOG_FILE) -> dict[str, ModelEntry]:
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = [_entry(raw) for raw in data["models"]]
    ids = [e.id for e in entries]
    if len(ids) != len(set(ids)):
        raise CatalogError("duplicate model ids in the catalogue")
    return {e.id: e for e in entries}


# ---------------------------------------------------------------- helpers


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_extract_zip(archive: Path, dest: Path) -> None:
    """Extract, refusing members that would land outside `dest`."""
    root = dest.resolve()
    with zipfile.ZipFile(archive) as zf:
        for member in zf.infolist():
            if member.is_dir():
                continue
            target = (root / member.filename).resolve()
            if not target.is_relative_to(root):
                raise DownloadError(f"{archive.name} contains an unsafe path")
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, target.open("wb") as out:
                shutil.copyfileobj(src, out)


def flatten_single_folder(folder: Path, marker: str) -> None:
    """Some zips wrap everything in one folder: lift its contents up if the marker is there."""
    if not marker or (folder / marker).exists():
        return
    children = [c for c in folder.iterdir()]
    if len(children) == 1 and children[0].is_dir() and (children[0] / marker).exists():
        inner = children[0]
        for item in inner.iterdir():
            item.replace(folder / item.name)
        inner.rmdir()


# ---------------------------------------------------------------- manager


@dataclass
class HfFunctions:
    """huggingface_hub entry points (injected so tests never touch the network)."""

    snapshot: Callable[..., str]
    file: Callable[..., str]


def _default_hf() -> HfFunctions:
    from huggingface_hub import hf_hub_download, snapshot_download

    return HfFunctions(snapshot_download, hf_hub_download)


@dataclass
class ModelManager:
    models_dir: Path
    catalog: Mapping[str, ModelEntry]
    hf: HfFunctions | None = None
    opener: Callable[..., Any] = urllib.request.urlopen
    _lock: threading.Lock = field(default_factory=threading.Lock)

    # ------------------------------------------------------------ state

    def is_installed(self, entry: ModelEntry) -> bool:
        if isinstance(entry.source, HfSource) and not entry.dest:
            try:
                self._hf().snapshot(
                    entry.source.repo,
                    revision=entry.source.revision,
                    cache_dir=self.models_dir,
                    local_files_only=True,
                )
            except Exception:  # not in the cache yet
                return False
            return True
        target = self.models_dir / entry.dest
        return (target / entry.marker).exists() if entry.marker else target.exists()

    def missing(self, ids: Sequence[str]) -> list[ModelEntry]:
        return [self.catalog[i] for i in ids if not self.is_installed(self.catalog[i])]

    def space_check(self, entries: Sequence[ModelEntry]) -> tuple[int, int]:
        """(MB needed, MB free) on the models drive."""
        self.models_dir.mkdir(parents=True, exist_ok=True)
        free = shutil.disk_usage(self.models_dir).free // (1 << 20)
        return sum(e.size_mb for e in entries), int(free)

    # ------------------------------------------------------------ download

    def download(
        self,
        entry: ModelEntry,
        progress: Progress | None = None,
        cancel: threading.Event | None = None,
    ) -> Path:
        needed, free = self.space_check([entry])
        if needed > free:
            raise DownloadError(
                f"{entry.title} needs {needed} MB but only {free} MB is free on that drive."
            )
        with self._lock:
            if isinstance(entry.source, HfSource):
                return self._download_hf(entry, entry.source)
            if isinstance(entry.source, FilesSource):
                return self._download_files(entry, entry.source, progress, cancel)
            return self._download_url(entry, entry.source, progress, cancel)

    def _download_files(
        self,
        entry: ModelEntry,
        source: FilesSource,
        progress: Progress | None,
        cancel: threading.Event | None,
    ) -> Path:
        """Each file to its own resumable `.part`, checked, then the whole folder swapped in
        at once: the engine never sees a half-downloaded model."""
        target = self.models_dir / entry.dest
        staging = self.models_dir / ".downloads" / f"{entry.id}.files"
        staging.mkdir(parents=True, exist_ok=True)
        total = sum(f.size for f in source.files)
        done_before = 0
        for remote in source.files:
            final = staging / remote.name
            if final.exists() and sha256_of(final) == remote.sha256:
                done_before += remote.size  # finished in an earlier, paused run
                if progress is not None:
                    progress(done_before, total)
                continue
            part = staging / f"{remote.name}.part"
            offset = done_before

            def report(done: int, _size: int, offset: int = offset) -> None:
                if progress is not None:
                    progress(offset + done, total)

            self._fetch(remote.url, part, report, cancel)
            if sha256_of(part) != remote.sha256:
                part.unlink(missing_ok=True)
                raise DownloadError(
                    f"{entry.title} was damaged in transit and has been deleted. Try again."
                )
            os.replace(part, final)
            done_before += remote.size
        if entry.marker and not (staging / entry.marker).exists():
            raise DownloadError(f"{entry.title}: the download doesn't contain {entry.marker}.")
        shutil.rmtree(target, ignore_errors=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        staging.replace(target)
        return target

    def _hf(self) -> HfFunctions:
        if self.hf is None:
            self.hf = _default_hf()
        return self.hf

    def _download_hf(self, entry: ModelEntry, source: HfSource) -> Path:
        hf = self._hf()
        try:
            if not entry.dest:
                return Path(
                    hf.snapshot(source.repo, revision=source.revision, cache_dir=self.models_dir)
                )
            target = self.models_dir / entry.dest
            target.mkdir(parents=True, exist_ok=True)
            for name in source.files:
                hf.file(source.repo, name, revision=source.revision, local_dir=target)
            return target
        except Exception as exc:
            raise DownloadError(f"Couldn't download {entry.title} ({type(exc).__name__}).") from exc

    def _download_url(
        self,
        entry: ModelEntry,
        source: UrlSource,
        progress: Progress | None,
        cancel: threading.Event | None,
    ) -> Path:
        target = self.models_dir / entry.dest
        name = source.url.rsplit("/", 1)[-1]
        staging = self.models_dir / ".downloads"
        staging.mkdir(parents=True, exist_ok=True)
        part = staging / f"{name}.part"
        self._fetch(source.url, part, progress, cancel)
        if sha256_of(part) != source.sha256:
            part.unlink(missing_ok=True)
            raise DownloadError(
                f"{entry.title} was damaged in transit and has been deleted. Try again."
            )
        if source.archive == "zip":
            unpacked = staging / f"{entry.id}.unpacked"
            shutil.rmtree(unpacked, ignore_errors=True)
            safe_extract_zip(part, unpacked)
            flatten_single_folder(unpacked, entry.marker)
            if entry.marker and not (unpacked / entry.marker).exists():
                raise DownloadError(f"{entry.title}: the download doesn't contain {entry.marker}.")
            shutil.rmtree(target, ignore_errors=True)
            target.parent.mkdir(parents=True, exist_ok=True)
            unpacked.replace(target)
            part.unlink(missing_ok=True)
            return target
        target.parent.mkdir(parents=True, exist_ok=True)
        final = target if target.suffix else target / name
        final.parent.mkdir(parents=True, exist_ok=True)
        os.replace(part, final)
        return final

    def _fetch(
        self,
        url: str,
        part: Path,
        progress: Progress | None,
        cancel: threading.Event | None,
    ) -> None:
        done = part.stat().st_size if part.exists() else 0
        # Named agent: Discord's firewall blocked Python's default one (2026-10-18); hosts
        # may do the same.
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        if done:
            request.add_header("Range", f"bytes={done}-")
        try:
            response = self.opener(request, timeout=30)  # nosec B310 - https only (catalogue check)
        except OSError as exc:
            raise DownloadError("Couldn't connect. Check the internet connection.") from exc
        with response:
            status = getattr(response, "status", 200)
            if done and status != 206:
                done = 0  # server ignored the Range: start over
            length = int(response.headers.get("Content-Length") or 0)
            total = done + length if length else 0
            with part.open("ab" if done else "wb") as out:
                while True:
                    if cancel is not None and cancel.is_set():
                        raise DownloadCancelled("Download paused; it continues where it stopped.")
                    block = response.read(CHUNK)
                    if not block:
                        break
                    out.write(block)
                    done += len(block)
                    if progress is not None:
                        progress(done, total)

    # ------------------------------------------------------------ moving the folder

    def move_to(self, new_dir: Path) -> list[str]:
        """Move everything to `new_dir` (Settings → model folder). Returns the moved names;
        anything that couldn't move stays where it was and is left out of the list."""
        new_dir.mkdir(parents=True, exist_ok=True)
        moved: list[str] = []
        if new_dir.resolve() == self.models_dir.resolve():
            return moved
        for item in list(self.models_dir.iterdir()) if self.models_dir.exists() else []:
            destination = new_dir / item.name
            if destination.exists():
                continue  # never overwrite what's already there
            try:
                shutil.move(str(item), str(destination))
            except OSError:
                continue
            moved.append(item.name)
        self.models_dir = new_dir
        return moved
