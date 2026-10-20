"""Build the Windows app folder (installer input) with PyInstaller (packaging; spec §11).

    python -m tools.build_app            # -> build/dist/LiveTranslator/
    python -m tools.build_app --check    # only run the release licence check on that folder

Steps: PyInstaller one-folder build (Qt DLLs stay separate files, which the LGPL needs),
then strip what must not ship (opencv's FFmpeg plugin D-034, QtAwesome fonts other than
Phosphor, PyAV D-027, NVIDIA runtime DLLs D-026: the setup wizard downloads those from
NVIDIA's own packages), add every licence text + THIRD_PARTY_LICENSES.md, and finish with the
release licence check. Build tool, not part of the app; PyInstaller is GPL with an exception
that allows distributing apps built with it.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from tools.release_license_check import scan
from tools.third_party import collect_texts, shipped_packages

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
DIST = BUILD / "dist"
APP = DIST / "LiveTranslator"
PACKAGE = ROOT / "livetranslator"

COLLECT_ALL = ("faster_whisper", "rapidocr", "sherpa_onnx", "opencc", "ctranslate2", "onnxruntime")
COLLECT_ALL_EXTRA = ("materialyoucolor", "qtawesome")  # dynamic imports / code + fonts
COLLECT_DATA: tuple[str, ...] = ()
HIDDEN = (
    "pynvml",
    "winrt.windows.foundation",
    "winrt.windows.foundation.collections",
    "winrt.windows.globalization",
    "winrt.windows.graphics.imaging",
    "winrt.windows.media.ocr",
    "winrt.windows.storage.streams",
)
EXCLUDE = (
    "av",  # D-027: GPL x264/x265 inside
    "torch",
    "torchaudio",
    "tkinter",
    "matplotlib",
    "IPython",
    "pytest",
    "nvidia",  # D-026: downloaded from NVIDIA's packages by the wizard, never bundled
)
STRIP_GLOBS = (
    "**/opencv_videoio_ffmpeg*.dll",  # D-034
    "**/av/**",
    "**/av.libs/**",
    "**/nvidia/**",
    "**/cublas*.dll",
    "**/cudnn*.dll",
    "**/cudart*.dll",
    "**/nvrtc*.dll",
)


def make_icon(path: Path) -> Path:
    from PySide6.QtWidgets import QApplication

    from livetranslator.platform.app_identity import write_icon
    from livetranslator.theme.icons import app_icon

    app = QApplication.instance() or QApplication([])
    written = write_icon(app_icon(), path.parent)
    del app
    if written is None:
        raise SystemExit("couldn't write the app icon")
    return written


def pyinstaller(icon_path: Path, console: bool = False) -> None:
    import PyInstaller.__main__ as pyi

    sep = ";"  # Windows --add-data separator
    args = [
        str(ROOT / "tools" / "app_entry.py"),
        "--name=LiveTranslator",
        "--onedir",
        "--console" if console else "--windowed",
        "--noconfirm",
        "--clean",
        f"--icon={icon_path}",
        f"--distpath={DIST}",
        f"--workpath={BUILD / 'work'}",
        f"--specpath={BUILD}",
        f"--add-data={PACKAGE / 'data'}{sep}livetranslator/data",
        f"--add-data={PACKAGE / 'theme' / 'fonts'}{sep}livetranslator/theme/fonts",
        *(f"--collect-all={name}" for name in (*COLLECT_ALL, *COLLECT_ALL_EXTRA)),
        *(f"--collect-data={name}" for name in COLLECT_DATA),
        *(f"--hidden-import={name}" for name in HIDDEN),
        *(f"--exclude-module={name}" for name in EXCLUDE),
    ]
    pyi.run(args)


def strip(app: Path) -> list[str]:
    removed: list[str] = []
    for pattern in STRIP_GLOBS:
        for path in sorted(app.glob(pattern), reverse=True):
            if path.is_file():
                path.unlink()
                removed.append(path.relative_to(app).as_posix())
            elif path.is_dir() and not any(path.iterdir()):
                path.rmdir()
    for font in app.rglob("qtawesome/fonts/*"):
        if font.is_file() and not font.name.lower().startswith("phosphor"):
            font.unlink()
            removed.append(font.relative_to(app).as_posix())
    return removed


def add_notices(app: Path) -> None:
    missing = collect_texts(app / "licenses", shipped_packages())
    if missing:
        raise SystemExit(f"no licence text for: {', '.join(missing)}")
    shutil.copy2(ROOT / "THIRD_PARTY_LICENSES.md", app / "THIRD_PARTY_LICENSES.md")


def check(app: Path) -> int:
    findings = scan(app)
    for f in findings:
        print(f"{'FAIL' if f.blocking else 'warn'}  {f.path}: {f.problem}")
    blocking = sum(f.blocking for f in findings)
    print(f"release licence check: {blocking} blocking, {len(findings) - blocking} warnings")
    return 1 if blocking else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the Live Translator app folder")
    parser.add_argument("--check", action="store_true", help="only check an existing build")
    parser.add_argument(
        "--console", action="store_true", help="test build that shows errors in a console"
    )
    args = parser.parse_args(argv)
    if not args.check:
        BUILD.mkdir(exist_ok=True)
        pyinstaller(make_icon(BUILD / "icon" / "app.ico"), console=args.console)
        removed = strip(APP)
        print(f"stripped {len(removed)} files")
        add_notices(APP)
    size = sum(f.stat().st_size for f in APP.rglob("*") if f.is_file()) >> 20
    print(f"{APP}: {size} MB")
    return check(APP)


if __name__ == "__main__":
    sys.exit(main())
