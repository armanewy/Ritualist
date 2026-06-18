from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from ritualist.approvals import ConfirmationDecision, normalize_confirmation_decision
from ritualist.home.confirmation import confirmation_action_label, remember_scope_text
from ritualist.overlay import ConfirmationRequest, format_confirmation_request
from ritualist.preferences import (
    APPROVAL_SOURCE_TRUSTS,
    RememberedApprovalScope,
    approval_matches,
    can_remember_approval,
    remember_approval,
)
from ritualist.runtime_models import ConfirmationRequested, ConfirmationResolved, StepState

from .models import AgentRunState, AgentState
from .notification_policy import (
    NotificationAction,
    NotificationDecision,
    NotificationEvent,
    NotificationRequest,
    choose_notification,
)
from .state import apply_runtime_event, derive_agent_state, initial_agent_state
from .tray_model import TrayContext, TrayModel, TrayState, build_tray_model


ConfirmationDecisionInput = bool | str | ConfirmationDecision
ConfirmationDecisionHandler = Callable[[ConfirmationDecision], None]


class ConfirmationDispatch(StrEnum):
    SHOWN = "shown"
    BACKGROUND_REVIEW = "background_review"
    REMEMBERED = "remembered"
    CANCELLED = "cancelled"


class ConfirmationPresenter(Protocol):
    def request_confirmation(
        self,
        request: ConfirmationRequest | str,
        *,
        on_decision: Callable[[ConfirmationDecisionInput], None],
        approve_label: str | None = None,
        negative_label: str = "Not now",
        remember_scope_text: str | None = None,
    ) -> None:
        """Show an owned top-level confirmation and report a user decision."""


@dataclass(frozen=True)
class ConfirmationContext:
    request: ConfirmationRequest | str
    confirmation_id: str = ""
    run_id: str = ""
    sequence: int = 0
    step_index: int = 1
    step_name: str = ""
    action: str = ""
    ritual_id: str = ""
    ritual_name: str = ""
    immediately_after_visible_user_interaction: bool = False
    ritualist_visible: bool = False
    remember_scope: RememberedApprovalScope | None = None
    local_user_approved_source: bool = True


@dataclass(frozen=True)
class ConfirmationResult:
    dispatch: ConfirmationDispatch
    state: AgentState
    notification: NotificationDecision | None = None
    tray_model: TrayModel | None = None
    remembered_approval: dict[str, Any] | None = None


@dataclass(frozen=True)
class _PendingConfirmation:
    context: ConfirmationContext
    on_decision: ConfirmationDecisionHandler


