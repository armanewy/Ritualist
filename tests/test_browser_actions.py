from __future__ import annotations

import logging
import threading
import time
from textwrap import dedent

import pytest

from setpiece.adapters.fake import FakeAdapters
from setpiece.actions.base import ActionContext
from setpiece.actions.browser_actions import BrowserWaitTextHandler
from setpiece.actions.browser_actions import BrowserWaitMediaPlayingHandler
from setpiece.actions.registry import create_default_registry
from setpiece.config import AppConfig
from setpiece.doctor import build_doctor_report
from setpiece.executor import WorkflowExecutor
from setpiece.models import BrowserWaitMediaPlayingStep, BrowserWaitTextStep, Recipe
from setpiece.overlay import ConfirmationRequest, NullOverlayController
from setpiece.recipe_loader import load_recipe
from setpiece.runtime_control import RuntimeControl, RuntimeStoppedError


def test_browser_wait_text_success_uses_fake_browser_adapter():
    recipe = Recipe.model_validate(
        {
            "id": "browser_wait",
            "name": "Browser Wait",
            "steps": [
                {"action": "browser.open", "url": "https://example.test"},
                {"action": "browser.wait_text", "text": "Ready", "timeout_seconds": 0.01},
            ],
        }
    )
    fakes = FakeAdapters()

    summary = WorkflowExecutor(adapters=fakes.bundle(), config=AppConfig()).run(recipe)

    assert summary.success
    assert [call[0] for call in fakes.browser.calls] == ["open_url", "text_visible", "close"]
    assert fakes.browser.calls[1][2]["text"] == "Ready"


def test_browser_open_passes_clean_start_options_to_adapter():
    recipe = Recipe.model_validate(
        {
            "id": "browser_open",
            "name": "Browser Open",
            "steps": [
                {
                    "action": "browser.open",
                    "url": "https://example.test",
                    "profile": "gaming_mode",
                    "clean_start": True,
                    "dismiss_restore_prompt": True,
                    "use_dedicated_profile": True,
                }
            ],
        }
    )
    fakes = FakeAdapters()

    summary = WorkflowExecutor(adapters=fakes.bundle(), config=AppConfig()).run(recipe)

    assert summary.success
    assert fakes.browser.calls[0][0] == "open_url"
    assert fakes.browser.calls[0][2] == {
        "browser": "chromium",
        "profile": "gaming_mode",
        "new_window": False,
        "keep_open": False,
        "clean_start": True,
        "dismiss_restore_prompt": True,
        "use_dedicated_profile": True,
    }


def test_browser_open_dry_run_describes_clean_start_options():
    recipe = Recipe.model_validate(
        {
            "id": "browser_open",
            "name": "Browser Open",
            "steps": [
                {
                    "action": "browser.open",
                    "url": "https://example.test",
                    "profile": "gaming_mode",
                    "clean_start": True,
                    "dismiss_restore_prompt": True,
                }
            ],
        }
    )

    summary = WorkflowExecutor(adapters=FakeAdapters().bundle(), config=AppConfig(), dry_run=True).run(recipe)

    assert summary.results[0].status == "dry-run"
    assert "clean start" in summary.results[0].message
    assert "safe restore prompt handling" in summary.results[0].message
    assert "managed profile 'gaming_mode'" in summary.results[0].message


def test_browser_open_native_uses_os_handoff_fake_without_managed_browser():
    recipe = Recipe.model_validate(
        {
            "id": "browser_native",
            "name": "Browser Native",
            "steps": [
                {
                    "action": "browser.open_native",
                    "url": "https://example.test",
                    "new_window": True,
                }
            ],
        }
    )
    fakes = FakeAdapters()

    summary = WorkflowExecutor(adapters=fakes.bundle(), config=AppConfig()).run(recipe)

    assert summary.success
    assert fakes.native_browser.calls == [
        ("open_url", ("https://example.test",), {"new_window": True})
    ]
    assert fakes.browser.calls == []
    assert summary.results[0].message == "handed URL to default browser"


