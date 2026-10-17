"""NVIDIA runtime libraries for CTranslate2 on Windows (T045; moved from the T032 benchmark).

CTranslate2 (faster-whisper, MT engines) needs cuBLAS and cuDNN. In development they come
from the nvidia-cublas-cu12 / nvidia-cudnn-cu12 pip wheels; how they are delivered to users
is open (D-026). Without them CTranslate2 still runs on the CPU.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from typing import Any

_added: set[str] = set()


def add_cuda_dll_dirs() -> list[Path]:
    """Make cuBLAS/cuDNN from the nvidia-* wheels loadable; returns the dirs added.

    ctranslate2 loads cublas64_12.dll lazily with a plain LoadLibrary at the first encode,
    which searches PATH but ignores os.add_dll_directory, so the bin dirs go on PATH too.
    """
    if sys.platform != "win32":
        return []
    added: list[Path] = []
    for name in ("nvidia.cublas", "nvidia.cudnn"):
        try:
            package: Any = importlib.import_module(name)
        except ImportError:
            continue
        for root in package.__path__:
            bin_dir = Path(root) / "bin"
            if not bin_dir.is_dir() or str(bin_dir) in _added:
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
