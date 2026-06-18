from __future__ import annotations

import os
from pathlib import Path

from ritualist.activity_collectors import (
    ActivityCollectionContext,
    FakeActivityCollector,
    FakeOpenAppsCollector,
    FakeRecentReferencesCollector,
)
from ritualist.activity_journal import ActivityJournal
from ritualist.activity_signals import (
    OPEN_WINDOWS_SOURCE_ID,
    RECENT_ITEMS_SOURCE_ID,
    RITUALIST_JOURNAL_SOURCE_ID,
    process_name_signal,
    window_metadata_signal,
)
from ritualist.collectors.open_windows import OpenWindowsAppsCollector
from ritualist.collectors.recent_items import RecentItemsCollector
from ritualist.local_activity_scan import (
    LocalActivityScanRequest,
    build_local_activity_collectors,
    scan_local_activity,
)


def test_scan_is_on_demand_and_caps_injected_collectors() -> None:
    apps = FakeOpenAppsCollector(process_names=("Code.exe", "Terminal.exe"))
    recent = FakeRecentReferencesCollector(
        references=(
            {"type": "folder", "label": "Project", "target": "Project"},
            {"type": "file", "label": "notes.md", "target": "notes.md"},
        )
    )

    assert apps.collect_count == 0
    assert recent.collect_count == 0

    result = scan_local_activity(
        LocalActivityScanRequest(max_signals=3),
        collectors=(apps, recent),
    )

    assert apps.collect_count == 1
    assert recent.collect_count == 1
    assert len(result.signals) == 3
    assert [signal.source_id for signal in result.signals] == [
        OPEN_WINDOWS_SOURCE_ID,
        OPEN_WINDOWS_SOURCE_ID,
        RECENT_ITEMS_SOURCE_ID,
    ]
    assert [warning.code for warning in result.warnings] == ["activity_signals_truncated"]


def test_default_scan_collects_nothing_without_explicit_sources() -> None:
    collectors = build_local_activity_collectors(LocalActivityScanRequest())
    result = scan_local_activity()

    assert collectors == ()
    assert result.signals == ()
    assert result.warnings == ()


def test_scan_turns_collector_exceptions_into_warnings() -> None:
    class BrokenCollector:
        collector_id = RECENT_ITEMS_SOURCE_ID

        def collect(self, *, context: ActivityCollectionContext | None = None):
            raise RuntimeError("boom")

    result = scan_local_activity(
        LocalActivityScanRequest(max_signals=5),
        collectors=(BrokenCollector(),),
    )

    assert result.supported is False
    assert result.signals == ()
    assert result.warnings[0].code == "collector_failed"
    assert "boom" in result.warnings[0].message


def test_default_builder_uses_only_allowed_selected_sources(tmp_path: Path) -> None:
    request = LocalActivityScanRequest(
        source_ids=("recent-items", "watch_me", "browser_history"),
        recent_item_roots=(tmp_path,),
    )

    collectors = build_local_activity_collectors(request)

    assert [collector.collector_id for collector in collectors] == [RECENT_ITEMS_SOURCE_ID]


def test_open_windows_collector_redacts_window_titles_by_default(monkeypatch) -> None:
    class FakeDelegate:
        def __init__(self, **_kwargs):
            pass

        def collect(self, *, context: ActivityCollectionContext | None = None):
            return FakeActivityCollector(
                collector_id=OPEN_WINDOWS_SOURCE_ID,
                signals=(
                    window_metadata_signal(
                        title="Secret Roadmap - Editor",
                        process_name="editor.exe",
                        foreground=True,
                    ),
                ),
            ).collect(context=context)

    monkeypatch.setattr("ritualist.collectors.open_windows.OpenWindowsCollector", FakeDelegate)

    result = OpenWindowsAppsCollector().collect()

    serialized = str(result.to_dict())
    assert "Secret Roadmap" not in serialized
    assert result.signals[0].label == "editor.exe"
    assert result.signals[0].metadata == {
        "title": "editor.exe",
        "app_name": "",
        "process_name": "editor.exe",
        "foreground": True,
    }


