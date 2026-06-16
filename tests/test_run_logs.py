from __future__ import annotations

import json
import os

from ritualist.adapters.fake import FakeAdapters
from ritualist.executor import WorkflowExecutor
from ritualist.models import Recipe
from ritualist.overlay import ScreenRect, TargetRegion
from ritualist.run_logs import (
    RunLogWriter,
    append_operator_note,
    list_recent_runs,
    load_run,
    reconcile_running_runs,
    summarize_run_record,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


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
    assert run_json["run_log_schema_version"] == 2
    assert run_json["last_heartbeat_at"]
    assert run_json["last_step_id"] == 2
    assert run_json["last_step_name"] == "app.launch"
    assert run_json["current_run_state"] == "success"
    assert run_json["current_step_state"] == "success"
    assert run_json["final_state"] == "success"
    assert [entry["state"] for entry in run_json["run_state_history"]] == ["running", "success"]
    assert run_json["event_summaries"][-1]["event"] == "run.finished"
    assert run_json["wait_metadata"] is None
    assert run_json["paused_metadata"] is None
    assert run_json["confirming_metadata"] is None
    assert steps[0]["message"] == "opened URL"
    assert [step["phase"] for step in steps] == ["steps", "steps"]
    assert "token=secret" not in (summary.run_dir / "steps.jsonl").read_text(encoding="utf-8")

    loaded = load_run(summary.run_dir)
    assert loaded is not None
    assert loaded.run_id == summary.run_dir.name
    assert loaded.metadata["recipe_id"] == "log_test"
    assert loaded.steps[0]["message"] == "opened URL"

    recent = list_recent_runs(base_dir=tmp_path)
    assert [record.run_id for record in recent] == [summary.run_dir.name]


def test_load_run_accepts_legacy_log_without_runtime_v2_fields(tmp_path):
    run_dir = tmp_path / "20260615T120000Z_legacy"
    run_dir.mkdir()
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "recipe_id": "legacy",
                "recipe_name": "Legacy",
                "status": "success",
                "started_at": "2026-06-15T12:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "steps.jsonl").write_text(
        '{"index": 1, "step_name": "Old step", "status": "success"}\n',
        encoding="utf-8",
    )

    loaded = load_run(run_dir)

    assert loaded is not None
    assert loaded.metadata["recipe_id"] == "legacy"
    assert "current_run_state" not in loaded.metadata
    assert loaded.steps[0]["step_name"] == "Old step"


