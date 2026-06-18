from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from ritualist.agent.confirmation_coordinator import (
    ConfirmationContext,
    ConfirmationCoordinator,
    ConfirmationDispatch,
)
from ritualist.agent.models import AgentRunState
from ritualist.agent.notification_policy import NotificationAction
from ritualist.agent.tray_model import TrayAttention
from ritualist.approvals import ConfirmationDecision
from ritualist.home.confirmation import confirmation_action_label
from ritualist.overlay import ConfirmationRequest
from ritualist.preferences import RememberedApprovalScope, approval_matches


class FakePresenter:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self._decision = None

    def request_confirmation(self, request: object, **kwargs: object) -> None:
        self.calls.append({"request": request, **kwargs})
        self._decision = kwargs["on_decision"]

    def decide(self, value: object) -> None:
        assert self._decision is not None
        self._decision(value)


class FakeTray:
    def __init__(self) -> None:
        self.models: list[object] = []

    def apply_model(self, model: object) -> None:
        self.models.append(model)


class FakeNotifier:
    def __init__(self) -> None:
        self.decisions: list[object] = []

    def notify(self, decision: object) -> None:
        self.decisions.append(decision)


def test_visible_user_confirmation_opens_owned_top_level_without_notification() -> None:
    presenter = FakePresenter()
    notifier = FakeNotifier()
    coordinator = ConfirmationCoordinator(presenter=presenter, notifier=notifier)
    decisions: list[ConfirmationDecision] = []

    result = coordinator.request_confirmation(
        ConfirmationContext(
            request=_launch_request(),
            confirmation_id="confirm-1",
            run_id="run-1",
            sequence=4,
            step_index=2,
            ritual_name="Gaming Mode",
            immediately_after_visible_user_interaction=True,
            ritualist_visible=True,
        ),
        on_decision=decisions.append,
    )

    assert result.dispatch == ConfirmationDispatch.SHOWN
    assert coordinator.state.state == AgentRunState.CONFIRMATION
    assert len(presenter.calls) == 1
    assert presenter.calls[0]["approve_label"] == "Launch Diablo IV"
    assert presenter.calls[0]["negative_label"] == "Not now"
    assert notifier.decisions == []

    presenter.decide(True)

    assert [decision.value for decision in decisions] == ["allow_once"]
    assert coordinator.state.state == AgentRunState.RUNNING


def test_background_confirmation_sets_agent_state_tray_and_review_notification() -> None:
    presenter = FakePresenter()
    tray = FakeTray()
    notifier = FakeNotifier()
    coordinator = ConfirmationCoordinator(presenter=presenter, tray=tray, notifier=notifier)
    decisions: list[ConfirmationDecision] = []

    result = coordinator.request_confirmation(
        ConfirmationContext(
            request=_launch_request(),
            confirmation_id="confirm-2",
            run_id="run-1",
            sequence=7,
            step_index=3,
            ritual_name="Gaming Mode",
            ritualist_visible=False,
        ),
        on_decision=decisions.append,
    )

    assert result.dispatch == ConfirmationDispatch.BACKGROUND_REVIEW
    assert coordinator.state.state == AgentRunState.CONFIRMATION
    assert presenter.calls == []
    assert decisions == []
    assert len(tray.models) == 1
    assert tray.models[0].attention == TrayAttention.NEEDS_REVIEW
    assert tray.models[0].tooltip == "Gaming Mode needs review: Launch Diablo IV"
    assert len(notifier.decisions) == 1
    assert notifier.decisions[0].actions == (NotificationAction.OPEN_REVIEW,)


def test_review_notification_opens_confirmation_but_never_approves() -> None:
    presenter = FakePresenter()
    coordinator = ConfirmationCoordinator(presenter=presenter, notifier=FakeNotifier())
    decisions: list[ConfirmationDecision] = []
    coordinator.request_confirmation(
        ConfirmationContext(
            request=_launch_request(),
            confirmation_id="confirm-3",
            run_id="run-1",
            ritual_name="Gaming Mode",
        ),
        on_decision=decisions.append,
    )

    opened = coordinator.handle_notification_action(NotificationAction.OPEN_REVIEW)

    assert opened is True
    assert len(presenter.calls) == 1
    assert decisions == []

    presenter.decide("allow_once")

    assert [decision.value for decision in decisions] == ["allow_once"]


