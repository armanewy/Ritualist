from __future__ import annotations

import dataclasses
import json
import os
import sys
import threading
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

_WRITE_LOCK = threading.Lock()


def enabled() -> bool:
    return os.environ.get("RITUALIST_E2E") == "1" and bool(_artifact_dir_text())


def record_event(event: str, **payload: Any) -> None:
    """Write an opt-in acceptance event.

    This module is intentionally inert unless the acceptance harness sets both
    RITUALIST_E2E=1 and RITUALIST_E2E_ARTIFACT_DIR.
    """

    artifact_dir = _artifact_dir()
    if artifact_dir is None:
        return
    try:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        path = artifact_dir / f"ritualist-e2e-{os.getpid()}.jsonl"
        row = {
            "schema": "ritualist.e2e_event.v1",
            "event": event,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "process_id": os.getpid(),
            "executable": sys.executable,
            "payload": _to_jsonable(payload),
        }
        line = json.dumps(row, sort_keys=True) + "\n"
        with _WRITE_LOCK:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line)
    except Exception:
        return


def _artifact_dir() -> Path | None:
    text = _artifact_dir_text()
    if not text or os.environ.get("RITUALIST_E2E") != "1":
        return None
    return Path(text)


def _artifact_dir_text() -> str:
    return os.environ.get("RITUALIST_E2E_ARTIFACT_DIR", "").strip()


def _to_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            return model_dump(mode="json")
        except TypeError:
            return model_dump()
    if dataclasses.is_dataclass(value):
        return _to_jsonable(dataclasses.asdict(value))
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_jsonable(item) for item in value]
    return str(value)
