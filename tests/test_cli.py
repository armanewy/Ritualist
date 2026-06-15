from __future__ import annotations

from typer.testing import CliRunner

from ritualist.adapters.fake import FakeAdapters
from ritualist.app_setup import InitReport, MigrationResult
from ritualist.cli import app
from ritualist.errors import DependencyMissingError
from ritualist.models import Recipe
from ritualist.run_logs import ReconciledRun, RunRecord
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


def test_init_prints_created_copied_and_migrated_report(tmp_path, monkeypatch):
    report = InitReport(
        paths={
            "app_data": tmp_path,
            "config": tmp_path / "config",
            "recipes": tmp_path / "recipes",
            "logs": tmp_path / "logs",
            "runs": tmp_path / "runs",
            "browser_profiles": tmp_path / "browser-profiles",
        },
        created_dirs={
            "config": tmp_path / "config",
            "recipes": tmp_path / "recipes",
            "logs": tmp_path / "logs",
            "runs": tmp_path / "runs",
            "browser_profiles": tmp_path / "browser-profiles",
        },
        config_created=True,
        sample_copied=True,
        migration=MigrationResult(
            recipe_path=tmp_path / "recipes" / "gaming_mode.yaml",
            changed=True,
            changes=["added keep_open: true to first browser.open step"],
        ),
    )
    monkeypatch.setattr("ritualist.cli.initialize_app", lambda: report)

    result = CliRunner().invoke(app, ["init"])

    assert result.exit_code == 0
    assert "Created config directory" in result.output
    assert "Copied bundled gaming_mode sample" in result.output
    assert "added keep_open: true to first browser.open step" in result.output


def test_init_prints_noop_report(tmp_path, monkeypatch):
    report = InitReport(
        paths={"app_data": tmp_path},
        created_dirs={},
        config_created=False,
        sample_copied=False,
        migration=MigrationResult(
            recipe_path=tmp_path / "recipes" / "gaming_mode.yaml",
            changed=False,
        ),
    )
    monkeypatch.setattr("ritualist.cli.initialize_app", lambda: report)

    result = CliRunner().invoke(app, ["init"])

    assert result.exit_code == 0
    assert "Initialization is already up to date" in result.output


def test_runs_lists_recent_run_records(tmp_path, monkeypatch):
    record = RunRecord(
        run_id="20260615T120000Z_gaming_mode",
        path=tmp_path / "20260615T120000Z_gaming_mode",
        metadata={
            "recipe_id": "gaming_mode",
            "status": "stopped",
            "started_at": "2026-06-15T12:00:00+00:00",
            "steps_completed": 3,
            "steps_total": 4,
        },
        steps=[],
    )
    monkeypatch.setattr("ritualist.cli.reconcile_running_runs", lambda **_kwargs: [])
    monkeypatch.setattr("ritualist.cli.list_recent_runs", lambda *, limit: [record])

    result = CliRunner().invoke(app, ["runs", "--limit", "1"])

    assert result.exit_code == 0
    assert "20260615T120000Z_gaming_mode" in result.output
    assert "gaming_mode" in result.output
    assert "stopped" in result.output


def test_runs_repairs_and_reports_interrupted_records(tmp_path, monkeypatch):
    run_path = tmp_path / "20260615T175148Z_gaming_mode"
    record = RunRecord(
        run_id="20260615T175148Z_gaming_mode",
        path=run_path,
        metadata={
            "recipe_id": "gaming_mode",
            "status": "interrupted",
            "started_at": "2026-06-15T17:51:48+00:00",
            "steps_completed": 6,
            "steps_total": 7,
        },
        steps=[],
    )
    monkeypatch.setattr(
        "ritualist.cli.reconcile_running_runs",
        lambda **_kwargs: [
            ReconciledRun(
                run_id="20260615T175148Z_gaming_mode",
                path=run_path,
                message="Ritualist exited before finalizing this run.",
            )
        ],
    )
    monkeypatch.setattr("ritualist.cli.list_recent_runs", lambda *, limit: [record])

    result = CliRunner().invoke(app, ["runs"])

    assert result.exit_code == 0
    assert "Marked 20260615T175148Z_gaming_mode as interrupted." in result.output
    assert "interrupted" in result.output


