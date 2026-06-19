from __future__ import annotations

import subprocess
import sys

from setpiece.agent.activation import ActivationIntent, parse_activation_message
from setpiece.agent.single_instance import (
    ActivationServer,
    SingleInstanceCoordinator,
    default_activation_server_name,
    send_activation_intent,
)


class FakeAcceptedSocket:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.disconnected = False

    def bytes_available(self) -> int:
        return len(self.data)

    def read_all(self) -> bytes:
        return self.data

    def disconnect_from_server(self) -> None:
        self.disconnected = True


class FakeServerAdapter:
    removed: list[str] = []

    def __init__(
        self,
        *,
        listen_result: bool = True,
        sockets: list[FakeAcceptedSocket] | None = None,
        error: str = "in use",
    ) -> None:
        self.listen_result = listen_result
        self.sockets = list(sockets or [])
        self.error = error
        self.handler = None
        self.listened_name = None
        self.closed = False

    @classmethod
    def remove_server(cls, server_name: str) -> bool:
        cls.removed.append(server_name)
        return True

    def set_new_connection_handler(self, handler) -> None:
        self.handler = handler

    def listen(self, server_name: str) -> bool:
        self.listened_name = server_name
        return self.listen_result

    def has_pending_connections(self) -> bool:
        return bool(self.sockets)

    def next_pending_connection(self):
        return self.sockets.pop(0)

    def error_string(self) -> str:
        return self.error

    def close(self) -> None:
        self.closed = True

    def trigger(self) -> None:
        assert self.handler is not None
        self.handler()


class FakeOwnerLock:
    def __init__(self, *, acquired: bool = True) -> None:
        self.acquired = acquired
        self.acquire_calls = 0
        self.released = False

    def acquire(self) -> bool:
        self.acquire_calls += 1
        return self.acquired

    def release(self) -> None:
        self.released = True


class FakeClientSocket:
    def __init__(
        self,
        *,
        connected: bool = True,
        written: bool = True,
        write_result: int | None = None,
    ) -> None:
        self.connected = connected
        self.written = written
        self.write_result = write_result
        self.server_name = None
        self.data = b""
        self.disconnected = False

    def connect_to_server(self, server_name: str) -> None:
        self.server_name = server_name

    def wait_for_connected(self, _timeout_ms: int) -> bool:
        return self.connected

    def write(self, data: bytes) -> int:
        self.data += data
        if self.write_result is not None:
            return self.write_result
        return len(data)

    def flush(self) -> bool:
        return True

    def wait_for_bytes_written(self, _timeout_ms: int) -> bool:
        return self.written

    def disconnect_from_server(self) -> None:
        self.disconnected = True


def test_single_instance_import_does_not_import_pyside() -> None:
    script = """
import sys
import setpiece.agent.single_instance
loaded = [name for name in sys.modules if name == "PySide6" or name.startswith("PySide6.")]
raise SystemExit(1 if loaded else 0)
"""
    result = subprocess.run([sys.executable, "-c", script], check=False)

    assert result.returncode == 0


def test_default_activation_server_name_is_user_scoped_and_safe() -> None:
    name = default_activation_server_name("setpiece")

    assert name.endswith("-activation-v1")
    assert "/" not in name
    assert "\\" not in name
    assert "setpiece-" in name


def test_activation_server_accepts_valid_intent_and_rejects_malformed_message() -> None:
    valid_socket = FakeAcceptedSocket(ActivationIntent("open_picker").to_bytes())
    malformed_socket = FakeAcceptedSocket(b'{"schema_version":"setpiece.activation.v1","intent":"bad"}')
    adapter = FakeServerAdapter(sockets=[valid_socket, malformed_socket])
    received: list[str] = []
    server = ActivationServer(
        lambda intent: received.append(intent.intent),
        server_name="setpiece-test",
        server_adapter=adapter,
    )

    assert server.start() is True
    adapter.trigger()

    assert adapter.listened_name == "setpiece-test"
    assert received == ["open_picker"]
    assert valid_socket.disconnected is True
    assert malformed_socket.disconnected is True


