from __future__ import annotations

from ritualist.models import BrowserMediaStep, BrowserOpenStep

from .base import ActionContext
from .metadata import ALL_PLATFORMS, ActionMetadata


class BrowserOpenHandler:
    action_type = "browser.open"
    metadata = ActionMetadata(
        action=action_type,
        schema_version="0.1",
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
        platform_support=ALL_PLATFORMS,
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
        action=action_type,
        schema_version="0.1",
        required_params=(),
        optional_params=("selector", "play", "loop", "muted", "timeout_seconds", "name", "optional"),
        required_capabilities=("playwright", "browser_control"),
        platform_support=ALL_PLATFORMS,
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
