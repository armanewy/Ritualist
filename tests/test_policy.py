from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZipFile

import pytest
import yaml
from typer.testing import CliRunner

from ritualist.cli import app
from ritualist.models import Recipe
from ritualist.packs import PACK_SCHEMA_V1, PackValidationError, export_recipe_pack, validate_pack
from ritualist.policy import (
    PolicyProfile,
    PrimitivePolicyEngine,
    build_policy_report_for_recipe,
    detect_never_importable_raw,
    explain_primitive_policy,
)


SAFETY = {
    "no_arbitrary_code": True,
    "no_coordinate_clicks": True,
    "no_remote_execution": True,
    "imported_recipes_must_not_run_automatically": True,
}


def test_read_only_imported_without_warning() -> None:
    recipe = Recipe.model_validate(
        {
            "id": "check_file",
            "name": "Check File",
            "steps": [{"action": "wait.seconds", "seconds": 1}],
            "verify": [{"action": "assert.path_exists", "path": "."}],
        }
    )

    report = build_policy_report_for_recipe(recipe, imported=True, private_or_local=False)

    assert report.allowed is True
    assert {finding.decision.value for finding in report.findings} == {"allowed"}
    assert {finding.category.value for finding in report.findings} == {
        "importable_without_warning"
    }


def test_modifies_files_imported_with_disclosure() -> None:
    engine = PrimitivePolicyEngine()
    finding = engine.evaluate_requirement(
        _fake_requirement("filesystem.write.file", "modifies_files"),
        imported=True,
        private_or_local=False,
    )

    assert finding.category.value == "importable_with_disclosure"
    assert finding.decision.value == "requires_disclosure"
    assert finding.blocked is False


def test_risky_imported_blocked_by_default() -> None:
    finding = explain_primitive_policy("uia.element.click_text")

    assert finding.category.value == "blocked_by_default"
    assert finding.decision.value == "blocked"
    assert finding.blocked is True


def test_policy_profiles_differ_for_private_risky_primitives() -> None:
    consumer = explain_primitive_policy(
        "uia.element.click_text",
        profile=PolicyProfile.CONSUMER_SAFE,
        imported=True,
        private_or_local=True,
    )
    power = explain_primitive_policy(
        "uia.element.click_text",
        profile=PolicyProfile.POWER_USER,
        imported=True,
        private_or_local=True,
    )
    lab = explain_primitive_policy(
        "uia.element.click_text",
        profile=PolicyProfile.LAB_ONLY,
        imported=True,
        private_or_local=True,
    )

    assert consumer.decision.value == "blocked"
    assert power.decision.value == "requires_confirmation"
    assert lab.decision.value == "requires_double_confirmation"


def test_never_importable_embedded_credentials_blocked() -> None:
    findings = detect_never_importable_raw(
        {
            "version": "0.1",
            "id": "bad",
            "name": "Bad",
            "variables": {"api_token": "real-token-value"},
            "steps": [{"action": "wait.seconds", "seconds": 1}],
        }
    )

    assert findings
    assert findings[0].primitive_id == "embedded_credentials"
    assert findings[0].blocked is True


def test_never_importable_elevated_launch_metadata_blocked() -> None:
    findings = detect_never_importable_raw(
        {
            "version": "0.1",
            "id": "bad",
            "name": "Bad",
            "steps": [
                {
                    "action": "app.launch",
                    "command": "helper.exe",
                    "run_as_admin": True,
                }
            ],
        }
    )

    assert any(
        finding.primitive_id == "arbitrary_unsigned_executables_launched_elevated"
        for finding in findings
    )


def test_validate_pack_blocks_never_importable_binary_asset(tmp_path: Path) -> None:
    path = _write_pack(
        tmp_path,
        recipe={"version": "0.1", "id": "bad", "name": "Bad", "steps": [{"action": "wait.seconds", "seconds": 1}]},
        manifest=_manifest(required_actions=["wait.seconds"], required_capabilities=[]),
        assets={"assets/helper.dll": b"opaque"},
    )

    with pytest.raises(PackValidationError, match="never-importable.*opaque_binary_helper_dlls"):
        validate_pack(path)


def test_nested_branch_primitive_blocked() -> None:
    recipe = Recipe.model_validate(
        {
            "id": "nested",
            "name": "Nested",
            "steps": [
                {
                    "action": "flow.if",
                    "condition": {"type": "path.exists", "path": "marker.txt"},
                    "then": [{"action": "browser.click_text", "text": "Continue"}],
                }
            ],
        }
    )

    report = build_policy_report_for_recipe(recipe, imported=True, private_or_local=False)

    assert report.allowed is False
    assert any(
        finding.primitive_id == "browser.interact.click_text"
        and finding.source == "steps[0].then[0]"
        for finding in report.blocked_findings
    )


