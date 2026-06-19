from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
import getpass
import hashlib
import tempfile
import time
import re

from setpiece.agent.activation import (
    ActivationIntent,
    ActivationIntentError,
    parse_activation_message,
)
from setpiece.e2e import record_event


DEFAULT_CONNECT_TIMEOUT_MS = 1000
DEFAULT_WRITE_TIMEOUT_MS = 1000
DEFAULT_READ_TIMEOUT_MS = 1000
DEFAULT_REDIRECT_ATTEMPTS = 3
DEFAULT_REDIRECT_RETRY_DELAY_SECONDS = 0.25

ActivationHandler = Callable[[ActivationIntent], None]


@dataclass(frozen=True)
class InstanceActivationResult:
    is_primary: bool
    redirected: bool
    server: "ActivationServer | None" = None
    error: str | None = None


class InstanceOwnerLock:
    def acquire(self) -> bool:
        raise NotImplementedError

    def release(self) -> None:
        raise NotImplementedError


def default_activation_server_name(app_id: str = "setpiece") -> str:
    safe_app_id = _safe_server_part(app_id) or "setpiece"
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
        _allow_foreground_activation()
        socket.connect_to_server(target_name)
        if not socket.wait_for_connected(connect_timeout_ms):
            return False
        data = intent.to_bytes()
        if int(socket.write(data)) <= 0:
            return False
        if hasattr(socket, "flush"):
            socket.flush()
        # Qt's Windows local-socket adapter can return False here even after the
        # primary process receives and handles the message. A positive write
        # after a successful connection is the durable redirect signal.
        if hasattr(socket, "wait_for_bytes_written"):
            socket.wait_for_bytes_written(write_timeout_ms)
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
        owner_lock: InstanceOwnerLock | None = None,
        read_timeout_ms: int = DEFAULT_READ_TIMEOUT_MS,
    ) -> None:
        self.server_name = server_name or default_activation_server_name()
        self.on_activation = on_activation
        if server_adapter is not None and server_factory is not None:
            raise ValueError("provide server_adapter or server_factory, not both")
        self._server = server_adapter or (server_factory() if server_factory else QtLocalServerAdapter())
        self._owner_lock = owner_lock
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
        if self._owner_lock is not None:
            self._owner_lock.release()
            self._owner_lock = None
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
        lock_factory: Callable[[], InstanceOwnerLock] | None = None,
        redirect_attempts: int = DEFAULT_REDIRECT_ATTEMPTS,
        redirect_retry_delay_seconds: float = DEFAULT_REDIRECT_RETRY_DELAY_SECONDS,
    ) -> None:
        self.server_name = server_name or default_activation_server_name()
        self.server_factory = server_factory
        self.socket_factory = socket_factory
        self.server_adapter_type = server_adapter_type or QtLocalServerAdapter
        self.lock_factory = lock_factory
        self.redirect_attempts = max(1, int(redirect_attempts))
        self.redirect_retry_delay_seconds = max(0.0, float(redirect_retry_delay_seconds))

    def become_primary_or_redirect(
        self,
        initial_intent: ActivationIntent,
        on_activation: ActivationHandler,
    ) -> InstanceActivationResult:
        owner_lock = self._new_owner_lock()
        if not owner_lock.acquire():
            record_event(
                "agent.single_instance.owner_busy",
                server_name=self.server_name,
                initial_intent=initial_intent.intent,
            )
            if self._send_to_primary(initial_intent):
                record_event(
                    "agent.single_instance.redirected",
                    server_name=self.server_name,
                    initial_intent=initial_intent.intent,
                )
                return InstanceActivationResult(is_primary=False, redirected=True)
            record_event(
                "agent.single_instance.redirect_failed",
                server_name=self.server_name,
                initial_intent=initial_intent.intent,
            )
            return InstanceActivationResult(
                is_primary=False,
                redirected=False,
                error="Setpiece is already running, but activation could not reach it.",
            )

        server = self._new_server(on_activation, owner_lock=owner_lock)
        if server.start():
            record_event(
                "agent.single_instance.primary",
                server_name=self.server_name,
                initial_intent=initial_intent.intent,
            )
            return InstanceActivationResult(is_primary=True, redirected=False, server=server)

        owner_lock.release()
        record_event(
            "agent.single_instance.listen_failed",
            server_name=self.server_name,
            initial_intent=initial_intent.intent,
            error=server.last_error or "",
        )
        if self._send_to_primary(initial_intent):
            record_event(
                "agent.single_instance.redirected",
                server_name=self.server_name,
                initial_intent=initial_intent.intent,
            )
            return InstanceActivationResult(is_primary=False, redirected=True)

        remove_activation_server(
            server_name=self.server_name,
            server_adapter_type=self.server_adapter_type,
        )
        retry_lock = self._new_owner_lock()
        if not retry_lock.acquire():
            record_event(
                "agent.single_instance.owner_busy_after_cleanup",
                server_name=self.server_name,
                initial_intent=initial_intent.intent,
            )
            return InstanceActivationResult(
                is_primary=False,
                redirected=False,
                error="Setpiece is already running, but activation could not reach it.",
            )

        retry_server = self._new_server(on_activation, owner_lock=retry_lock)
        if retry_server.start():
            record_event(
                "agent.single_instance.primary_after_stale_cleanup",
                server_name=self.server_name,
                initial_intent=initial_intent.intent,
            )
            return InstanceActivationResult(is_primary=True, redirected=False, server=retry_server)

        retry_lock.release()
        record_event(
            "agent.single_instance.failed",
            server_name=self.server_name,
            initial_intent=initial_intent.intent,
            error=retry_server.last_error or server.last_error or "single-instance activation failed",
        )
        return InstanceActivationResult(
            is_primary=False,
            redirected=False,
            error=retry_server.last_error or server.last_error or "single-instance activation failed",
        )

    def _new_server(
        self,
        on_activation: ActivationHandler,
        *,
        owner_lock: InstanceOwnerLock | None = None,
    ) -> ActivationServer:
        return ActivationServer(
            on_activation,
            server_name=self.server_name,
            server_factory=self.server_factory,
            owner_lock=owner_lock,
        )

    def _new_owner_lock(self) -> InstanceOwnerLock:
        if self.lock_factory is not None:
            return self.lock_factory()
        return FileInstanceOwnerLock(self.server_name)

    def _send_to_primary(self, initial_intent: ActivationIntent) -> bool:
        for attempt in range(self.redirect_attempts):
            if send_activation_intent(
                initial_intent,
                server_name=self.server_name,
                socket_factory=self.socket_factory,
            ):
                return True
            if attempt + 1 < self.redirect_attempts and self.redirect_retry_delay_seconds:
                time.sleep(self.redirect_retry_delay_seconds)
        return False


