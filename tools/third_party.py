"""Third-party notices (T113; spec §11): what the app ships and under which licences.

    python -m tools.third_party            # write THIRD_PARTY_LICENSES.md + the About data
    python -m tools.third_party --check    # fail if either is out of date (CI, tests)

Lists every runtime package the app ships (the licence gate's own dependency closure, minus
packages the build strips), the downloadable models (the catalogue), the bundled fonts and
icons, and the Qt / PySide6 LGPL notice with its source offer. `collect_texts(dest)` copies
every licence text into a build's `licenses/` folder: the package's own file when its wheel
has one, else the text kept in `licenses/packages/` (fetched from the project's repository
at the matching version tag, 2026-10-19).
"""

from __future__ import annotations

import argparse
import importlib.metadata as md
import json
import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from packaging.utils import canonicalize_name

from livetranslator import APP_DISPLAY_NAME
from livetranslator.services.models import load_catalog
from tools.check_licenses import (
    ROOT,
    LicenseRecord,
    evaluate,
    fetch_records,
    installed_requires,
    load_overrides,
    load_policy,
    parse_requirements,
    runtime_closure,
)

NOTICES_MD = ROOT / "THIRD_PARTY_LICENSES.md"
ABOUT_JSON = ROOT / "livetranslator" / "data" / "third_party.json"
TEXTS = ROOT / "licenses"
PROJECT_URL = "https://github.com/Unbakedcookie/Live-Translator-pc-app"
# Wheels without a licence file: the text kept in licenses/packages/ (by package or prefix).
MANUAL_TEXTS = {
    "ctranslate2": "ctranslate2.txt",
    "flatbuffers": "flatbuffers.txt",
    "loguru": "loguru.txt",
    "nvidia-ml-py": "nvidia-ml-py.txt",
    "tokenizers": "tokenizers.txt",
}
MANUAL_PREFIXES = {"winrt-": "winrt.txt"}
SAME_PROJECT = {"sherpa-onnx-core": "sherpa-onnx"}  # ships the sibling package's licence
FONTS = (
    ("Inter", "SIL Open Font License 1.1", "OFL-Inter.txt", "https://rsms.me/inter/"),
    ("Noto Sans", "SIL Open Font License 1.1", "OFL-NotoSans.txt", "https://notofonts.github.io/"),
    ("Phosphor icons (via QtAwesome)", "MIT", "", "https://phosphoricons.com/"),
)
QT_NOTICE = (
    f"{APP_DISPLAY_NAME} uses Qt for Python (PySide6, Shiboken6) and the Qt libraries under "
    "the GNU Lesser General Public License version 3 (licenses/LGPL-3.0.txt, which adds to "
    "licenses/GPL-3.0.txt). They are included unmodified as separate files in the app folder, "
    "and you may replace them with your own compatible build. Their source code is available "
    "at https://code.qt.io and https://download.qt.io/official_releases/QtForPython/; on "
    f"request we will send the exact source of the versions shipped ({PROJECT_URL}/issues)."
)


@dataclass(frozen=True)
class Package:
    name: str
    version: str
    license: str
    url: str


@dataclass(frozen=True)
class Model:
    title: str
    license: str
    credit: str


# ---------------------------------------------------------------- gathering


def shipped_packages() -> list[Package]:
    policy = load_policy(ROOT / "tools" / "license_policy.toml")
    overrides = load_overrides(ROOT / "tools" / "license_overrides.toml")
    roots = parse_requirements((ROOT / "requirements.txt").read_text(encoding="utf-8"))
    closure, missing = runtime_closure(roots, installed_requires)
    if missing:
        raise SystemExit(f"not installed: {', '.join(sorted(missing))}")
    names = sorted(closure - set(policy.excluded))
    records = fetch_records(names)
    packages: list[Package] = []
    for name in names:
        dist = md.distribution(name)
        verdict = evaluate(records.get(name, LicenseRecord(name)), policy, overrides.get(name))
        packages.append(Package(dist.metadata["Name"], dist.version, verdict.license, _url(dist)))
    return packages


def _url(dist: md.Distribution) -> str:
    meta = dist.metadata
    for entry in meta.get_all("Project-URL") or []:
        label, _, url = entry.partition(",")
        if label.strip().lower() in ("homepage", "home", "source", "repository", "source code"):
            return url.strip()
    return str(meta.get("Home-page") or "")


def models() -> list[Model]:
    return [
        Model(entry.title, entry.license, entry.attribution)
        for entry in load_catalog().values()
        if not entry.dest.startswith("opus-mt/")
    ] + _opus_summary()


