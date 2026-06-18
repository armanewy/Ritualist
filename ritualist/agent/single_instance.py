from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
import getpass
import hashlib
import re

from ritualist.agent.activation import (
    ActivationIntent,
    ActivationIntentError,
    parse_activation_message,
)


DEFAULT_CONNECT_TIMEOUT_MS = 1000
DEFAULT_WRITE_TIMEOUT_MS = 1000
DEFAULT_READ_TIMEOUT_MS = 1000

ActivationHandler = Callable[[ActivationIntent], None]


@dataclass(frozen=True)
class InstanceActivationResult:
    is_primary: bool
    redirected: bool
    server: "ActivationServer | None" = None
    error: str | None = None


def default_activation_server_name(app_id: str = "ritualist") -> str:
    safe_app_id = _safe_server_part(app_id) or "ritualist"
    user = _safe_server_part(getpass.getuser()) or "user"
    home = str(Path.home()).casefold()
    digest = hashlib.sha256(f"{safe_app_id}\0{user}\0{home}".encode("utf-8")).hexdigest()[:16]
    return f"{safe_app_id}-{user}-{digest}-activation-v1"


def send_activation_intent(
    intent: ActivationIntent,
    *,
    server_name: str | None = None,
    socket_factory: Callable[[], Any] | None = None,
    connect_timeout_ms: int = DEFAULT_CONNECT_TIMEOUT_MS,
    write_timeout_ms: int = DEFAULT_WRITE_TIMEOUT_MS,
) -> bool:
    socket = socket_factory() if socket_factory is not None else QtLocalSocketAdapter()
    target_name = server_name or default_activation_server_name()
    try:
        socket.connect_to_server(target_name)
        if not socket.wait_for_connected(connect_timeout_ms):
            return False
        socket.write(intent.to_bytes())
        if hasattr(socket, "flush"):
            socket.flush()
        if not socket.wait_for_bytes_written(write_timeout_ms):
            return False
        return True
    finally:
        if hasattr(socket, "disconnect_from_server"):
            socket.disconnect_from_server()


def remove_activation_server(
    *,
    server_name: str | None = None,
    server_adapter_type: Any | None = None,
) -> bool:
    adapter_type = server_adapter_type or QtLocalServerAdapter
    return bool(adapter_type.remove_server(server_name or default_activation_server_name()))


class ActivationServer:
    def __init__(
        self,
        on_activation: ActivationHandler,
        *,
        server_name: str | None = None,
        server_adapter: Any | None = None,
        server_factory: Callable[[], Any] | None = None,
        read_timeout_ms: int = DEFAULT_READ_TIMEOUT_MS,
    ) -> None:
        self.server_name = server_name or default_activation_server_name()
        self.on_activation = on_activation
        if server_adapter is not None and server_factory is not None:
            raise ValueError("provide server_adapter or server_factory, not both")
        self._server = server_adapter or (server_factory() if server_factory else QtLocalServerAdapter())
        self._read_timeout_ms = read_timeout_ms
        self._started = False
        self.last_error: str | None = None

    def start(self) -> bool:
        self._server.set_new_connection_handler(self.accept_pending_connections)
        if self._server.listen(self.server_name):
            self._started = True
            self.last_error = None
            return True
        self.last_error = self._server.error_string()
        return False

    def close(self) -> None:
        self._server.close()
        self._started = False

    def accept_pending_connections(self) -> None:
        while self._server.has_pending_connections():
            socket = self._server.next_pending_connection()
            if socket is not None:
                self.accept_socket(socket)

    def accept_socket(self, socket: Any) -> bool:
        try:
            if _bytes_available(socket) <= 0 and hasattr(socket, "wait_for_ready_read"):
                socket.wait_for_ready_read(self._read_timeout_ms)
            raw = _read_socket_bytes(socket)
            intent = parse_activation_message(raw)
        except (ActivationIntentError, OSError, TypeError, ValueError):
            return False
        finally:
            if hasattr(socket, "disconnect_from_server"):
                socket.disconnect_from_server()
        self.on_activation(intent)
        return True


