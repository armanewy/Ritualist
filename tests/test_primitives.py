from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from ritualist.actions.registry import create_default_registry
from ritualist.cli import app
from ritualist.doctor import build_doctor_report
from ritualist.models import Recipe
from ritualist.primitives import (
    FakePrimitiveAdapter,
    KNOWN_PRIMITIVE_FAMILIES,
    PrimitiveAdapterBinding,
    PrimitiveArtifact,
    PrimitiveCapability,
    PrimitiveFamily,
    PrimitiveParameter,
    PrimitivePlanStep,
    PrimitiveRisk,
    PrimitiveSpec,
    PrimitiveVerb,
    create_primitive_registry,
)


def test_primitive_risk_enum_values_are_stable() -> None:
    assert {risk.value for risk in PrimitiveRisk} == {
        "read_only",
        "launches_app",
        "controls_ui",
        "modifies_files",
        "risky",
    }


def test_primitive_model_serialization() -> None:
    spec = PrimitiveSpec(
        family=PrimitiveFamily("browser.session"),
        verb=PrimitiveVerb("open"),
        display_name="Open Browser Session",
        description="Open a managed browser session.",
        required_capabilities=(PrimitiveCapability.PLAYWRIGHT, PrimitiveCapability.BROWSER_CONTROL),
        supported_platforms=("windows", "macos", "linux"),
        risk=PrimitiveRisk.LAUNCHES_APP,
        confirmation_policy="optional",
        allowed_in_imported_packs=False,
        adapter_binding=PrimitiveAdapterBinding("playwright", "managed_browser"),
        parameters=(
            PrimitiveParameter("url", required=True),
            PrimitiveParameter("profile", required=False),
        ),
        action_name="browser.open",
    )

    serialized = spec.to_dict()

    assert serialized["primitive_id"] == "browser.session.open"
    assert serialized["family"] == "browser.session"
    assert serialized["verb"] == "open"
    assert serialized["risk"] == "launches_app"
    assert serialized["required_capabilities"] == ["playwright", "browser_control"]
    assert serialized["adapter_binding"]["adapter_id"] == "playwright"
    assert serialized["parameters"][0] == {
        "name": "url",
        "required": True,
        "description": "",
        "sensitive": False,
    }


def test_primitive_family_validation_supports_dotted_names() -> None:
    assert PrimitiveFamily("firmware.vendor_flash").name == "firmware.vendor_flash"
    assert {
        "app.process",
        "browser.session",
        "browser.interact",
        "firmware.guard",
        "firmware.vendor_flash",
    }.issubset(KNOWN_PRIMITIVE_FAMILIES)
    with pytest.raises(ValueError, match="primitive family"):
        PrimitiveFamily("Firmware Vendor Flash")


def test_primitive_registry_maps_all_default_actions() -> None:
    action_registry = create_default_registry()
    primitive_registry = create_primitive_registry(action_registry)

    assert len(primitive_registry.specs()) >= len(action_registry.action_types())
    for action_name in action_registry.action_types():
        spec = primitive_registry.spec_for_action(action_name)
        assert spec.action_name == action_name
        assert spec.risk.value in {risk.value for risk in PrimitiveRisk}
        assert spec.adapter_binding.adapter_id


def test_existing_action_policy_is_visible_per_primitive() -> None:
    registry = create_primitive_registry()

    click_text = registry.spec_for_action("desktop.click_text")
    browser_open = registry.spec_for_action("browser.open")
    file_assert = registry.spec_for_action("assert.file_exists")

    assert click_text.primitive_id == "uia.element.click_text"
    assert click_text.risk is PrimitiveRisk.RISKY
    assert click_text.allowed_in_imported_packs is False
    assert click_text.confirmation_policy == "required_for_play"
    assert browser_open.adapter_binding.adapter_id == "playwright"
    assert file_assert.allowed_in_imported_packs is True


def test_primitives_json_cli_outputs_inspectable_metadata() -> None:
    result = CliRunner().invoke(app, ["primitives", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    primitive_ids = {entry["primitive_id"] for entry in data}
    assert "browser.session.open" in primitive_ids
    assert "uia.element.click_text" in primitive_ids
    click_text = next(entry for entry in data if entry["primitive_id"] == "uia.element.click_text")
    assert click_text["risk"] == "risky"
    assert click_text["allowed_in_imported_packs"] is False
    assert click_text["adapter_binding"]["adapter_id"] == "windows_uia"


def test_primitive_show_cli_outputs_one_primitive() -> None:
    result = CliRunner().invoke(app, ["primitive", "show", "browser.session.open", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["primitive_id"] == "browser.session.open"
    assert data["action_name"] == "browser.open"


def test_primitive_families_cli_lists_families() -> None:
    result = CliRunner().invoke(app, ["primitive", "families", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "browser.session" in data
    assert "window.topology" in data


def test_fake_primitive_adapter_contract() -> None:
    adapter = FakePrimitiveAdapter(
        supported_primitives=("browser.session.open",),
        supported_families=("browser.session",),
        supported_verbs=("open",),
    )
    step = PrimitivePlanStep("browser.session.open", action_name="browser.open")

    dry_run = adapter.dry_run(step)
    execute = adapter.execute(step)
    verify = adapter.verify(step)
    artifact = PrimitiveArtifact("log", "redacted-log", path=None)

    assert dry_run.status == "dry-run"
    assert adapter.supported_families == ("browser.session",)
    assert adapter.supported_verbs == ("open",)
    assert execute.status == "skipped"
    assert verify.status == "ok"
    assert artifact.to_dict()["redacted"] is True


def test_doctor_reports_primitive_requirements() -> None:
    recipe = Recipe.model_validate(
        {
            "id": "runbook",
            "name": "Runbook",
            "steps": [{"action": "browser.open", "url": "https://example.test"}],
        }
    )

    report = build_doctor_report(recipe)
    data = report.to_dict()

    assert report.primitive_specs[0].primitive_id == "browser.session.open"
    assert any(check.section == "Primitives" for check in report.checks)
    assert data["primitives"][0]["primitive_id"] == "browser.session.open"
    assert data["primitives"][0]["allowed_in_imported_packs"] is False
