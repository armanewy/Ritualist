from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .actions.base import StepResult
from .models import Recipe
from .paths import runs_dir


class RunLogWriter:
    def __init__(self, *, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or runs_dir()
        self.run_dir: Path | None = None
        self._run_json: Path | None = None
        self._steps_jsonl: Path | None = None
        self._metadata: dict[str, Any] = {}

    def start(self, recipe: Recipe, *, dry_run: bool) -> None:
        started_at = _now_iso()
        self.run_dir = self._create_run_dir(recipe.id)
        self._run_json = self.run_dir / "run.json"
        self._steps_jsonl = self.run_dir / "steps.jsonl"
        self._metadata = {
            "recipe_id": recipe.id,
            "recipe_name": recipe.name,
            "dry_run": dry_run,
            "status": "running",
            "started_at": started_at,
            "ended_at": None,
            "steps_total": len(recipe.steps),
            "steps_completed": 0,
        }
        self._write_run_json()
        self._steps_jsonl.write_text("", encoding="utf-8")

    def write_step(self, result: StepResult) -> None:
        if self._steps_jsonl is None:
            return
        payload = {
            "index": result.index,
            "step_name": result.step_name,
            "action": result.action,
            "status": result.status,
            "message": _safe_message(result),
            "started_at": result.started_at.isoformat(),
            "ended_at": result.ended_at.isoformat(),
            "optional": result.optional,
            "dry_run": result.dry_run,
        }
        with self._steps_jsonl.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self._metadata["steps_completed"] = result.index
        self._write_run_json()

    def finish(self, *, success: bool) -> None:
        if self._run_json is None:
            return
        self._metadata["status"] = "success" if success else "stopped"
        self._metadata["ended_at"] = _now_iso()
        self._write_run_json()

    def _create_run_dir(self, recipe_id: str) -> Path:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        base_name = f"{timestamp}_{recipe_id}"
        candidate = self.base_dir / base_name
        counter = 2
        while candidate.exists():
            candidate = self.base_dir / f"{base_name}_{counter}"
            counter += 1
        candidate.mkdir(parents=True, exist_ok=False)
        return candidate

    def _write_run_json(self) -> None:
        if self._run_json is None:
            return
        self._run_json.write_text(
            json.dumps(self._metadata, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


def _safe_message(result: StepResult) -> str:
    if result.action == "browser.open":
        if result.dry_run:
            return "would open URL"
        if result.status == "success":
            return "opened URL"
        return "browser.open did not complete"
    return result.message


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
