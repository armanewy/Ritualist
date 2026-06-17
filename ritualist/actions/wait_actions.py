from __future__ import annotations

import os
import queue
import re
import threading
import time
from collections.abc import Callable
from pathlib import Path

from ritualist.errors import RitualistError, UserCancelledError
from ritualist.models import (
    WaitForFileStep,
    WaitForProcessExitStep,
    WaitForProcessStep,
    WaitForUserStep,
    WaitForWindowGoneStep,
    WaitForWindowStep,
    WaitSecondsStep,
)
from ritualist.overlay import ConfirmationRequest

from .base import ActionContext
from .metadata import ALL_PLATFORMS, ActionMetadata, WINDOWS_ONLY


DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_POLL_INTERVAL_SECONDS = 0.1


class WaitSecondsHandler:
    action_type = "wait.seconds"
    metadata = ActionMetadata(
        action_name=action_type,
        schema_version="0.1",
        category="wait",
        required_params=("seconds",),
        optional_params=("timeout_seconds", "on_timeout", "name", "optional", "when"),
        required_capabilities=(),
        supported_platforms=ALL_PLATFORMS,
        side_effect_level="read_only",
        confirmation_policy="never",
        allowed_in_imported_packs=True,
    )

    def __init__(self, *, poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS) -> None:
        self.poll_interval_seconds = poll_interval_seconds

    def run(self, step: WaitSecondsStep, context: ActionContext) -> str:
        timeout = step.timeout_seconds or step.seconds
        _wait_active_duration(
            step.seconds,
            timeout_seconds=timeout,
            poll_interval_seconds=self.poll_interval_seconds,
            context=context,
            timeout_message=f"wait.seconds timed out after {timeout:g}s",
        )
        return f"waited {step.seconds:g}s"


class WaitForUserHandler:
    action_type = "wait.for_user"
    metadata = ActionMetadata(
        action_name=action_type,
        schema_version="0.1",
        category="wait",
        required_params=("prompt",),
        optional_params=("timeout_seconds", "on_timeout", "name", "optional", "when"),
        required_capabilities=(),
        supported_platforms=ALL_PLATFORMS,
        side_effect_level="read_only",
        confirmation_policy="always",
        allowed_in_imported_packs=True,
    )

    def run(self, step: WaitForUserStep, context: ActionContext) -> str:
        _cooperate(context)
        request = ConfirmationRequest(
            prompt=step.prompt,
            action=step.action,
            step_name=step.display_name,
            recipe_name=context.recipe.name,
        )
        accepted = _confirm_user(request, context=context, timeout_seconds=step.timeout_seconds)
        if not accepted:
            raise UserCancelledError("user declined wait prompt")
        _cooperate(context)
        return "user continued"


class WaitForFileHandler:
    action_type = "wait.for_file"
    metadata = ActionMetadata(
        action_name=action_type,
        schema_version="0.1",
        category="wait",
        required_params=("path",),
        optional_params=("timeout_seconds", "on_timeout", "name", "optional", "when"),
        required_capabilities=("file_read",),
        supported_platforms=ALL_PLATFORMS,
        side_effect_level="read_only",
        confirmation_policy="never",
        allowed_in_imported_packs=True,
    )

    def __init__(self, *, poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS) -> None:
        self.poll_interval_seconds = poll_interval_seconds

    def run(self, step: WaitForFileStep, context: ActionContext) -> str:
        path = _expand_path(step.path)
        timeout = step.timeout_seconds or DEFAULT_TIMEOUT_SECONDS
        _wait_until(
            lambda: path.is_file(),
            timeout_seconds=timeout,
            poll_interval_seconds=self.poll_interval_seconds,
            context=context,
            timeout_message=f"wait.for_file timed out after {timeout:g}s: {step.path}",
        )
        return f"file appeared: {step.path}"


