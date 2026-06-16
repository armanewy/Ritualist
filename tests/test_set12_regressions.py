from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile

import yaml
from typer.testing import CliRunner

from ritualist.adapters.fake import FakeAdapters
from ritualist.cli import app
from ritualist.executor import WorkflowExecutor
from ritualist.home import HomeRunHistoryCache, load_installed_home_cards
from ritualist.models import Recipe
from ritualist.packs import (
    MANIFEST_NAME,
    PACK_SCHEMA_V1,
    RECIPE_NAME,
    import_pack,
)
from ritualist.recipe_loader import load_recipe
from ritualist.run_logs import RunLogWriter, list_recent_runs, load_run, reconcile_running_runs
from ritualist.runtime_control import RuntimeControl


def test_bundled_gaming_mode_validates_and_dry_runs_without_adapters(tmp_path, monkeypatch):
    sample_path = _gaming_mode_sample_path()
    fakes = FakeAdapters()
    writers = []

    def writer_factory():
        writer = RunLogWriter(base_dir=tmp_path / "runs")
        writers.append(writer)
        return writer

    monkeypatch.setattr("ritualist.cli.create_default_adapters", lambda: fakes.bundle())
    monkeypatch.setattr("ritualist.cli.RunLogWriter", writer_factory)

    validate_result = CliRunner().invoke(app, ["validate", str(sample_path)])
    dry_run_result = CliRunner().invoke(app, ["dry-run", str(sample_path)])

    assert validate_result.exit_code == 0, validate_result.output
    assert "Gaming Mode" in validate_result.output
    assert "Ask before clicking Play" in validate_result.output
    assert "Recipe is valid." in validate_result.output

    assert dry_run_result.exit_code == 0, dry_run_result.output
    assert "dry-run" in dry_run_result.output
    assert "Keep-open: inactive" in dry_run_result.output
    assert fakes.browser.calls == []
    assert fakes.window.calls == []
    assert fakes.shell.calls == []
    assert fakes.desktop.calls == []
    assert writers and writers[0].run_dir is not None
    steps = _read_steps(writers[0].run_dir)
    assert len(steps) == 7
    assert {step["status"] for step in steps} == {"dry-run"}


