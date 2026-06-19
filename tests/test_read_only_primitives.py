from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

import pytest
from typer.testing import CliRunner

from setpiece.adapters.fake import FakeAdapters
from setpiece.cli import app
from setpiece.errors import PlatformUnsupportedError, SetpieceError
from setpiece.models import Recipe
from setpiece.overlay import ScreenRect
from setpiece.primitive_runtime import (
    FORBIDDEN_DIAGNOSTIC_CLASSES,
    run_read_only_primitive,
)
from setpiece.primitives import PrimitiveRisk, create_primitive_registry
from setpiece.doctor import build_doctor_report


REQUESTED_READ_ONLY_PRIMITIVES = {
    "app.process.list",
    "app.process.find",
    "app.process.is_running",
    "app.process.wait_running",
    "app.process.wait_exit",
    "window.topology.list_windows",
    "window.topology.find_window",
    "window.topology.get_bounds",
    "window.topology.get_foreground",
    "window.topology.monitor_list",
    "uia.element.list_labels",
    "uia.element.find_text",
    "uia.element.find_control",
    "uia.element.candidate_dump",
    "browser.assert.text_visible",
    "browser.assert.title_matches",
    "browser.assert.url_matches",
    "browser.assert.element_visible",
    "hardware.inventory.snapshot",
    "hardware.inventory.bios",
    "hardware.inventory.cpu",
    "hardware.inventory.gpu",
    "hardware.inventory.motherboard",
    "hardware.inventory.disks",
    "hardware.inventory.network_adapters",
    "hardware.inventory.pnp_devices",
    "network.connectivity.snapshot",
    "network.connectivity.dns",
    "network.connectivity.tcp",
    "network.connectivity.route_hint",
    "network.connectivity.profile",
    "diagnostics.bundle.collect_minimal",
    "diagnostics.bundle.collect_support",
    "diagnostics.bundle.collect_gamer_crash",
}


def test_requested_read_only_primitives_are_registered() -> None:
    registry = create_primitive_registry()

    missing = REQUESTED_READ_ONLY_PRIMITIVES - set(registry.primitive_ids())

    assert missing == set()
    for primitive_id in REQUESTED_READ_ONLY_PRIMITIVES:
        spec = registry.spec(primitive_id)
        assert spec.risk is PrimitiveRisk.READ_ONLY
        assert spec.confirmation_policy == "never"


def test_no_mutation_primitive_is_registered_in_read_only_patch() -> None:
    registry = create_primitive_registry()
    primitive_ids = set(registry.primitive_ids())

    forbidden = {
        "app.process.kill",
        "app.process.terminate",
        "service.control.stop",
        "service.control.start",
        "driver.install.raw",
        "firmware.vendor_flash.update",
        "registry.write.value",
        "firewall.write.rule",
        "storage.write.partition",
    }

    assert forbidden.isdisjoint(primitive_ids)


def test_process_primitive_uses_process_name_metadata_alias(monkeypatch) -> None:
    class FakeProcess:
        def __init__(self, pid: int, name: str, status: str = "running") -> None:
            self.info = {"pid": pid, "name": name, "status": status}

    class FakePsutil:
        class NoSuchProcess(Exception):
            pass

        class AccessDenied(Exception):
            pass

        @staticmethod
        def process_iter(_attrs):
            return [FakeProcess(1, "Setpiece.exe"), FakeProcess(2, "Other.exe")]

    monkeypatch.setattr("setpiece.primitive_runtime._psutil", lambda: FakePsutil)

    result = run_read_only_primitive(
        "app.process.is_running",
        parameters={"process_name": "Setpiece.exe"},
    )

    assert result.status == "success"
    assert result.details["matched"] is True


