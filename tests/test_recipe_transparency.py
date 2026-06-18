from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from ritualist.errors import RecipeValidationError
from ritualist.cli import app
from ritualist.recipe_transparency import (
    load_recipe_overrides,
    open_yaml_payload,
    save_recipe_setup_overrides,
    view_recipe_payload,
)


runner = CliRunner()


def test_view_recipe_payload_explains_setup_and_safety(tmp_path: Path) -> None:
    recipe_path = _gaming_recipe(tmp_path)

    payload = view_recipe_payload(recipe_path, overrides_root=tmp_path / "overrides")

    assert payload["schema_version"] == "recipe.transparency.v1"
    assert payload["recipe_id"] == "gaming_mode"
    assert payload["purpose"] == "Prepare a truthful Gaming Room."
    assert [field["name"] for field in payload["setup_fields"][:8]] == [
        "ambience_enabled",
        "ambience_url",
        "ambience_browser_mode",
        "minimize_ambience",
        "battle_net_path",
        "battle_net_window",
        "target_game",
        "target_id",
    ]
    assert payload["actions"]["auto_run_after_edit"] is False
    assert "python -m ritualist doctor gaming_mode" == payload["actions"]["doctor"]
    assert "python -m ritualist dry-run gaming_mode" == payload["actions"]["dry_run"]
    assert any("Never automates gameplay" in item for item in payload["what_ritualist_will_never_do"])
    assert any(step["requires_confirmation"] for step in payload["confirmations"])
    assert payload["blocked_branches"]
    assert any("Editing setup saves overrides only" in line for line in payload["plain_language_plan"])


def test_save_recipe_setup_overrides_stores_separately_and_validates(tmp_path: Path) -> None:
    recipe_path = _gaming_recipe(tmp_path)
    overrides_root = tmp_path / "setup-overrides"

    result = save_recipe_setup_overrides(
        recipe_path,
        {
            "ambience_enabled": False,
            "ambience_browser_mode": "managed",
            "minimize_ambience": "true",
            "battle_net_window": "Battle.net Fixture",
        },
        overrides_root=overrides_root,
    )

    assert result.recipe_id == "gaming_mode"
    assert result.recipe_path == recipe_path
    assert result.overrides_path == overrides_root / "gaming_mode.yaml"
    assert result.side_effects == {
        "bundled_recipe_modified": False,
        "ran_recipe": False,
        "opened_external_app": False,
    }
    assert result.overrides["ambience_enabled"] is False
    assert result.overrides["minimize_ambience"] is True
    assert "Battle.net Fixture" in result.overrides_path.read_text(encoding="utf-8")
    assert load_recipe_overrides(recipe_path, overrides_root=overrides_root) == result.overrides
    assert recipe_path.read_text(encoding="utf-8") == _GAMING_RECIPE_TEXT


def test_setup_overrides_reject_unknown_or_script_like_fields(tmp_path: Path) -> None:
    recipe_path = _gaming_recipe(tmp_path)

    with pytest.raises(RecipeValidationError, match="unknown setup field"):
        save_recipe_setup_overrides(
            recipe_path,
            {"surprise_field": "value"},
            overrides_root=tmp_path / "overrides",
        )

    with pytest.raises(RecipeValidationError, match="not allowed"):
        save_recipe_setup_overrides(
            recipe_path,
            {"python_script": "print('no')"},
            overrides_root=tmp_path / "overrides",
        )

    with pytest.raises(RecipeValidationError, match="native or managed"):
        save_recipe_setup_overrides(
            recipe_path,
            {"ambience_browser_mode": "signed_in_magic"},
            overrides_root=tmp_path / "overrides",
        )


def test_open_yaml_payload_returns_reference_without_side_effects(tmp_path: Path) -> None:
    recipe_path = _gaming_recipe(tmp_path)

    payload = open_yaml_payload(recipe_path)

    assert payload["schema_version"] == "recipe.open_yaml_reference.v1"
    assert payload["recipe_path"] == str(recipe_path)
    assert payload["side_effects"] == {
        "opened_editor": False,
        "ran_recipe": False,
        "modified_recipe": False,
    }
    assert "Advanced YAML" in payload["warning"]


def test_recipe_cli_views_edits_and_resolves_yaml_without_running(tmp_path: Path) -> None:
    recipe_path = _gaming_recipe(tmp_path)
    overrides_dir = tmp_path / "overrides"

    view = runner.invoke(app, ["recipe", "view", str(recipe_path), "--json"])
    assert view.exit_code == 0, view.output
    assert '"schema_version": "recipe.transparency.v1"' in view.output
    assert "Never automates gameplay" in view.output

    edit = runner.invoke(
        app,
        [
            "recipe",
            "edit-setup",
            str(recipe_path),
            "--set",
            "ambience_browser_mode=managed",
            "--set",
            "minimize_ambience=true",
            "--overrides-dir",
            str(overrides_dir),
            "--json",
        ],
    )
    assert edit.exit_code == 0, edit.output
    assert (overrides_dir / "gaming_mode.yaml").exists()
    assert '"ran_recipe": false' in edit.output
    assert '"bundled_recipe_modified": false' in edit.output

    open_yaml = runner.invoke(app, ["recipe", "open-yaml", str(recipe_path), "--json"])
    assert open_yaml.exit_code == 0, open_yaml.output
    assert '"opened_editor": false' in open_yaml.output
    assert '"ran_recipe": false' in open_yaml.output


_GAMING_RECIPE_TEXT = """\
version: "0.1"
id: gaming_mode
name: Gaming Mode
description: Prepare a truthful Gaming Room.
variables:
  ambience_enabled: true
  ambience_url: "https://example.com/ambience"
  ambience_browser_mode: native
  minimize_ambience: false
  battle_net_path: 'C:\\Program Files (x86)\\Battle.net\\Battle.net Launcher.exe'
  battle_net_window: Battle.net
  target_game: Diablo IV
  target_id: diablo_iv
environment:
  os:
    - windows
  required_capabilities:
    - windows_uia
  expected_windows:
    - title_contains: "{{ battle_net_window }}"
  expected_labels:
    - window_title_contains: "{{ battle_net_window }}"
      text: Play
steps:
  - name: Optional ambience
    action: browser.open_native
    url: "{{ ambience_url }}"
    optional: true
  - name: Inspect Diablo readiness
    action: target.inspect
    target: "{{ target_id }}"
  - name: Branch on readiness
    action: flow.if
    condition:
      type: target.readiness_state
      target: "{{ target_id }}"
      readiness_state: play_available_enabled
    then:
      - name: Start Diablo IV
        action: desktop.click_text
        text: Play
        window_title_contains: "{{ battle_net_window }}"
        requires_confirmation: true
    else:
      - name: Explain blocked state
        action: human.prompt
        prompt: "Battle.net is not ready to play."
verify:
  - name: Verify Diablo process
    action: assert.process_running
    process_name: Diablo IV
"""


def _gaming_recipe(tmp_path: Path) -> Path:
    recipe_path = tmp_path / "gaming_mode.yaml"
    parsed = yaml.safe_load(_GAMING_RECIPE_TEXT)
    assert parsed["id"] == "gaming_mode"
    recipe_path.write_text(_GAMING_RECIPE_TEXT, encoding="utf-8")
    return recipe_path
