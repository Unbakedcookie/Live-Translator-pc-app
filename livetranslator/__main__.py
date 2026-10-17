"""Command-line entry point: `python -m livetranslator` (T011).

The windowed app is wired in here as it is built (M02 floating window, M07 tray). Until then
the entry point offers the diagnostic options below.
"""

from __future__ import annotations

import argparse
import sys

from loguru import logger

from livetranslator import APP_DISPLAY_NAME, __version__
from livetranslator.app.log import setup_logging
from livetranslator.app.paths import app_paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="livetranslator", description=APP_DISPLAY_NAME)
    parser.add_argument("--version", action="version", version=f"{APP_DISPLAY_NAME} {__version__}")
    parser.add_argument(
        "--paths",
        action="store_true",
        help="print the settings, data and log folders, then exit",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    paths = app_paths()

    if args.paths:
        print(f"settings: {paths.settings_file}")
        print(f"data:     {paths.data_dir}")
        print(f"models:   {paths.default_models_dir} (default)")
        print(f"logs:     {paths.log_dir}")
        return 0

    paths.ensure()
    setup_logging(paths.log_dir)
    logger.info("{} {} started", APP_DISPLAY_NAME, __version__)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