def _opus_summary() -> list[Model]:
    pairs = [e for e in load_catalog().values() if e.dest.startswith("opus-mt/")]
    if not pairs:
        return [
            Model(
                "Translation models (OPUS-MT)",
                "CC-BY-4.0 / Apache-2.0",
                "Helsinki-NLP / OPUS-MT (University of Helsinki), converted to CTranslate2",
            )
        ]
    licences = " / ".join(sorted({e.license for e in pairs}))
    return [
        Model(
            f"Translation models (OPUS-MT, {len(pairs)} language directions)",
            licences,
            "Helsinki-NLP / OPUS-MT (University of Helsinki), converted to CTranslate2; each "
            "download keeps its LICENCE.txt",
        )
    ]


# ---------------------------------------------------------------- licence texts


def package_texts(name: str) -> list[tuple[str, Path]]:
    """(file name in the build, source) of `name`'s licence texts."""
    dist = md.distribution(SAME_PROJECT.get(canonicalize_name(name), name))
    found = [
        (Path(str(f)).name, Path(str(dist.locate_file(f))))
        for f in dist.files or []
        if any(key in f.name.upper() for key in ("LICEN", "COPYING", "NOTICE"))
    ]
    if found:
        return found
    key = canonicalize_name(name)
    manual = MANUAL_TEXTS.get(key) or next(
        (text for prefix, text in MANUAL_PREFIXES.items() if key.startswith(prefix)), None
    )
    if manual is None:
        return []
    return [(manual, TEXTS / "packages" / manual)]


def collect_texts(dest: Path, packages: list[Package]) -> list[str]:
    """Copy every licence text into `dest` (a build's licences folder). Returns the packages
    that have none (the release check fails on them)."""
    dest.mkdir(parents=True, exist_ok=True)
    for text in TEXTS.glob("*.txt"):
        shutil.copy2(text, dest / text.name)
    missing: list[str] = []
    for package in packages:
        texts = package_texts(package.name)
        if not texts:
            missing.append(package.name)
            continue
        folder = dest / "packages" / canonicalize_name(package.name)
        folder.mkdir(parents=True, exist_ok=True)
        for file_name, source in texts:
            shutil.copy2(source, folder / file_name)
    return missing


# ---------------------------------------------------------------- outputs


def about_data(packages: list[Package]) -> dict[str, object]:
    return {
        "packages": [asdict(p) for p in packages],
        "models": [asdict(m) for m in models()],
        "fonts": [
            {"name": name, "license": licence, "url": url} for name, licence, _f, url in FONTS
        ],
        "qt_notice": QT_NOTICE,
    }


def markdown(packages: list[Package], model_rows: list[Model]) -> str:
    lines = [
        "# Third-party licences",
        "",
        "Generated by `python -m tools.third_party`; do not edit by hand. Full licence texts are",
        "in the `licenses/` folder of the installed app.",
        "",
        "## Qt and Qt for Python (LGPL-3.0)",
        "",
        QT_NOTICE,
        "",
        "## Python packages shipped with the app",
        "",
        "| Package | Version | Licence | Project |",
        "|---|---|---|---|",
        *(f"| {p.name} | {p.version} | {p.license} | {p.url or '—'} |" for p in packages),
        "",
        "Python itself: Python Software Foundation License (`licenses/Python.txt`).",
        "",
        "## Models the app downloads",
        "",
        "| Model | Licence | Credit |",
        "|---|---|---|",
        *(f"| {m.title} | {m.license} | {m.credit} |" for m in model_rows),
        "",
        "## Fonts and icons",
        "",
        "| Name | Licence | Project |",
        "|---|---|---|",
        *(f"| {name} | {licence} | {url} |" for name, licence, _file, url in FONTS),
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write the third-party licence notices")
    parser.add_argument("--check", action="store_true", help="fail if the files are stale")
    args = parser.parse_args(argv)
    packages = shipped_packages()
    without = [p.name for p in packages if not package_texts(p.name)]
    if without:
        print(f"no licence text for: {', '.join(without)}", file=sys.stderr)
        return 1
    data = about_data(packages)
    about = json.dumps(data, indent=1, ensure_ascii=False) + "\n"
    notes = markdown(packages, models())
    if args.check:
        stale = [
            path.name
            for path, text in ((ABOUT_JSON, about), (NOTICES_MD, notes))
            if not path.exists() or path.read_text(encoding="utf-8") != text
        ]
        if stale:
            print(f"out of date: {', '.join(stale)} (run python -m tools.third_party)")
            return 1
        print("third-party notices are up to date")
        return 0
    ABOUT_JSON.write_text(about, encoding="utf-8")
    NOTICES_MD.write_text(notes, encoding="utf-8")
    print(f"wrote {NOTICES_MD.name} and {ABOUT_JSON.name}: {len(packages)} packages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