def test_show_run_prints_summary_and_steps(tmp_path, monkeypatch):
    record = RunRecord(
        run_id="20260615T120000Z_gaming_mode",
        path=tmp_path / "20260615T120000Z_gaming_mode",
        metadata={
            "recipe_id": "gaming_mode",
            "recipe_name": "Gaming Mode",
            "status": "interrupted",
            "dry_run": False,
            "started_at": "2026-06-15T12:00:00+00:00",
            "ended_at": "2026-06-15T12:01:00+00:00",
            "final_message": "Ritualist exited before finalizing this run.",
        },
        steps=[
            {
                "index": 1,
                "status": "success",
                "step_name": "Open music",
                "action": "browser.open",
                "message": "opened URL",
            }
        ],
    )
    monkeypatch.setattr("ritualist.cli.reconcile_running_runs", lambda **_kwargs: [])
    monkeypatch.setattr("ritualist.cli.load_run", lambda ref: record)

    result = CliRunner().invoke(app, ["show-run", "20260615T120000Z_gaming_mode"])

    assert result.exit_code == 0
    assert "Gaming Mode" in result.output
    assert "interrupted" in result.output
    assert "Ritualist exited before finalizing this run." in result.output
    assert "Open music" in result.output
    assert "opened URL" in result.output


def test_show_run_exits_one_for_unknown_run(monkeypatch):
    monkeypatch.setattr("ritualist.cli.reconcile_running_runs", lambda **_kwargs: [])
    monkeypatch.setattr("ritualist.cli.load_run", lambda ref: None)

    result = CliRunner().invoke(app, ["show-run", "missing-run"])

    assert result.exit_code == 1
    assert "run not found" in result.output


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


def test_doctor_reports_assertion_checks(monkeypatch):
    recipe = Recipe.model_validate(
        {
            "id": "runbook",
            "name": "Runbook",
            "preflight": [
                {"action": "assert.process_running", "process_name": "demo.exe"},
                {"action": "assert.file_exists", "path": "C:/demo/profile.json"},
            ],
            "steps": [{"action": "app.launch", "command": "demo.exe"}],
            "verify": [
                {
                    "action": "assert.window_text_visible",
                    "window_title_contains": "Vendor App",
                    "text": "Connected",
                },
                {"action": "assert.browser_text_visible", "text": "Ready"},
            ],
        }
    )
    monkeypatch.setattr("ritualist.cli.load_recipe_reference", lambda *_args, **_kwargs: recipe)
    monkeypatch.setattr("ritualist.doctor.sys.platform", "win32")
    monkeypatch.setattr("ritualist.doctor.importlib.util.find_spec", lambda name: object())

    result = CliRunner().invoke(app, ["doctor", "runbook"])

    assert result.exit_code == 0
    assert "assert.window_text_visible" in result.output
    assert "Connected" in result.output
    assert "assert.browser_text_visible" in result.output
    assert "psutil import works" in result.output


def test_doctor_warns_when_browser_assertion_has_no_browser_open(monkeypatch):
    recipe = Recipe.model_validate(
        {
            "id": "runbook",
            "name": "Runbook",
            "steps": [{"action": "app.launch", "command": "demo.exe"}],
            "verify": [{"action": "assert.browser_text_visible", "text": "Ready"}],
        }
    )
    monkeypatch.setattr("ritualist.cli.load_recipe_reference", lambda *_args, **_kwargs: recipe)
    monkeypatch.setattr("ritualist.doctor.importlib.util.find_spec", lambda name: object())

    result = CliRunner().invoke(app, ["doctor", "runbook"])

    assert result.exit_code == 0
    assert "assert.browser_text_visible" in result.output
    assert "browser.open" in result.output


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
    assert "Window: Battle.net" in result.output
    assert "Target: Play" in result.output
    assert "Confirmation declined; no confirmed risky action was performed." in result.output


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