class WaitForProcessHandler:
    action_type = "wait.for_process"
    metadata = ActionMetadata(
        action_name=action_type,
        schema_version="0.1",
        category="wait",
        required_params=("process_name",),
        optional_params=("timeout_seconds", "on_timeout", "name", "optional", "when"),
        required_capabilities=("process_inspection",),
        supported_platforms=ALL_PLATFORMS,
        side_effect_level="read_only",
        confirmation_policy="never",
        allowed_in_imported_packs=True,
    )

    def __init__(self, *, poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS) -> None:
        self.poll_interval_seconds = poll_interval_seconds

    def run(self, step: WaitForProcessStep, context: ActionContext) -> str:
        timeout = step.timeout_seconds or DEFAULT_TIMEOUT_SECONDS
        _wait_until(
            lambda: context.adapters.shell.process_running(step.process_name, timeout_seconds=0),
            timeout_seconds=timeout,
            poll_interval_seconds=self.poll_interval_seconds,
            context=context,
            timeout_message=f"wait.for_process timed out after {timeout:g}s: {step.process_name}",
        )
        return f"process appeared: {step.process_name}"


class WaitForProcessExitHandler:
    action_type = "wait.for_process_exit"
    metadata = ActionMetadata(
        action_name=action_type,
        schema_version="0.1",
        category="wait",
        required_params=("process_name",),
        optional_params=("timeout_seconds", "on_timeout", "name", "optional", "when"),
        required_capabilities=("process_inspection",),
        supported_platforms=ALL_PLATFORMS,
        side_effect_level="read_only",
        confirmation_policy="never",
        allowed_in_imported_packs=True,
    )

    def __init__(self, *, poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS) -> None:
        self.poll_interval_seconds = poll_interval_seconds

    def run(self, step: WaitForProcessExitStep, context: ActionContext) -> str:
        timeout = step.timeout_seconds or DEFAULT_TIMEOUT_SECONDS
        _wait_until(
            lambda: not context.adapters.shell.process_running(step.process_name, timeout_seconds=0),
            timeout_seconds=timeout,
            poll_interval_seconds=self.poll_interval_seconds,
            context=context,
            timeout_message=f"wait.for_process_exit timed out after {timeout:g}s: {step.process_name}",
        )
        return f"process exited: {step.process_name}"


class WaitForWindowHandler:
    action_type = "wait.for_window"
    metadata = ActionMetadata(
        action_name=action_type,
        schema_version="0.1",
        category="wait",
        required_params=(),
        optional_params=(
            "title_contains",
            "process_name",
            "timeout_seconds",
            "on_timeout",
            "name",
            "optional",
            "when",
        ),
        required_capabilities=("windows_uia", "window_management"),
        supported_platforms=WINDOWS_ONLY,
        side_effect_level="read_only",
        confirmation_policy="never",
        allowed_in_imported_packs=True,
    )

    def __init__(self, *, poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS) -> None:
        self.poll_interval_seconds = poll_interval_seconds

    def run(self, step: WaitForWindowStep, context: ActionContext) -> str:
        timeout = step.timeout_seconds or DEFAULT_TIMEOUT_SECONDS
        _wait_until(
            lambda: context.adapters.window.window_exists(
                title_contains=step.title_contains,
                process_name=step.process_name,
                timeout_seconds=0,
            ),
            timeout_seconds=timeout,
            poll_interval_seconds=self.poll_interval_seconds,
            context=context,
            timeout_message=f"wait.for_window timed out after {timeout:g}s: {_window_label(step)}",
        )
        return f"window appeared: {_window_label(step)}"


class WaitForWindowGoneHandler:
    action_type = "wait.for_window_gone"
    metadata = ActionMetadata(
        action_name=action_type,
        schema_version="0.1",
        category="wait",
        required_params=(),
        optional_params=(
            "title_contains",
            "process_name",
            "timeout_seconds",
            "on_timeout",
            "name",
            "optional",
            "when",
        ),
        required_capabilities=("windows_uia", "window_management"),
        supported_platforms=WINDOWS_ONLY,
        side_effect_level="read_only",
        confirmation_policy="never",
        allowed_in_imported_packs=True,
    )

    def __init__(self, *, poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS) -> None:
        self.poll_interval_seconds = poll_interval_seconds

    def run(self, step: WaitForWindowGoneStep, context: ActionContext) -> str:
        timeout = step.timeout_seconds or DEFAULT_TIMEOUT_SECONDS
        _wait_until(
            lambda: not context.adapters.window.window_exists(
                title_contains=step.title_contains,
                process_name=step.process_name,
                timeout_seconds=0,
            ),
            timeout_seconds=timeout,
            poll_interval_seconds=self.poll_interval_seconds,
            context=context,
            timeout_message=f"wait.for_window_gone timed out after {timeout:g}s: {_window_label(step)}",
        )
        return f"window closed: {_window_label(step)}"


