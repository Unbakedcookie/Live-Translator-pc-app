"""Command-line entry point: `python -m livetranslator` (T011, T024).

With no options it starts the app. `--version` and `--paths` are diagnostics.
"""

from __future__ import annotations

import argparse
import sys

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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
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
