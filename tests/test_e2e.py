from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from enum import Enum
from pathlib import Path

from ritualist import paths
from ritualist.e2e import enabled, record_event


class _State(Enum):
    READY = "ready"


def test_record_event_is_inert_without_opt_in(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("RITUALIST_E2E", raising=False)
    monkeypatch.setenv("RITUALIST_E2E_ARTIFACT_DIR", str(tmp_path))

    record_event("acceptance.test", value=1)

    assert enabled() is False
    assert list(tmp_path.iterdir()) == []


def test_record_event_writes_jsonl_when_enabled(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("RITUALIST_E2E", "1")
    monkeypatch.setenv("RITUALIST_E2E_ARTIFACT_DIR", str(tmp_path))

    record_event("acceptance.test", path=tmp_path / "example.txt", state=_State.READY)

    [event_file] = list(tmp_path.glob("ritualist-e2e-*.jsonl"))
    rows = [json.loads(line) for line in event_file.read_text(encoding="utf-8").splitlines()]
    assert enabled() is True
    assert rows[0]["schema"] == "ritualist.e2e_event.v1"
    assert rows[0]["event"] == "acceptance.test"
    assert rows[0]["payload"]["path"].endswith("example.txt")
    assert rows[0]["payload"]["state"] == "ready"


def test_record_event_serializes_concurrent_writes(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("RITUALIST_E2E", "1")
    monkeypatch.setenv("RITUALIST_E2E_ARTIFACT_DIR", str(tmp_path))

    def write_event(index: int) -> None:
        record_event("acceptance.concurrent", index=index)

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(write_event, range(100)))

    [event_file] = list(tmp_path.glob("ritualist-e2e-*.jsonl"))
    rows = [json.loads(line) for line in event_file.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 100
    assert {row["payload"]["index"] for row in rows} == set(range(100))


def test_e2e_app_data_override_is_opt_in(monkeypatch, tmp_path: Path) -> None:
    override = tmp_path / "isolated-app-data"

    monkeypatch.setenv("RITUALIST_E2E_APP_DATA_DIR", str(override))
    monkeypatch.delenv("RITUALIST_E2E", raising=False)
    assert paths.app_data_path() != override

    monkeypatch.setenv("RITUALIST_E2E", "1")
    assert paths.app_data_path() == override