def test_open_windows_collector_can_include_titles_when_explicitly_requested(monkeypatch) -> None:
    class FakeDelegate:
        def __init__(self, **_kwargs):
            pass

        def collect(self, *, context: ActivityCollectionContext | None = None):
            return FakeActivityCollector(
                collector_id=OPEN_WINDOWS_SOURCE_ID,
                signals=(
                    window_metadata_signal(
                        title="Visible Window",
                        process_name="editor.exe",
                    ),
                ),
            ).collect(context=context)

    monkeypatch.setattr("ritualist.collectors.open_windows.OpenWindowsCollector", FakeDelegate)

    result = OpenWindowsAppsCollector(include_window_titles=True).collect()

    assert result.signals[0].metadata["title"] == "Visible Window"


def test_recent_items_collector_is_shallow_limited_and_metadata_only(tmp_path: Path) -> None:
    root = tmp_path / "recent"
    root.mkdir()
    nested = root / "nested"
    nested.mkdir()
    hidden_detail = nested / "private.txt"
    hidden_detail.write_text("do not read or expose", encoding="utf-8")
    older = root / "older.txt"
    newer = root / "newer.txt"
    app = root / "tool.exe"
    older.write_text("older content", encoding="utf-8")
    newer.write_text("newer content", encoding="utf-8")
    app.write_text("binary placeholder", encoding="utf-8")
    os.utime(older, (10, 10))
    os.utime(nested, (20, 20))
    os.utime(newer, (30, 30))
    os.utime(app, (40, 40))

    result = RecentItemsCollector(
        roots=(root,),
        max_items=2,
        include_default_windows_recent=False,
    ).collect()

    assert [signal.label for signal in result.signals] == ["tool.exe", "newer.txt"]
    assert [signal.metadata["reference_type"] for signal in result.signals] == ["app", "file"]
    assert all(signal.metadata["target"] == signal.label for signal in result.signals)
    assert "private.txt" not in str(result.to_dict())
    assert "do not read or expose" not in str(result.to_dict())
    assert [warning.code for warning in result.warnings] == ["recent_items_truncated"]


def test_recent_items_collector_handles_unavailable_roots_as_warning(tmp_path: Path) -> None:
    missing_root = tmp_path / "missing"

    result = RecentItemsCollector(
        roots=(missing_root,),
        include_default_windows_recent=False,
    ).collect()

    assert result.signals == ()
    assert result.warnings[0].code == "recent_items_root_unavailable"


def test_activity_journal_scan_uses_sanitized_activity_journal_contract(tmp_path: Path) -> None:
    journal = ActivityJournal(path=tmp_path / "activity.jsonl", enabled=True)
    assert journal.write(
        "shortcut_opened",
        shortcut_id="open_docs",
        url="https://example.test/private",
        folder_path="C:/Users/alice/Documents/Project",
        screenshot="pixels",
        coordinates={"x": 10, "y": 20},
    )

    result = scan_local_activity(
        LocalActivityScanRequest(
            source_ids=(RITUALIST_JOURNAL_SOURCE_ID,),
            journal=journal,
        )
    )

    assert len(result.signals) == 1
    signal = result.signals[0]
    assert signal.source_id == RITUALIST_JOURNAL_SOURCE_ID
    assert signal.label == "open_docs"
    assert signal.value == "shortcut_opened"
    assert signal.metadata == {
        "event_type": "shortcut_opened",
        "shortcut_id": "open_docs",
    }
    assert "example.test" not in str(result.to_dict())
    assert "Project" not in str(result.to_dict())


def test_scan_has_no_scheduler_or_monitor_methods() -> None:
    collector = FakeActivityCollector(
        collector_id=OPEN_WINDOWS_SOURCE_ID,
        signals=(process_name_signal("Code.exe"),),
    )

    result = scan_local_activity(collectors=(collector,))

    assert len(result.signals) == 1
    assert not hasattr(result, "start")
    assert not hasattr(result, "stop")