class ConfirmationCoordinator:
    """Routes confirmation requests between the Agent and the top-level UI.

    The coordinator intentionally owns no approval persistence format. Remembered
    approvals go through the existing preferences approval store and the shared
    ConfirmationDecision model.
    """

    def __init__(
        self,
        *,
        presenter: ConfirmationPresenter,
        state: AgentState | None = None,
        tray: Any | None = None,
        notifier: Any | None = None,
        approval_store_path: Path | None = None,
    ) -> None:
        self.presenter = presenter
        self._state = state or initial_agent_state()
        self._tray = tray
        self._notifier = notifier
        self._approval_store_path = approval_store_path
        self._pending: _PendingConfirmation | None = None
        self.last_notification: NotificationDecision | None = None
        self.last_tray_model: TrayModel | None = None
        self.last_remembered_approval: dict[str, Any] | None = None

    @property
    def state(self) -> AgentState:
        return self._state

    @property
    def pending_confirmation(self) -> ConfirmationContext | None:
        return self._pending.context if self._pending is not None else None

    def request_confirmation(
        self,
        context: ConfirmationContext,
        *,
        on_decision: ConfirmationDecisionHandler,
    ) -> ConfirmationResult:
        context = _complete_context(context)
        remembered = self._matching_remembered_approval(context)
        if remembered is not None:
            self.last_remembered_approval = remembered
            decision = ConfirmationDecision.allow_once()
            on_decision(decision)
            return ConfirmationResult(
                dispatch=ConfirmationDispatch.REMEMBERED,
                state=self._state,
                remembered_approval=remembered,
            )

        self._enter_confirmation_state(context)
        self._pending = _PendingConfirmation(context=context, on_decision=on_decision)

        if _should_open_immediately(context):
            if self._show_pending_confirmation():
                return ConfirmationResult(dispatch=ConfirmationDispatch.SHOWN, state=self._state)
            return ConfirmationResult(dispatch=ConfirmationDispatch.CANCELLED, state=self._state)

        tray_model = self._publish_confirmation_tray_state(context)
        notification = self._send_review_notification(context)
        return ConfirmationResult(
            dispatch=ConfirmationDispatch.BACKGROUND_REVIEW,
            state=self._state,
            notification=notification,
            tray_model=tray_model,
        )

    def open_review(self) -> bool:
        """Open the pending confirmation after an explicit Review action."""

        return self._show_pending_confirmation()

    def handle_notification_action(self, action: NotificationAction | str) -> bool:
        normalized = str(getattr(action, "value", action) or "")
        if normalized != NotificationAction.OPEN_REVIEW.value:
            return False
        return self.open_review()

    def decline_pending(self) -> bool:
        if self._pending is None:
            return False
        self._resolve_pending(self._pending.context.confirmation_id, ConfirmationDecision.cancel())
        return True

    def resolve_pending(self, decision: ConfirmationDecisionInput) -> bool:
        if self._pending is None:
            return False
        normalized = normalize_confirmation_decision(decision)
        self._resolve_pending(self._pending.context.confirmation_id, normalized)
        return True

    def _enter_confirmation_state(self, context: ConfirmationContext) -> None:
        if context.ritual_id or context.ritual_name:
            self._state = derive_agent_state(
                self._state.model_copy(
                    update={
                        "active_ritual_id": context.ritual_id or self._state.active_ritual_id,
                        "active_ritual_name": context.ritual_name or self._state.active_ritual_name,
                    }
                )
            )
        self._state = apply_runtime_event(
            self._state,
            ConfirmationRequested(
                run_id=context.run_id,
                sequence=max(0, int(context.sequence)),
                confirmation_id=context.confirmation_id,
                step_index=max(1, int(context.step_index)),
                step_name=context.step_name,
                action=context.action,
                prompt=format_confirmation_request(context.request),
                target=_target_label(context.request),
                target_type=_target_type(context.request),
            ),
        )

    def _show_pending_confirmation(self) -> bool:
        pending = self._pending
        if pending is None:
            return False
        context = pending.context
        scope_text = remember_scope_text(context.remember_scope)

        def handle_decision(value: ConfirmationDecisionInput) -> None:
            self._resolve_pending(context.confirmation_id, normalize_confirmation_decision(value))

        try:
            self.presenter.request_confirmation(
                context.request,
                on_decision=handle_decision,
                approve_label=confirmation_action_label(context.request),
                negative_label="Not now",
                remember_scope_text=scope_text,
            )
        except TypeError:
            try:
                self.presenter.request_confirmation(context.request, on_decision=handle_decision)
            except Exception:  # noqa: BLE001 - confirmation failures must take the safe path.
                self._resolve_pending(context.confirmation_id, ConfirmationDecision.cancel())
                return False
        except Exception:  # noqa: BLE001 - confirmation failures must take the safe path.
            self._resolve_pending(context.confirmation_id, ConfirmationDecision.cancel())
            return False
        return True

    def _resolve_pending(self, confirmation_id: str, decision: ConfirmationDecision) -> None:
        pending = self._pending
        if pending is None or pending.context.confirmation_id != confirmation_id:
            return
        context = pending.context
        self._pending = None
        remembered = self._store_remembered_approval(context, decision)
        if remembered is not None:
            self.last_remembered_approval = remembered
        self._state = apply_runtime_event(
            self._state,
            ConfirmationResolved(
                run_id=context.run_id,
                sequence=max(0, int(context.sequence)) + 1,
                confirmation_id=context.confirmation_id,
                step_index=max(1, int(context.step_index)),
                step_name=context.step_name,
                action=context.action,
                approved=decision.approved,
                state=StepState.RUNNING if decision.approved else StepState.CANCELLED,
                message="approved" if decision.approved else "declined",
            ),
        )
        pending.on_decision(decision)

    def _publish_confirmation_tray_state(self, context: ConfirmationContext) -> TrayModel:
        model = build_tray_model(
            TrayContext(
                state=TrayState.CONFIRMATION,
                ritual_name=context.ritual_name or self._state.active_ritual_name,
                current_step=context.step_name,
                required_decision=confirmation_action_label(context.request),
            )
        )
        self.last_tray_model = model
        tray = self._tray
        if tray is None:
            return model
        if hasattr(tray, "apply_model"):
            tray.apply_model(model)
            return model
        if hasattr(tray, "set_confirmation"):
            tray.set_confirmation(model.tooltip)
            return model
        system_tray_icon = getattr(tray, "system_tray_icon", None)
        if system_tray_icon is not None and hasattr(system_tray_icon, "setToolTip"):
            system_tray_icon.setToolTip(model.tooltip)
        return model

    def _send_review_notification(self, context: ConfirmationContext) -> NotificationDecision:
        decision = choose_notification(
            NotificationRequest(
                event=NotificationEvent.CONFIRMATION_REQUIRED,
                ritual_name=context.ritual_name or self._state.active_ritual_name,
                step_name=context.step_name,
                decision_prompt=confirmation_action_label(context.request),
                app_in_background=True,
            )
        )
        self.last_notification = decision
        if decision.should_notify:
            _notify(self._notifier, decision)
        return decision

    def _matching_remembered_approval(self, context: ConfirmationContext) -> dict[str, Any] | None:
        scope = context.remember_scope
        if scope is None:
            return None
        if not approval_matches(
            scope,
            path=self._approval_store_path,
            local_user_approved_source=(
                context.local_user_approved_source
                and scope.source_trust in APPROVAL_SOURCE_TRUSTS
            ),
        ):
            return None
        return {"status": "applied", "scope": scope.to_dict()}

    def _store_remembered_approval(
        self,
        context: ConfirmationContext,
        decision: ConfirmationDecision,
    ) -> dict[str, Any] | None:
        scope = context.remember_scope
        if not decision.approved or not decision.remember or scope is None:
            return None
        if not can_remember_approval(scope):
            return {"status": "not_stored", "reason": "approval scope is not rememberable"}
        entry = remember_approval(scope, path=self._approval_store_path)
        return {
            "status": "stored",
            "approval_id": str(entry.get("id") or ""),
            "scope": scope.to_dict(),
        }


