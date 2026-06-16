from __future__ import annotations

import threading
import time
import json
from pathlib import Path

from ritualist.adapters.fake import FakeAdapters
from ritualist.executor import WorkflowExecutor
from ritualist.models import Recipe
from ritualist.overlay import ConfirmationRequest
from ritualist.recipe_loader import load_recipe
from ritualist.run_logs import RunLogWriter
from ritualist.runtime_control import RuntimeControl


def test_wait_seconds_success() -> None:
    summary = _run_step({"action": "wait.seconds", "seconds": 0.01})

    assert summary.success
    assert summary.results[0].status == "success"
    assert summary.results[0].message == "waited 0.01s"


def test_wait_seconds_paused_and_resumed_does_not_spend_timeout() -> None:
    control = RuntimeControl()
    recipe = _recipe({"action": "wait.seconds", "seconds": 0.12, "timeout_seconds": 0.15})
    result: dict[str, object] = {}

    thread = threading.Thread(
        target=lambda: result.setdefault(
            "summary",
            WorkflowExecutor(
                adapters=FakeAdapters().bundle(),
                runtime_control=control,
            ).run(recipe),
        )
    )
    thread.start()

    time.sleep(0.07)
    control.pause()
    time.sleep(0.2)
    assert thread.is_alive()

    control.resume()
    thread.join(timeout=1.0)

    assert not thread.is_alive()
    summary = result["summary"]
    assert summary.success
    assert summary.results[0].status == "success"


def test_wait_for_file_succeeds_when_file_appears(tmp_path) -> None:
    target = tmp_path / "ready.txt"

    def create_file() -> None:
        time.sleep(0.05)
        target.write_text("ready", encoding="utf-8")

    thread = threading.Thread(target=create_file)
    thread.start()

    try:
        summary = _run_step(
            {
                "action": "wait.for_file",
                "path": str(target),
                "timeout_seconds": 1.0,
            }
        )
    finally:
        thread.join(timeout=1.0)

    assert summary.success
    assert summary.results[0].status == "success"
    assert "file appeared" in summary.results[0].message


def test_wait_for_file_logs_recipe_path_without_expanded_env_secret(tmp_path, monkeypatch) -> None:
    secret_path = tmp_path / "secret-token-value.txt"
    secret_path.write_text("ready", encoding="utf-8")
    monkeypatch.setenv("RITUALIST_SECRET_WAIT_PATH", str(secret_path))
    writer = RunLogWriter(base_dir=tmp_path / "runs")

    summary = WorkflowExecutor(
        adapters=FakeAdapters().bundle(),
        run_logger=writer,
    ).run(_recipe({"action": "wait.for_file", "path": "%RITUALIST_SECRET_WAIT_PATH%"}))

    assert summary.success
    assert summary.run_dir is not None
    steps_text = (summary.run_dir / "steps.jsonl").read_text(encoding="utf-8")
    assert "secret-token-value" not in steps_text
    assert "%RITUALIST_SECRET_WAIT_PATH%" in steps_text


def test_wait_for_file_times_out(tmp_path) -> None:
    summary = _run_step(
        {
            "action": "wait.for_file",
            "path": str(tmp_path / "missing.txt"),
            "timeout_seconds": 0.01,
        }
    )

    assert not summary.success
    assert summary.results[0].status == "failed"
    assert "wait.for_file timed out" in summary.results[0].message


def test_wait_for_user_times_out_when_confirmation_does_not_return() -> None:
    def slow_confirm(_request):
        time.sleep(0.2)
        return True

    summary = _run_step(
        {
            "action": "wait.for_user",
            "prompt": "Continue?",
            "timeout_seconds": 0.01,
        },
        confirmer=slow_confirm,
    )

    assert not summary.success
    assert summary.results[0].status == "failed"
    assert "wait.for_user timed out" in summary.results[0].message


