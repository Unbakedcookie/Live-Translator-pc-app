"""Settings → About (T113; spec §11): version, privacy, and every licence the app ships with.

Reads `data/third_party.json`, written by `python -m tools.third_party` (a test keeps it in
step with the installed packages). The Qt / PySide6 LGPL notice and source offer come first.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import QPushButton, QWidget

from livetranslator import APP_DISPLAY_NAME, __version__
from livetranslator.ui.settings.context import SettingsContext
from livetranslator.ui.settings.rows import SettingsPage

DATA = Path(__file__).resolve().parents[1] / "data" / "third_party.json"
PROJECT_URL = "https://github.com/Unbakedcookie/Live-Translator-pc-app"
# D-011: a plain notice, not legal advice
OTHERS_NOTE = (
    "It writes down what other people say. Some places require everyone's agreement before a "
    "conversation is recorded or transcribed, so tell the people you talk to and follow the "
    "rules where you live. Nothing is saved unless you export it."
)


def licenses_dir() -> Path:
    """The licence texts: next to the app when installed, the repo's folder when run from
    source."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "licenses"
    return Path(__file__).resolve().parents[2] / "licenses"


def load_notices(path: Path = DATA) -> dict[str, Any]:
    try:
        return dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return {"packages": [], "models": [], "fonts": [], "qt_notice": ""}


class AboutPage(SettingsPage):
    title_text = "About"
    icon_name = "info"

    def __init__(self, ctx: SettingsContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        notices = load_notices()
        self.intro(
            f"{APP_DISPLAY_NAME} {__version__}. Everything runs on this PC: nothing anyone "
            "says is sent over the internet, and logs never contain it."
        )
        app = self.section()
        texts = QPushButton("Open folder")
        texts.clicked.connect(lambda: ctx.open_folder(licenses_dir()))
        app.row("Licence texts", "The full text of every licence below.", texts)
        app.row("Project page", PROJECT_URL)
        app.row(
            f"{APP_DISPLAY_NAME} licence",
            "MIT License: free to use, change and share (LICENSE.txt next to the app).",
        )
        app.row("Listening to others", OTHERS_NOTE)
        qt = self.section("Qt and Qt for Python")
        qt.row("GNU Lesser General Public License v3", str(notices.get("qt_notice", "")))
        models = self.section("Models it downloads")
        for model in notices.get("models", []):
            models.row(str(model["title"]), f"{model['license']} · {model['credit']}")
        fonts = self.section("Fonts and icons")
        for font in notices.get("fonts", []):
            fonts.row(str(font["name"]), f"{font['license']} · {font['url']}")
        packages = self.section("Software it includes")
        self.package_count = len(notices.get("packages", []))
        for package in notices.get("packages", []):
            packages.row(
                f"{package['name']} {package['version']}",
                f"{package['license']}" + (f" · {package['url']}" if package["url"] else ""),
            )
        packages.row("Python", "Python Software Foundation License")
        self.finish()
