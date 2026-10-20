"""D-026: NVIDIA libraries are found in the folder the setup wizard downloads them to."""

from pathlib import Path

from livetranslator.platform import cuda


def test_downloaded_libraries_are_found(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(cuda, "_runtime_roots", [])
    monkeypatch.setattr(cuda.importlib, "import_module", _no_pip_wheels)
    assert cuda.runtime_bin_dirs() == [] and not cuda.runtime_present()
    root = tmp_path / "cuda"
    for name in ("cublas", "cudnn"):
        (root / name / "nvidia" / name / "bin").mkdir(parents=True)
    cuda.set_runtime_root(root)
    cuda.set_runtime_root(root)  # once only
    assert [d.parent.name for d in cuda.runtime_bin_dirs()] == ["cublas", "cudnn"]
    assert cuda.runtime_present()


def _no_pip_wheels(name: str):
    raise ImportError(name)