def test_closing_confirmation_chooses_safe_negative_path() -> None:
    presenter = FakePresenter()
    coordinator = ConfirmationCoordinator(presenter=presenter)
    decisions: list[ConfirmationDecision] = []
    coordinator.request_confirmation(
        ConfirmationContext(
            request=_launch_request(),
            confirmation_id="confirm-4",
            run_id="run-1",
            ritual_name="Gaming Mode",
            immediately_after_visible_user_interaction=True,
            ritualist_visible=True,
        ),
        on_decision=decisions.append,
    )

    presenter.decide(False)

    assert [decision.value for decision in decisions] == ["cancel"]
    assert coordinator.state.state == AgentRunState.STOPPED


def test_remembered_approval_uses_existing_store_and_exact_scope_copy(tmp_path: Path) -> None:
    store_path = tmp_path / "local-preferences.json"
    scope = _remember_scope()
    presenter = FakePresenter()
    coordinator = ConfirmationCoordinator(presenter=presenter, approval_store_path=store_path)
    decisions: list[ConfirmationDecision] = []

    coordinator.request_confirmation(
        ConfirmationContext(
            request=_launch_request(step_name="Open Settings"),
            confirmation_id="confirm-5",
            run_id="run-1",
            ritual_name="Project Setup",
            immediately_after_visible_user_interaction=True,
            ritualist_visible=True,
            remember_scope=scope,
        ),
        on_decision=decisions.append,
    )

    remember_copy = presenter.calls[0]["remember_scope_text"]
    assert "recipe_or_intent_id=project_setup" in remember_copy
    assert "content_hash=abc123" in remember_copy
    assert "step_id=main:2" in remember_copy
    assert "action_or_primitive_id=app.open" in remember_copy

    presenter.decide(ConfirmationDecision.always_allow_local())

    assert [decision.value for decision in decisions] == ["always_allow_local"]
    assert approval_matches(scope, path=store_path, local_user_approved_source=True)

    remembered_presenter = FakePresenter()
    remembered_coordinator = ConfirmationCoordinator(
        presenter=remembered_presenter,
        approval_store_path=store_path,
    )
    remembered_decisions: list[ConfirmationDecision] = []

    result = remembered_coordinator.request_confirmation(
        ConfirmationContext(
            request=_launch_request(step_name="Open Settings"),
            confirmation_id="confirm-6",
            run_id="run-2",
            ritual_name="Project Setup",
            remember_scope=scope,
        ),
        on_decision=remembered_decisions.append,
    )

    assert result.dispatch == ConfirmationDispatch.REMEMBERED
    assert remembered_presenter.calls == []
    assert [decision.value for decision in remembered_decisions] == ["allow_once"]


def test_confirmation_copy_uses_specific_action_and_avoids_vague_proceed() -> None:
    assert confirmation_action_label(_launch_request()) == "Launch Diablo IV"
    assert confirmation_action_label("Proceed") == "Allow once"
    assert (
        confirmation_action_label(
            ConfirmationRequest(
                prompt="Click target?",
                action="desktop.click_text",
                step_name="Click target",
                target_scope="desktop",
            )
        )
        == "Allow once"
    )


def test_agent_confirmation_imports_without_gui_or_windows_dependencies() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    code = """
import sys
import ritualist.agent.confirmation_coordinator

blocked = ["PySide6", "pywinauto", "win32api", "win32gui", "win32con"]
loaded = [name for name in blocked if name in sys.modules]
if loaded:
    raise SystemExit(f"confirmation coordinator loaded GUI/Windows modules: {loaded}")
"""

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def _launch_request(*, step_name: str = "Launch Diablo IV") -> ConfirmationRequest:
    return ConfirmationRequest(
        prompt="Launch Diablo IV?",
        recipe_name="Gaming Mode",
        step_name=step_name,
        action="app.launch",
        target_scope="desktop",
        target_type="application",
        window_title="Battle.net",
        target_text="Diablo IV",
        target_identity="battle-net-diablo-iv",
        safety_message="Launching a local app requires explicit confirmation.",
    )


def _remember_scope() -> RememberedApprovalScope:
    return RememberedApprovalScope(
        recipe_or_intent_id="project_setup",
        content_hash="abc123",
        step_id="main:2",
        action_or_primitive_id="app.open",
        resolved_target_identity="settings-app",
        target_context="Windows Settings",
        target_text="Settings",
        target_scope="desktop",
        target_application="Windows Settings",
        risk_level="low",
        source_trust="local_user",
    )