def test_bundled_gaming_mode_doctor_json_reports_healthy_when_dependencies_are_available(
    tmp_path,
    monkeypatch,
):
    app_path = tmp_path / "Battle.net Launcher.exe"
    app_path.write_text("", encoding="utf-8")
    profile_root = tmp_path / "profiles"
    profile_root.mkdir()
    window_calls = []
    label_calls = []

    monkeypatch.setattr("ritualist.doctor.browser_profiles_dir", lambda: profile_root)
    monkeypatch.setattr("ritualist.doctor.sys.platform", "win32")
    monkeypatch.setattr("ritualist.doctor.importlib.util.find_spec", lambda _name: object())
    monkeypatch.setattr(
        "ritualist.adapters.window_manager.WindowsWindowManager.window_exists",
        lambda self, **kwargs: window_calls.append(kwargs) or True,
    )
    monkeypatch.setattr(
        "ritualist.adapters.windows_uia.WindowsUIAutomationAdapter.text_visible",
        lambda self, **kwargs: label_calls.append(kwargs) or True,
    )

    result = CliRunner().invoke(
        app,
        [
            "doctor",
            str(_gaming_mode_sample_path()),
            "--json",
            "--var",
            f"battle_net_path={app_path}",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema_version"] == "doctor.v2"
    assert payload["recipe_id"] == "gaming_mode"
    assert payload["compatibility"] == {
        "status": "compatible",
        "errors_count": 0,
        "warnings_count": 0,
    }
    assert "desktop.click_text" in {action["action_name"] for action in payload["actions"]}
    assert window_calls[0]["title_contains"] == "Battle.net"
    assert label_calls[0]["text"] == "Play"


def test_runs_show_run_and_interrupted_repair_use_local_run_logs(tmp_path, monkeypatch):
    runs_root = tmp_path / "runs"
    run_dir = runs_root / "20260615T175148Z_gaming_mode"
    run_dir.mkdir(parents=True)
    _write_run_metadata(
        run_dir,
        {
            "recipe_id": "gaming_mode",
            "recipe_name": "Gaming Mode",
            "dry_run": False,
            "status": "running",
            "process_id": 424242,
            "process_start_time": 1.0,
            "started_at": "2026-06-15T17:51:48+00:00",
            "ended_at": None,
            "last_heartbeat_at": datetime.now(timezone.utc).isoformat(),
            "last_step_id": 1,
            "last_step_name": "Open ambience video",
            "current_run_state": "running",
            "current_step_state": "success",
            "final_state": None,
            "run_state_history": [],
            "event_summaries": [],
            "steps_completed": 1,
            "steps_total": 7,
        },
    )
    _write_steps(
        run_dir,
        [
            {
                "index": 1,
                "step_name": "Open ambience video",
                "action": "browser.open",
                "status": "success",
                "message": "opened URL",
                "phase": "steps",
            }
        ],
    )

    def repair_runs(**kwargs):
        return reconcile_running_runs(
            base_dir=runs_root,
            process_checker=lambda _pid: (False, None),
            **kwargs,
        )

    monkeypatch.setattr("ritualist.cli.reconcile_running_runs", repair_runs)
    monkeypatch.setattr(
        "ritualist.cli.list_recent_runs",
        lambda *, limit: list_recent_runs(limit=limit, base_dir=runs_root),
    )
    monkeypatch.setattr(
        "ritualist.cli.load_run",
        lambda ref: load_run(ref, base_dir=runs_root),
    )

    runs_result = CliRunner().invoke(app, ["runs", "--limit", "1"])
    show_result = CliRunner().invoke(app, ["show-run", run_dir.name])

    assert runs_result.exit_code == 0, runs_result.output
    assert "Marked 20260615T175148Z_gaming_mode as interrupted." in runs_result.output
    assert "gaming_mode" in runs_result.output
    assert "interrupted" in runs_result.output
    repaired_metadata = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert repaired_metadata["status"] == "interrupted"
    assert repaired_metadata["final_state"] == "interrupted"
    assert repaired_metadata["interruption_reason"] == "recorded process 424242 is not running"

    assert show_result.exit_code == 0, show_result.output
    assert "Runbook summary:" in show_result.output
    assert "Final status: interrupted" in show_result.output
    assert "Stopped/interrupted: interrupted" in show_result.output
    assert "Open ambience video" in show_result.output


def test_bundled_gaming_mode_keep_open_survives_declined_play_confirmation(
    tmp_path,
    monkeypatch,
):
    fakes = FakeAdapters()
    keep_alive_calls = []

    monkeypatch.setattr("ritualist.cli.create_default_adapters", lambda: fakes.bundle())
    monkeypatch.setattr(
        "ritualist.cli.RunLogWriter",
        lambda: RunLogWriter(base_dir=tmp_path / "runs"),
    )
    monkeypatch.setattr(
        "ritualist.cli._keep_alive_until_interrupted",
        lambda: keep_alive_calls.append(True),
    )

    result = CliRunner().invoke(app, ["run", str(_gaming_mode_sample_path())], input="n\n")

    assert result.exit_code == 1
    assert keep_alive_calls == [True]
    assert fakes.browser.calls[0][0] == "open_url"
    assert fakes.browser.calls[0][2]["keep_open"] is True
    assert [call[2]["text"] for call in fakes.desktop.calls] == ["Diablo IV"]
    assert "Target: Play" in result.output
    assert "Confirmation declined; no confirmed risky action was performed." in result.output


def test_bundled_gaming_mode_generates_home_card_from_sample_metadata(tmp_path):
    recipe = load_recipe(_gaming_mode_sample_path())
    cards = load_installed_home_cards(
        recipe_rows=[(_gaming_mode_sample_path(), recipe, None)],
        run_history_cache=HomeRunHistoryCache(base_dir=tmp_path / "runs"),
    )

    assert len(cards) == 1
    card = cards[0]
    assert card.id == "gaming_mode"
    assert card.title == "Diablo IV Night"
    assert card.category == "Gaming"
    assert card.subtitle == "YouTube ambience + Battle.net"
    assert card.description.startswith("Open a looping video")
    assert card.to_qml()["keep_open_active"] == "false"


def test_wait_action_pause_resume_keeps_timeout_budget_and_continues_next_step():
    control = RuntimeControl()
    fakes = FakeAdapters()
    recipe = Recipe.model_validate(
        {
            "id": "pause_resume",
            "name": "Pause Resume",
            "steps": [
                {"action": "wait.seconds", "seconds": 0.12, "timeout_seconds": 0.15},
                {"action": "app.launch", "command": "demo.exe"},
            ],
        }
    )
    result = {}

    thread = threading.Thread(
        target=lambda: result.setdefault(
            "summary",
            WorkflowExecutor(
                adapters=fakes.bundle(),
                runtime_control=control,
            ).run(recipe),
        )
    )
    thread.start()

    time.sleep(0.06)
    control.pause()
    time.sleep(0.2)
    assert thread.is_alive()
    assert fakes.shell.calls == []

    control.resume()
    thread.join(timeout=1.0)

    assert not thread.is_alive()
    assert result["summary"].success
    assert [step.status for step in result["summary"].results] == ["success", "success"]
    assert fakes.shell.calls[0][0] == "launch"


def test_pack_import_quarantines_without_enabling_or_running(tmp_path, monkeypatch):
    imported_root = tmp_path / "imported-packs"
    recipes_root = tmp_path / "recipes"
    pack_path = _write_wait_pack(tmp_path)

    monkeypatch.setattr("ritualist.packs.imported_packs_path", lambda: imported_root)
    monkeypatch.setattr(
        "ritualist.packs.imported_packs_dir",
        lambda: imported_root.mkdir(parents=True, exist_ok=True) or imported_root,
    )
    monkeypatch.setattr(
        "ritualist.packs.recipes_dir",
        lambda: recipes_root.mkdir(parents=True, exist_ok=True) or recipes_root,
    )
    monkeypatch.setattr("ritualist.cli.imported_packs_path", lambda: imported_root)

    record = import_pack(pack_path)

    assert record.status == "disabled"
    assert record.recipe_path.exists()
    assert not (recipes_root / "demo_recipe.yaml").exists()

    def fail_load(*_args, **_kwargs):
        raise AssertionError("quarantined import should be rejected before recipe loading")

    monkeypatch.setattr("ritualist.cli.load_recipe_reference", fail_load)
    result = CliRunner().invoke(app, ["run", str(record.recipe_path)])

    assert result.exit_code == 1
    assert "quarantined imported recipes cannot be run directly" in result.output


def _gaming_mode_sample_path() -> Path:
    return Path(__file__).resolve().parents[1] / "ritualist" / "sample_recipes" / "gaming_mode.yaml"


def _read_steps(run_dir: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in (run_dir / "steps.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _write_run_metadata(run_dir: Path, metadata: dict[str, object]) -> None:
    (run_dir / "run.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _write_steps(run_dir: Path, steps: list[dict[str, object]]) -> None:
    (run_dir / "steps.jsonl").write_text(
        "".join(json.dumps(step, ensure_ascii=False) + "\n" for step in steps),
        encoding="utf-8",
    )


def _write_wait_pack(tmp_path: Path) -> Path:
    path = tmp_path / "demo.ritualistpack"
    with ZipFile(path, "w") as archive:
        archive.writestr(
            MANIFEST_NAME,
            yaml.safe_dump(
                {
                    "schema": PACK_SCHEMA_V1,
                    "id": "demo_pack",
                    "name": "Demo Pack",
                    "version": "1.0.0",
                    "required_ritualist_version": ">=0.1.0-alpha.1",
                    "supported_os": ["windows", "macos", "linux"],
                    "required_capabilities": [],
                    "required_actions": ["wait.seconds"],
                    "variables": {},
                    "safety": {
                        "no_arbitrary_code": True,
                        "no_coordinate_clicks": True,
                        "no_remote_execution": True,
                        "imported_recipes_must_not_run_automatically": True,
                    },
                },
                sort_keys=False,
            ),
        )
        archive.writestr(
            RECIPE_NAME,
            yaml.safe_dump(
                {
                    "version": "0.1",
                    "id": "demo_recipe",
                    "name": "Demo Recipe",
                    "steps": [{"action": "wait.seconds", "seconds": 0.1}],
                },
                sort_keys=False,
            ),
        )
    return path
