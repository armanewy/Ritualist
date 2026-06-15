from __future__ import annotations

from ritualist.adapters.fake import FakeAdapters
from ritualist.executor import WorkflowExecutor
from ritualist.models import Recipe


def test_dry_run_does_not_call_adapters_or_confirmation():
    recipe = Recipe.model_validate(
        {
            "name": "Dry",
            "steps": [
                {"action": "browser.open", "url": "https://example.test"},
                {
                    "action": "desktop.click_text",
                    "text": "Play",
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