def create_wait_handlers():
    return (
        WaitSecondsHandler(),
        WaitForUserHandler(),
        WaitForFileHandler(),
        WaitForProcessHandler(),
        WaitForProcessExitHandler(),
        WaitForWindowHandler(),
        WaitForWindowGoneHandler(),
    )


def _wait_active_duration(
    duration_seconds: float,
    *,
    timeout_seconds: float,
    poll_interval_seconds: float,
    context: ActionContext,
    timeout_message: str,
) -> None:
    elapsed = 0.0
    while elapsed < duration_seconds:
        _cooperate(context)
        if elapsed >= timeout_seconds:
            raise RitualistError(timeout_message)
        remaining_duration = duration_seconds - elapsed
        remaining_timeout = timeout_seconds - elapsed
        sleep_seconds = min(poll_interval_seconds, remaining_duration, remaining_timeout)
        if sleep_seconds <= 0:
            raise RitualistError(timeout_message)
        time.sleep(sleep_seconds)
        elapsed += sleep_seconds
    _cooperate(context)


def _wait_until(
    predicate: Callable[[], bool],
    *,
    timeout_seconds: float,
    poll_interval_seconds: float,
    context: ActionContext,
    timeout_message: str,
) -> None:
    elapsed = 0.0
    while True:
        _cooperate(context)
        if predicate():
            return
        if elapsed >= timeout_seconds:
            raise RitualistError(timeout_message)
        sleep_seconds = min(poll_interval_seconds, timeout_seconds - elapsed)
        if sleep_seconds <= 0:
            raise RitualistError(timeout_message)
        time.sleep(sleep_seconds)
        elapsed += sleep_seconds


def _cooperate(context: ActionContext) -> None:
    if context.heartbeat is not None:
        context.heartbeat()
    if context.runtime_control is not None:
        context.runtime_control.heartbeat()
    if context.heartbeat is not None:
        context.heartbeat()


def _confirm_user(
    request: ConfirmationRequest,
    *,
    context: ActionContext,
    timeout_seconds: float | None,
) -> bool:
    if timeout_seconds is None:
        return context.confirm(request)

    results: queue.Queue[tuple[str, object]] = queue.Queue(maxsize=1)

    def run_confirmation() -> None:
        try:
            results.put(("result", context.confirm(request)))
        except Exception as exc:  # noqa: BLE001 - re-raised in runtime thread.
            results.put(("error", exc))

    thread = threading.Thread(target=run_confirmation, daemon=True)
    thread.start()
    deadline = time.monotonic() + timeout_seconds
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RitualistError(f"wait.for_user timed out after {timeout_seconds:g}s")
        try:
            kind, value = results.get(timeout=min(DEFAULT_POLL_INTERVAL_SECONDS, remaining))
        except queue.Empty:
            _cooperate(context)
            continue
        if kind == "error":
            if isinstance(value, BaseException):
                raise value
            raise RitualistError(str(value))
        return bool(value)


def _expand_path(raw: str) -> Path:
    expanded = os.path.expanduser(os.path.expandvars(raw))

    def replace_percent_var(match: re.Match[str]) -> str:
        key = match.group(1)
        return os.environ.get(key, match.group(0))

    return Path(re.sub(r"%([^%]+)%", replace_percent_var, expanded))


def _window_label(step: WaitForWindowStep | WaitForWindowGoneStep) -> str:
    return step.title_contains or step.process_name or "window"
