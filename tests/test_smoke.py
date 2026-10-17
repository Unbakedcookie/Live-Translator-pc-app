"""T011 — the package starts via `python -m livetranslator` (Tier A)."""

import subprocess  # nosec B404
import sys
from pathlib import Path

from loguru import logger

from livetranslator import __version__
from livetranslator.__main__ import main

ROOT = Path(__file__).resolve().parents[1]


def test_module_entry_prints_version():
    out = subprocess.run(  # nosec B603
        [sys.executable, "-m", "livetranslator", "--version"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert out.stdout == f"Live Translator {__version__}\n"


def test_paths_option_lists_folders(isolated_home: Path, capsys):
    assert main(["--paths"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        f"settings: {isolated_home / 'config' / 'settings.json'}",
        f"data:     {isolated_home / 'data'}",
        f"models:   {isolated_home / 'data' / 'models'} (default)",
        f"logs:     {isolated_home / 'logs'}",
    ]
    assert not isolated_home.exists()  # --paths only reports; it creates nothing


def test_plain_start_creates_folders_and_logs(isolated_home: Path):
    assert main([]) == 0
    logger.complete()
    log_text = (isolated_home / "logs" / "livetranslator.log").read_text(encoding="utf-8")
    assert f"Live Translator {__version__} started" in log_text
    assert (isolated_home / "config").is_dir()
    assert (isolated_home / "data").is_dir()