class SingleInstanceCoordinator:
    def __init__(
        self,
        *,
        server_name: str | None = None,
        server_factory: Callable[[], Any] | None = None,
        socket_factory: Callable[[], Any] | None = None,
        server_adapter_type: Any | None = None,
    ) -> None:
        self.server_name = server_name or default_activation_server_name()
        self.server_factory = server_factory
        self.socket_factory = socket_factory
        self.server_adapter_type = server_adapter_type or QtLocalServerAdapter

    def become_primary_or_redirect(
        self,
        initial_intent: ActivationIntent,
        on_activation: ActivationHandler,
    ) -> InstanceActivationResult:
        server = self._new_server(on_activation)
        if server.start():
            return InstanceActivationResult(is_primary=True, redirected=False, server=server)

        if send_activation_intent(
            initial_intent,
            server_name=self.server_name,
            socket_factory=self.socket_factory,
        ):
            return InstanceActivationResult(is_primary=False, redirected=True)

        remove_activation_server(
            server_name=self.server_name,
            server_adapter_type=self.server_adapter_type,
        )
        retry_server = self._new_server(on_activation)
        if retry_server.start():
            return InstanceActivationResult(is_primary=True, redirected=False, server=retry_server)

        return InstanceActivationResult(
            is_primary=False,
            redirected=False,
            error=retry_server.last_error or server.last_error or "single-instance activation failed",
        )

    def _new_server(self, on_activation: ActivationHandler) -> ActivationServer:
        return ActivationServer(
            on_activation,
            server_name=self.server_name,
            server_factory=self.server_factory,
        )


class QtLocalServerAdapter:
    def __init__(self) -> None:
        QLocalServer, _QLocalSocket = _load_qt_network()
        self._server = QLocalServer()
        self._set_user_access_option(QLocalServer)

    @classmethod
    def remove_server(cls, server_name: str) -> bool:
        QLocalServer, _QLocalSocket = _load_qt_network()
        return bool(QLocalServer.removeServer(server_name))

    def set_new_connection_handler(self, handler: Callable[[], None]) -> None:
        self._server.newConnection.connect(handler)

    def listen(self, server_name: str) -> bool:
        return bool(self._server.listen(server_name))

    def has_pending_connections(self) -> bool:
        return bool(self._server.hasPendingConnections())

    def next_pending_connection(self) -> Any:
        socket = self._server.nextPendingConnection()
        if socket is None:
            return None
        return QtLocalSocketConnection(socket)

    def error_string(self) -> str:
        return str(self._server.errorString())

    def close(self) -> None:
        self._server.close()

    def _set_user_access_option(self, qlocal_server: Any) -> None:
        option = _resolve_qt_member(qlocal_server, ("SocketOption", "UserAccessOption"))
        if option is None:
            option = getattr(qlocal_server, "UserAccessOption", None)
        if option is not None and hasattr(self._server, "setSocketOptions"):
            self._server.setSocketOptions(option)


class QtLocalSocketAdapter:
    def __init__(self) -> None:
        _QLocalServer, QLocalSocket = _load_qt_network()
        self._socket = QLocalSocket()

    def connect_to_server(self, server_name: str) -> None:
        self._socket.connectToServer(server_name)

    def wait_for_connected(self, timeout_ms: int) -> bool:
        return bool(self._socket.waitForConnected(timeout_ms))

    def write(self, data: bytes) -> int:
        return int(self._socket.write(data))

    def flush(self) -> bool:
        return bool(self._socket.flush())

    def wait_for_bytes_written(self, timeout_ms: int) -> bool:
        return bool(self._socket.waitForBytesWritten(timeout_ms))

    def disconnect_from_server(self) -> None:
        self._socket.disconnectFromServer()


class QtLocalSocketConnection:
    def __init__(self, socket: Any) -> None:
        self._socket = socket

    def bytes_available(self) -> int:
        return int(self._socket.bytesAvailable())

    def wait_for_ready_read(self, timeout_ms: int) -> bool:
        return bool(self._socket.waitForReadyRead(timeout_ms))

    def read_all(self) -> bytes:
        return bytes(self._socket.readAll())

    def disconnect_from_server(self) -> None:
        self._socket.disconnectFromServer()


def _read_socket_bytes(socket: Any) -> bytes:
    if hasattr(socket, "read_all"):
        return bytes(socket.read_all())
    if hasattr(socket, "readAll"):
        return bytes(socket.readAll())
    raise TypeError("socket does not support read_all")


def _bytes_available(socket: Any) -> int:
    if hasattr(socket, "bytes_available"):
        return int(socket.bytes_available())
    if hasattr(socket, "bytesAvailable"):
        return int(socket.bytesAvailable())
    return 0


def _load_qt_network() -> tuple[Any, Any]:
    try:
        from PySide6.QtNetwork import QLocalServer, QLocalSocket
    except ImportError as exc:
        from ritualist.errors import DependencyMissingError

        raise DependencyMissingError("Single-instance activation requires PySide6") from exc
    return QLocalServer, QLocalSocket


def _resolve_qt_member(root: Any, path: tuple[str, ...]) -> Any:
    value = root
    for part in path:
        value = getattr(value, part, None)
        if value is None:
            return None
    return value


def _safe_server_part(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._-")[:64]
