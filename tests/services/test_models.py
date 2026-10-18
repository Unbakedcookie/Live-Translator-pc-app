"""T054 — catalogue rules and downloads against a local HTTP server (Range support)."""

import hashlib
import io
import json
import threading
import urllib.request
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from livetranslator.services.models import (
    ALLOWED_LICENSES,
    CatalogError,
    DownloadCancelled,
    DownloadError,
    HfFunctions,
    HfSource,
    ModelEntry,
    ModelManager,
    UrlSource,
    load_catalog,
)

PAYLOAD = bytes(range(256)) * 4096 * 3  # 3 MiB: several 1 MiB read blocks
PAYLOAD_SHA = hashlib.sha256(PAYLOAD).hexdigest()


def zip_bytes(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


ZIPPED = zip_bytes({"llama-b1/llama-server.exe": b"exe", "llama-b1/ggml.dll": b"dll"})


class Server:
    def __init__(self) -> None:
        self.files = {"/model.onnx": PAYLOAD, "/build.zip": ZIPPED}
        self.ranges: list[str] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args) -> None:  # quiet
                pass

            def do_GET(self) -> None:
                data = outer.files.get(self.path)
                if data is None:
                    self.send_error(404)
                    return
                start = 0
                rng = self.headers.get("Range")
                if rng:
                    outer.ranges.append(rng)
                    start = int(rng.removeprefix("bytes=").split("-")[0])
                    self.send_response(206)
                else:
                    self.send_response(200)
                body = data[start:]
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def url(self, path: str) -> str:
        return f"https://example.test{path}"  # catalogue requires https; opener maps it

    def opener(self, request: urllib.request.Request, timeout: float = 30):
        local = request.full_url.replace("https://example.test", f"http://127.0.0.1:{self.port}")
        req = urllib.request.Request(local, headers=dict(request.header_items()))
        return urllib.request.urlopen(req, timeout=timeout)  # nosec B310 - local test server


@pytest.fixture
def server():
    s = Server()
    yield s
    s.httpd.shutdown()


def url_entry(
    server: Server,
    path: str = "/model.onnx",
    sha: str = PAYLOAD_SHA,
    dest: str = "speakers/model.onnx",
    marker: str = "",
) -> ModelEntry:
    archive = "zip" if path.endswith(".zip") else ""
    return ModelEntry(
        id="m",
        title="Test model",
        kind="speakers",
        license="MIT",
        size_mb=1,
        source=UrlSource(server.url(path), sha, archive),
        dest=dest,
        marker=marker,
    )


def manager(tmp_path: Path, server: Server, **kw) -> ModelManager:
    return ModelManager(tmp_path / "models", {}, opener=server.opener, **kw)


# ---------------------------------------------------------------- catalogue


def test_shipped_catalogue_is_valid():
    catalog = load_catalog()
    assert {"whisper-large-v3-turbo", "speakers-titanet", "qwen3-4b"} <= set(catalog)
    for entry in catalog.values():
        assert entry.license in ALLOWED_LICENSES
        if isinstance(entry.source, HfSource):
            assert len(entry.source.revision) == 40  # pinned commit
        else:
            assert entry.source.url.startswith("https://") and len(entry.source.sha256) == 64


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"license": "CC-BY-NC-4.0"}, "isn't allowed"),
        ({"source": {"type": "hf", "repo": "a/b", "revision": "main"}}, "pin a commit"),
        ({"source": {"type": "url", "url": "http://x/y", "sha256": "0" * 64}}, "HTTPS"),
        ({"source": {"type": "url", "url": "https://x/y", "sha256": "abc"}}, "SHA-256"),
        ({"dest": "../outside"}, "inside the models folder"),
    ],
)
def test_catalogue_rules(tmp_path: Path, change: dict, message: str):
    raw = {
        "id": "x",
        "title": "X",
        "kind": "speech",
        "license": "MIT",
        "size_mb": 1,
        "source": {"type": "hf", "repo": "a/b", "revision": "a" * 40},
        "dest": "x",
    }
    raw.update(change)
    path = tmp_path / "c.json"
    path.write_text(json.dumps({"models": [raw]}), encoding="utf-8")
    with pytest.raises(CatalogError, match=message):
        load_catalog(path)


# ---------------------------------------------------------------- downloads


