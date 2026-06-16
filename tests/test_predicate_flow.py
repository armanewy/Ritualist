from __future__ import annotations

import json
import logging

import pytest

from ritualist.actions.base import ActionContext
from ritualist.adapters.fake import FakeAdapters
from ritualist.config import AppConfig
from ritualist.executor import WorkflowExecutor
from ritualist.models import Condition, Recipe
from ritualist.overlay import NullOverlayController
from ritualist.predicates import evaluate_condition
from ritualist.run_logs import RunLogWriter
from ritualist.runtime_control import RuntimeControl


def test_predicate_true_false_and_composition(tmp_path):
    marker = tmp_path / "ready.txt"
    marker.write_text("ok", encoding="utf-8")
    fakes = FakeAdapters()
    fakes.shell.responses["process_running"] = False
    context = _context(fakes)

    assert evaluate_condition(
        Condition.model_validate({"type": "file.exists", "path": str(marker)}),
        context,
    ).matched
    assert not evaluate_condition(
        Condition.model_validate({"type": "process.running", "process_name": "missing.exe"}),
        context,
    ).matched
    all_result = evaluate_condition(
        Condition.model_validate(
            {
                "all": [
                    {"type": "file.exists", "path": str(marker)},
                    {"not": {"type": "path.exists", "path": str(tmp_path / "missing")}},
                ]
            }
        ),
        context,
    )
    any_result = evaluate_condition(
        Condition.model_validate(
            {
                "any": [
                    {"type": "path.exists", "path": str(tmp_path / "missing")},
                    {"type": "file.exists", "path": str(marker)},
                ]
            }
        ),
        context,
    )

    assert all_result.matched is True
    assert any_result.matched is True
    assert all_result.details["operator"] == "all"
    assert any_result.details["operator"] == "any"


def test_window_and_browser_predicates_use_read_only_adapters():
    fakes = FakeAdapters()
    fakes.desktop.responses["text_visible"] = [False, True]
    fakes.browser.responses["text_visible"] = True
    context = _context(fakes)

    window_result = evaluate_condition(
        Condition.model_validate(
            {
                "type": "window.text_visible",
                "window_title_contains": "Battle.net",
                "text": "Play",
            }
        ),
        context,
    )
    browser_result = evaluate_condition(
        Condition.model_validate({"type": "browser.text_visible", "text": "Ready"}),
        context,
    )

    assert window_result.matched is False
    assert browser_result.matched is True
    assert [call[0] for call in fakes.desktop.calls] == ["text_visible"]
    assert [call[0] for call in fakes.browser.calls] == ["text_visible"]


def test_step_when_false_skips_and_records_condition(tmp_path):
    recipe = Recipe.model_validate(
        {
            "id": "run",
            "name": "Run",
            "steps": [
                {
                    "action": "app.launch",
                    "command": "demo.exe",
                    "when": {"type": "path.exists", "path": str(tmp_path / "missing")},
                }
            ],
        }
    )
    fakes = FakeAdapters()

    summary = WorkflowExecutor(adapters=fakes.bundle()).run(recipe)

    assert summary.success
    assert summary.results[0].status == "skipped"
    assert "condition not matched" in summary.results[0].message
    assert summary.results[0].metadata["condition"]["matched"] is False
    assert fakes.shell.calls == []


