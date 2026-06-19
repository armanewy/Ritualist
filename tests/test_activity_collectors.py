from __future__ import annotations

from pathlib import Path

from setpiece import activity_collectors
from setpiece.activity_collectors import (
    ActivityCollectionContext,
    FakeActivityCollector,
    FakeOpenAppsCollector,
    FakeRecentReferencesCollector,
    FakeSetpieceJournalCollector,
    OpenWindowsCollector,
    SetpieceJournalCollector,
    collect_activity_signals,
)
from setpiece.activity_signals import (
    OPEN_WINDOWS_SOURCE_ID,
    RECENT_ITEMS_SOURCE_ID,
    SETPIECE_JOURNAL_SOURCE_ID,
    ActivityWarning,
    process_name_signal,
)
from setpiece.run_logs import RunRecord


def test_collect_activity_signals_is_on_demand_and_merges_fake_collectors() -> None:
    apps = FakeOpenAppsCollector(process_names=("Code.exe",))
    recent = FakeRecentReferencesCollector(
        references=(
            {"type": "folder", "label": "Project", "path": "C:/work/project"},
            {"type": "app", "label": "Editor", "target": "Code.exe"},
        )
    )

    assert apps.collect_count == 0
    assert recent.collect_count == 0

    result = collect_activity_signals((apps, recent))

    assert apps.collect_count == 1
    assert recent.collect_count == 1
    assert result.supported is True
    assert [signal.source_id for signal in result.signals] == [
        OPEN_WINDOWS_SOURCE_ID,
        RECENT_ITEMS_SOURCE_ID,
        RECENT_ITEMS_SOURCE_ID,
    ]
    assert [signal.metadata.get("reference_type") for signal in result.signals[1:]] == [
        "folder",
        "app",
    ]


def test_collect_activity_signals_truncates_to_context_limit() -> None:
    collector = FakeActivityCollector(
        collector_id="fake",
        signals=tuple(process_name_signal(f"app-{index}.exe") for index in range(4)),
    )

    result = collect_activity_signals(
        (collector,),
        context=ActivityCollectionContext(max_signals=2),
    )

    assert len(result.signals) == 2
    assert [warning.code for warning in result.warnings] == ["activity_signals_truncated"]


def test_collect_activity_signals_reports_collector_failures() -> None:
    class BrokenCollector:
        collector_id = "open_windows"

        def collect(self, *, context: ActivityCollectionContext | None = None):
            raise RuntimeError("boom")

    result = collect_activity_signals((BrokenCollector(),))

    assert result.supported is False
    assert result.signals == ()
    assert result.warnings[0].code == "collector_failed"
    assert "boom" in result.warnings[0].message


def test_fake_journal_collector_emits_sanitized_journal_events() -> None:
    collector = FakeSetpieceJournalCollector(
        events=(
            {
                "run_id": "run-1",
                "recipe_id": "gaming_mode",
                "recipe_name": "Gaming Mode",
                "status": "stopped",
                "steps": [{"name": "not copied"}],
            },
        )
    )

    result = collector.collect()

    assert result.collector_id == SETPIECE_JOURNAL_SOURCE_ID
    assert result.signals[0].label == "Gaming Mode"
    assert result.signals[0].value == "stopped"
    assert result.signals[0].metadata == {
        "recipe_id": "gaming_mode",
        "recipe_name": "Gaming Mode",
        "status": "stopped",
    }


def test_setpiece_journal_collector_uses_run_summaries_without_steps_or_notes(
    monkeypatch, tmp_path: Path
) -> None:
    record = RunRecord(
        run_id="run-1",
        path=tmp_path / "run-1",
        metadata={
            "recipe_id": "support_triage_workspace",
            "recipe_name": "Support Triage",
            "status": "success",
            "started_at": "2026-06-17T00:00:00Z",
            "ended_at": "2026-06-17T00:01:00Z",
        },
        steps=[{"name": "private step detail"}],
        notes=[{"body": "private note"}],
    )

    monkeypatch.setattr("setpiece.run_logs.list_recent_runs", lambda **_kwargs: [record])

    result = SetpieceJournalCollector(base_dir=tmp_path).collect()

    assert result.supported is True
    assert result.signals[0].metadata == {
        "recipe_id": "support_triage_workspace",
        "recipe_name": "Support Triage",
        "status": "success",
        "started_at": "2026-06-17T00:00:00Z",
        "ended_at": "2026-06-17T00:01:00Z",
        "run_id": "run-1",
    }
    serialized = result.to_dict()
    assert "private step detail" not in str(serialized)
    assert "private note" not in str(serialized)


def test_open_windows_collector_non_windows_returns_warning_empty_result(monkeypatch) -> None:
    monkeypatch.setattr(activity_collectors.sys, "platform", "linux")

    result = OpenWindowsCollector().collect()

    assert result.supported is False
    assert result.signals == ()
    assert result.warnings[0].code == "unsupported_platform"
    assert result.warnings[0].source_id == OPEN_WINDOWS_SOURCE_ID


def test_open_windows_collector_defaults_to_visible_windows_only() -> None:
    collector = OpenWindowsCollector()

    assert collector.include_windows is True
    assert collector.include_processes is False


def test_fake_open_apps_collector_emits_process_and_sanitized_window_metadata() -> None:
    result = FakeOpenAppsCollector(
        process_names=("Battle.net.exe",),
        windows=(
            {
                "title": "Battle.net",
                "app_name": "Battle.net",
                "process_name": "Battle.net.exe",
                "foreground": True,
                "bounds": "not copied",
            },
        ),
    ).collect()

    assert [signal.kind for signal in result.signals] == ["process_name", "window_metadata"]
    assert result.signals[1].metadata == {
        "title": "Battle.net",
        "app_name": "Battle.net",
        "process_name": "Battle.net.exe",
        "foreground": True,
    }
    assert "bounds" not in result.signals[1].metadata


def test_fake_recent_references_rejects_browser_history_shape() -> None:
    collector = FakeRecentReferencesCollector(
        references=({"type": "url", "label": "Visited", "target": "https://example.test"},)
    )

    result = collect_activity_signals((collector,))

    assert result.supported is False
    assert result.signals == ()
    assert result.warnings[0].code == "collector_failed"


def test_fake_activity_collector_preserves_warnings() -> None:
    warning = ActivityWarning(
        code="operator_review",
        source_id=RECENT_ITEMS_SOURCE_ID,
        message="needs review",
    )
    collector = FakeActivityCollector(
        collector_id="recent_items",
        warnings=(warning,),
        supported=True,
    )

    result = collect_activity_signals((collector,))

    assert result.supported is True
    assert result.warnings == (warning,)