class FileInstanceOwnerLock(InstanceOwnerLock):
    def __init__(self, server_name: str, *, lock_dir: Path | None = None) -> None:
        safe_name = _safe_server_part(server_name) or "setpiece"
        self.path = (lock_dir or Path(tempfile.gettempdir()) / "Setpiece") / f"{safe_name}.lock"
        self._file: Any | None = None
        self._locked = False

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+b")
        try:
            handle.seek(0)
            if handle.read(1) == b"":
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            if not _try_lock_file(handle):
                handle.close()
                return False
        except OSError:
            handle.close()
            return False
        self._file = handle
        self._locked = True
        return True

    def release(self) -> None:
        handle = self._file
        if handle is None:
            return
        try:
            if self._locked:
                _unlock_file(handle)
        finally:
            self._locked = False
            self._file = None
            handle.close()


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
        from setpiece.errors import DependencyMissingError

        raise DependencyMissingError("Single-instance activation requires PySide6") from exc
    return QLocalServer, QLocalSocket


def _try_lock_file(handle: Any) -> bool:
    if hasattr(handle, "fileno"):
        handle.seek(0)
    if _is_windows():
        import msvcrt

        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True

    import fcntl

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def _unlock_file(handle: Any) -> None:
    handle.seek(0)
    if _is_windows():
        import msvcrt

        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        return

    import fcntl

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass


def _is_windows() -> bool:
    import os

    return os.name == "nt"


def _allow_foreground_activation() -> None:
    if not _is_windows():
        return
    try:
        import ctypes
        from ctypes import wintypes

        ctypes.windll.user32.AllowSetForegroundWindow.argtypes = [wintypes.DWORD]
        ctypes.windll.user32.AllowSetForegroundWindow.restype = wintypes.BOOL
        ctypes.windll.user32.AllowSetForegroundWindow(0xFFFFFFFF)
    except Exception:
        return


def _resolve_qt_member(root: Any, path: tuple[str, ...]) -> Any:
    value = root
    for part in path:
        value = getattr(value, part, None)
        if value is None:
            return None
    return value


def _safe_server_part(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._-")[:64]