def test_browser_open_native_dry_run_does_not_handoff_or_initialize_playwright():
    recipe = Recipe.model_validate(
        {
            "id": "browser_native",
            "name": "Browser Native",
            "steps": [{"action": "browser.open_native", "url": "https://example.test"}],
        }
    )
    fakes = FakeAdapters()

    summary = WorkflowExecutor(adapters=fakes.bundle(), config=AppConfig(), dry_run=True).run(recipe)

    assert summary.success
    assert summary.results[0].status == "dry-run"
    assert summary.results[0].message == "would hand off URL to default browser"
    assert fakes.native_browser.calls == []
    assert fakes.browser.calls == []


def test_browser_open_native_doctor_does_not_require_playwright(monkeypatch):
    recipe = Recipe.model_validate(
        {
            "id": "browser_native",
            "name": "Browser Native",
            "steps": [{"action": "browser.open_native", "url": "https://example.test"}],
        }
    )
    monkeypatch.setattr("setpiece.doctor.importlib.util.find_spec", lambda _name: None)

    report = build_doctor_report(recipe)

    assert report.errors_count == 0
    assert report.required_capabilities == ["native_browser_handoff"]
    assert any(
        check.name == "native_browser_handoff" and check.status == "ok"
        for check in report.checks
    )


def test_browser_open_native_rejects_malformed_and_non_http_urls():
    for url in ("javascript:alert(1)", "file:///tmp/index.html", "https://"):
        with pytest.raises(Exception, match="HTTP or HTTPS URL"):
            Recipe.model_validate(
                {
                    "id": "browser_native",
                    "name": "Browser Native",
                    "steps": [{"action": "browser.open_native", "url": url}],
                }
            )


def test_managed_browser_open_metadata_remains_explicit():
    catalog_entry = create_default_registry().metadata("browser.open")

    assert catalog_entry.required_capabilities == ("playwright", "browser_control")
    assert "profile" in catalog_entry.optional_params
    assert "use_dedicated_profile" in catalog_entry.optional_params


def test_browser_wait_text_timeout_fails_without_page_contents():
    recipe = Recipe.model_validate(
        {
            "id": "browser_wait",
            "name": "Browser Wait",
            "steps": [
                {"action": "browser.open", "url": "https://example.test"},
                {"action": "browser.wait_text", "text": "Ready", "timeout_seconds": 0.01},
            ],
        }
    )
    fakes = FakeAdapters()
    fakes.browser.responses["text_visible"] = False

    summary = WorkflowExecutor(adapters=fakes.bundle(), config=AppConfig()).run(recipe)

    assert not summary.success
    assert summary.results[-1].action == "browser.wait_text"
    assert summary.results[-1].status == "failed"
    assert "timed out" in summary.results[-1].message
    assert "Ready" in summary.results[-1].message


def test_browser_click_text_invokes_adapter_with_structured_target():
    recipe = Recipe.model_validate(
        {
            "id": "browser_click",
            "name": "Browser Click",
            "steps": [
                {"action": "browser.open", "url": "https://example.test"},
                {"action": "browser.click_text", "text": "Continue"},
            ],
        }
    )
    fakes = FakeAdapters()

    summary = WorkflowExecutor(adapters=fakes.bundle(), config=AppConfig()).run(recipe)

    assert summary.success
    assert [call[0] for call in fakes.browser.calls] == ["open_url", "click_text", "close"]
    assert fakes.browser.calls[1][2] == {
        "text": "Continue",
        "exact": True,
        "timeout_seconds": 10.0,
    }
    assert summary.results[1].metadata["browser_click"] == {
        "target_type": "text",
        "text": "Continue",
    }


def test_browser_wait_media_playing_polls_until_media_advances():
    recipe = Recipe.model_validate(
        {
            "id": "browser_media_wait",
            "name": "Browser Media Wait",
            "steps": [
                {
                    "action": "browser.wait_media_playing",
                    "selector": "video",
                    "timeout_seconds": 1,
                    "sample_seconds": 0.01,
                }
            ],
        }
    )
    fakes = FakeAdapters()
    fakes.browser.responses["media_playing"] = [False, True]

    summary = WorkflowExecutor(adapters=fakes.bundle(), config=AppConfig()).run(recipe)

    assert summary.success
    assert [call[0] for call in fakes.browser.calls] == ["media_playing", "media_playing", "close"]
    assert fakes.browser.calls[0][2] == {
        "selector": "video",
        "sample_seconds": 0.01,
        "timeout_seconds": 0.25,
    }