def test_process_read_only_verbs_use_fake_psutil(monkeypatch) -> None:
    class FakeProcess:
        def __init__(self, pid: int, name: str, status: str = "running") -> None:
            self.info = {"pid": pid, "name": name, "status": status}

    class FakePsutil:
        class NoSuchProcess(Exception):
            pass

        class AccessDenied(Exception):
            pass

        @staticmethod
        def process_iter(_attrs):
            return [FakeProcess(1, "Setpiece.exe"), FakeProcess(2, "Other.exe")]

    monkeypatch.setattr("setpiece.primitive_runtime._psutil", lambda: FakePsutil)

    results = [
        run_read_only_primitive("app.process.list"),
        run_read_only_primitive("app.process.find", parameters={"contains": "setpiece"}),
        run_read_only_primitive("app.process.is_running", parameters={"name": "Setpiece.exe"}),
        run_read_only_primitive("app.process.wait_running", parameters={"name": "Setpiece.exe"}),
        run_read_only_primitive("app.process.wait_exit", parameters={"name": "Missing.exe"}),
    ]

    assert [result.status for result in results] == ["success"] * 5
    assert results[0].details["count"] == 2
    assert results[1].details["processes"][0]["name"] == "Setpiece.exe"
    assert results[2].details["matched"] is True
    assert results[3].details["waited_for"] == "wait_running"
    assert results[4].details["waited_for"] == "wait_exit"


def test_process_primitive_requires_specific_target(monkeypatch) -> None:
    class FakePsutil:
        class NoSuchProcess(Exception):
            pass

        class AccessDenied(Exception):
            pass

        @staticmethod
        def process_iter(_attrs):
            return []

    monkeypatch.setattr("setpiece.primitive_runtime._psutil", lambda: FakePsutil)

    with pytest.raises(SetpieceError, match="requires one of pid, name, process_name, or contains"):
        run_read_only_primitive("app.process.is_running")


def test_window_topology_primitive_uses_fake_window_adapter() -> None:
    fakes = FakeAdapters()
    fakes.window.responses["list_windows"] = [
        {"title": "Battle.net", "process_id": 42, "bounds": {"x": 1, "y": 2, "width": 3, "height": 4}}
    ]

    result = run_read_only_primitive(
        "window.topology.list_windows",
        parameters={"title_contains": "Battle"},
        adapters=fakes.bundle(),
    )

    assert result.status == "success"
    assert result.details["windows"][0]["title"] == "Battle.net"
    assert fakes.window.calls[0][0] == "list_windows"
    assert fakes.window.calls[0][2]["title_contains"] == "Battle"


def test_window_topology_read_only_verbs_do_not_call_mutating_window_methods() -> None:
    fakes = FakeAdapters()
    fakes.window.responses["list_windows"] = [
        {"title": "Battle.net", "process_id": 42, "bounds": {"x": 1, "y": 2, "width": 3, "height": 4}}
    ]
    fakes.window.responses["foreground_window_title"] = "Battle.net"
    fakes.window.responses["list_monitors"] = [ScreenRect(0, 0, 1920, 1080)]

    results = [
        run_read_only_primitive(
            "window.topology.list_windows",
            parameters={"title_contains": "Battle"},
            adapters=fakes.bundle(),
        ),
        run_read_only_primitive(
            "window.topology.find_window",
            parameters={"title_contains": "Battle"},
            adapters=fakes.bundle(),
        ),
        run_read_only_primitive(
            "window.topology.get_bounds",
            parameters={"title_contains": "Battle"},
            adapters=fakes.bundle(),
        ),
        run_read_only_primitive("window.topology.get_foreground", adapters=fakes.bundle()),
        run_read_only_primitive("window.topology.monitor_list", adapters=fakes.bundle()),
    ]

    assert [result.status for result in results] == ["success"] * 5
    _assert_no_mutating_adapter_calls(fakes)
    assert [call[0] for call in fakes.window.calls] == [
        "list_windows",
        "list_windows",
        "list_windows",
        "foreground_window_title",
        "list_monitors",
    ]


def test_uia_element_primitive_lists_labels_with_fake_adapter() -> None:
    fakes = FakeAdapters()
    fakes.desktop.responses["inspect_windows"] = [
        SimpleNamespace(title="Battle.net", labels=["Diablo IV", "Play"])
    ]

    result = run_read_only_primitive(
        "uia.element.list_labels",
        parameters={"window_title_contains": "Battle.net", "limit": 2},
        adapters=fakes.bundle(),
    )

    assert result.status == "success"
    assert result.details["windows"] == [{"title": "Battle.net", "labels": ["Diablo IV", "Play"]}]
    assert fakes.desktop.calls[0][0] == "inspect_windows"


