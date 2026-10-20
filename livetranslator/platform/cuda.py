"""NVIDIA runtime libraries for CTranslate2 on Windows (T045; moved from the T032 benchmark).

CTranslate2 (faster-whisper, MT engines) needs cuBLAS and cuDNN. In development they come
from the nvidia-cublas-cu12 / nvidia-cudnn-cu12 pip wheels. The built app doesn't ship them
(NVIDIA's licence, D-026): the setup wizard downloads those same wheels from NVIDIA's
packages on PyPI into `<models>/cuda/<name>/`, registered here with `set_runtime_root`.
Without them CTranslate2 still runs on the CPU.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from typing import Any

_added: set[str] = set()
_runtime_roots: list[Path] = []  # <models>/cuda: wheels the setup wizard downloaded
RUNTIME_PACKAGES = ("cublas", "cudnn", "cuda_nvrtc")


def set_runtime_root(root: Path) -> None:
    """Where downloaded NVIDIA libraries live (`<root>/<name>/nvidia/<package>/bin`)."""
    if root not in _runtime_roots:
        _runtime_roots.append(root)


def runtime_bin_dirs() -> list[Path]:
    """Every NVIDIA library folder found: the pip wheels (development), then downloads."""
    dirs: list[Path] = []
    for name in RUNTIME_PACKAGES:
        try:
            package: Any = importlib.import_module(f"nvidia.{name}")
        except ImportError:
            continue
        dirs += [Path(root) / "bin" for root in package.__path__]
    for root in _runtime_roots:
        dirs += sorted(root.glob("*/nvidia/*/bin"))
    return [d for d in dirs if d.is_dir()]


def runtime_present() -> bool:
    """cuBLAS can be loaded (from either place); CTranslate2 needs nothing else on the GPU
    for Whisper and Opus-MT (measured 2026-10-19: no cuDNN loaded while transcribing)."""
    return "cublas" in {d.parent.name for d in runtime_bin_dirs()}


def add_cuda_dll_dirs() -> list[Path]:
    """Make cuBLAS/cuDNN from the nvidia-* wheels loadable; returns the dirs added.

    ctranslate2 loads cublas64_12.dll lazily with a plain LoadLibrary at the first encode,
    which searches PATH but ignores os.add_dll_directory, so the bin dirs go on PATH too.
    """
    if sys.platform != "win32":
        return []
    added: list[Path] = []
    for bin_dir in runtime_bin_dirs():
        if str(bin_dir) in _added:
            continue
        os.add_dll_directory(str(bin_dir))
        os.environ["PATH"] = f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"
        _added.add(str(bin_dir))
        added.append(bin_dir)
    return added


def cuda_device_count() -> int:
    """GPUs CTranslate2 can see (0 without a driver or without ctranslate2)."""
    try:
        import ctranslate2

        return int(ctranslate2.get_cuda_device_count())
    except Exception:  # missing package or driver: CPU only
        return 0
