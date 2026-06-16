from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from logging import Logger
from typing import Any, Protocol

from ritualist.config import AppConfig
from ritualist.actions.metadata import ActionMetadata
from ritualist.models import ExecutableStep, Recipe
from ritualist.overlay import ConfirmationRequest, OverlayController
from ritualist.runtime_control import RuntimeControl


ConfirmationCallback = Callable[[ConfirmationRequest | str], bool]
StatusCallback = Callable[["StepEvent"], None]


@dataclass
class AdapterBundle:
    shell: Any
    browser: Any
    window: Any
    desktop: Any
    input: Any


@dataclass(frozen=True)
class ActionOutcome:
    message: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StepEvent:
    index: int
    total: int
    step_name: str
    action: str
    status: str
    message: str = ""
    wait_action: str = ""
    wait_target: str = ""
    wait_started_at: datetime | None = None
    wait_elapsed_seconds: float | None = None
    wait_timeout_seconds: float | None = None
    keep_open_active: bool = False


@dataclass(frozen=True)
class StepResult:
    index: int
    step_name: str
    action: str
    status: str
    message: str
    started_at: datetime
    ended_at: datetime
    phase: str = "steps"
    optional: bool = False
    dry_run: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RunSummary:
    recipe_id: str
    recipe_name: str
    results: list[StepResult]
    run_dir: Path | None = None

    @property
    def success(self) -> bool:
        return all(result.status in {"success", "skipped", "dry-run"} for result in self.results)


@dataclass
class ActionContext:
    adapters: AdapterBundle
    dry_run: bool
    logger: Logger
    confirm: ConfirmationCallback
    recipe: Recipe
    config: AppConfig
    overlay: OverlayController
    runtime_control: RuntimeControl
    heartbeat: Callable[[], None] | None = None


class ActionHandler(Protocol):
    action_type: str
    metadata: ActionMetadata

    def run(self, step: ExecutableStep, context: ActionContext) -> str | ActionOutcome:
        """Run an action and return a short user-facing message plus optional metadata."""


def target_region_metadata(region: Any) -> dict[str, Any]:
    if region is None:
        return {}

    preview: dict[str, Any] = {}
    window_title = getattr(region, "window_title", None)
    target_text = getattr(region, "target_text", None)
    control_type = getattr(region, "control_type", None)
    rect = getattr(region, "rect", None)

    if window_title:
        preview["window_title"] = str(window_title)
    if target_text:
        preview["target_text"] = str(target_text)
    if control_type:
        preview["control_type"] = str(control_type)
    if rect is not None and getattr(rect, "is_valid", True):
        preview["bounds"] = {
            "x": int(getattr(rect, "x")),
            "y": int(getattr(rect, "y")),
            "width": int(getattr(rect, "width")),
            "height": int(getattr(rect, "height")),
        }

    return {"target_preview": preview} if preview else {}
