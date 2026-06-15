from __future__ import annotations

from ritualist.actions.registry import create_default_registry


def test_default_registry_contains_supported_actions():
    registry = create_default_registry()

    assert registry.action_types() == [
        "app.launch",
        "app.wait_process",
        "browser.media",
        "browser.open",
        "confirm.ask",
        "desktop.click_text",
        "input.hotkey",
        "window.focus",
        "window.maximize",
        "window.minimize",
        "window.wait",
    ]
