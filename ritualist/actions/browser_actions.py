from __future__ import annotations

from ritualist.models import BrowserMediaStep, BrowserOpenStep

from .base import ActionContext


class BrowserOpenHandler:
    action_type = "browser.open"

    def run(self, step: BrowserOpenStep, context: ActionContext) -> str:
        context.adapters.browser.open_url(step.url, browser=step.browser)
        return f"opened {step.url}"


class BrowserMediaHandler:
    action_type = "browser.media"

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
