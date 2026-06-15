from __future__ import annotations

import json

from ritualist.adapters.fake import FakeAdapters
from ritualist.executor import WorkflowExecutor
from ritualist.models import Recipe
from ritualist.run_logs import RunLogWriter, list_recent_runs, load_run


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
