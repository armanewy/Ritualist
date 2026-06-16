from __future__ import annotations

import time

from ritualist.errors import RitualistError
from ritualist.models import (
    BrowserClickRoleStep,
    BrowserClickTestIdStep,
    BrowserClickTextStep,
    BrowserElementVisibleStep,
    BrowserMediaStep,
    BrowserOpenStep,
    BrowserWaitTextStep,
    BrowserWaitTitleStep,
    BrowserWaitUrlStep,
)

from .base import ActionContext, ActionOutcome
from .metadata import ALL_PLATFORMS, ActionMetadata


class BrowserOpenHandler:
    action_type = "browser.open"
    metadata = ActionMetadata(
        action_name=action_type,
        schema_version="0.1",
        category="browser",
        required_params=("url",),
        optional_params=(
            "browser",
            "profile",
            "new_window",
            "keep_open",
            "name",
            "optional",
            "timeout_seconds",
        ),
        required_capabilities=("playwright", "browser_control"),
        supported_platforms=ALL_PLATFORMS,
        side_effect_level="launches_app",
        confirmation_policy="optional",
        allowed_in_imported_packs=False,
    )

    def run(self, step: BrowserOpenStep, context: ActionContext) -> str:
        context.adapters.browser.open_url(
            step.url,
            browser=step.browser,
            profile=step.profile,
            new_window=step.new_window,
            keep_open=step.keep_open,
        )
        return f"opened {step.url}"


class BrowserMediaHandler:
    action_type = "browser.media"
    metadata = ActionMetadata(
        action_name=action_type,
        schema_version="0.1",
        category="browser",
        required_params=(),
        optional_params=("selector", "play", "loop", "muted", "timeout_seconds", "name", "optional"),
        required_capabilities=("playwright", "browser_control"),
        supported_platforms=ALL_PLATFORMS,
        side_effect_level="controls_ui",
        confirmation_policy="optional",
        allowed_in_imported_packs=False,
    )

    def run(self, step: BrowserMediaStep, context: ActionContext) -> str:
        context.adapters.browser.configure_media(
            selector=step.selector,
            play=step.play,
            loop=step.loop,
            muted=step.muted,
            timeout_seconds=step.timeout_seconds or 10.0,
        )
        changes = []
        if step.loop is not None:
            changes.append(f"loop={step.loop}")
        if step.play is not None:
            changes.append(f"play={step.play}")
        if step.muted is not None:
            changes.append(f"muted={step.muted}")
        return "configured media" + (f" ({', '.join(changes)})" if changes else "")


class BrowserWaitTextHandler:
    action_type = "browser.wait_text"
    metadata = ActionMetadata(
        action_name=action_type,
        schema_version="0.1",
        category="browser",
        required_params=("text",),
        optional_params=("exact", "timeout_seconds", "on_timeout", "name", "optional", "when"),
        required_capabilities=("playwright", "browser_control"),
        supported_platforms=ALL_PLATFORMS,
        side_effect_level="read_only",
        confirmation_policy="never",
        allowed_in_imported_packs=True,
    )

    def run(self, step: BrowserWaitTextStep, context: ActionContext) -> str:
        timeout = step.timeout_seconds or 10.0
        if not _wait_until(
            lambda: context.adapters.browser.text_visible(
                text=step.text,
                exact=step.exact,
                timeout_seconds=min(timeout, 0.25),
            ),
            timeout_seconds=timeout,
            context=context,
        ):
            raise RitualistError(f"browser.wait_text timed out: visible text not found: {step.text}")
        return f"visible browser text found: {step.text}"


class BrowserWaitTitleHandler:
    action_type = "browser.wait_title"
    metadata = ActionMetadata(
        action_name=action_type,
        schema_version="0.1",
        category="browser",
        required_params=(),
        optional_params=(
            "title",
            "title_contains",
            "timeout_seconds",
            "on_timeout",
            "name",
            "optional",
            "when",
        ),
        required_capabilities=("playwright", "browser_control"),
        supported_platforms=ALL_PLATFORMS,
        side_effect_level="read_only",
        confirmation_policy="never",
        allowed_in_imported_packs=True,
    )

    def run(self, step: BrowserWaitTitleStep, context: ActionContext) -> str:
        timeout = step.timeout_seconds or 10.0
        if not _wait_until(
            lambda: context.adapters.browser.title_matches(
                title=step.title,
                title_contains=step.title_contains,
                timeout_seconds=min(timeout, 0.25),
            ),
            timeout_seconds=timeout,
            context=context,
        ):
            target = step.title or step.title_contains or "title"
            raise RitualistError(f"browser.wait_title timed out: title not found: {target}")
        return f"browser title matched: {step.title or step.title_contains}"


class BrowserWaitUrlHandler:
    action_type = "browser.wait_url"
    metadata = ActionMetadata(
        action_name=action_type,
        schema_version="0.1",
        category="browser",
        required_params=(),
        optional_params=(
            "url",
            "url_contains",
            "timeout_seconds",
            "on_timeout",
            "name",
            "optional",
            "when",
        ),
        required_capabilities=("playwright", "browser_control"),
        supported_platforms=ALL_PLATFORMS,
        side_effect_level="read_only",
        confirmation_policy="never",
        allowed_in_imported_packs=True,
    )

    def run(self, step: BrowserWaitUrlStep, context: ActionContext) -> str:
        timeout = step.timeout_seconds or 10.0
        if not _wait_until(
            lambda: context.adapters.browser.url_matches(
                url=step.url,
                url_contains=step.url_contains,
                timeout_seconds=min(timeout, 0.25),
            ),
            timeout_seconds=timeout,
            context=context,
        ):
            target = step.url or step.url_contains or "URL"
            raise RitualistError(f"browser.wait_url timed out: URL not found: {target}")
        return f"browser URL matched: {step.url or step.url_contains}"


