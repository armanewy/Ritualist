from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from setpiece.cli import app
from setpiece.themes import ThemeDocument, load_theme, resolve_theme_tokens, validate_theme


def _theme_path(tmp_path: Path, text: str) -> Path:
    root = tmp_path / "theme"
    root.mkdir()
    path = root / "theme.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_bundled_setpiece_paper_theme_validates() -> None:
    result = validate_theme("setpiece.paper")

    assert result.valid is True
    assert result.theme_id == "setpiece.paper"
    assert result.errors == ()
    assert not [warning for warning in result.warnings if warning.startswith("accessibility:")]
    assert result.accessibility["warning_count"] == 0
    checks = {check["id"]: check for check in result.accessibility["checks"]}
    assert checks["focus_ring_on_surface"]["passed"] is True
    assert checks["focus_ring_on_background"]["passed"] is True


def test_invalid_theme_color_fails(tmp_path: Path) -> None:
    path = _theme_path(
        tmp_path,
        """
schema: setpiece.theme.v1
id: bad.color
name: Bad Color
tokens:
  color.background: not-a-color
""",
    )

    result = validate_theme(path)

    assert result.valid is False
    assert any("color.background" in error for error in result.errors)


def test_invalid_token_reference_fails(tmp_path: Path) -> None:
    path = _theme_path(
        tmp_path,
        """
schema: setpiece.theme.v1
id: bad.reference
name: Bad Reference
tokens:
  color.background: "{color.missing}"
""",
    )

    result = validate_theme(path)

    assert result.valid is False
    assert any("missing token reference" in error for error in result.errors)


def test_recursive_token_reference_fails(tmp_path: Path) -> None:
    path = _theme_path(
        tmp_path,
        """
schema: setpiece.theme.v1
id: bad.recursive
name: Bad Recursive
tokens:
  color.background: "{color.surface}"
  color.surface: "{color.background}"
""",
    )

    result = validate_theme(path)

    assert result.valid is False
    assert any("recursive token reference" in error for error in result.errors)


def test_token_reference_must_match_receiving_token_type(tmp_path: Path) -> None:
    path = _theme_path(
        tmp_path,
        """
schema: setpiece.theme.v1
id: bad.cross_type
name: Bad Cross Type
tokens:
  color.background: "{spacing.md}"
  spacing.md: 12
""",
    )

    result = validate_theme(path)

    assert result.valid is False
    assert any("color.background" in error and "color tokens" in error for error in result.errors)


def test_remote_asset_url_rejected(tmp_path: Path) -> None:
    path = _theme_path(
        tmp_path,
        """
schema: setpiece.theme.v1
id: bad.remote
name: Bad Remote
assets:
  hero: https://example.invalid/hero.png
""",
    )

    result = validate_theme(path)

    assert result.valid is False
    assert any("remote asset URLs" in error for error in result.errors)


def test_arbitrary_code_fields_rejected(tmp_path: Path) -> None:
    path = _theme_path(
        tmp_path,
        """
schema: setpiece.theme.v1
id: bad.code
name: Bad Code
component_variants:
  ritual.card:
    standard:
      on_click: "python: do_thing()"
""",
    )

    result = validate_theme(path)

    assert result.valid is False
    assert any("executable or behavior fields" in error for error in result.errors)


def test_missing_asset_is_warning_not_crash(tmp_path: Path) -> None:
    path = _theme_path(
        tmp_path,
        """
schema: setpiece.theme.v1
id: missing.asset
name: Missing Asset
assets:
  hero: assets/missing.png
""",
    )

    result = validate_theme(path)

    assert result.valid is True
    assert any("asset file is missing" in warning for warning in result.warnings)


def test_low_contrast_theme_emits_accessibility_warning(tmp_path: Path) -> None:
    path = _theme_path(
        tmp_path,
        """
schema: setpiece.theme.v1
id: low.contrast
name: Low Contrast
tokens:
  color.surface: "#ffffff"
  color.text: "#fefefe"
  color.text_muted: "#fdfdfd"
  color.focus_ring: "#fefefe"
  color.accent: "#ffffff"
  color.on_accent: "#fefefe"
""",
    )

    result = validate_theme(path)

    assert result.valid is True
    assert any("accessibility:" in warning for warning in result.warnings)
    assert result.accessibility["warning_count"] >= 1


def test_focus_ring_low_contrast_emits_accessibility_warning(tmp_path: Path) -> None:
    path = _theme_path(
        tmp_path,
        """
schema: setpiece.theme.v1
id: low.focus
name: Low Focus
tokens:
  color.background: "#ffffff"
  color.surface: "#ffffff"
  color.focus_ring: "#fefefe"
""",
    )

    result = validate_theme(path)

    assert result.valid is True
    assert any("focus_ring_on_surface" in warning for warning in result.warnings)
    assert any("focus_ring_on_background" in warning for warning in result.warnings)


def test_missing_accessibility_colors_fall_back_before_contrast_check(tmp_path: Path) -> None:
    path = _theme_path(
        tmp_path,
        """
schema: setpiece.theme.v1
id: fallback.contrast
name: Fallback Contrast
tokens: {}
""",
    )

    result = validate_theme(path)

    assert result.valid is True
    assert not [warning for warning in result.warnings if warning.startswith("accessibility:")]
    assert result.accessibility["warning_count"] == 0


def test_theme_pack_cannot_bind_behavior(tmp_path: Path) -> None:
    path = _theme_path(
        tmp_path,
        """
schema: setpiece.theme.v1
id: bad.behavior
name: Bad Behavior
component_variants:
  ritual.card:
    standard:
      binding:
        kind: recipe
        recipe_id: gaming_mode
""",
    )

    result = validate_theme(path)

    assert result.valid is False
    assert any("behavior fields" in error for error in result.errors)


def test_theme_resolver_merges_overrides() -> None:
    theme = ThemeDocument.model_validate(
        {
            "schema": "setpiece.theme.v1",
            "id": "merge.test",
            "name": "Merge Test",
            "tokens": {"color.background": "#ffffff"},
        }
    )

    result = resolve_theme_tokens(
        theme,
        canvas_overrides={"color.surface": "{color.background}"},
        component_overrides={"spacing.md": 16},
        runtime_state_overrides={"opacity.disabled": 0.4},
    )

    assert result.valid is True
    assert result.tokens["color.surface"] == "#ffffff"
    assert result.tokens["spacing.md"] == 16
    assert result.tokens["opacity.disabled"] == 0.4


def test_theme_cli_show_and_validate_json() -> None:
    runner = CliRunner()

    show = runner.invoke(app, ["theme", "show", "setpiece.paper", "--json"])
    validate = runner.invoke(app, ["theme", "validate", "setpiece.paper", "--json"])
    list_result = runner.invoke(app, ["theme", "list", "--json"])

    assert show.exit_code == 0
    assert validate.exit_code == 0
    assert list_result.exit_code == 0
    assert json.loads(show.output)["theme"]["id"] == "setpiece.paper"
    validation = json.loads(validate.output)
    assert validation["valid"] is True
    assert validation["accessibility"]["warning_count"] == 0
    assert any(row["id"] == "setpiece.paper" for row in json.loads(list_result.output))


def test_load_theme_accepts_prompt_requested_path() -> None:
    theme = load_theme(Path("themes/setpiece-paper/theme.yaml"))

    assert theme.id == "setpiece.paper"
