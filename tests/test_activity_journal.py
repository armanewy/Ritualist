from __future__ import annotations

import json

from setpiece.activity_journal import (
    ActivityJournal,
    ALLOWED_EVENT_TYPES,
    JournalEvent,
    delete_journal,
    read_journal,
)


def _jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_journal_does_not_write_when_local_learning_is_disabled(tmp_path) -> None:
    path = tmp_path / "activity.jsonl"
    journal = ActivityJournal(path=path, enabled=False)

    assert journal.write("room_opened", room_id="gaming_desktop") is False

    assert not path.exists()


def test_journal_writes_allowed_setpiece_owned_events_when_enabled(tmp_path) -> None:
    path = tmp_path / "activity.jsonl"
    journal = ActivityJournal(path=path, enabled=True)

    for event_type in sorted(ALLOWED_EVENT_TYPES):
        assert journal.write(event_type, room_id="gaming_desktop", component_id="play") is True

    entries = _jsonl(path)
    assert [entry["event_type"] for entry in entries] == sorted(ALLOWED_EVENT_TYPES)
    assert all(entry["schema_version"] == "setpiece.activity_journal.v1" for entry in entries)


def test_journal_rejects_unknown_or_non_setpiece_events(tmp_path) -> None:
    path = tmp_path / "activity.jsonl"
    journal = ActivityJournal(path=path, enabled=True)

    assert journal.write("browser_history_seen", url="https://example.com/private") is False
    assert journal.write("screenshot_captured", path="C:/Users/me/Desktop/private.png") is False

    assert not path.exists()


def test_journal_sanitizes_urls_paths_and_forbidden_capture_fields(tmp_path) -> None:
    path = tmp_path / "activity.jsonl"
    journal = ActivityJournal(path=path, enabled=True)

    assert journal.write(
        "shortcut_opened",
        url="https://example.test/private/page?q=secret",
        folder_path="C:/Users/alice/Documents/Project",
        screenshot="base64-pixels",
        coordinates={"x": 12, "y": 34},
        nested={
            "file": "/home/alice/token.txt",
            "keystrokes": "hunter2",
            "label": "Docs shortcut",
        },
    )

    payload = _jsonl(path)[0]["payload"]
    assert payload == {
        "folder_path": "Project",
        "nested": {"file": "token.txt", "label": "Docs shortcut"},
        "url": "example.test",
    }


def test_journal_write_is_nonfatal_on_io_errors(tmp_path) -> None:
    directory_path = tmp_path / "journal-as-directory"
    directory_path.mkdir()
    journal = ActivityJournal(path=directory_path, enabled=True)

    assert journal.write("room_opened", room_id="support_desk") is False


def test_journal_enabled_predicate_is_nonfatal_and_dynamic(tmp_path) -> None:
    path = tmp_path / "activity.jsonl"
    enabled = False
    journal = ActivityJournal(path=path, enabled=lambda: enabled)

    assert journal.write("room_opened", room_id="project_room") is False
    enabled = True
    assert journal.write("room_opened", room_id="project_room") is True

    assert len(_jsonl(path)) == 1


def test_journal_reader_is_bounded_and_skips_malformed_lines(tmp_path) -> None:
    path = tmp_path / "activity.jsonl"
    journal = ActivityJournal(path=path, enabled=True)
    for index in range(6):
        assert journal.write("component_clicked", component_id=f"component-{index}")
    with path.open("a", encoding="utf-8") as handle:
        handle.write("{not json}\n")
        handle.write(json.dumps({"schema_version": "other", "event_type": "room_opened"}) + "\n")

    events = read_journal(path, limit=3)

    assert [event.event_type for event in events] == ["component_clicked"] * 3
    assert [event.payload["component_id"] for event in events] == [
        "component-3",
        "component-4",
        "component-5",
    ]


def test_journal_delete_removes_file_and_is_idempotent(tmp_path) -> None:
    path = tmp_path / "activity.jsonl"
    journal = ActivityJournal(path=path, enabled=True)
    assert journal.write("recipe_dry_run", recipe_id="safe_setup") is True

    assert journal.delete() is True
    assert not path.exists()
    assert delete_journal(path) is True


def test_journal_read_returns_typed_events(tmp_path) -> None:
    path = tmp_path / "activity.jsonl"
    journal = ActivityJournal(path=path, enabled=True)
    assert journal.write("recipe_run_finished", recipe_id="support_triage", status="success")

    events = journal.read(limit=10)

    assert events == [
        JournalEvent(
            event_type="recipe_run_finished",
            payload={"recipe_id": "support_triage", "status": "success"},
        )
    ]
