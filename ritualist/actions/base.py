from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from logging import Logger
from typing import Any, Protocol

from ritualist.models import Recipe, WorkflowStep


ConfirmationCallback = Callable[[str], bool]
StatusCallback = Callable[["StepEvent"], None]


@dataclass
class AdapterBundle:
    shell: Any
    browser: Any
    window: Any
    desktop: Any
    input: Any


@dataclass(frozen=True)
class StepEvent:
    index: int
    total: int
    step_name: str
    action: str
    status: str
    message: str = ""


@dataclass(frozen=True)
class StepResult:
    index: int
    step_name: str
    action: str
    status: str
    message: str
    started_at: datetime
    ended_at: datetime
    optional: bool = False
    dry_run: bool = False


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


class ActionHandler(Protocol):
    action_type: str

    def run(self, step: WorkflowStep, context: ActionContext) -> str:
        """Run an action and return a short user-facing message."""
