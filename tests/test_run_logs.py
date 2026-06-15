from __future__ import annotations

import json
import os

from ritualist.adapters.fake import FakeAdapters
from ritualist.executor import WorkflowExecutor
from ritualist.models import Recipe
from ritualist.run_logs import RunLogWriter, list_recent_runs, load_run, reconcile_running_runs


def test_run_log_writer_creates_run_files_and_redacts_browser_url(tmp_path):
    recipe = Recipe.model_validate(
        {
            "id": "log_test",
            "name": "Log Test",
            "steps": [
                {"action": "browser.open", "url": "https://example.test/?token=secret"},
                {"action": "app.launch", "command": "demo.exe"},
            ],
        }
    )
    writer = RunLogWriter(base_dir=tmp_path)

    summary = WorkflowExecutor(
        adapters=FakeAdapters().bundle(),
        run_logger=writer,
        confirmer=lambda _: True,
    ).run(recipe)

    assert summary.success
    assert summary.run_dir is not None
    run_json = json.loads((summary.run_dir / "run.json").read_text(encoding="utf-8"))
    steps = [
        json.loads(line)
        for line in (summary.run_dir / "steps.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert run_json["recipe_id"] == "log_test"
    assert run_json["status"] == "success"
    assert run_json["process_id"] == os.getpid()
    assert run_json["run_writer_id"]
    assert run_json["last_heartbeat_at"]
    assert run_json["last_step_id"] == 2
    assert run_json["last_step_name"] == "app.launch"
    assert steps[0]["message"] == "opened URL"
    assert "token=secret" not in (summary.run_dir / "steps.jsonl").read_text(encoding="utf-8")

    loaded = load_run(summary.run_dir)
    assert loaded is not None
    assert loaded.run_id == summary.run_dir.name
    assert loaded.metadata["recipe_id"] == "log_test"
    assert loaded.steps[0]["message"] == "opened URL"

    recent = list_recent_runs(base_dir=tmp_path)
    assert [record.run_id for record in recent] == [summary.run_dir.name]


def test_run_log_writer_redacts_failed_browser_url(tmp_path):
    recipe = Recipe.model_validate(
        {
            "id": "log_test",
            "name": "Log Test",
            "steps": [{"action": "browser.open", "url": "https://example.test/?token=secret"}],
        }
    )
    fakes = FakeAdapters()
    fakes.browser.failures["open_url"] = RuntimeError("failed https://example.test/?token=secret")
    writer = RunLogWriter(base_dir=tmp_path)

    summary = WorkflowExecutor(adapters=fakes.bundle(), run_logger=writer).run(recipe)

    assert not summary.success
    steps_text = (summary.run_dir / "steps.jsonl").read_text(encoding="utf-8")
    assert "browser.open did not complete" in steps_text
    assert "token=secret" not in steps_text


def test_reconcile_running_run_with_dead_pid_marks_interrupted_and_keeps_steps(tmp_path):
    run_dir = tmp_path / "20260615T175148Z_gaming_mode"
    run_dir.mkdir()
    metadata = {
        "recipe_id": "gaming_mode",
        "recipe_name": "Gaming Mode",
        "status": "running",
        "process_id": 999999,
        "process_start_time": 1.0,
        "started_at": "2026-06-15T17:51:48+00:00",
        "last_heartbeat_at": "2026-06-15T17:51:48+00:00",
        "last_step_id": 7,
        "last_step_name": "Ask before clicking Play",
        "steps_total": 7,
        "steps_completed": 6,
    }
    (run_dir / "run.json").write_text(json.dumps(metadata), encoding="utf-8")
    steps_text = '{"index": 6, "step_name": "Select Diablo IV"}\n'
    (run_dir / "steps.jsonl").write_text(steps_text, encoding="utf-8")

    repaired = reconcile_running_runs(
        base_dir=tmp_path,
        process_checker=lambda pid: (False, None),
    )

    assert [repair.run_id for repair in repaired] == ["20260615T175148Z_gaming_mode"]
    updated = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert updated["status"] == "interrupted"
    assert updated["final_message"] == (
        "Ritualist exited before finalizing this run. "
        "Last recorded step: Ask before clicking Play."
    )
    assert (run_dir / "steps.jsonl").read_text(encoding="utf-8") == steps_text


def test_reconcile_running_run_with_active_pid_is_left_running(tmp_path):
    run_dir = tmp_path / "20260615T180000Z_gaming_mode"
    run_dir.mkdir()
    metadata = {
        "recipe_id": "gaming_mode",
        "recipe_name": "Gaming Mode",
        "status": "running",
        "process_id": os.getpid(),
        "process_start_time": 123.0,
        "started_at": "2026-06-15T18:00:00+00:00",
        "last_heartbeat_at": "2026-06-15T18:00:00+00:00",
        "last_step_id": 1,
        "last_step_name": "Open ambience video",
    }
    (run_dir / "run.json").write_text(json.dumps(metadata), encoding="utf-8")
    (run_dir / "steps.jsonl").write_text("", encoding="utf-8")

    repaired = reconcile_running_runs(
        base_dir=tmp_path,
        process_checker=lambda pid: (True, 123.0),
    )

    assert repaired == []
    updated = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert updated["status"] == "running"


def test_reconcile_legacy_running_run_without_pid_marks_interrupted(tmp_path):
    run_dir = tmp_path / "20260615T175615Z_gaming_mode"
    run_dir.mkdir()
    metadata = {
        "recipe_id": "gaming_mode",
        "recipe_name": "Gaming Mode",
        "status": "running",
        "started_at": "2026-06-15T17:56:15+00:00",
    }
    (run_dir / "run.json").write_text(json.dumps(metadata), encoding="utf-8")
    (run_dir / "steps.jsonl").write_text(
        '{"index": 6, "step_name": "Select Diablo IV"}\n',
        encoding="utf-8",
    )

    repaired = reconcile_running_runs(base_dir=tmp_path)

    assert [repair.run_id for repair in repaired] == ["20260615T175615Z_gaming_mode"]
    updated = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert updated["status"] == "interrupted"
    assert updated["final_message"] == (
        "Ritualist exited before finalizing this run. Last recorded step: Select Diablo IV."
    )
