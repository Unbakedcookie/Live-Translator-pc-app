"""Command-line entry point: `python -m livetranslator` (T011, T024).

With no options it starts the app. `--version` and `--paths` are diagnostics.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from livetranslator import APP_DISPLAY_NAME, __version__
from livetranslator.app.paths import app_paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="livetranslator", description=APP_DISPLAY_NAME)
    parser.add_argument("--version", action="version", version=f"{APP_DISPLAY_NAME} {__version__}")
    parser.add_argument(
        "--paths",
        action="store_true",
        help="print the settings, data and log folders, then exit",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="play a scripted conversation into the windows (look-and-feel review)",
    )
    parser.add_argument(
        "--no-speech",
        action="store_true",
        help="don't open the microphone or speakers (windows and settings only)",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="import every part of the app and report what's missing (checks a build)",
    )
    parser.add_argument(
        "--engine-check",
        metavar="CLIP_WAV",
        type=Path,
        help="transcribe and translate a 16 kHz mono WAV with the real engines; the report "
        "also goes to engine-check.txt in the log folder",
    )
    return parser


def self_test() -> int:
    """Import every module of the package (a built app must contain them all), then the
    engines' native libraries. Prints one line per failure; exit code 1 if any."""
    import importlib
    import pkgutil

    import livetranslator

    failures = []
    names = [m.name for m in pkgutil.walk_packages(livetranslator.__path__, "livetranslator.")]
    for name in [*names, "ctranslate2", "onnxruntime", "sherpa_onnx", "rapidocr", "opencc"]:
        try:
            importlib.import_module(name)
        except Exception as exc:  # report every problem, not just the first
            failures.append(f"{name}: {type(exc).__name__}: {exc}")
    try:  # things an import alone doesn't prove (2026-10-19: icons failed only when used)
        import os

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        from livetranslator.services.models import load_catalog
        from livetranslator.theme.icons import icon
        from livetranslator.theme.tokens import DEFAULT_PALETTE_ID, PALETTES
        from livetranslator.ui.about import load_notices

        app = QApplication.instance() or QApplication([])
        if icon("translate", PALETTES[DEFAULT_PALETTE_ID]).isNull():
            failures.append("icons: the translate icon is empty")
        if not load_catalog():
            failures.append("catalogue: no models listed")
        if not load_notices()["packages"]:
            failures.append("third-party notices: missing")
        from livetranslator.services.asr.vad import default_model_path

        if not default_model_path().is_file():  # imports faster_whisper without PyAV
            failures.append("voice detector: silero_vad model missing")
        del app
    except Exception as exc:
        failures.append(f"smoke test: {type(exc).__name__}: {exc}")
    for line in failures:
        print(f"FAIL {line}")
    print(f"self-test: {len(names)} modules, {len(failures)} failures")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.self_test:
        return self_test()
    if args.engine_check is not None:
        from livetranslator.app.engine_check import engine_check

        return engine_check(args.engine_check)
    if args.paths:
        paths = app_paths()
        print(f"settings: {paths.settings_file}")
        print(f"data:     {paths.data_dir}")
        print(f"models:   {paths.default_models_dir} (default)")
        print(f"logs:     {paths.log_dir}")
        return 0

    from livetranslator.app.application import run  # Qt is only loaded when the app starts

    return run(demo=args.demo, speech=not args.no_speech)


if __name__ == "__main__":
    sys.exit(main())
