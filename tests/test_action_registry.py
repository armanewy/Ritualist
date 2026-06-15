from __future__ import annotations

from ritualist.actions.registry import create_default_registry


def test_default_registry_contains_supported_actions():
    registry = create_default_registry()

    assert registry.action_types() == [
        "app.launch",
        "app.wait_process",
        "assert.browser_text_visible",
        "assert.file_exists",
        "assert.path_exists",
        "assert.process_running",
        "assert.registry_value",
        "assert.window_exists",
        "assert.window_text_visible",
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
