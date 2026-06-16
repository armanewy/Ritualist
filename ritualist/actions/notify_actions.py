from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from ritualist.models import NotifyBeepStep, NotifySoundStep, NotifyToastStep

from .base import ActionContext, ActionOutcome
from .metadata import ALL_PLATFORMS, ActionMetadata


class NotifyToastHandler:
    action_type = "notify.toast"
    metadata = ActionMetadata(
        action_name=action_type,
        schema_version="0.1",
        category="notify",
        required_params=("title", "message"),
        optional_params=("name", "optional", "when"),
        required_capabilities=(),
        supported_platforms=ALL_PLATFORMS,
        side_effect_level="read_only",
        confirmation_policy="never",
        allowed_in_imported_packs=True,
    )

    def run(self, step: NotifyToastStep, context: ActionContext) -> ActionOutcome:
        context.logger.info("notification: %s - %s", step.title, step.message)
        return ActionOutcome(
            message=f"notification: {step.title} - {step.message}",
            metadata={"notification": {"type": "toast", "title": step.title}},
        )


class NotifyBeepHandler:
    action_type = "notify.beep"
    metadata = ActionMetadata(
        action_name=action_type,
        schema_version="0.1",
        category="notify",
        required_params=(),
        optional_params=("name", "optional", "when"),
        required_capabilities=(),
        supported_platforms=ALL_PLATFORMS,
        side_effect_level="read_only",
        confirmation_policy="never",
        allowed_in_imported_packs=True,
    )

    def run(self, step: NotifyBeepStep, context: ActionContext) -> ActionOutcome:
        _play_fallback_beep()
        context.logger.info("notification beep")
        return ActionOutcome(
            message="notification beep",
            metadata={"notification": {"type": "beep"}},
        )


class NotifySoundHandler:
    action_type = "notify.sound"
    metadata = ActionMetadata(
        action_name=action_type,
        schema_version="0.1",
        category="notify",
        required_params=(),
        optional_params=("path", "name", "optional", "when"),
        required_capabilities=(),
        supported_platforms=ALL_PLATFORMS,
        side_effect_level="read_only",
        confirmation_policy="never",
        allowed_in_imported_packs=True,
    )

    def run(self, step: NotifySoundStep, context: ActionContext) -> ActionOutcome:
        if step.path:
            path = _expand_path(step.path)
            if path.exists() and path.is_file():
                played = _play_local_sound(path)
                if played:
                    return ActionOutcome(
                        message=f"played sound: {path}",
                        metadata={"notification": {"type": "sound", "path": str(path)}},
                    )
                _play_fallback_beep()
                return ActionOutcome(
                    message=f"sound playback unavailable, used fallback beep: {path}",
                    metadata={
                        "notification": {
                            "type": "sound",
                            "path": str(path),
                            "fallback": "beep",
                        }
                    },
                )
            _play_fallback_beep()
            return ActionOutcome(
                message=f"sound file missing, used fallback beep: {path}",
                metadata={
                    "notification": {
                        "type": "sound",
                        "path": str(path),
                        "fallback": "beep",
                        "missing": True,
                    }
                },
            )
        _play_fallback_beep()
        return ActionOutcome(
            message="no sound file provided, used fallback beep",
            metadata={"notification": {"type": "sound", "fallback": "beep"}},
        )


def create_notification_handlers():
    return (
        NotifyToastHandler(),
        NotifySoundHandler(),
        NotifyBeepHandler(),
    )


def _play_local_sound(path: Path) -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winsound
    except ImportError:
        return False
    try:
        winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
    except RuntimeError:
        return False
    return True


def _play_fallback_beep() -> None:
    if sys.platform == "win32":
        try:
            import winsound

            winsound.MessageBeep()
            return
        except Exception:  # noqa: BLE001 - notification fallback is best-effort.
            pass
    try:
        sys.stdout.write("\a")
        sys.stdout.flush()
    except Exception:  # noqa: BLE001 - notification fallback must not fail a workflow.
        pass


def _expand_path(raw: str) -> Path:
    expanded = os.path.expanduser(os.path.expandvars(raw))

    def replace_percent_var(match: re.Match[str]) -> str:
        key = match.group(1)
        return os.environ.get(key, match.group(0))

    return Path(re.sub(r"%([^%]+)%", replace_percent_var, expanded))
