"""Single instance: a second launch asks the running one to show its window."""

import os
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from rpc_buddy import APP_ID


def _socket_path() -> str:
    runtime = Path(os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}")
    # Inside the Flatpak, this per-app directory is shared by all instances.
    app_dir = runtime / "app" / APP_ID
    base = app_dir if app_dir.is_dir() else runtime
    return str(base / "rpc-buddy.sock")


def notify_running_instance() -> bool:
    """True if another instance is running (it was asked to show itself)."""
    socket = QLocalSocket()
    socket.connectToServer(_socket_path())
    if not socket.waitForConnected(500):
        return False
    socket.write(b"show\n")
    socket.waitForBytesWritten(500)
    socket.disconnectFromServer()
    return True


class InstanceServer(QObject):
    show_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        path = _socket_path()
        QLocalServer.removeServer(path)  # stale socket from a crashed instance
        self._server = QLocalServer(self)
        self._server.listen(path)
        self._server.newConnection.connect(self._on_connection)

    def _on_connection(self) -> None:
        while (conn := self._server.nextPendingConnection()) is not None:
            conn.readyRead.connect(lambda c=conn: self._read(c))
            conn.disconnected.connect(conn.deleteLater)

    def _read(self, conn: QLocalSocket) -> None:
        if b"show" in bytes(conn.readAll()):
            self.show_requested.emit()
