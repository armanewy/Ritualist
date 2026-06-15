from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .actions.base import StepResult
from .models import Recipe
from .paths import runs_dir


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    path: Path
    metadata: dict[str, Any]
    steps: list[dict[str, Any]]


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


def list_recent_runs(*, limit: int = 10, base_dir: Path | None = None) -> list[RunRecord]:
    root = base_dir or runs_dir()
    if not root.exists():
        return []
    records: list[RunRecord] = []
    for path in sorted(
        (candidate for candidate in root.iterdir() if candidate.is_dir()),
        key=lambda candidate: candidate.stat().st_mtime,
        reverse=True,
    ):
        record = load_run(path)
        if record is not None:
            records.append(record)
        if len(records) >= limit:
            break
    return records


def resolve_run_reference(run_id_or_path: str | Path, *, base_dir: Path | None = None) -> Path:
    raw = Path(run_id_or_path)
    if raw.exists() or raw.parent != Path("."):
        return raw
    return (base_dir or runs_dir()) / str(run_id_or_path)


def load_run(run_id_or_path: str | Path, *, base_dir: Path | None = None) -> RunRecord | None:
    path = resolve_run_reference(run_id_or_path, base_dir=base_dir)
    run_json = path / "run.json"
    steps_jsonl = path / "steps.jsonl"
    if not run_json.exists():
        return None
    try:
        metadata = json.loads(run_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    steps: list[dict[str, Any]] = []
    if steps_jsonl.exists():
        try:
            for line in steps_jsonl.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    steps.append(json.loads(line))
        except (OSError, json.JSONDecodeError):
            steps = []
    return RunRecord(run_id=path.name, path=path, metadata=metadata, steps=steps)