class BrowserElementVisibleHandler:
    action_type = "browser.element_visible"
    metadata = ActionMetadata(
        action_name=action_type,
        schema_version="0.1",
        category="browser",
        required_params=(),
        optional_params=(
            "text",
            "role",
            "accessible_name",
            "test_id",
            "exact",
            "timeout_seconds",
            "on_timeout",
            "name",
            "optional",
            "when",
        ),
        required_capabilities=("playwright", "browser_control"),
        supported_platforms=ALL_PLATFORMS,
        side_effect_level="read_only",
        confirmation_policy="never",
        allowed_in_imported_packs=True,
    )

    def run(self, step: BrowserElementVisibleStep, context: ActionContext) -> str:
        timeout = step.timeout_seconds or 10.0
        if not _wait_until(
            lambda: context.adapters.browser.element_visible(
                text=step.text,
                role=step.role,
                accessible_name=step.accessible_name,
                test_id=step.test_id,
                exact=step.exact,
                timeout_seconds=min(timeout, 0.25),
            ),
            timeout_seconds=timeout,
            context=context,
        ):
            raise RitualistError(
                f"browser.element_visible timed out: element not visible: {_element_target(step)}"
            )
        return f"browser element visible: {_element_target(step)}"


class BrowserClickTextHandler:
    action_type = "browser.click_text"
    metadata = ActionMetadata(
        action_name=action_type,
        schema_version="0.1",
        category="browser",
        required_params=("text",),
        optional_params=("exact", "requires_confirmation", "timeout_seconds", "name", "optional", "when"),
        required_capabilities=("playwright", "browser_control"),
        supported_platforms=ALL_PLATFORMS,
        side_effect_level="risky",
        confirmation_policy="optional",
        allowed_in_imported_packs=False,
    )

    def run(self, step: BrowserClickTextStep, context: ActionContext) -> ActionOutcome:
        context.adapters.browser.click_text(
            text=step.text,
            exact=step.exact,
            timeout_seconds=step.timeout_seconds or 10.0,
        )
        return ActionOutcome(
            message=f"clicked browser text: {step.text}",
            metadata={"browser_click": {"target_type": "text", "text": step.text}},
        )


class BrowserClickRoleHandler:
    action_type = "browser.click_role"
    metadata = ActionMetadata(
        action_name=action_type,
        schema_version="0.1",
        category="browser",
        required_params=("role", "accessible_name"),
        optional_params=("exact", "requires_confirmation", "timeout_seconds", "name", "optional", "when"),
        required_capabilities=("playwright", "browser_control"),
        supported_platforms=ALL_PLATFORMS,
        side_effect_level="risky",
        confirmation_policy="optional",
        allowed_in_imported_packs=False,
    )

    def run(self, step: BrowserClickRoleStep, context: ActionContext) -> ActionOutcome:
        context.adapters.browser.click_role(
            role=step.role,
            accessible_name=step.accessible_name,
            exact=step.exact,
            timeout_seconds=step.timeout_seconds or 10.0,
        )
        return ActionOutcome(
            message=f"clicked browser role: {step.role} named {step.accessible_name}",
            metadata={
                "browser_click": {
                    "target_type": "role",
                    "role": step.role,
                    "accessible_name": step.accessible_name,
                }
            },
        )


class BrowserClickTestIdHandler:
    action_type = "browser.click_test_id"
    metadata = ActionMetadata(
        action_name=action_type,
        schema_version="0.1",
        category="browser",
        required_params=("test_id",),
        optional_params=("requires_confirmation", "timeout_seconds", "name", "optional", "when"),
        required_capabilities=("playwright", "browser_control"),
        supported_platforms=ALL_PLATFORMS,
        side_effect_level="risky",
        confirmation_policy="optional",
        allowed_in_imported_packs=False,
    )

    def run(self, step: BrowserClickTestIdStep, context: ActionContext) -> ActionOutcome:
        context.adapters.browser.click_test_id(
            test_id=step.test_id,
            timeout_seconds=step.timeout_seconds or 10.0,
        )
        return ActionOutcome(
            message=f"clicked browser test id: {step.test_id}",
            metadata={"browser_click": {"target_type": "test_id", "test_id": step.test_id}},
        )


def create_browser_handlers():
    return (
        BrowserOpenHandler(),
        BrowserMediaHandler(),
        BrowserWaitTextHandler(),
        BrowserWaitTitleHandler(),
        BrowserWaitUrlHandler(),
        BrowserElementVisibleHandler(),
        BrowserClickTextHandler(),
        BrowserClickRoleHandler(),
        BrowserClickTestIdHandler(),
    )


def _wait_until(
    predicate,
    *,
    timeout_seconds: float | None,
    context: ActionContext,
    poll_interval_seconds: float = 0.25,
) -> bool:
    timeout = timeout_seconds or 0
    deadline = time.monotonic() + timeout
    while True:
        _cooperate(context)
        if predicate():
            return True
        if timeout <= 0 or time.monotonic() >= deadline:
            return False
        sleep_seconds = min(poll_interval_seconds, max(deadline - time.monotonic(), 0))
        if sleep_seconds <= 0:
            return False
        time.sleep(sleep_seconds)


def _cooperate(context: ActionContext) -> None:
    if context.heartbeat is not None:
        context.heartbeat()
    if context.runtime_control is not None:
        context.runtime_control.heartbeat()


def _element_target(step: BrowserElementVisibleStep) -> str:
    if step.text:
        return f"text {step.text}"
    if step.role:
        return f"role {step.role} named {step.accessible_name}"
    return f"test id {step.test_id}"
