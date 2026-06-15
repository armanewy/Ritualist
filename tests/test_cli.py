from __future__ import annotations

import json

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


def test_actions_lists_registered_metadata():
    result = CliRunner().invoke(app, ["actions"])

    assert result.exit_code == 0
    assert "Registered Actions" in result.output
    assert "desktop.click_text" in result.output
    assert "required_for_play" in result.output


def test_actions_prints_json_metadata():
    result = CliRunner().invoke(app, ["actions", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    click_text = next(item for item in data if item["action_name"] == "desktop.click_text")
    assert click_text["schema_version"] == "0.1"
    assert click_text["category"] == "desktop"
    assert click_text["supported_platforms"] == ["windows"]
    assert click_text["side_effect_level"] == "risky"
    assert click_text["confirmation_policy"] == "required_for_play"
    assert click_text["allowed_in_imported_packs"] is False


def test_perf_load_recipes_prints_duration_and_counts(tmp_path, monkeypatch):
    recipe = Recipe.model_validate(
        {
            "id": "demo",
            "name": "Demo",
            "steps": [{"action": "app.launch", "command": "demo.exe"}],
        }
    )
    monkeypatch.setattr(
        "ritualist.cli.discover_recipes",
        lambda: [(tmp_path / "demo.yaml", recipe, None)],
    )

    result = CliRunner().invoke(app, ["perf", "load-recipes"])

    assert result.exit_code == 0
    assert "duration_ms:" in result.output
    assert "recipes: 1" in result.output
    assert "valid: 1" in result.output


def test_perf_doctor_json_is_valid(tmp_path, monkeypatch):
    app_path = tmp_path / "demo.exe"
    app_path.write_text("", encoding="utf-8")
    recipe = Recipe.model_validate(
        {
            "id": "demo",
            "name": "Demo",
            "steps": [{"action": "app.launch", "command": str(app_path)}],
        }
    )
    monkeypatch.setattr(
        "ritualist.cli.load_recipe_for_diagnostics",
        lambda *_args, **_kwargs: (recipe, {}, []),
    )

    result = CliRunner().invoke(app, ["perf", "doctor", "demo", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["operation"] == "perf.doctor"
    assert data["recipe_id"] == "demo"
    assert data["duration_ms"] >= 0
    assert data["counts"]["checks"] >= 1


def test_perf_list_runs_json_counts_steps(tmp_path, monkeypatch):
    record = RunRecord(
        run_id="20260615T120000Z_demo",
        path=tmp_path / "20260615T120000Z_demo",
        metadata={"recipe_id": "demo", "status": "success"},
        steps=[{"index": 1, "status": "success"}],
    )
    monkeypatch.setattr("ritualist.cli.list_recent_runs", lambda *, limit: [record])

    result = CliRunner().invoke(app, ["perf", "list-runs", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["operation"] == "perf.list-runs"
    assert data["counts"]["runs"] == 1
    assert data["counts"]["steps"] == 1
    assert data["runs"][0]["run_id"] == "20260615T120000Z_demo"


def test_perf_fake_run_uses_fake_adapters_and_confirms(monkeypatch):
    fakes = FakeAdapters()
    recipe = Recipe.model_validate(
        {
            "id": "demo",
            "name": "Demo",
            "steps": [
                {"action": "browser.open", "url": "https://example.test"},
                {"action": "app.launch", "command": "demo.exe"},
                {
                    "action": "desktop.click_text",
                    "text": "Play",
                    "window_title_contains": "Demo",
                    "requires_confirmation": True,
                },
            ],
        }
    )
    monkeypatch.setattr("ritualist.cli.load_recipe_reference", lambda *_args, **_kwargs: recipe)
    monkeypatch.setattr("ritualist.cli.FakeAdapters", lambda: fakes)

    result = CliRunner().invoke(app, ["perf", "fake-run", "demo", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["operation"] == "perf.fake-run"
    assert data["success"] is True
    assert data["counts"]["steps_completed"] == 3
    assert data["counts"]["confirmations"] == 1
    assert data["counts"]["browser_calls"] == 1
    assert data["counts"]["shell_calls"] == 1
    assert data["counts"]["desktop_calls"] == 1
    assert fakes.browser.calls[0][0] == "open_url"
    assert fakes.shell.calls[0][0] == "launch"
    assert fakes.desktop.calls[0][0] == "click_text"


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

    monkeypatch.setattr(
        "ritualist.cli.load_recipe_for_diagnostics",
        lambda *_args, **_kwargs: (recipe, {}, []),
    )
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
    monkeypatch.setattr(
        "ritualist.cli.load_recipe_for_diagnostics",
        lambda *_args, **_kwargs: (recipe, {}, []),
    )
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
    monkeypatch.setattr(
        "ritualist.cli.load_recipe_for_diagnostics",
        lambda *_args, **_kwargs: (recipe, {}, []),
    )
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


def test_doctor_json_outputs_stable_shape(monkeypatch):
    recipe = Recipe.model_validate(
        {
            "id": "runbook",
            "name": "Runbook",
            "variables": {"app_path": "demo.exe"},
            "environment": {"required_capabilities": ["app_launch"]},
            "steps": [{"action": "app.launch", "command": "demo.exe"}],
        }
    )
    monkeypatch.setattr(
        "ritualist.cli.load_recipe_for_diagnostics",
        lambda *_args, **_kwargs: (recipe, {}, []),
    )

    result = CliRunner().invoke(app, ["doctor", "runbook", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert set(data) == {
        "schema_version",
        "recipe_id",
        "recipe_name",
        "compatibility",
        "checks",
        "capabilities",
        "variables",
        "actions",
        "environment",
    }
    assert data["schema_version"] == "doctor.v2"
    assert data["recipe_id"] == "runbook"
    assert data["recipe_name"] == "Runbook"
    assert data["compatibility"]["status"] == "compatible"
    assert data["compatibility"]["errors_count"] == 0
    assert data["compatibility"]["warnings_count"] == 0
    assert {check["status"] for check in data["checks"]} == {"ok"}
    assert {"id", "category", "status", "message", "details"} <= set(data["checks"][0])
    assert data["capabilities"] == [
        {
            "id": "app_launch",
            "status": "ok",
            "message": "local app launch is available through the OS",
            "details": {"capability": "app_launch"},
        }
    ]
    assert data["variables"] == [
        {
            "name": "app_path",
            "status": "configured",
            "details": {"has_recipe_default": True, "hint": None},
        }
    ]
    assert data["actions"][0]["action"] == "app.launch"
    assert data["environment"]["current_os"] in {"windows", "macos", "linux"}
    assert data["environment"]["required_capabilities"] == ["app_launch"]


def test_doctor_json_reports_warning_status_and_counts(monkeypatch):
    recipe = Recipe.model_validate(
        {
            "id": "runbook",
            "name": "Runbook",
            "steps": [{"action": "app.launch", "command": "demo.exe"}],
            "verify": [{"action": "assert.browser_text_visible", "text": "Ready"}],
        }
    )
    monkeypatch.setattr(
        "ritualist.cli.load_recipe_for_diagnostics",
        lambda *_args, **_kwargs: (recipe, {}, []),
    )
    monkeypatch.setattr("ritualist.doctor.importlib.util.find_spec", lambda name: object())

    result = CliRunner().invoke(app, ["doctor", "runbook", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["compatibility"] == {
        "status": "compatible_with_warnings",
        "errors_count": 0,
        "warnings_count": 1,
    }
    assert "warning" in {check["status"] for check in data["checks"]}


def test_doctor_reports_supported_environment_os(monkeypatch):
    recipe = Recipe.model_validate(
        {
            "id": "runbook",
            "name": "Runbook",
            "environment": {"os": ["linux"]},
            "steps": [{"action": "app.launch", "command": "demo.exe"}],
        }
    )
    monkeypatch.setattr(
        "ritualist.cli.load_recipe_for_diagnostics",
        lambda *_args, **_kwargs: (recipe, {}, []),
    )
    monkeypatch.setattr("ritualist.doctor.sys.platform", "linux")

    result = CliRunner().invoke(app, ["doctor", "runbook"])

    assert result.exit_code == 0
    assert "current OS linux is allowed" in result.output


def test_doctor_reports_missing_capability(monkeypatch):
    recipe = Recipe.model_validate(
        {
            "id": "runbook",
            "name": "Runbook",
            "environment": {"required_capabilities": ["windows_uia"]},
            "steps": [{"action": "app.launch", "command": "demo.exe"}],
        }
    )
    monkeypatch.setattr(
        "ritualist.cli.load_recipe_for_diagnostics",
        lambda *_args, **_kwargs: (recipe, {}, []),
    )
    monkeypatch.setattr("ritualist.doctor.sys.platform", "linux")

    result = CliRunner().invoke(app, ["doctor", "runbook"])

    assert result.exit_code == 1
    assert "windows_uia" in result.output
    assert "incompatible" in result.output


def test_doctor_reports_environment_required_capability(monkeypatch):
    recipe = Recipe.model_validate(
        {
            "id": "runbook",
            "name": "Runbook",
            "environment": {"required_capabilities": ["playwright"]},
            "steps": [{"action": "app.launch", "command": "demo.exe"}],
        }
    )
    monkeypatch.setattr(
        "ritualist.cli.load_recipe_for_diagnostics",
        lambda *_args, **_kwargs: (recipe, {}, []),
    )
    monkeypatch.setattr(
        "ritualist.doctor.importlib.util.find_spec",
        lambda name: None if name == "playwright.sync_api" else object(),
    )

    result = CliRunner().invoke(app, ["doctor", "runbook"])

    assert result.exit_code == 1
    assert "Playwright import failed" in result.output
    assert "ritualist[browser]" in result.output


def test_doctor_reports_platform_mismatch(monkeypatch):
    recipe = Recipe.model_validate(
        {
            "id": "runbook",
            "name": "Runbook",
            "environment": {"os": ["windows"]},
            "steps": [{"action": "app.launch", "command": "demo.exe"}],
        }
    )
    monkeypatch.setattr(
        "ritualist.cli.load_recipe_for_diagnostics",
        lambda *_args, **_kwargs: (recipe, {}, []),
    )
    monkeypatch.setattr("ritualist.doctor.sys.platform", "linux")

    result = CliRunner().invoke(app, ["doctor", "runbook"])

    assert result.exit_code == 1
    assert "recipe expects OS windows" in result.output


def test_doctor_reports_missing_variable_with_setup_hint(tmp_path, monkeypatch):
    path = tmp_path / "runbook.yaml"
    path.write_text(
        """
version: "0.1"
id: runbook
name: Runbook
environment:
  variable_hints:
    app_path: Set this to your local executable path.
steps:
  - action: app.launch
    command: "${app_path}"
""",
        encoding="utf-8",
    )
    monkeypatch.setattr("ritualist.doctor.sys.platform", "win32")

    result = CliRunner().invoke(app, ["doctor", str(path)])

    assert result.exit_code == 1
    assert "missing variable 'app_path'" in result.output
    assert "Set this to your local executable path." in result.output


def test_doctor_reports_missing_app_path(tmp_path, monkeypatch):
    missing = tmp_path / "missing.exe"
    recipe = Recipe.model_validate(
        {
            "id": "runbook",
            "name": "Runbook",
            "steps": [{"action": "app.launch", "command": str(missing)}],
        }
    )
    monkeypatch.setattr(
        "ritualist.cli.load_recipe_for_diagnostics",
        lambda *_args, **_kwargs: (recipe, {}, []),
    )

    result = CliRunner().invoke(app, ["doctor", "runbook"])

    assert result.exit_code == 1
    assert "path does not exist" in result.output
    assert str(missing) in result.output


def test_doctor_checks_expected_windows_and_labels(monkeypatch):
    recipe = Recipe.model_validate(
        {
            "id": "runbook",
            "name": "Runbook",
            "environment": {
                "expected_windows": [{"title_contains": "Vendor App"}],
                "expected_labels": [
                    {"window_title_contains": "Vendor App", "text": "Connected"}
                ],
            },
            "steps": [{"action": "app.launch", "command": "demo.exe"}],
        }
    )
    window_calls = []
    label_calls = []

    def window_exists(self, **kwargs):
        window_calls.append(kwargs)
        return True

    def text_visible(self, **kwargs):
        label_calls.append(kwargs)
        return True

    monkeypatch.setattr(
        "ritualist.cli.load_recipe_for_diagnostics",
        lambda *_args, **_kwargs: (recipe, {}, []),
    )
    monkeypatch.setattr("ritualist.doctor.sys.platform", "win32")
    monkeypatch.setattr("ritualist.doctor.importlib.util.find_spec", lambda name: object())
    monkeypatch.setattr(
        "ritualist.adapters.window_manager.WindowsWindowManager.window_exists",
        window_exists,
    )
    monkeypatch.setattr(
        "ritualist.adapters.windows_uia.WindowsUIAutomationAdapter.text_visible",
        text_visible,
    )

    result = CliRunner().invoke(app, ["doctor", "runbook"])

    assert result.exit_code == 0
    assert "expected window found: Vendor App" in result.output
    assert "expected label found: 'Connected' in 'Vendor App'" in result.output
    assert window_calls[0]["title_contains"] == "Vendor App"
    assert label_calls[0]["text"] == "Connected"


def test_doctor_expected_label_check_is_side_effect_free(monkeypatch):
    recipe = Recipe.model_validate(
        {
            "id": "runbook",
            "name": "Runbook",
            "environment": {
                "expected_labels": [
                    {"window_title_contains": "Battle.net", "text": "Play"}
                ],
            },
            "steps": [{"action": "app.launch", "command": "demo.exe"}],
        }
    )
    label_calls = []

    def text_visible(self, **kwargs):
        label_calls.append(kwargs)
        return False

    def click_text(self, **kwargs):
        raise AssertionError("doctor must not click expected labels")

    monkeypatch.setattr(
        "ritualist.cli.load_recipe_for_diagnostics",
        lambda *_args, **_kwargs: (recipe, {}, []),
    )
    monkeypatch.setattr("ritualist.doctor.sys.platform", "win32")
    monkeypatch.setattr("ritualist.doctor.importlib.util.find_spec", lambda name: object())
    monkeypatch.setattr(
        "ritualist.adapters.windows_uia.WindowsUIAutomationAdapter.text_visible",
        text_visible,
    )
    monkeypatch.setattr(
        "ritualist.adapters.windows_uia.WindowsUIAutomationAdapter.click_text",
        click_text,
    )

    result = CliRunner().invoke(app, ["doctor", "runbook"])

    assert result.exit_code == 0
    assert "expected label not currently visible: 'Play' in 'Battle.net'" in result.output
    assert label_calls == [
        {
            "text": "Play",
            "window_title_contains": "Battle.net",
            "control_type": None,
            "exact": True,
            "timeout_seconds": 1.0,
        }
    ]


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
