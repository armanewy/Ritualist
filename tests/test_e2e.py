from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from enum import Enum
from pathlib import Path

from setpiece import paths
from setpiece.e2e import enabled, record_event


class _State(Enum):
    READY = "ready"


def test_record_event_is_inert_without_opt_in(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("SETPIECE_E2E", raising=False)
    monkeypatch.setenv("SETPIECE_E2E_ARTIFACT_DIR", str(tmp_path))

    record_event("acceptance.test", value=1)

    assert enabled() is False
    assert list(tmp_path.iterdir()) == []


def test_record_event_writes_jsonl_when_enabled(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SETPIECE_E2E", "1")
    monkeypatch.setenv("SETPIECE_E2E_ARTIFACT_DIR", str(tmp_path))

    record_event("acceptance.test", path=tmp_path / "example.txt", state=_State.READY)

    [event_file] = list(tmp_path.glob("setpiece-e2e-*.jsonl"))
    rows = [json.loads(line) for line in event_file.read_text(encoding="utf-8").splitlines()]
    assert enabled() is True
    assert rows[0]["schema"] == "setpiece.e2e_event.v1"
    assert rows[0]["event"] == "acceptance.test"
    assert rows[0]["payload"]["path"].endswith("example.txt")
    assert rows[0]["payload"]["state"] == "ready"


def test_record_event_serializes_concurrent_writes(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SETPIECE_E2E", "1")
    monkeypatch.setenv("SETPIECE_E2E_ARTIFACT_DIR", str(tmp_path))

    def write_event(index: int) -> None:
        record_event("acceptance.concurrent", index=index)

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(write_event, range(100)))

    [event_file] = list(tmp_path.glob("setpiece-e2e-*.jsonl"))
    rows = [json.loads(line) for line in event_file.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 100
    assert {row["payload"]["index"] for row in rows} == set(range(100))


def test_e2e_app_data_override_is_opt_in(monkeypatch, tmp_path: Path) -> None:
    override = tmp_path / "isolated-app-data"

    monkeypatch.setenv("SETPIECE_E2E_APP_DATA_DIR", str(override))
    monkeypatch.delenv("SETPIECE_E2E", raising=False)
    assert paths.app_data_path() != override

    monkeypatch.setenv("SETPIECE_E2E", "1")
    assert paths.app_data_path() == override


def test_e2e_path_override_keeps_logs_and_legacy_paths_isolated(
    monkeypatch,
    tmp_path: Path,
) -> None:
    override = tmp_path / "isolated-app-data"

    monkeypatch.setenv("SETPIECE_E2E", "1")
    monkeypatch.setenv("SETPIECE_E2E_APP_DATA_DIR", str(override))

    assert paths.app_data_path() == override
    assert paths.logs_path() == override / "logs"
    assert paths.default_log_file() == override / "logs" / "setpiece.log"
    assert paths.legacy_app_data_path() == override / "legacy" / "Ritualist"
    assert paths.legacy_logs_path() == override / "legacy" / "Ritualist-Logs"
