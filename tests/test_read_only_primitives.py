from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

import pytest
from typer.testing import CliRunner

from ritualist.adapters.fake import FakeAdapters
from ritualist.cli import app
from ritualist.errors import PlatformUnsupportedError, RitualistError
from ritualist.models import Recipe
from ritualist.overlay import ScreenRect
from ritualist.primitive_runtime import (
    FORBIDDEN_DIAGNOSTIC_CLASSES,
    run_read_only_primitive,
)
from ritualist.primitives import PrimitiveRisk, create_primitive_registry
from ritualist.doctor import build_doctor_report


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
            return [FakeProcess(1, "Ritualist.exe"), FakeProcess(2, "Other.exe")]

    monkeypatch.setattr("ritualist.primitive_runtime._psutil", lambda: FakePsutil)

    result = run_read_only_primitive(
        "app.process.is_running",
        parameters={"process_name": "Ritualist.exe"},
    )

    assert result.status == "success"
    assert result.details["matched"] is True


def test_process_primitive_requires_specific_target(monkeypatch) -> None:
    class FakePsutil:
        class NoSuchProcess(Exception):
            pass

        class AccessDenied(Exception):
            pass

        @staticmethod
        def process_iter(_attrs):
            return []

    monkeypatch.setattr("ritualist.primitive_runtime._psutil", lambda: FakePsutil)

    with pytest.raises(RitualistError, match="requires one of pid, name, process_name, or contains"):
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


def test_primitive_run_rejects_non_read_only_primitives() -> None:
    with pytest.raises(RitualistError, match="only supports read-only primitives"):
        run_read_only_primitive("uia.element.click_text", dry_run=True)


def test_hardware_inventory_unsupported_platform_is_friendly(monkeypatch) -> None:
    monkeypatch.setattr("ritualist.primitive_runtime.sys.platform", "linux")

    with pytest.raises(PlatformUnsupportedError, match="only supported on Windows"):
        run_read_only_primitive("hardware.inventory.snapshot")


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

    monkeypatch.setattr("ritualist.cli.run_read_only_primitive", fake_run)

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
