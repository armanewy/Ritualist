from __future__ import annotations

from setpiece.adapters.fake import FakeAdapters
from setpiece.executor import WorkflowExecutor
from setpiece.models import Recipe


def test_dry_run_does_not_call_adapters_or_confirmation():
    recipe = Recipe.model_validate(
        {
            "id": "dry",
            "name": "Dry",
            "steps": [
                {"action": "browser.open", "url": "https://example.test"},
                {
                    "action": "desktop.click_text",
                    "text": "Play",
                    "window_title_contains": "Battle.net",
                    "requires_confirmation": True,
                },
            ],
        }
    )
    fakes = FakeAdapters()
    confirmations: list[str] = []

    summary = WorkflowExecutor(
        adapters=fakes.bundle(),
        dry_run=True,
        confirmer=lambda prompt: confirmations.append(prompt) or True,
    ).run(recipe)

    assert summary.success
    assert [result.status for result in summary.results] == ["dry-run", "dry-run"]
    assert fakes.browser.calls == []
    assert fakes.desktop.calls == []
    assert confirmations == []


def test_dry_run_prints_planned_window_layout_operation():
    recipe = Recipe.model_validate(
        {
            "id": "dry",
            "name": "Dry",
            "steps": [
                {
                    "action": "window.move",
                    "title_contains": "Battle.net",
                    "x": 100,
                    "y": 200,
                }
            ],
        }
    )
    fakes = FakeAdapters()

    summary = WorkflowExecutor(adapters=fakes.bundle(), dry_run=True).run(recipe)

    assert summary.success
    assert summary.results[0].status == "dry-run"
    assert summary.results[0].message == "would move window 'Battle.net' to 100,200"
    assert fakes.window.calls == []