def test_browser_wait_media_playing_times_out_when_paused_or_stalled():
    recipe = Recipe.model_validate(
        {
            "id": "browser_media_wait",
            "name": "Browser Media Wait",
            "steps": [
                {
                    "action": "browser.wait_media_playing",
                    "selector": "video",
                    "timeout_seconds": 0.01,
                }
            ],
        }
    )
    fakes = FakeAdapters()
    fakes.browser.responses["media_playing"] = False

    summary = WorkflowExecutor(adapters=fakes.bundle(), config=AppConfig()).run(recipe)

    assert not summary.success
    assert summary.results[0].action == "browser.wait_media_playing"
    assert summary.results[0].status == "failed"
    assert "timed out" in summary.results[0].message


def test_browser_click_role_invokes_adapter_with_accessible_name():
    recipe = Recipe.model_validate(
        {
            "id": "browser_click",
            "name": "Browser Click",
            "steps": [
                {"action": "browser.open", "url": "https://example.test"},
                {
                    "action": "browser.click_role",
                    "role": "button",
                    "accessible_name": "Continue",
                    "exact": False,
                },
            ],
        }
    )
    fakes = FakeAdapters()

    summary = WorkflowExecutor(adapters=fakes.bundle(), config=AppConfig()).run(recipe)

    assert summary.success
    assert [call[0] for call in fakes.browser.calls] == ["open_url", "click_role", "close"]
    assert fakes.browser.calls[1][2]["role"] == "button"
    assert fakes.browser.calls[1][2]["accessible_name"] == "Continue"
    assert fakes.browser.calls[1][2]["exact"] is False


def test_browser_click_test_id_invokes_adapter_with_test_id():
    recipe = Recipe.model_validate(
        {
            "id": "browser_click",
            "name": "Browser Click",
            "steps": [
                {"action": "browser.open", "url": "https://example.test"},
                {"action": "browser.click_test_id", "test_id": "continue-button"},
            ],
        }
    )
    fakes = FakeAdapters()

    summary = WorkflowExecutor(adapters=fakes.bundle(), config=AppConfig()).run(recipe)

    assert summary.success
    assert [call[0] for call in fakes.browser.calls] == ["open_url", "click_test_id", "close"]
    assert fakes.browser.calls[1][2]["test_id"] == "continue-button"


def test_risky_browser_click_requires_confirmation(tmp_path):
    path = tmp_path / "risky.yaml"
    path.write_text(
        dedent(
            """
            version: "0.1"
            id: risky
            name: Risky
            steps:
              - action: browser.click_text
                text: Buy now
            """
        ),
        encoding="utf-8",
    )

    with pytest.raises(Exception, match="requires_confirmation"):
        load_recipe(path)


def test_browser_click_actions_are_risky_and_blocked_in_imported_packs():
    registry = create_default_registry()

    for action in ("browser.click_text", "browser.click_role", "browser.click_test_id"):
        metadata = registry.metadata(action)
        assert metadata.side_effect_level == "risky"
        assert metadata.allowed_in_imported_packs is False