def _complete_context(context: ConfirmationContext) -> ConfirmationContext:
    request = context.request
    updates: dict[str, Any] = {}
    if not context.confirmation_id:
        updates["confirmation_id"] = uuid.uuid4().hex
    if isinstance(request, ConfirmationRequest):
        if not context.step_name:
            updates["step_name"] = request.step_name
        if not context.action:
            updates["action"] = request.action
        if not context.ritual_name and request.recipe_name:
            updates["ritual_name"] = request.recipe_name
    if not (updates.get("step_name") or context.step_name):
        updates["step_name"] = confirmation_action_label(request)
    if not (updates.get("action") or context.action):
        updates["action"] = "confirm.ask"
    if not updates:
        return context
    return replace(context, **updates)


def _should_open_immediately(context: ConfirmationContext) -> bool:
    return (
        context.immediately_after_visible_user_interaction
        and context.ritualist_visible
    )


def _target_label(request: ConfirmationRequest | str) -> str:
    if isinstance(request, str):
        return ""
    return str(
        request.target_text
        or request.target_role
        or request.target_test_id
        or request.target_identity
        or ""
    )


def _target_type(request: ConfirmationRequest | str) -> str:
    if isinstance(request, str):
        return ""
    return str(request.target_type or request.control_type or "")


def _notify(notifier: Any | None, decision: NotificationDecision) -> None:
    if notifier is None:
        return
    if callable(notifier):
        notifier(decision)
        return
    notify = getattr(notifier, "notify", None)
    if callable(notify):
        notify(decision)
