"""One running copy (user report 2026-10-18: no way to bring the app back once its windows
were gone). Starting the app again while it runs asks the running copy to show its windows,
then exits: two copies would fight over the shortcuts, the microphone and the GPU.

A per-user local socket (a named pipe on Windows) carries the one-word request.
"""

from __future__ import annotations

import getpass
import hashlib
import re
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject
from PySide6.QtNetwork import QLocalServer, QLocalSocket

SHOW = b"show"
CONNECT_TIMEOUT_MS = 500


def server_name(app_name: str, profile: Path | None = None) -> str:
    """Per user, and per settings folder: a test profile (LIVETRANSLATOR_HOME) runs next to
    the everyday app instead of handing over to it."""
    user = re.sub(r"[^A-Za-z0-9_-]", "_", getpass.getuser())
    if profile is None:
        return f"{app_name}-{user}"
    digest = hashlib.sha256(str(profile.resolve()).casefold().encode()).hexdigest()[:12]
    return f"{app_name}-{user}-{digest}"


def ask_running_copy_to_show(name: str) -> bool:
    """True if another copy is running (and was asked to show its windows)."""
    socket = QLocalSocket()
    socket.connectToServer(name)
    if not socket.waitForConnected(CONNECT_TIMEOUT_MS):
        return False
    socket.write(SHOW)
    socket.flush()
    socket.waitForBytesWritten(CONNECT_TIMEOUT_MS)
    socket.disconnectFromServer()
    return True


class SingleInstance(QObject):
    """Listens for later copies; `on_show` runs when one starts."""

    def __init__(self, name: str, on_show: Callable[[], object], parent: QObject | None = None):
        super().__init__(parent)
        self._on_show = on_show
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        if not self.server.listen(name):
            QLocalServer.removeServer(name)  # left over from a crashed copy
            self.server.listen(name)
        self.server.newConnection.connect(self._on_connection)

    @property
    def listening(self) -> bool:
        return self.server.isListening()

    def _on_connection(self) -> None:
        socket = self.server.nextPendingConnection()
        if socket is None:
            return
        socket.readyRead.connect(lambda: self._on_ready(socket))
        socket.disconnected.connect(socket.deleteLater)
        if socket.bytesAvailable():  # the request can arrive before readyRead is connected
            self._on_ready(socket)

    def _on_ready(self, socket: QLocalSocket) -> None:
        if bytes(socket.readAll().data()).strip() == SHOW:
            self._on_show()