def test_declined_risky_browser_click_stops_before_clicking():
    requested: list[ConfirmationRequest] = []

    def confirm(prompt):
        assert isinstance(prompt, ConfirmationRequest)
        requested.append(prompt)
        return False

    recipe = Recipe.model_validate(
        {
            "id": "browser_click",
            "name": "Browser Click",
            "steps": [
                {"action": "browser.open", "url": "https://example.test"},
                {
                    "action": "browser.click_text",
                    "text": "Buy now",
                    "requires_confirmation": True,
                },
            ],
        }
    )
    fakes = FakeAdapters()
    fakes.browser.responses["page_context"] = {
        "title": "Checkout",
        "url": "https://user:pass@shop.example.test:8443/reset/password-token?token=secret#payment",
    }

    summary = WorkflowExecutor(
        adapters=fakes.bundle(),
        config=AppConfig(),
        confirmer=confirm,
    ).run(recipe)

    assert not summary.success
    assert summary.results[-1].status == "cancelled"
    assert [call[0] for call in fakes.browser.calls] == ["open_url", "page_context", "close"]
    assert requested[0].action == "browser.click_text"
    assert requested[0].target_scope == "browser"
    assert requested[0].target_type == "text"
    assert requested[0].target_text == "Buy now"
    assert requested[0].browser_title == "Checkout"
    assert requested[0].browser_url == "https://shop.example.test:8443/[redacted]"
    assert "token" not in requested[0].browser_url
    assert "password" not in requested[0].browser_url
    assert "user" not in requested[0].browser_url
    assert "pass" not in requested[0].browser_url
    assert "requires explicit confirmation" in (requested[0].safety_message or "")


def test_risky_browser_role_confirmation_includes_role_metadata():
    requested: list[ConfirmationRequest] = []
    recipe = Recipe.model_validate(
        {
            "id": "browser_click",
            "name": "Browser Click",
            "steps": [
                {
                    "action": "browser.click_role",
                    "role": "button",
                    "accessible_name": "Confirm order",
                    "requires_confirmation": True,
                },
            ],
        }
    )

    summary = WorkflowExecutor(
        adapters=FakeAdapters().bundle(),
        config=AppConfig(),
        confirmer=lambda prompt: requested.append(prompt) or False,
    ).run(recipe)

    assert not summary.success
    assert requested[0].target_scope == "browser"
    assert requested[0].target_type == "role"
    assert requested[0].target_role == "button"
    assert requested[0].target_text == "Confirm order"


def test_browser_click_dry_run_does_not_click():
    recipe = Recipe.model_validate(
        {
            "id": "browser_click",
            "name": "Browser Click",
            "steps": [{"action": "browser.click_text", "text": "Continue"}],
        }
    )
    fakes = FakeAdapters()

    summary = WorkflowExecutor(
        adapters=fakes.bundle(),
        config=AppConfig(),
        dry_run=True,
    ).run(recipe)

    assert summary.success
    assert summary.results[0].status == "dry-run"
    assert fakes.browser.calls == []


def test_browser_wait_timeout_runs_on_timeout_actions():
    recipe = Recipe.model_validate(
        {
            "id": "browser_wait",
            "name": "Browser Wait",
            "steps": [
                {
                    "action": "browser.wait_text",
                    "text": "Ready",
                    "timeout_seconds": 0.01,
                    "on_timeout": [
                        {
                            "action": "notify.toast",
                            "title": "Timeout",
                            "message": "Browser text was not visible.",
                        }
                    ],
                }
            ],
        }
    )
    fakes = FakeAdapters()
    fakes.browser.responses["text_visible"] = False

    summary = WorkflowExecutor(adapters=fakes.bundle(), config=AppConfig()).run(recipe)

    assert [result.action for result in summary.results] == ["browser.wait_text", "notify.toast"]
    assert summary.results[0].status == "failed"
    assert summary.results[1].status == "success"


def test_stop_during_browser_wait_is_cooperative():
    control = RuntimeControl()
    heartbeats = 0

    def heartbeat() -> None:
        nonlocal heartbeats
        heartbeats += 1
        control.stop()

    context = _context(FakeAdapters(), control=control, heartbeat=heartbeat)
    step = BrowserWaitTextStep.model_validate(
        {"action": "browser.wait_text", "text": "Ready", "timeout_seconds": 5}
    )

    with pytest.raises(RuntimeStoppedError):
        BrowserWaitTextHandler().run(step, context)

    assert heartbeats == 1


