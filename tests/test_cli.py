from __future__ import annotations

from typer.testing import CliRunner

from ritualist.adapters.fake import FakeAdapters
from ritualist.cli import app
from ritualist.errors import DependencyMissingError
from ritualist.models import Recipe
from ritualist.adapters.windows_uia import WindowInspection


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


def test_inspect_window_help_works():
    result = CliRunner().invoke(app, ["inspect-window", "--help"])

    assert result.exit_code == 0
    assert "inspect-window" in result.output


def test_doctor_help_works():
    result = CliRunner().invoke(app, ["doctor", "--help"])

    assert result.exit_code == 0
    assert "recipe" in result.output


def test_inspect_window_prints_labels(monkeypatch):
    def inspect(self, *, title_contains: str, limit: int, control_type: str | None):
        assert title_contains == "Battle.net"
        assert limit == 2
        assert control_type == "Button"
        return [WindowInspection(title="Battle.net", labels=["Diablo IV", "Play"])]

    monkeypatch.setattr(
        "ritualist.adapters.windows_uia.WindowsUIAutomationAdapter.inspect_windows",
        inspect,
    )

    result = CliRunner().invoke(
        app,
        ["inspect-window", "Battle.net", "--limit", "2", "--control-type", "Button"],
    )

    assert result.exit_code == 0
    assert "Window:" in result.output
    assert "Diablo IV" in result.output
    assert "Play" in result.output


def test_inspect_window_prints_json(monkeypatch):
    monkeypatch.setattr(
        "ritualist.adapters.windows_uia.WindowsUIAutomationAdapter.inspect_windows",
        lambda *_args, **_kwargs: [WindowInspection(title="Battle.net", labels=["Play"])],
    )

    result = CliRunner().invoke(app, ["inspect-window", "Battle.net", "--json"])

    assert result.exit_code == 0
    assert '"title": "Battle.net"' in result.output
    assert '"Play"' in result.output


def test_doctor_reports_recipe_checks(tmp_path, monkeypatch):
    app_path = tmp_path / "Battle.net Launcher.exe"
    app_path.write_text("", encoding="utf-8")
    recipe = Recipe.model_validate(
        {
            "id": "gaming_mode",
            "name": "Gaming Mode",
            "steps": [
                {
                    "action": "browser.open",
                    "url": "https://example.test",
                    "profile": "gaming_mode",
                },
                {"action": "app.launch", "command": str(app_path)},
                {
                    "action": "desktop.click_text",
                    "text": "Play",
                    "window_title_contains": "Battle.net",
                    "requires_confirmation": True,
                },
            ],
        }
    )

    monkeypatch.setattr("ritualist.cli.load_recipe_reference", lambda *_args, **_kwargs: recipe)
    monkeypatch.setattr("ritualist.doctor.browser_profiles_dir", lambda: tmp_path / "profiles")
    monkeypatch.setattr("ritualist.doctor.sys.platform", "win32")
    monkeypatch.setattr(
        "ritualist.doctor.importlib.util.find_spec",
        lambda name: object(),
    )

    result = CliRunner().invoke(app, ["doctor", "gaming_mode"])

    assert result.exit_code == 0
    assert "Playwright import works" in result.output
    assert "path exists" in result.output
    assert "target window contains" in result.output


def test_doctor_fails_on_error_and_preserves_dependency_extras(monkeypatch):
    recipe = Recipe.model_validate(
        {
            "id": "gaming_mode",
            "name": "Gaming Mode",
            "steps": [{"action": "browser.open", "url": "https://example.test"}],
        }
    )
    monkeypatch.setattr("ritualist.cli.load_recipe_reference", lambda *_args, **_kwargs: recipe)
    monkeypatch.setattr("ritualist.doctor.importlib.util.find_spec", lambda name: None)

    result = CliRunner().invoke(app, ["doctor", "gaming_mode"])

    assert result.exit_code == 1
    assert "ritualist[browser]" in result.output


def test_doctor_no_strict_prints_errors_but_exits_zero(monkeypatch):
    recipe = Recipe.model_validate(
        {
            "id": "gaming_mode",
            "name": "Gaming Mode",
            "steps": [{"action": "browser.open", "url": "https://example.test"}],
        }
    )
    monkeypatch.setattr("ritualist.cli.load_recipe_reference", lambda *_args, **_kwargs: recipe)
    monkeypatch.setattr("ritualist.doctor.importlib.util.find_spec", lambda name: None)

    result = CliRunner().invoke(app, ["doctor", "gaming_mode", "--no-strict"])

    assert result.exit_code == 0
    assert "ritualist[browser]" in result.output


