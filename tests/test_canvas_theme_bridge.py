from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ritualist.canvas import (
    CanvasDocument,
    CanvasRuntimeContext,
    CanvasTheme,
    CanvasThemeTokens,
    build_canvas_view_model,
    bundled_canvas_ids,
    load_canvas,
    validate_canvas_document,
)
from ritualist.canvas.app import build_canvas_use_payload
from ritualist.cli import app
from ritualist.errors import RitualistError
from ritualist.themes import APP_DEFAULT_TOKENS


def test_canvas_with_ritualist_paper_theme_validates_and_renders_payload() -> None:
    canvas = CanvasDocument(
        id="paper_canvas",
        name="Paper Canvas",
        theme=CanvasTheme(id="ritualist.paper", name="Ritualist Paper"),
    )

    validation = validate_canvas_document(canvas, check_bindings=False)
    model = build_canvas_view_model(
        canvas,
        context=CanvasRuntimeContext(recipe_ids=set(), target_ids=set(), recent_runs=()),
    )
    payload = model.to_dict()

    assert validation.valid
    assert payload["canvas"]["theme"]["id"] == "ritualist.paper"
    assert payload["canvas"]["theme"]["source"] == "bundled"
    assert payload["canvas"]["theme"]["validation"]["valid"] is True
    assert payload["canvas"]["theme"]["tokens"]["background"] == "#f6f2ea"
    assert payload["runtime"]["theme"]["id"] == "ritualist.paper"


def test_canvas_use_payload_emits_selected_theme_id_for_mock_render() -> None:
    canvas = CanvasDocument(
        id="paper_payload",
        name="Paper Payload",
        theme=CanvasTheme(id="ritualist.paper", name="Ritualist Paper"),
    )

    payload = build_canvas_use_payload(canvas, recipe_ids=set(), target_ids=set())

    assert payload["canvas"]["theme"]["id"] == "ritualist.paper"
    assert payload["canvas"]["theme"]["validation"]["valid"] is True


def test_invalid_selected_theme_blocks_canvas_render(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_theme(
        tmp_path,
        "bad.theme",
        """
schema: ritualist.theme.v1
id: bad.theme
name: Bad Theme
tokens:
  color.background: not-a-color
""",
    )
    monkeypatch.setattr("ritualist.themes.themes_path", lambda: tmp_path / "themes")
    canvas = CanvasDocument(
        id="bad_theme_canvas",
        name="Bad Theme Canvas",
        theme=CanvasTheme(id="bad.theme", name="Bad Theme"),
    )

    validation = validate_canvas_document(canvas, check_bindings=False)

    assert not validation.valid
    assert any("color.background" in error for error in validation.errors)
    with pytest.raises(RitualistError, match="canvas theme 'bad.theme' is invalid"):
        build_canvas_view_model(
            canvas,
            context=CanvasRuntimeContext(recipe_ids=set(), target_ids=set(), recent_runs=()),
        )


def test_invalid_non_dotted_selected_theme_does_not_fall_back_to_embedded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_theme(
        tmp_path,
        "badtheme",
        """
schema: ritualist.theme.v1
id: badtheme
name: Bad Theme
qml: evil
tokens:
  color.background: "#abcdef"
""",
    )
    monkeypatch.setattr("ritualist.themes.themes_path", lambda: tmp_path / "themes")
    canvas = CanvasDocument(
        id="bad_non_dotted_theme_canvas",
        name="Bad Non-Dotted Theme Canvas",
        theme=CanvasTheme(id="badtheme", name="Bad Theme"),
    )

    validation = validate_canvas_document(canvas, check_bindings=False)

    assert not validation.valid
    assert any("invalid theme" in error for error in validation.errors)
    with pytest.raises(RitualistError, match="canvas theme 'badtheme' is invalid"):
        build_canvas_view_model(
            canvas,
            context=CanvasRuntimeContext(recipe_ids=set(), target_ids=set(), recent_runs=()),
        )


def test_partial_selected_theme_uses_app_defaults_and_missing_asset_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_theme(
        tmp_path,
        "partial.theme",
        """
schema: ritualist.theme.v1
id: partial.theme
name: Partial Theme
tokens:
  color.background: "#abcdef"
assets:
  hero: assets/missing.png
""",
    )
    monkeypatch.setattr("ritualist.themes.themes_path", lambda: tmp_path / "themes")
    canvas = CanvasDocument(
        id="partial_theme_canvas",
        name="Partial Theme Canvas",
        theme=CanvasTheme(id="partial.theme", name="Partial Theme"),
    )

    payload = build_canvas_view_model(
        canvas,
        context=CanvasRuntimeContext(recipe_ids=set(), target_ids=set(), recent_runs=()),
    ).to_dict()
    theme = payload["canvas"]["theme"]

    assert theme["validation"]["valid"] is True
    assert theme["tokens"]["background"] == "#abcdef"
    assert theme["tokens"]["panel"] == CanvasThemeTokens().panel
    assert theme["resolved_tokens"]["color.surface"] == APP_DEFAULT_TOKENS["color.surface"]
    assert any("asset file is missing" in warning for warning in theme["warnings"])


def test_existing_sample_canvases_still_validate_with_theme_bridge() -> None:
    for canvas_id in bundled_canvas_ids():
        result = validate_canvas_document(load_canvas(canvas_id), check_bindings=False)
        assert result.valid, (canvas_id, result.errors)


def test_perf_canvas_use_includes_theme_validation_status() -> None:
    result = CliRunner().invoke(app, ["perf", "canvas-use", "--mock-components", "6", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["view_summary"]["theme_id"] == "ritualist_default"
    assert payload["view_summary"]["theme_validation"]["valid"] is True


def _write_theme(tmp_path: Path, theme_id: str, text: str) -> None:
    root = tmp_path / "themes" / theme_id.replace(".", "-")
    root.mkdir(parents=True)
    (root / "theme.yaml").write_text(text.strip() + "\n", encoding="utf-8")
