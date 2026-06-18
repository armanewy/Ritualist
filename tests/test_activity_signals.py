from __future__ import annotations

from pathlib import Path

import pytest

from ritualist.activity_signals import (
    OPEN_WINDOWS_SOURCE_ID,
    RECENT_ITEMS_SOURCE_ID,
    RITUALIST_JOURNAL_SOURCE_ID,
    ActivityCollectionResult,
    ActivitySignal,
    ActivityWarning,
    journal_event_signal,
    normalize_activity_metadata,
    process_name_signal,
    recent_reference_signal,
    window_metadata_signal,
)


def test_activity_signal_normalizes_allowed_journal_event() -> None:
    signal = ActivitySignal(
        kind="Journal Event",
        source_id="Ritualist Journal",
        label="  Coding Mode\n",
        value=" stopped ",
        metadata={"Recipe ID": "coding_mode", "run_id": "abc123"},
    )

    assert signal.kind == "journal_event"
    assert signal.source_id == RITUALIST_JOURNAL_SOURCE_ID
    assert signal.label == "Coding Mode"
    assert signal.value == "stopped"
    assert signal.metadata == {"recipe_id": "coding_mode", "run_id": "abc123"}
    assert signal.to_dict()["metadata"] == {"recipe_id": "coding_mode", "run_id": "abc123"}


@pytest.mark.parametrize(
    ("kind", "source_id"),
    [
        ("browser_history", RITUALIST_JOURNAL_SOURCE_ID),
        ("journal_event", "watch_me"),
        ("window_metadata", RECENT_ITEMS_SOURCE_ID),
        ("recent_reference", OPEN_WINDOWS_SOURCE_ID),
    ],
)
def test_activity_signal_rejects_forbidden_or_mismatched_sources(
    kind: str, source_id: str
) -> None:
    with pytest.raises(ValueError):
        ActivitySignal(kind=kind, source_id=source_id, label="bad")


@pytest.mark.parametrize(
    "metadata",
    [
        {"screenshot": "pixels"},
        {"ocr_text": "captured"},
        {"browser_history": ["https://example.test"]},
        {"browserhistory": ["https://example.test"]},
        {"file_contents": "secret"},
        {"coordinates": [10, 20]},
        {"x": 10},
        {"python": "print('no')"},
        {"nested": {"url": "https://example.test"}},
        {"screenshot_path": "C:/private.png"},
        {"recording_file": "capture.mp4"},
        {"click_coordinate_x": 10},
        {"keystroke_count": 5},
        {"keylog": "enabled"},
        {"keylogger": "enabled"},
        {"key_log": "enabled"},
        {"key logger": "enabled"},
        {"keyboard_logger": "enabled"},
        {"keyboard logger": "enabled"},
        {"keyboardlogger": "enabled"},
        {"ocr_result": "captured text"},
        {"browser_history_url": "https://example.test/private"},
        {"watch_me": "enabled"},
        {"watchme": "enabled"},
        {"watch-me": "enabled"},
        {"teach_by_watching": "enabled"},
        {"teachbywatching": "enabled"},
        {"screen_recorder": "enabled"},
        {"screen-recorder": "enabled"},
        {"screen recorder": "enabled"},
        {"screenrecorder": "enabled"},
        {"recorder": "enabled"},
        {"windows_recall": "enabled"},
        {"windowsrecall": "enabled"},
        {"screen capture": "enabled"},
        {"screencapture": "enabled"},
    ],
)
def test_activity_metadata_rejects_forbidden_capture_and_code_keys(
    metadata: dict[str, object]
) -> None:
    with pytest.raises(ValueError):
        normalize_activity_metadata(metadata)


def test_activity_signal_constructors_emit_allowed_shapes(tmp_path: Path) -> None:
    folder = tmp_path / "project"
    journal = journal_event_signal(label="Gaming Mode", value="success", metadata={"status": "success"})
    process = process_name_signal("Battle.net.exe")
    window = window_metadata_signal(
        title="Battle.net",
        app_name="Battle.net",
        process_name="Battle.net.exe",
        foreground=True,
    )
    reference = recent_reference_signal(
        reference_type="folder",
        label="Project Folder",
        target=folder,
    )

    assert journal.source_id == RITUALIST_JOURNAL_SOURCE_ID
    assert process.source_id == OPEN_WINDOWS_SOURCE_ID
    assert process.metadata == {"process_name": "Battle.net.exe"}
    assert window.metadata == {
        "title": "Battle.net",
        "app_name": "Battle.net",
        "process_name": "Battle.net.exe",
        "foreground": True,
    }
    assert reference.source_id == RECENT_ITEMS_SOURCE_ID
    assert reference.metadata == {"reference_type": "folder", "target": str(folder)}


@pytest.mark.parametrize("reference_type", ["app", "file", "folder"])
def test_recent_reference_types_are_limited_to_app_file_folder(reference_type: str) -> None:
    signal = recent_reference_signal(
        reference_type=reference_type,
        label="Recent",
        target="target",
    )

    assert signal.metadata["reference_type"] == reference_type


@pytest.mark.parametrize("reference_type", ["url", "browser", "history", "room"])
def test_recent_reference_rejects_non_app_file_folder_types(reference_type: str) -> None:
    with pytest.raises(ValueError):
        recent_reference_signal(reference_type=reference_type, label="Recent", target="target")


def test_activity_collection_result_serializes_warnings_and_signals() -> None:
    result = ActivityCollectionResult(
        collector_id=" Fake Collector ",
        signals=(process_name_signal("chrome.exe"),),
        warnings=(
            ActivityWarning(
                code=" unsupported-platform ",
                message=" Not available here ",
                source_id=OPEN_WINDOWS_SOURCE_ID,
            ),
        ),
        supported=False,
    )

    assert result.collector_id == "fake_collector"
    assert result.to_dict() == {
        "collector_id": "fake_collector",
        "supported": False,
        "signals": [
            {
                "kind": "process_name",
                "source_id": OPEN_WINDOWS_SOURCE_ID,
                "label": "chrome.exe",
                "value": "chrome.exe",
                "metadata": {"process_name": "chrome.exe"},
            }
        ],
        "warnings": [
            {
                "code": "unsupported_platform",
                "message": "Not available here",
                "source_id": OPEN_WINDOWS_SOURCE_ID,
                "severity": "warning",
            }
        ],
    }