def test_successful_run_with_keep_open_recipe_requests_keep_alive(monkeypatch):
    fakes = FakeAdapters()
    recipe = Recipe.model_validate(
        {
            "id": "demo",
            "name": "Demo",
            "steps": [
                {
                    "action": "browser.open",
                    "url": "https://example.test",
                    "keep_open": True,
                }
            ],
        }
    )
    called = []
    monkeypatch.setattr("ritualist.cli.load_recipe_reference", lambda *_args, **_kwargs: recipe)
    monkeypatch.setattr("ritualist.cli.create_default_adapters", lambda: fakes.bundle())
    monkeypatch.setattr("ritualist.cli.RunLogWriter", DummyRunLogWriter)
    monkeypatch.setattr("ritualist.cli._keep_alive_until_interrupted", lambda: called.append(True))

    result = CliRunner().invoke(app, ["run", "demo"])

    assert result.exit_code == 0
    assert called == [True]


def test_failed_later_step_after_keep_open_browser_keeps_alive(monkeypatch):
    fakes = FakeAdapters()
    fakes.shell.failures["launch"] = RuntimeError("boom")
    recipe = Recipe.model_validate(
        {
            "id": "demo",
            "name": "Demo",
            "steps": [
                {
                    "action": "browser.open",
                    "url": "https://example.test",
                    "keep_open": True,
                },
                {"action": "app.launch", "command": "demo.exe"},
            ],
        }
    )
    called = []
    monkeypatch.setattr("ritualist.cli.load_recipe_reference", lambda *_args, **_kwargs: recipe)
    monkeypatch.setattr("ritualist.cli.create_default_adapters", lambda: fakes.bundle())
    monkeypatch.setattr("ritualist.cli.RunLogWriter", DummyRunLogWriter)
    monkeypatch.setattr("ritualist.cli._keep_alive_until_interrupted", lambda: called.append(True))

    result = CliRunner().invoke(app, ["run", "demo"])

    assert result.exit_code == 1
    assert called == [True]


def test_cancelled_final_confirmation_after_keep_open_browser_keeps_alive(monkeypatch):
    fakes = FakeAdapters()
    recipe = Recipe.model_validate(
        {
            "id": "demo",
            "name": "Demo",
            "steps": [
                {
                    "action": "browser.open",
                    "url": "https://example.test",
                    "keep_open": True,
                },
                {
                    "action": "desktop.click_text",
                    "text": "Play",
                    "window_title_contains": "Battle.net",
                    "requires_confirmation": True,
                },
            ],
        }
    )
    called = []
    monkeypatch.setattr("ritualist.cli.load_recipe_reference", lambda *_args, **_kwargs: recipe)
    monkeypatch.setattr("ritualist.cli.create_default_adapters", lambda: fakes.bundle())
    monkeypatch.setattr("ritualist.cli.RunLogWriter", DummyRunLogWriter)
    monkeypatch.setattr("ritualist.cli._keep_alive_until_interrupted", lambda: called.append(True))

    result = CliRunner().invoke(app, ["run", "demo"], input="n\n")

    assert result.exit_code == 1
    assert called == [True]
    assert fakes.desktop.calls == []


def test_dry_run_never_keeps_alive(monkeypatch):
    fakes = FakeAdapters()
    recipe = Recipe.model_validate(
        {
            "id": "demo",
            "name": "Demo",
            "steps": [
                {
                    "action": "browser.open",
                    "url": "https://example.test",
                    "keep_open": True,
                }
            ],
        }
    )
    called = []
    monkeypatch.setattr("ritualist.cli.load_recipe_reference", lambda *_args, **_kwargs: recipe)
    monkeypatch.setattr("ritualist.cli.create_default_adapters", lambda: fakes.bundle())
    monkeypatch.setattr("ritualist.cli.RunLogWriter", DummyRunLogWriter)
    monkeypatch.setattr("ritualist.cli._keep_alive_until_interrupted", lambda: called.append(True))

    result = CliRunner().invoke(app, ["dry-run", "demo"])

    assert result.exit_code == 0
    assert called == []


def test_keep_alive_option_runs_even_after_failure(monkeypatch):
    fakes = FakeAdapters()
    fakes.shell.failures["launch"] = RuntimeError("boom")
    recipe = Recipe.model_validate(
        {
            "id": "demo",
            "name": "Demo",
            "steps": [{"action": "app.launch", "command": "demo.exe"}],
        }
    )
    called = []
    monkeypatch.setattr("ritualist.cli.load_recipe_reference", lambda *_args, **_kwargs: recipe)
    monkeypatch.setattr("ritualist.cli.create_default_adapters", lambda: fakes.bundle())
    monkeypatch.setattr("ritualist.cli.RunLogWriter", DummyRunLogWriter)
    monkeypatch.setattr("ritualist.cli._keep_alive_until_interrupted", lambda: called.append(True))

    result = CliRunner().invoke(app, ["run", "demo", "--keep-alive"])

    assert result.exit_code == 1
    assert called == [True]