def test_uia_element_read_only_verbs_do_not_click() -> None:
    fakes = FakeAdapters()
    fakes.desktop.responses["inspect_windows"] = [
        SimpleNamespace(title="Battle.net", labels=["Diablo IV", "Play"])
    ]

    results = [
        run_read_only_primitive(
            "uia.element.list_labels",
            parameters={"window_title_contains": "Battle.net"},
            adapters=fakes.bundle(),
        ),
        run_read_only_primitive(
            "uia.element.find_text",
            parameters={"window_title_contains": "Battle.net", "text": "Play"},
            adapters=fakes.bundle(),
        ),
        run_read_only_primitive(
            "uia.element.find_control",
            parameters={
                "window_title_contains": "Battle.net",
                "text": "Play",
                "control_type": "Button",
            },
            adapters=fakes.bundle(),
        ),
        run_read_only_primitive(
            "uia.element.candidate_dump",
            parameters={"window_title_contains": "Battle.net"},
            adapters=fakes.bundle(),
        ),
    ]

    assert [result.status for result in results] == ["success"] * 4
    _assert_no_mutating_adapter_calls(fakes)
    assert "click_text" not in [call[0] for call in fakes.desktop.calls]
    assert [call[0] for call in fakes.desktop.calls] == [
        "inspect_windows",
        "find_text_region",
        "find_text_region",
        "inspect_windows",
    ]


def test_browser_assert_primitive_uses_fake_browser_adapter() -> None:
    fakes = FakeAdapters()

    result = run_read_only_primitive(
        "browser.assert.element_visible",
        parameters={"role": "button", "accessible_name": "Continue"},
        adapters=fakes.bundle(),
    )

    assert result.status == "success"
    assert result.details["matched"] is True
    assert fakes.browser.calls[0][0] == "element_visible"
    assert fakes.browser.calls[0][2]["role"] == "button"


def test_browser_assert_read_only_verbs_do_not_click_or_open() -> None:
    fakes = FakeAdapters()

    results = [
        run_read_only_primitive(
            "browser.assert.text_visible",
            parameters={"text": "Ready"},
            adapters=fakes.bundle(),
        ),
        run_read_only_primitive(
            "browser.assert.title_matches",
            parameters={"title_contains": "Example"},
            adapters=fakes.bundle(),
        ),
        run_read_only_primitive(
            "browser.assert.url_matches",
            parameters={"url_contains": "example.test"},
            adapters=fakes.bundle(),
        ),
        run_read_only_primitive(
            "browser.assert.element_visible",
            parameters={"role": "button", "accessible_name": "Continue"},
            adapters=fakes.bundle(),
        ),
    ]

    assert [result.status for result in results] == ["success"] * 4
    _assert_no_mutating_adapter_calls(fakes)
    assert [call[0] for call in fakes.browser.calls] == [
        "text_visible",
        "title_matches",
        "url_matches",
        "element_visible",
    ]


def test_primitive_run_rejects_non_read_only_primitives() -> None:
    with pytest.raises(SetpieceError, match="only supports read-only primitives"):
        run_read_only_primitive("uia.element.click_text", dry_run=True)


def test_hardware_inventory_unsupported_platform_is_friendly(monkeypatch) -> None:
    monkeypatch.setattr("setpiece.primitive_runtime.sys.platform", "linux")

    with pytest.raises(PlatformUnsupportedError, match="only supported on Windows"):
        run_read_only_primitive("hardware.inventory.snapshot")


def test_hardware_inventory_component_verbs_use_fake_psutil(monkeypatch) -> None:
    class FakeUsage:
        total = 1000
        free = 250

    class FakePsutil:
        @staticmethod
        def cpu_count(logical=True):
            return 8 if logical else 4

        @staticmethod
        def disk_partitions(all=False):
            return [SimpleNamespace(device="C:", mountpoint="C:\\", fstype="NTFS")]

        @staticmethod
        def disk_usage(_mountpoint):
            return FakeUsage()

        @staticmethod
        def net_if_addrs():
            return {
                "Ethernet": [
                    SimpleNamespace(family=SimpleNamespace(__str__=lambda self: "AF_INET"))
                ]
            }

    monkeypatch.setattr("setpiece.primitive_runtime.sys.platform", "win32")
    monkeypatch.setattr("setpiece.primitive_runtime._optional_psutil", lambda: FakePsutil)

    primitive_ids = [
        "hardware.inventory.snapshot",
        "hardware.inventory.bios",
        "hardware.inventory.cpu",
        "hardware.inventory.gpu",
        "hardware.inventory.motherboard",
        "hardware.inventory.disks",
        "hardware.inventory.network_adapters",
        "hardware.inventory.pnp_devices",
    ]
    results = [run_read_only_primitive(primitive_id) for primitive_id in primitive_ids]

    assert [result.status for result in results] == ["success"] * len(primitive_ids)
    assert results[0].details["cpu"]["logical_count"] == 8
    assert results[5].details["disks"][0]["device"] == "C:"