def test_activation_server_close_releases_owner_lock() -> None:
    lock = FakeOwnerLock()
    adapter = FakeServerAdapter()
    server = ActivationServer(
        lambda _intent: None,
        server_name="setpiece-test",
        server_adapter=adapter,
        owner_lock=lock,
    )

    assert server.start() is True
    server.close()

    assert lock.released is True
    assert adapter.closed is True


def test_send_activation_intent_uses_local_socket_adapter_contract() -> None:
    client = FakeClientSocket()

    redirected = send_activation_intent(
        ActivationIntent("open_settings"),
        server_name="setpiece-test",
        socket_factory=lambda: client,
    )

    assert redirected is True
    assert client.server_name == "setpiece-test"
    assert parse_activation_message(client.data).intent == "open_settings"
    assert client.disconnected is True


def test_send_activation_intent_accepts_positive_write_when_qt_wait_times_out() -> None:
    client = FakeClientSocket(written=False)

    redirected = send_activation_intent(
        ActivationIntent("open_picker"),
        server_name="setpiece-test",
        socket_factory=lambda: client,
    )

    assert redirected is True
    assert parse_activation_message(client.data).intent == "open_picker"
    assert client.disconnected is True


def test_send_activation_intent_reports_failed_connection() -> None:
    client = FakeClientSocket(connected=False)

    redirected = send_activation_intent(
        ActivationIntent("open_builder"),
        server_name="setpiece-test",
        socket_factory=lambda: client,
    )

    assert redirected is False
    assert client.data == b""
    assert client.disconnected is True


def test_send_activation_intent_reports_failed_write() -> None:
    client = FakeClientSocket(write_result=0)

    redirected = send_activation_intent(
        ActivationIntent("open_picker"),
        server_name="setpiece-test",
        socket_factory=lambda: client,
    )

    assert redirected is False
    assert client.disconnected is True


def test_coordinator_redirects_second_process_when_primary_exists() -> None:
    client = FakeClientSocket()
    lock = FakeOwnerLock(acquired=False)
    coordinator = SingleInstanceCoordinator(
        server_name="setpiece-test",
        server_factory=lambda: (_ for _ in ()).throw(AssertionError("server should not start")),
        socket_factory=lambda: client,
        server_adapter_type=FakeServerAdapter,
        lock_factory=lambda: lock,
        redirect_attempts=1,
    )

    result = coordinator.become_primary_or_redirect(
        ActivationIntent("open_run_log"),
        lambda _intent: None,
    )

    assert result.is_primary is False
    assert result.redirected is True
    assert parse_activation_message(client.data).intent == "open_run_log"
    assert lock.acquire_calls == 1


def test_coordinator_primary_keeps_owner_lock_until_server_closes() -> None:
    server = FakeServerAdapter(listen_result=True)
    lock = FakeOwnerLock(acquired=True)
    coordinator = SingleInstanceCoordinator(
        server_name="setpiece-test",
        server_factory=lambda: server,
        server_adapter_type=FakeServerAdapter,
        lock_factory=lambda: lock,
    )

    result = coordinator.become_primary_or_redirect(
        ActivationIntent("open_picker"),
        lambda _intent: None,
    )

    assert result.is_primary is True
    assert result.server is not None
    assert lock.released is False
    result.server.close()
    assert lock.released is True


def test_coordinator_removes_stale_server_and_retries_primary_claim() -> None:
    FakeServerAdapter.removed.clear()
    first = FakeServerAdapter(listen_result=False, error="stale")
    second = FakeServerAdapter(listen_result=True)
    servers = [first, second]
    locks = [FakeOwnerLock(acquired=True), FakeOwnerLock(acquired=True)]
    client = FakeClientSocket(connected=False)
    coordinator = SingleInstanceCoordinator(
        server_name="setpiece-test",
        server_factory=lambda: servers.pop(0),
        socket_factory=lambda: client,
        server_adapter_type=FakeServerAdapter,
        lock_factory=lambda: locks.pop(0),
        redirect_attempts=1,
    )

    result = coordinator.become_primary_or_redirect(
        ActivationIntent("open_picker"),
        lambda _intent: None,
    )

    assert result.is_primary is True
    assert result.redirected is False
    assert result.server is not None
    assert result.server.server_name == "setpiece-test"
    assert FakeServerAdapter.removed == ["setpiece-test"]