def test_on_timeout_primitive_blocked_if_unsafe() -> None:
    recipe = Recipe.model_validate(
        {
            "id": "timeout",
            "name": "Timeout",
            "steps": [
                {
                    "action": "wait.for_file",
                    "path": "marker.txt",
                    "timeout_seconds": 1,
                    "on_timeout": [{"action": "browser.click_text", "text": "Continue"}],
                }
            ],
        }
    )

    report = build_policy_report_for_recipe(recipe, imported=True, private_or_local=False)

    assert report.allowed is False
    assert any(
        finding.primitive_id == "browser.interact.click_text"
        and finding.source == "steps[0].on_timeout[0]"
        for finding in report.blocked_findings
    )


def test_exported_packs_do_not_include_local_policy_state(tmp_path: Path) -> None:
    recipe_path = tmp_path / "recipe.yaml"
    recipe_path.write_text(
        """
version: "0.1"
id: export_policy
name: Export Policy
steps:
  - action: wait.seconds
    seconds: 1
""".lstrip(),
        encoding="utf-8",
    )
    out_path = tmp_path / "policy.ritualistpack"

    export_recipe_pack(recipe_path, out_path)

    with ZipFile(out_path) as archive:
        manifest = archive.read("manifest.yaml").decode("utf-8")
        recipe = archive.read("recipe.yaml").decode("utf-8")
    payload = manifest + "\n" + recipe
    assert "policy_profile" not in payload
    assert "approval" not in payload
    assert "managed_policy" not in payload


def test_policy_cli_show_json() -> None:
    result = CliRunner().invoke(app, ["policy", "show", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["schema_version"] == "primitive.policy.v1"
    assert "consumer_safe" in payload["profiles"]


def test_policy_cli_check_blocks_risky_recipe(tmp_path: Path) -> None:
    recipe_path = tmp_path / "risky.yaml"
    recipe_path.write_text(
        """
version: "0.1"
id: risky
name: Risky
steps:
  - action: desktop.click_text
    window_title_contains: Battle.net
    text: Play
    requires_confirmation: true
""".lstrip(),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["policy", "check", str(recipe_path), "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["allowed"] is False
    assert any(
        finding["primitive_id"] == "uia.element.click_text"
        for finding in payload["findings"]
    )


def test_no_arbitrary_scripts_accepted_by_pack_policy(tmp_path: Path) -> None:
    path = _write_pack(
        tmp_path,
        recipe={"version": "0.1", "id": "bad", "name": "Bad", "steps": [{"action": "shell.run", "command": "echo hi"}]},
        manifest=_manifest(required_actions=["shell.run"], required_capabilities=[]),
    )

    with pytest.raises(PackValidationError, match="arbitrary code actions"):
        validate_pack(path)


def _fake_requirement(primitive_id: str, risk: str):
    from ritualist.policy import PrimitiveRequirement
    from ritualist.primitives import (
        PrimitiveAdapterBinding,
        PrimitiveFamily,
        PrimitiveRisk,
        PrimitiveSpec,
        PrimitiveVerb,
    )

    family, _, verb = primitive_id.rpartition(".")
    spec = PrimitiveSpec(
        family=PrimitiveFamily(family),
        verb=PrimitiveVerb(verb),
        display_name=primitive_id,
        description=primitive_id,
        required_capabilities=(),
        supported_platforms=("windows", "macos", "linux"),
        risk=PrimitiveRisk(risk),
        confirmation_policy="never",
        allowed_in_imported_packs=True,
        adapter_binding=PrimitiveAdapterBinding("fake", "fake"),
    )
    return PrimitiveRequirement(primitive_id=primitive_id, source="test", spec=spec, risk=spec.risk)


def _manifest(*, required_actions: list[str], required_capabilities: list[str]) -> dict[str, object]:
    return {
        "schema": PACK_SCHEMA_V1,
        "id": "demo_pack",
        "name": "Demo Pack",
        "version": "1.0.0",
        "required_ritualist_version": ">=0.1.0-alpha.1",
        "supported_os": ["windows", "macos", "linux"],
        "required_capabilities": required_capabilities,
        "required_actions": required_actions,
        "variables": {},
        "safety": dict(SAFETY),
    }


def _write_pack(
    tmp_path: Path,
    *,
    manifest: dict[str, object],
    recipe: dict[str, object],
    assets: dict[str, bytes] | None = None,
) -> Path:
    path = tmp_path / "demo.ritualistpack"
    with ZipFile(path, "w") as archive:
        archive.writestr("manifest.yaml", yaml.safe_dump(manifest, sort_keys=False))
        archive.writestr("recipe.yaml", yaml.safe_dump(recipe, sort_keys=False))
        for name, content in (assets or {}).items():
            archive.writestr(name, content)
    return path
