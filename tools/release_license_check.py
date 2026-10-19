"""Release licence check for a built app folder (T113; spec §11).

    python -m tools.release_license_check dist/LiveTranslator

Fails (exit 1) when the build contains something that would make the app not shareable, or
lacks a notice we owe. Each rule cites the DATA_TRACKER item it comes from:

- GPL-only Qt module DLLs (D-021: PySide6-Essentials only, LGPL).
- PyAV / its GPL x264/x265 libraries (D-027: `av` is excluded).
- opencv's FFmpeg video plugin (D-034: stripped; images don't need it).
- Unused QtAwesome icon fonts (only Phosphor is used; the others carry their own licences).
- Missing licence texts: LGPL-3.0 + GPL-3.0 (Qt), Apache-2.0, OFL (Inter / Noto Sans),
  and THIRD_PARTY_LICENSES.md.

Warnings (exit 0) flag things still under review, e.g. NVIDIA runtime DLLs (D-026).
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

GPL_ONLY_QT = re.compile(
    r"^Qt6(Charts|DataVisualization|Graphs|VirtualKeyboard|Quick3D\w*|QuickTimeline|"
    r"Lottie\w*|Coap|Mqtt|OpcUa)\.dll$",
    re.IGNORECASE,
)
PYAV = re.compile(r"^(libx264|libx265|av\.libs|avcodec|avformat)", re.IGNORECASE)
OPENCV_FFMPEG = re.compile(r"^opencv_videoio_ffmpeg.*\.dll$", re.IGNORECASE)
NVIDIA = re.compile(r"^(cublas|cudnn|cudart|nvrtc)\w*\.dll$", re.IGNORECASE)
ALLOWED_ICON_FONT = re.compile(r"^phosphor", re.IGNORECASE)
REQUIRED_NOTICES = {
    "LGPL-3.0.txt": "Qt / PySide6 (D-021)",
    "GPL-3.0.txt": "Qt / PySide6 is offered under LGPLv3, which refers to the GPLv3 text",
    "Apache-2.0.txt": "Apache-licensed components and models",
    "OFL-Inter.txt": "the Inter font",
    "OFL-NotoSans.txt": "the Noto Sans font",
}
THIRD_PARTY = "THIRD_PARTY_LICENSES.md"
LICENSES_DIR = "licenses"


@dataclass(frozen=True)
class Finding:
    path: str
    problem: str
    blocking: bool = True


def scan(build: Path) -> list[Finding]:
    findings: list[Finding] = []
    for path in sorted(build.rglob("*")):
        rel = path.relative_to(build).as_posix()
        name = path.name
        if path.is_file() and GPL_ONLY_QT.match(name):
            findings.append(Finding(rel, "GPL-only Qt module (D-021): remove it from the build"))
        if PYAV.match(name) or (path.is_dir() and name == "av"):
            findings.append(Finding(rel, "PyAV / GPL x264-x265 must not ship (D-027)"))
        if path.is_file() and OPENCV_FFMPEG.match(name):
            findings.append(Finding(rel, "opencv FFmpeg video plugin must be stripped (D-034)"))
        if path.is_file() and NVIDIA.match(name):
            findings.append(
                Finding(rel, "NVIDIA runtime DLL: redistribution still under review (D-026)", False)
            )
        if (
            path.is_file()
            and path.suffix.lower() == ".ttf"
            and path.parent.name == "fonts"
            and path.parent.parent.name == "qtawesome"
            and not ALLOWED_ICON_FONT.match(name)
        ):
            findings.append(Finding(rel, "unused QtAwesome icon font: remove it from the build"))
    licenses = build / LICENSES_DIR
    for notice, why in REQUIRED_NOTICES.items():
        if not (licenses / notice).is_file():
            findings.append(Finding(f"{LICENSES_DIR}/{notice}", f"missing licence text for {why}"))
    if not (build / THIRD_PARTY).is_file():
        findings.append(Finding(THIRD_PARTY, "missing third-party licence list"))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("build", type=Path, help="the built app folder (onedir)")
    args = parser.parse_args(argv)
    if not args.build.is_dir():
        print(f"not a folder: {args.build}", file=sys.stderr)
        return 2
    findings = scan(args.build)
    for f in findings:
        print(f"{'FAIL' if f.blocking else 'warn'}  {f.path}: {f.problem}")
    blocking = [f for f in findings if f.blocking]
    print(
        f"release licence check: {len(blocking)} blocking, {len(findings) - len(blocking)} warnings"
    )
    return 1 if blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())