def test_run_log_writer_records_action_result_metadata(tmp_path):
    recipe = Recipe.model_validate(
        {
            "id": "log_test",
            "name": "Log Test",
            "steps": [
                {
                    "action": "desktop.click_text",
                    "text": "Diablo IV",
                    "window_title_contains": "Battle.net",
                }
            ],
        }
    )
    fakes = FakeAdapters()
    fakes.desktop.responses["click_text"] = TargetRegion(
        rect=ScreenRect(30, 40, 120, 36),
        window_title="Battle.net",
        target_text="Diablo IV",
    )
    writer = RunLogWriter(base_dir=tmp_path)

    summary = WorkflowExecutor(
        adapters=fakes.bundle(),
        run_logger=writer,
    ).run(recipe)

    assert summary.run_dir is not None
    steps = [
        json.loads(line)
        for line in (summary.run_dir / "steps.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert steps[0]["metadata"] == summary.results[0].metadata
    run_json = json.loads((summary.run_dir / "run.json").read_text(encoding="utf-8"))
    step_finished = [
        entry for entry in run_json["event_summaries"] if entry["event"] == "step.finished"
    ][-1]
    assert step_finished["metadata"] == summary.results[0].metadata


def test_run_log_writer_records_runtime_v2_metadata_hooks(tmp_path):
    recipe = Recipe.model_validate(
        {
            "id": "log_test",
            "name": "Log Test",
            "steps": [{"action": "window.wait", "title_contains": "Battle.net"}],
        }
    )
    writer = RunLogWriter(base_dir=tmp_path)

    writer.start(recipe, dry_run=False)
    writer.record_run_state("paused", event="run.state_changed", message="user requested pause")
    writer.record_step_state(
        "waiting",
        step_id=1,
        step_name="Wait for Battle.net",
        action="window.wait",
        metadata={"timeout_seconds": 10},
    )
    writer.set_wait_metadata({"reason": "window", "title_contains": "Battle.net"})
    writer.set_paused_metadata({"reason": "user"})
    writer.set_confirming_metadata({"action": "desktop.click_text", "target_text": "Play"})

    assert writer.run_dir is not None
    loaded = load_run(writer.run_dir)

    assert loaded is not None
    assert loaded.metadata["current_run_state"] == "paused"
    assert loaded.metadata["current_step_state"] == "waiting"
    assert loaded.metadata["wait_metadata"] == {
        "reason": "window",
        "title_contains": "Battle.net",
    }
    assert loaded.metadata["paused_metadata"] == {"reason": "user"}
    assert loaded.metadata["confirming_metadata"] == {
        "action": "desktop.click_text",
        "target_text": "Play",
    }
    assert loaded.metadata["run_state_history"][-1]["state"] == "paused"
    assert loaded.metadata["event_summaries"][-1]["event"] == "confirmation.requested"


def test_run_log_writer_records_user_entered_operator_note(tmp_path):
    recipe = Recipe.model_validate(
        {
            "id": "log_test",
            "name": "Log Test",
            "steps": [{"action": "app.launch", "command": "demo.exe"}],
        }
    )
    writer = RunLogWriter(base_dir=tmp_path)

    writer.start(recipe, dry_run=False)
    entry = writer.add_operator_note("Operator checked the window title.")

    assert entry is not None
    assert writer.run_dir is not None
    notes_text = (writer.run_dir / "operator_notes.jsonl").read_text(encoding="utf-8")
    notes = [json.loads(line) for line in notes_text.splitlines()]
    assert notes == [entry]
    assert notes[0]["source"] == "user"
    assert notes[0]["user_entered"] is True
    assert notes[0]["kind"] == "operator_note"
    assert notes[0]["note"] == "Operator checked the window title."

    run_json_text = (writer.run_dir / "run.json").read_text(encoding="utf-8")
    run_json = json.loads(run_json_text)
    assert run_json["operator_notes_count"] == 1
    assert run_json["last_operator_note_at"] == entry["at"]
    assert run_json["event_summaries"][-1]["event"] == "operator_note.added"
    assert "Operator checked the window title." not in run_json_text

    loaded = load_run(writer.run_dir)
    assert loaded is not None
    assert loaded.notes == [entry]


def test_append_operator_note_adds_note_to_finished_run(tmp_path):
    recipe = Recipe.model_validate(
        {
            "id": "log_test",
            "name": "Log Test",
            "steps": [{"action": "app.launch", "command": "demo.exe"}],
        }
    )
    writer = RunLogWriter(base_dir=tmp_path)

    summary = WorkflowExecutor(adapters=FakeAdapters().bundle(), run_logger=writer).run(recipe)
    assert summary.run_dir is not None
    entry = append_operator_note(summary.run_dir, "Follow-up note after the run.")

    assert entry is not None
    loaded = load_run(summary.run_dir)
    assert loaded is not None
    assert loaded.notes == [entry]
    assert loaded.notes[0]["user_entered"] is True
    assert loaded.metadata["operator_notes_count"] == 1
    assert loaded.metadata["last_operator_note_at"] == entry["at"]


def test_active_run_writer_preserves_externally_appended_note_counters(tmp_path):
    recipe = Recipe.model_validate(
        {
            "id": "log_test",
            "name": "Log Test",
            "steps": [{"action": "app.launch", "command": "demo.exe"}],
        }
    )
    writer = RunLogWriter(base_dir=tmp_path)

    writer.start(recipe, dry_run=False)
    assert writer.run_dir is not None
    entry = append_operator_note(writer.run_dir, "Note added while run is active.")
    writer.heartbeat(step_id=1, step_name="app.launch")

    loaded = load_run(writer.run_dir)
    assert loaded is not None
    assert loaded.notes == [entry]
    assert loaded.metadata["operator_notes_count"] == 1
    assert loaded.metadata["last_operator_note_at"] == entry["at"]


def test_run_log_writer_maps_dry_run_status_to_runtime_step_state(tmp_path):
    recipe = Recipe.model_validate(
        {
            "id": "log_test",
            "name": "Log Test",
            "steps": [{"action": "app.launch", "command": "demo.exe"}],
        }
    )
    writer = RunLogWriter(base_dir=tmp_path)

    summary = WorkflowExecutor(
        adapters=FakeAdapters().bundle(),
        run_logger=writer,
        dry_run=True,
    ).run(recipe)

    assert summary.run_dir is not None
    run_json = json.loads((summary.run_dir / "run.json").read_text(encoding="utf-8"))
    steps = [
        json.loads(line)
        for line in (summary.run_dir / "steps.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert steps[0]["status"] == "dry-run"
    assert run_json["current_step_state"] == "success"
    step_finished = [
        entry for entry in run_json["event_summaries"] if entry["event"] == "step.finished"
    ][-1]
    assert step_finished["step_state"] == "success"


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


def test_run_log_writer_records_failed_final_state_for_required_failure(tmp_path):
    recipe = Recipe.model_validate(
        {
            "id": "log_test",
            "name": "Log Test",
            "steps": [{"action": "browser.open", "url": "https://example.test"}],
        }
    )
    fakes = FakeAdapters()
    fakes.browser.failures["open_url"] = RuntimeError("network blocked")
    writer = RunLogWriter(base_dir=tmp_path)

    summary = WorkflowExecutor(adapters=fakes.bundle(), run_logger=writer).run(recipe)

    assert not summary.success
    assert summary.run_dir is not None
    run_json = json.loads((summary.run_dir / "run.json").read_text(encoding="utf-8"))
    assert run_json["status"] == "failed"
    assert run_json["final_state"] == "failed"
    assert run_json["current_run_state"] == "failed"


def test_run_log_writer_throttles_steady_heartbeat_writes(tmp_path):
    recipe = Recipe.model_validate(
        {
            "id": "log_test",
            "name": "Log Test",
            "steps": [{"action": "app.launch", "command": "demo.exe"}],
        }
    )
    clock = FakeClock()
    writer = RunLogWriter(base_dir=tmp_path, monotonic_clock=clock)

    writer.start(recipe, dry_run=False)
    assert writer.run_dir is not None
    run_json = writer.run_dir / "run.json"
    writer.heartbeat(step_id=1, step_name="app.launch", run_state="running", step_state="running")
    first = run_json.read_text(encoding="utf-8")

    clock.advance(0.2)
    writer.heartbeat(step_id=1, step_name="app.launch", run_state="running", step_state="running")
    second = run_json.read_text(encoding="utf-8")

    clock.advance(1.0)
    writer.heartbeat(step_id=1, step_name="app.launch", run_state="running", step_state="running")
    third = run_json.read_text(encoding="utf-8")

    assert second == first
    assert third != second


def test_run_log_writer_counts_preflight_and_verify_steps(tmp_path):
    marker = tmp_path / "marker.txt"
    marker.write_text("ok", encoding="utf-8")
    recipe = Recipe.model_validate(
        {
            "id": "log_test",
            "name": "Log Test",
            "preflight": [{"action": "assert.file_exists", "path": str(marker)}],
            "steps": [{"action": "app.launch", "command": "demo.exe"}],
            "verify": [{"action": "assert.path_exists", "path": str(marker)}],
        }
    )
    writer = RunLogWriter(base_dir=tmp_path)

    summary = WorkflowExecutor(adapters=FakeAdapters().bundle(), run_logger=writer).run(recipe)

    assert summary.success
    assert summary.run_dir is not None
    run_json = json.loads((summary.run_dir / "run.json").read_text(encoding="utf-8"))
    assert run_json["steps_total"] == 3
    assert run_json["steps_completed"] == 3
    steps = [
        json.loads(line)
        for line in (summary.run_dir / "steps.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [step["phase"] for step in steps] == ["preflight", "steps", "verify"]
    assert run_json["last_step_phase"] == "verify"
    assert run_json["current_phase"] == "verify"
    step_events = [
        entry for entry in run_json["event_summaries"] if entry["event"] == "step.finished"
    ]
    assert [entry["phase"] for entry in step_events] == ["preflight", "steps", "verify"]


def test_runbook_summary_reports_preflight_actions_assertions_and_prompts(tmp_path):
    marker = tmp_path / "marker.txt"
    marker.write_text("ok", encoding="utf-8")
    recipe = Recipe.model_validate(
        {
            "id": "summary_test",
            "name": "Summary Test",
            "preflight": [{"action": "assert.file_exists", "path": str(marker)}],
            "steps": [
                {"action": "wait.for_user", "prompt": "Continue?"},
                {"action": "app.launch", "command": "demo.exe"},
            ],
            "verify": [{"action": "assert.path_exists", "path": str(marker)}],
        }
    )
    writer = RunLogWriter(base_dir=tmp_path)

    summary = WorkflowExecutor(
        adapters=FakeAdapters().bundle(),
        confirmer=lambda _request: True,
        run_logger=writer,
    ).run(recipe)

    assert summary.run_dir is not None
    record = load_run(summary.run_dir)
    assert record is not None
    runbook = summarize_run_record(record)
    assert runbook.preflight_status == "passed"
    assert runbook.preflight_passed == 1
    assert runbook.preflight_failed == 0
    assert runbook.actions_completed == 2
    assert runbook.assertions_passed == 2
    assert runbook.assertions_failed == 0
    assert runbook.human_prompts_answered == 1
    assert runbook.final_status == "success"
    assert runbook.stop_semantics == "none"
    assert runbook.last_step == "#4 assert.path_exists (success)"


def test_runbook_summary_reports_dry_run_preflight_without_pass_counts(tmp_path):
    marker = tmp_path / "marker.txt"
    marker.write_text("ok", encoding="utf-8")
    recipe = Recipe.model_validate(
        {
            "id": "summary_test",
            "name": "Summary Test",
            "preflight": [{"action": "assert.file_exists", "path": str(marker)}],
            "steps": [{"action": "wait.seconds", "seconds": 1}],
            "verify": [{"action": "assert.path_exists", "path": str(marker)}],
        }
    )
    writer = RunLogWriter(base_dir=tmp_path)

    summary = WorkflowExecutor(
        adapters=FakeAdapters().bundle(),
        run_logger=writer,
        dry_run=True,
    ).run(recipe)

    assert summary.run_dir is not None
    record = load_run(summary.run_dir)
    assert record is not None
    runbook = summarize_run_record(record)
    assert runbook.preflight_status == "dry-run"
    assert runbook.preflight_passed == 0
    assert runbook.preflight_failed == 0
    assert runbook.actions_completed == 0
    assert runbook.assertions_passed == 0
    assert runbook.assertions_failed == 0


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
    assert updated["current_run_state"] == "interrupted"
    assert "current_step_state" not in updated
    assert updated["final_state"] == "interrupted"
    assert updated["run_state_history"][-1]["event"] == "run.interrupted"
    assert updated["event_summaries"][-1]["event"] == "run.interrupted"
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
    assert updated["final_state"] == "interrupted"
    assert updated["final_message"] == (
        "Ritualist exited before finalizing this run. Last recorded step: Select Diablo IV."
    )
