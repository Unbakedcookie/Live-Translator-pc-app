"""Windows session end (log off / shut down), for windows that only hide when closed."""

from __future__ import annotations

from PySide6.QtGui import QGuiApplication


def session_ending() -> bool:
    """True while Windows is ending the session: a close must then be accepted, or the app
    would show up as "preventing shutdown"."""
    app = QGuiApplication.instance()
    return isinstance(app, QGuiApplication) and app.isSavingSession()
