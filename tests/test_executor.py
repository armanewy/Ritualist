from __future__ import annotations

from ritualist.adapters.fake import FakeAdapters
from ritualist.executor import WorkflowExecutor
from ritualist.models import Recipe


def test_executor_runs_steps_in_order():
    recipe = Recipe.model_validate(
        {
            "name": "Run",
            "steps": [
                {"action": "browser.open", "url": "https://example.test"},
                {"action": "browser.media", "loop": True, "play": True},
                {"action": "app.launch", "command": "demo.exe"},
            ],
        }
    )
    fakes = FakeAdapters()

    summary = WorkflowExecutor(adapters=fakes.bundle(), confirmer=lambda _: True).run(recipe)

    assert summary.success
    assert [result.status for result in summary.results] == ["success", "success", "success"]
    assert fakes.browser.calls[0][0] == "open_url"
    assert fakes.browser.calls[1][0] == "configure_media"
    assert fakes.shell.calls[0][0] == "launch"


def test_executor_stops_on_required_failure():
    recipe = Recipe.model_validate(
        {
            "name": "Run",
            "steps": [
                {"action": "browser.open", "url": "https://example.test"},
                {"action": "app.launch", "command": "demo.exe"},
            ],
        }
    )
    fakes = FakeAdapters()
    fakes.browser.failures["open_url"] = RuntimeError("network blocked")

    summary = WorkflowExecutor(adapters=fakes.bundle()).run(recipe)

    assert not summary.success
    assert len(summary.results) == 1
    assert summary.results[0].status == "failed"
    assert fakes.shell.calls == []


def test_executor_continues_after_optional_failure():
    recipe = Recipe.model_validate(
        {
            "name": "Run",
            "steps": [
                {"action": "desktop.click_text", "text": "Diablo IV", "optional": True},
                {"action": "app.launch", "command": "demo.exe"},
            ],
        }
    )
    fakes = FakeAdapters()
    fakes.desktop.failures["click_text"] = RuntimeError("not found")

    summary = WorkflowExecutor(adapters=fakes.bundle()).run(recipe)

    assert summary.success
    assert [result.status for result in summary.results] == ["skipped", "success"]
    assert fakes.shell.calls[0][0] == "launch"


def test_executor_cancels_when_confirmation_declined():
    recipe = Recipe.model_validate(
        {
            "name": "Run",
            "steps": [
                {
                    "action": "desktop.click_text",
                    "text": "Play",
                    "requires_confirmation": True,
                }
            ],
        }
    )

    summary = WorkflowExecutor(adapters=FakeAdapters().bundle(), confirmer=lambda _: False).run(recipe)

    assert not summary.success
    assert summary.results[0].status == "cancelled"