def test_network_connectivity_verbs_use_socket_fakes(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []

    class FakeConnection:
        def __enter__(self):
            calls.append(("tcp_enter", None))
            return self

        def __exit__(self, *_args):
            calls.append(("tcp_exit", None))

    class FakeSocket:
        def __init__(self, *_args, **_kwargs):
            calls.append(("socket", None))

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            calls.append(("socket_exit", None))

        def connect(self, target):
            calls.append(("route_connect", target))

        def getsockname(self):
            return ("192.0.2.10", 50000)

    monkeypatch.setattr("setpiece.primitive_runtime.socket.gethostname", lambda: "host")
    monkeypatch.setattr("setpiece.primitive_runtime.socket.getfqdn", lambda: "host.example")
    monkeypatch.setattr(
        "setpiece.primitive_runtime.socket.getaddrinfo",
        lambda host, _port: calls.append(("dns", host)) or [(2, None, None, None, None)],
    )
    monkeypatch.setattr(
        "setpiece.primitive_runtime.socket.create_connection",
        lambda target, timeout=None: calls.append(("tcp", target)) or FakeConnection(),
    )
    monkeypatch.setattr("setpiece.primitive_runtime.socket.socket", FakeSocket)

    results = [
        run_read_only_primitive("network.connectivity.profile"),
        run_read_only_primitive("network.connectivity.dns", parameters={"host": "example.test"}),
        run_read_only_primitive(
            "network.connectivity.tcp",
            parameters={"host": "example.test", "port": 443},
        ),
        run_read_only_primitive(
            "network.connectivity.route_hint",
            parameters={"host": "example.test", "port": 443},
        ),
        run_read_only_primitive(
            "network.connectivity.snapshot",
            parameters={"host": "example.test"},
        ),
    ]

    assert [result.status for result in results] == ["success"] * 5
    assert results[1].details["resolved"] is True
    assert results[2].details["connected"] is True
    assert results[3].details["local_address"] == "192.0.2.10"
    assert ("tcp", ("example.test", 443)) in calls
    assert ("route_connect", ("example.test", 443)) in calls


def test_doctor_knows_new_capability_names(monkeypatch) -> None:
    recipe = Recipe.model_validate(
        {
            "id": "diagnostics",
            "name": "Diagnostics",
            "environment": {
                "required_capabilities": [
                    "network_connectivity",
                    "diagnostics_collect",
                ]
            },
            "steps": [{"action": "wait.seconds", "seconds": 0.1}],
        }
    )

    report = build_doctor_report(recipe)
    statuses = {check.name: check.status for check in report.checks}

    assert statuses["network_connectivity"] == "ok"
    assert statuses["diagnostics_collect"] == "ok"


def test_diagnostics_bundle_excludes_forbidden_secret_classes(tmp_path: Path) -> None:
    result = run_read_only_primitive(
        "diagnostics.bundle.collect_minimal",
        parameters={"output_dir": str(tmp_path)},
    )

    assert result.status == "success"
    bundle_dir = Path(result.details["bundle_dir"])
    archive = Path(result.details["archive"])
    redaction_summary = json.loads((bundle_dir / "redaction_summary.json").read_text(encoding="utf-8"))
    manifest = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))

    assert set(FORBIDDEN_DIAGNOSTIC_CLASSES) <= set(redaction_summary["forbidden_classes_excluded"])
    assert redaction_summary["screenshots_included"] is False
    assert redaction_summary["clipboard_included"] is False
    assert redaction_summary["browser_history_included"] is False
    assert redaction_summary["cookies_included"] is False
    assert archive.exists()
    assert manifest["redacted"] is True
    assert all(entry["sha256"] for entry in manifest["files"])
    assert all(
        forbidden not in path.name.casefold()
        for path in [*bundle_dir.iterdir(), archive]
        for forbidden in ("cookie", "history", "password", "token", "private_key", "screenshot", "clipboard")
    )
    with ZipFile(archive) as zip_file:
        assert "diagnostics.json" in zip_file.namelist()
        assert "redaction_summary.json" in zip_file.namelist()


