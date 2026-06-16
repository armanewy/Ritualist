from __future__ import annotations

from ritualist.adapters.fake import FakeAdapters
from ritualist.executor import WorkflowExecutor
from ritualist.models import Recipe
from ritualist.overlay import ConfirmationRequest
from ritualist.run_logs import RunLogWriter
from ritualist.runtime_control import RuntimeControl


def test_human_prompt_records_safe_operator_response_metadata(tmp_path) -> None:
    requests: list[ConfirmationRequest | str] = []
    writer = RunLogWriter(base_dir=tmp_path)

    summary = WorkflowExecutor(
        adapters=FakeAdapters().bundle(),
        confirmer=lambda request: requests.append(request) or True,
        run_logger=writer,
    ).run(
        _recipe(
            {
                "action": "human.prompt",
                "prompt": "Continue after checking token secret-123?",
            }
        )
    )

    assert summary.success
    assert len(requests) == 1
    assert isinstance(requests[0], ConfirmationRequest)
    assert requests[0].action == "human.prompt"
    assert requests[0].prompt == "Continue after checking token secret-123?"
    assert summary.results[0].metadata == {
        "operator_response": {
            "action": "human.prompt",
            "response": "acknowledged",
        }
    }
    assert summary.run_dir is not None
    steps_text = (summary.run_dir / "steps.jsonl").read_text(encoding="utf-8")
    assert "secret-123" not in steps_text


def test_human_checklist_shows_items_but_logs_only_counts(tmp_path) -> None:
    requests: list[ConfirmationRequest | str] = []
    writer = RunLogWriter(base_dir=tmp_path)

    summary = WorkflowExecutor(
        adapters=FakeAdapters().bundle(),
        confirmer=lambda request: requests.append(request) or True,
        run_logger=writer,
    ).run(
        _recipe(
            {
                "action": "human.checklist",
                "prompt": "Complete manual checks",
                "items": ["Check private token secret-456", "Confirm local app is ready"],
            }
        )
    )

    assert summary.success
    assert isinstance(requests[0], ConfirmationRequest)
    assert "Check private token secret-456" in requests[0].prompt
    assert summary.results[0].metadata == {
        "operator_response": {
            "action": "human.checklist",
            "response": "completed",
            "item_count": 2,
        }
    }
    assert summary.run_dir is not None
    steps_text = (summary.run_dir / "steps.jsonl").read_text(encoding="utf-8")
    assert "secret-456" not in steps_text


def test_human_checklist_decline_cancels_run() -> None:
    summary = WorkflowExecutor(
        adapters=FakeAdapters().bundle(),
        confirmer=lambda _request: False,
    ).run(
        _recipe(
            {
                "action": "human.checklist",
                "prompt": "Complete manual checks",
                "items": ["Confirm local app is ready"],
            },
            {"action": "app.launch", "command": "demo.exe"},
        )
    )

    assert not summary.success
    assert len(summary.results) == 1
    assert summary.results[0].status == "cancelled"
    assert summary.results[0].message == "operator declined checklist"


def test_human_confirm_evidence_records_count_metadata() -> None:
    summary = WorkflowExecutor(
        adapters=FakeAdapters().bundle(),
        confirmer=lambda _request: True,
    ).run(
        _recipe(
            {
                "action": "human.confirm_evidence",
                "prompt": "Confirm visible evidence",
                "evidence": ["Status shows Connected", "No warning dialog is open"],
            }
        )
    )

    assert summary.success
    assert summary.results[0].metadata == {
        "operator_response": {
            "action": "human.confirm_evidence",
            "response": "confirmed",
            "evidence_count": 2,
        }
    }


def test_human_prompt_supports_stop_during_confirmation() -> None:
    control = RuntimeControl()

    def stop_and_accept(_request: ConfirmationRequest | str) -> bool:
        control.stop()
        return True

    summary = WorkflowExecutor(
        adapters=FakeAdapters().bundle(),
        confirmer=stop_and_accept,
        runtime_control=control,
    ).run(_recipe({"action": "human.prompt", "prompt": "Continue?"}))

    assert not summary.success
    assert summary.results[0].status == "cancelled"
    assert "runtime stopped" in summary.results[0].message


def test_note_add_records_redacted_metadata_without_prompting(tmp_path) -> None:
    writer = RunLogWriter(base_dir=tmp_path)

    def fail_if_prompted(_request: ConfirmationRequest | str) -> bool:
        raise AssertionError("note.add should not request confirmation")

    summary = WorkflowExecutor(
        adapters=FakeAdapters().bundle(),
        confirmer=fail_if_prompted,
        run_logger=writer,
    ).run(_recipe({"action": "note.add", "text": "Operator saw secret-789"}))

    assert summary.success
    assert summary.results[0].message == "note recorded"
    assert summary.results[0].metadata == {
        "note": {
            "action": "note.add",
            "recorded": True,
            "text_redacted": True,
            "text_length": len("Operator saw secret-789"),
        }
    }
    assert summary.run_dir is not None
    steps_text = (summary.run_dir / "steps.jsonl").read_text(encoding="utf-8")
    assert "secret-789" not in steps_text


def _recipe(*steps: dict[str, object]) -> Recipe:
    return Recipe.model_validate(
        {
            "id": "human_actions",
            "name": "Human Actions",
            "steps": list(steps),
        }
    )