def test_step_when_condition_result_is_written_to_run_log(tmp_path):
    recipe = Recipe.model_validate(
        {
            "id": "run",
            "name": "Run",
            "steps": [
                {
                    "action": "app.launch",
                    "command": "demo.exe",
                    "when": {"type": "path.exists", "path": str(tmp_path / "missing")},
                }
            ],
        }
    )
    writer = RunLogWriter(base_dir=tmp_path / "runs")

    summary = WorkflowExecutor(adapters=FakeAdapters().bundle(), run_logger=writer).run(recipe)

    assert summary.run_dir is not None
    rows = [
        json.loads(line)
        for line in (summary.run_dir / "steps.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    skipped_step = next(row for row in rows if row.get("action") == "app.launch")
    assert skipped_step["metadata"]["condition"]["matched"] is False
    assert "path does not exist" in skipped_step["metadata"]["condition"]["message"]


def test_flow_if_runs_then_branch(tmp_path):
    marker = tmp_path / "ready.txt"
    marker.write_text("ok", encoding="utf-8")
    recipe = Recipe.model_validate(
        {
            "id": "run",
            "name": "Run",
            "steps": [
                {
                    "action": "flow.if",
                    "condition": {"type": "file.exists", "path": str(marker)},
                    "then": [{"action": "notify.toast", "title": "Ready", "message": "Play is visible."}],
                    "else": [{"action": "notify.beep"}],
                }
            ],
        }
    )

    summary = WorkflowExecutor(adapters=FakeAdapters().bundle()).run(recipe)

    assert summary.success
    assert [result.action for result in summary.results] == ["flow.if", "notify.toast"]
    assert summary.results[0].metadata["branch"] == "then"
    assert summary.results[1].phase == "steps:then"


def test_flow_if_runs_else_branch(tmp_path):
    recipe = Recipe.model_validate(
        {
            "id": "run",
            "name": "Run",
            "steps": [
                {
                    "action": "flow.if",
                    "condition": {"type": "path.exists", "path": str(tmp_path / "missing")},
                    "then": [{"action": "notify.toast", "title": "Ready", "message": "Ready."}],
                    "else": [{"action": "notify.toast", "title": "Not ready", "message": "Missing."}],
                }
            ],
        }
    )

    summary = WorkflowExecutor(adapters=FakeAdapters().bundle()).run(recipe)

    assert summary.success
    assert [result.action for result in summary.results] == ["flow.if", "notify.toast"]
    assert summary.results[0].metadata["branch"] == "else"
    assert summary.results[1].phase == "steps:else"
    assert "Not ready" in summary.results[1].message


def test_dry_run_does_not_evaluate_desktop_predicates():
    recipe = Recipe.model_validate(
        {
            "id": "run",
            "name": "Run",
            "steps": [
                {
                    "action": "flow.if",
                    "condition": {
                        "type": "window.text_visible",
                        "window_title_contains": "Battle.net",
                        "text": "Play",
                    },
                    "then": [{"action": "notify.toast", "title": "Ready", "message": "Ready."}],
                    "else": [{"action": "notify.toast", "title": "Not ready", "message": "Missing."}],
                }
            ],
        }
    )
    fakes = FakeAdapters()

    summary = WorkflowExecutor(adapters=fakes.bundle(), dry_run=True).run(recipe)

    assert summary.success
    assert [result.action for result in summary.results] == [
        "flow.if",
        "notify.toast",
        "notify.toast",
    ]
    assert all(result.status == "dry-run" for result in summary.results)
    assert fakes.desktop.calls == []


def test_wait_on_timeout_runs_structured_timeout_actions(tmp_path):
    recipe = Recipe.model_validate(
        {
            "id": "run",
            "name": "Run",
            "steps": [
                {
                    "action": "wait.for_file",
                    "path": str(tmp_path / "missing"),
                    "timeout_seconds": 0.01,
                    "on_timeout": [
                        {
                            "action": "notify.toast",
                            "title": "Timeout",
                            "message": "Condition did not become true.",
                        }
                    ],
                }
            ],
        }
    )

    summary = WorkflowExecutor(adapters=FakeAdapters().bundle()).run(recipe)

    assert not summary.success
    assert [result.action for result in summary.results] == ["wait.for_file", "notify.toast"]
    assert summary.results[0].status == "failed"
    assert summary.results[1].status == "success"
    assert summary.results[1].phase == "steps:on_timeout"


def test_notify_actions_are_local_and_cross_platform(tmp_path):
    missing_sound = tmp_path / "missing.wav"
    recipe = Recipe.model_validate(
        {
            "id": "run",
            "name": "Run",
            "steps": [
                {"action": "notify.toast", "title": "Ready", "message": "Done."},
                {"action": "notify.beep"},
                {"action": "notify.sound", "path": str(missing_sound)},
            ],
        }
    )

    summary = WorkflowExecutor(adapters=FakeAdapters().bundle(), config=AppConfig()).run(recipe)

    assert summary.success
    assert [result.action for result in summary.results] == [
        "notify.toast",
        "notify.beep",
        "notify.sound",
    ]
    assert "fallback beep" in summary.results[2].message


def test_condition_rejects_arbitrary_expression_shape():
    with pytest.raises(ValueError, match="extra"):
        Condition.model_validate({"expr": "window.text_visible('Play')"})


def test_condition_rejects_unsupported_predicate_fields():
    with pytest.raises(ValueError, match="file.exists does not support exact"):
        Condition.model_validate({"type": "file.exists", "path": "demo.txt", "exact": False})


def test_condition_rejects_unused_composition_fields():
    with pytest.raises(ValueError, match="condition.any does not support path"):
        Condition.model_validate(
            {
                "any": [{"type": "path.exists", "path": "demo.txt"}],
                "path": "ignored.txt",
            }
        )


def _context(fakes: FakeAdapters) -> ActionContext:
    return ActionContext(
        adapters=fakes.bundle(),
        dry_run=False,
        logger=logging.getLogger("test"),
        confirm=lambda _request: True,
        recipe=Recipe.model_validate(
            {"id": "predicate_test", "name": "Predicate Test", "steps": [{"action": "notify.beep"}]}
        ),
        config=AppConfig(),
        overlay=NullOverlayController(),
        runtime_control=RuntimeControl(),
    )
