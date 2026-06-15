from __future__ import annotations

from typer.testing import CliRunner

from ritualist.adapters.fake import FakeAdapters
from ritualist.cli import app
from ritualist.errors import DependencyMissingError
from ritualist.models import Recipe


class DummyRunLogWriter:
    run_dir = None

    def start(self, recipe, *, dry_run: bool) -> None:
        self.recipe = recipe
        self.dry_run = dry_run
        self.steps = []

    def write_step(self, result) -> None:
        self.steps.append(result)

    def finish(self, *, success: bool) -> None:
        self.success = success


def test_run_defaults_to_real_run(monkeypatch):
    fakes = FakeAdapters()
    recipe = Recipe.model_validate(
        {
            "id": "demo",
            "name": "Demo",
            "steps": [{"action": "app.launch", "command": "demo.exe"}],
        }
    )
    monkeypatch.setattr("ritualist.cli.load_recipe_reference", lambda *_args, **_kwargs: recipe)
    monkeypatch.setattr("ritualist.cli.create_default_adapters", lambda: fakes.bundle())
    monkeypatch.setattr("ritualist.cli.RunLogWriter", DummyRunLogWriter)

    result = CliRunner().invoke(app, ["run", "demo"])

    assert result.exit_code == 0
    assert fakes.shell.calls[0][0] == "launch"


def test_dry_run_command_does_not_call_adapters(monkeypatch):
    fakes = FakeAdapters()
    recipe = Recipe.model_validate(
        {
            "id": "demo",
            "name": "Demo",
            "steps": [{"action": "app.launch", "command": "demo.exe"}],
        }
    )
    monkeypatch.setattr("ritualist.cli.load_recipe_reference", lambda *_args, **_kwargs: recipe)
    monkeypatch.setattr("ritualist.cli.create_default_adapters", lambda: fakes.bundle())
    monkeypatch.setattr("ritualist.cli.RunLogWriter", DummyRunLogWriter)

    result = CliRunner().invoke(app, ["dry-run", "demo"])

    assert result.exit_code == 0
    assert "dry-run" in result.output
    assert fakes.shell.calls == []


def test_exception_text_is_rich_escaped(monkeypatch):
    def raise_error(*_args, **_kwargs):
        raise DependencyMissingError("install ritualist[gui]")

    monkeypatch.setattr("ritualist.cli.load_recipe_reference", raise_error)

    result = CliRunner().invoke(app, ["validate", "demo"])

    assert result.exit_code == 1
    assert "ritualist[gui]" in result.output