def test_stop_during_wait_yields_cancelled() -> None:
    control = RuntimeControl()
    recipe = _recipe({"action": "wait.seconds", "seconds": 5.0, "timeout_seconds": 5.0})
    result: dict[str, object] = {}

    thread = threading.Thread(
        target=lambda: result.setdefault(
            "summary",
            WorkflowExecutor(
                adapters=FakeAdapters().bundle(),
                runtime_control=control,
            ).run(recipe),
        )
    )
    thread.start()

    time.sleep(0.05)
    control.stop()
    thread.join(timeout=1.0)

    assert not thread.is_alive()
    summary = result["summary"]
    assert not summary.success
    assert summary.results[0].status == "cancelled"
    assert "runtime stopped" in summary.results[0].message


def test_wait_seconds_records_waiting_state_while_active(tmp_path) -> None:
    writer = RunLogWriter(base_dir=tmp_path / "runs")
    result: dict[str, object] = {}

    thread = threading.Thread(
        target=lambda: result.setdefault(
            "summary",
            WorkflowExecutor(
                adapters=FakeAdapters().bundle(),
                run_logger=writer,
            ).run(_recipe({"action": "wait.seconds", "seconds": 0.3})),
        )
    )
    thread.start()

    try:
        observed_waiting = False
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            if writer.run_dir is not None:
                metadata = json.loads((writer.run_dir / "run.json").read_text(encoding="utf-8"))
                observed_waiting = (
                    metadata.get("current_run_state") == "waiting"
                    and metadata.get("current_step_state") == "waiting"
                )
                if observed_waiting:
                    break
            time.sleep(0.01)
    finally:
        thread.join(timeout=1.0)

    assert observed_waiting is True
    assert not thread.is_alive()
    assert result["summary"].success


def test_wait_for_user_uses_confirmation_callback_without_risky_action() -> None:
    requests: list[ConfirmationRequest | str] = []

    summary = _run_step(
        {"action": "wait.for_user", "prompt": "Continue?"},
        confirmer=lambda request: requests.append(request) or True,
    )

    assert summary.success
    assert len(requests) == 1
    assert isinstance(requests[0], ConfirmationRequest)
    assert requests[0].action == "wait.for_user"
    assert requests[0].prompt == "Continue?"
    assert requests[0].recipe_name == "Wait Test"


def test_sample_wait_runbook_executes_with_fake_adapters() -> None:
    recipe = load_recipe(Path(__file__).parent / "fixtures" / "wait_runbook.yaml")
    requests: list[ConfirmationRequest | str] = []

    summary = WorkflowExecutor(
        adapters=FakeAdapters().bundle(),
        confirmer=lambda request: requests.append(request) or True,
    ).run(recipe)

    assert summary.success
    assert [result.action for result in summary.results] == ["wait.seconds", "wait.for_user"]
    assert len(requests) == 1
    assert isinstance(requests[0], ConfirmationRequest)
    assert requests[0].action == "wait.for_user"


def test_process_and_window_waits_poll_until_state_changes() -> None:
    fakes = FakeAdapters()
    fakes.shell.responses["process_running"] = [False, True, True, False]
    fakes.window.responses["window_exists"] = [False, True, True, False]
    recipe = _recipe(
        {"action": "wait.for_process", "process_name": "demo.exe", "timeout_seconds": 1.0},
        {"action": "wait.for_process_exit", "process_name": "demo.exe", "timeout_seconds": 1.0},
        {"action": "wait.for_window", "title_contains": "Demo", "timeout_seconds": 1.0},
        {"action": "wait.for_window_gone", "title_contains": "Demo", "timeout_seconds": 1.0},
    )

    summary = WorkflowExecutor(adapters=fakes.bundle()).run(recipe)

    assert summary.success
    assert [result.status for result in summary.results] == ["success"] * 4
    assert [call[0] for call in fakes.shell.calls] == ["process_running"] * 4
    assert [call[0] for call in fakes.window.calls] == ["window_exists"] * 4


def _run_step(step: dict[str, object], *, confirmer=None):
    return WorkflowExecutor(
        adapters=FakeAdapters().bundle(),
        confirmer=confirmer,
    ).run(_recipe(step))


def _recipe(*steps: dict[str, object]) -> Recipe:
    return Recipe.model_validate(
        {
            "id": "wait_test",
            "name": "Wait Test",
            "steps": list(steps),
        }
    )