def test_url_download_verifies_and_moves_into_place(tmp_path: Path, server: Server):
    mgr = manager(tmp_path, server)
    entry = url_entry(server)
    assert not mgr.is_installed(entry)
    seen: list[tuple[int, int]] = []
    path = mgr.download(entry, progress=lambda d, t: seen.append((d, t)))
    assert path == tmp_path / "models" / "speakers" / "model.onnx"
    assert path.read_bytes() == PAYLOAD and mgr.is_installed(entry)
    assert seen[-1] == (len(PAYLOAD), len(PAYLOAD))
    assert not list((tmp_path / "models" / ".downloads").glob("*.part"))


def test_resume_continues_a_partial_download(tmp_path: Path, server: Server):
    mgr = manager(tmp_path, server)
    staging = tmp_path / "models" / ".downloads"
    staging.mkdir(parents=True)
    (staging / "model.onnx.part").write_bytes(PAYLOAD[:300_000])
    path = mgr.download(url_entry(server))
    assert server.ranges == ["bytes=300000-"]
    assert path.read_bytes() == PAYLOAD


def test_cancel_keeps_the_partial_file_for_later(tmp_path: Path, server: Server):
    mgr = manager(tmp_path, server)
    cancel = threading.Event()

    def stop_after_first_block(done: int, total: int) -> None:
        cancel.set()

    with pytest.raises(DownloadCancelled):
        mgr.download(url_entry(server), progress=stop_after_first_block, cancel=cancel)
    part = tmp_path / "models" / ".downloads" / "model.onnx.part"
    assert 0 < part.stat().st_size < len(PAYLOAD)
    assert mgr.download(url_entry(server)).read_bytes() == PAYLOAD  # resumes
    assert server.ranges


def test_wrong_hash_deletes_the_file(tmp_path: Path, server: Server):
    mgr = manager(tmp_path, server)
    with pytest.raises(DownloadError, match="damaged"):
        mgr.download(url_entry(server, sha="0" * 64))
    assert not list((tmp_path / "models").rglob("model.onnx*"))


def test_zip_is_extracted_flattened_and_swapped_in(tmp_path: Path, server: Server):
    mgr = manager(tmp_path, server)
    entry = url_entry(
        server,
        "/build.zip",
        sha=hashlib.sha256(ZIPPED).hexdigest(),
        dest="llama.cpp/vulkan",
        marker="llama-server.exe",
    )
    target = mgr.download(entry)
    assert sorted(p.name for p in target.iterdir()) == ["ggml.dll", "llama-server.exe"]
    assert mgr.is_installed(entry)


def test_not_enough_space_is_reported_before_downloading(tmp_path: Path, server: Server):
    mgr = manager(tmp_path, server)
    huge = url_entry(server)
    huge = ModelEntry(**{**huge.__dict__, "size_mb": 10**9})
    with pytest.raises(DownloadError, match="only"):
        mgr.download(huge)
    assert server.ranges == [] and not (tmp_path / "models" / ".downloads").exists()


def test_hugging_face_sources_use_huggingface_hub(tmp_path: Path):
    calls: list[tuple] = []

    def snapshot(repo, revision, cache_dir, local_files_only=False):
        calls.append(("snapshot", repo, revision, local_files_only))
        if local_files_only:
            raise FileNotFoundError("not cached")
        return str(cache_dir / "snap")

    def file(repo, filename, revision, local_dir):
        calls.append(("file", repo, filename, revision))
        (Path(local_dir) / filename).write_bytes(b"gguf")
        return str(Path(local_dir) / filename)

    mgr = ModelManager(tmp_path / "m", {}, hf=HfFunctions(snapshot, file))
    whole = ModelEntry("w", "W", "speech", "MIT", 1, HfSource("o/w", "a" * 40), "")
    assert not mgr.is_installed(whole)
    mgr.download(whole)
    one = ModelEntry(
        "q",
        "Q",
        "translation",
        "Apache-2.0",
        1,
        HfSource("o/q", "b" * 40, ("q.gguf",)),
        "qwen",
        "q.gguf",
    )
    mgr.download(one)
    assert mgr.is_installed(one)
    assert ("snapshot", "o/w", "a" * 40, False) in calls
    assert ("file", "o/q", "q.gguf", "b" * 40) in calls


def test_changing_the_folder_moves_models(tmp_path: Path):
    old, new = tmp_path / "old", tmp_path / "new"
    (old / "speakers").mkdir(parents=True)
    (old / "speakers" / "a.onnx").write_bytes(b"x")
    (new / "keep").mkdir(parents=True)
    (old / "keep").mkdir()  # already exists at the destination: never overwritten
    mgr = ModelManager(old, {})
    assert mgr.move_to(new) == ["speakers"]
    assert (new / "speakers" / "a.onnx").read_bytes() == b"x"
    assert (old / "keep").exists() and mgr.models_dir == new