def test_pause_resume_during_browser_wait_is_cooperative():
    control = RuntimeControl()
    fakes = FakeAdapters()
    fakes.browser.responses["text_visible"] = False
    heartbeats = 0
    pause_started = threading.Event()

    def resume_soon() -> None:
        pause_started.wait(timeout=1)
        time.sleep(0.02)
        control.resume()

    resume_thread = threading.Thread(target=resume_soon, daemon=True)
    resume_thread.start()

    def heartbeat() -> None:
        nonlocal heartbeats
        heartbeats += 1
        if heartbeats == 1:
            control.pause()
            pause_started.set()

    context = _context(fakes, control=control, heartbeat=heartbeat)
    step = BrowserWaitTextStep.model_validate(
        {"action": "browser.wait_text", "text": "Ready", "timeout_seconds": 0.05}
    )

    with pytest.raises(Exception, match="timed out"):
        BrowserWaitTextHandler().run(step, context)

    resume_thread.join(timeout=1)
    assert pause_started.is_set()
    assert control.is_paused() is False
    assert heartbeats >= 2


def test_stop_during_browser_wait_media_playing_is_cooperative():
    control = RuntimeControl()
    heartbeats = 0

    def heartbeat() -> None:
        nonlocal heartbeats
        heartbeats += 1
        control.stop()

    context = _context(FakeAdapters(), control=control, heartbeat=heartbeat)
    step = BrowserWaitMediaPlayingStep.model_validate(
        {"action": "browser.wait_media_playing", "selector": "video", "timeout_seconds": 5}
    )

    with pytest.raises(RuntimeStoppedError):
        BrowserWaitMediaPlayingHandler().run(step, context)

    assert heartbeats == 1


def test_pause_resume_during_browser_wait_media_playing_is_cooperative():
    control = RuntimeControl()
    fakes = FakeAdapters()
    fakes.browser.responses["media_playing"] = False
    heartbeats = 0
    pause_started = threading.Event()

    def resume_soon() -> None:
        pause_started.wait(timeout=1)
        time.sleep(0.02)
        control.resume()

    resume_thread = threading.Thread(target=resume_soon, daemon=True)
    resume_thread.start()

    def heartbeat() -> None:
        nonlocal heartbeats
        heartbeats += 1
        if heartbeats == 1:
            control.pause()
            pause_started.set()

    context = _context(fakes, control=control, heartbeat=heartbeat)
    step = BrowserWaitMediaPlayingStep.model_validate(
        {"action": "browser.wait_media_playing", "selector": "video", "timeout_seconds": 0.05}
    )

    with pytest.raises(Exception, match="timed out"):
        BrowserWaitMediaPlayingHandler().run(step, context)

    resume_thread.join(timeout=1)
    assert pause_started.is_set()
    assert control.is_paused() is False
    assert heartbeats >= 2


def test_browser_wait_heartbeat_is_not_duplicated_per_poll_cycle(monkeypatch):
    fakes = FakeAdapters()
    fakes.browser.responses["text_visible"] = False
    heartbeats = 0

    def heartbeat() -> None:
        nonlocal heartbeats
        heartbeats += 1

    context = _context(fakes, control=RuntimeControl(), heartbeat=heartbeat)
    ticks = iter([0.0, 1.0])
    monkeypatch.setattr("setpiece.actions.browser_actions.time.monotonic", lambda: next(ticks))
    step = BrowserWaitTextStep.model_validate(
        {"action": "browser.wait_text", "text": "Ready", "timeout_seconds": 1}
    )

    with pytest.raises(Exception, match="timed out"):
        BrowserWaitTextHandler().run(step, context)

    assert heartbeats == 1


def _context(
    fakes: FakeAdapters,
    *,
    control: RuntimeControl,
    heartbeat,
) -> ActionContext:
    return ActionContext(
        adapters=fakes.bundle(),
        dry_run=False,
        logger=logging.getLogger("test"),
        confirm=lambda _request: True,
        recipe=Recipe.model_validate(
            {"id": "browser_actions", "name": "Browser Actions", "steps": [{"action": "wait.seconds", "seconds": 0.1}]}
        ),
        config=AppConfig(),
        overlay=NullOverlayController(),
        runtime_control=control,
        heartbeat=heartbeat,
    )