def test_diagnostics_bundle_only_writes_redacted_artifacts_under_output_dir(tmp_path: Path) -> None:
    output_dir = tmp_path / "diagnostics"

    result = run_read_only_primitive(
        "diagnostics.bundle.collect_support",
        parameters={"output_dir": str(output_dir)},
    )

    assert result.status == "success"
    bundle_dir = Path(result.details["bundle_dir"])
    archive = Path(result.details["archive"])
    assert bundle_dir.is_relative_to(output_dir)
    assert archive.parent == output_dir
    assert {artifact.redacted for artifact in result.artifacts} == {True}
    assert all(Path(artifact.path or "").is_relative_to(output_dir) for artifact in result.artifacts)
    manifest = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
    assert set(FORBIDDEN_DIAGNOSTIC_CLASSES) <= set(manifest["forbidden_classes_excluded"])


def test_primitive_run_cli_dry_run_outputs_json() -> None:
    result = CliRunner().invoke(
        app,
        ["primitive", "run", "hardware.inventory.snapshot", "--dry-run", "--json"],
    )

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["status"] == "dry-run"
    assert data["details"]["primitive_id"] == "hardware.inventory.snapshot"


def test_diagnostics_collect_cli_dry_run_outputs_json() -> None:
    result = CliRunner().invoke(
        app,
        ["diagnostics", "collect", "--preset", "minimal", "--dry-run", "--json"],
    )

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["status"] == "dry-run"
    assert data["details"]["primitive_id"] == "diagnostics.bundle.collect_minimal"


def test_primitive_run_cli_reports_bad_required_integer() -> None:
    result = CliRunner().invoke(
        app,
        ["primitive", "run", "network.connectivity.tcp", "--param", "host=localhost"],
    )

    assert result.exit_code == 1
    assert "primitive parameter 'port' is required" in result.output


def test_inspect_window_uses_uia_list_labels_primitive(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_run(primitive_id: str, *, parameters=None, **_kwargs):
        calls.append((primitive_id, dict(parameters or {})))
        return SimpleNamespace(
            to_dict=lambda: {
                "details": {
                    "windows": [{"title": "Battle.net", "labels": ["Diablo IV", "Play"]}]
                }
            },
            details={"windows": [{"title": "Battle.net", "labels": ["Diablo IV", "Play"]}]},
        )

    monkeypatch.setattr("setpiece.cli.run_read_only_primitive", fake_run)

    result = CliRunner().invoke(
        app,
        ["inspect-window", "Battle.net", "--limit", "2", "--control-type", "Button"],
    )

    assert result.exit_code == 0
    assert calls == [
        (
            "uia.element.list_labels",
            {"window_title_contains": "Battle.net", "limit": 2, "control_type": "Button"},
        )
    ]
    assert "Diablo IV" in result.output


def test_window_monitor_result_serializes_bounds() -> None:
    fakes = FakeAdapters()
    fakes.window.responses["list_monitors"] = [ScreenRect(0, 0, 1920, 1080)]

    result = run_read_only_primitive("window.topology.monitor_list", adapters=fakes.bundle())

    assert result.status == "success"
    assert result.details["monitors"] == [{"x": 0, "y": 0, "width": 1920, "height": 1080}]


def _assert_no_mutating_adapter_calls(fakes: FakeAdapters) -> None:
    assert _called_names(fakes.shell.calls).isdisjoint({"launch", "wait_process"})
    assert _called_names(fakes.browser.calls).isdisjoint(
        {"open_url", "close", "configure_media", "click_text", "click_role", "click_test_id"}
    )
    assert _called_names(fakes.window.calls).isdisjoint(
        {
            "focus",
            "minimize",
            "move_window",
            "resize_window",
            "maximize",
            "maximize_window",
            "restore_window",
            "snap_left",
            "snap_right",
            "snap_top",
            "snap_bottom",
            "wait",
        }
    )
    assert _called_names(fakes.desktop.calls).isdisjoint({"click_text"})
    assert _called_names(fakes.input.calls).isdisjoint({"hotkey"})


def _called_names(calls: list[tuple[str, tuple[object, ...], dict[str, object]]]) -> set[str]:
    return {name for name, _args, _kwargs in calls}
