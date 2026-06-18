from __future__ import annotations

from ritualist.activity_signals import (
    ActivityCollectionResult,
    journal_event_signal,
    process_name_signal,
    recent_reference_signal,
)
from ritualist.suggestions.miner import mine_suggestions
from ritualist.suggestions.models import SuggestionKind, SuggestionPrivacyLevel
from ritualist.suggestions.storage import SuggestionStore


def test_miner_promotes_repeated_single_folder_app_and_domain_to_shortcuts() -> None:
    signals = (
        recent_reference_signal(
            reference_type="folder",
            label="Project Area",
            target="C:/Users/alice/Project Area",
        ),
        recent_reference_signal(reference_type="folder", label="Downloads", target="Downloads"),
        recent_reference_signal(
            reference_type="folder",
            label="Project Area",
            target="C:/Users/alice/Project Area",
        ),
        process_name_signal("Code.exe"),
        process_name_signal("Code.exe"),
        journal_event_signal(
            label="docs",
            value="shortcut_opened",
            metadata={"event_type": "shortcut_opened", "domain": "docs.example.com"},
        ),
        journal_event_signal(
            label="docs",
            value="shortcut_opened",
            metadata={"event_type": "shortcut_opened", "domain": "docs.example.com"},
        ),
    )

    suggestions = mine_suggestions(ActivityCollectionResult(signals=signals))
    shortcut_titles = {
        suggestion.title
        for suggestion in suggestions
        if suggestion.kind is SuggestionKind.SHORTCUT_COMPONENT
    }

    assert "Review Project Area shortcut" in shortcut_titles
    assert "Review Code shortcut" in shortcut_titles
    assert "Review docs example domain shortcut" in shortcut_titles
    assert "Review Downloads shortcut" not in shortcut_titles

    serialized = str([suggestion.to_dict() for suggestion in suggestions])
    assert "C:/Users/alice" not in serialized
    assert "Code.exe" not in serialized
    assert "docs.example.com" not in serialized


def test_miner_detects_multistep_app_folder_and_app_domain_clusters_without_raw_urls() -> None:
    events = [
        process_name_signal("Editor.exe"),
        recent_reference_signal(
            reference_type="folder",
            label="Workspace",
            target="C:/Users/alice/Workspace",
        ),
        process_name_signal("Editor.exe"),
        recent_reference_signal(
            reference_type="folder",
            label="Workspace",
            target="C:/Users/alice/Workspace",
        ),
        {
            "event_type": "shortcut_opened",
            "source_id": "ritualist_journal",
            "payload": {
                "context_id": "support-1",
                "app_label": "Browser",
                "domain": "portal.example.com",
                "shortcut_id": "open_portal",
            },
        },
        {
            "event_type": "shortcut_opened",
            "source_id": "ritualist_journal",
            "payload": {
                "context_id": "support-2",
                "app_label": "Browser",
                "domain": "portal.example.com",
                "shortcut_id": "open_portal",
            },
        },
    ]

    suggestions = mine_suggestions(events)
    ritual_titles = {
        suggestion.title
        for suggestion in suggestions
        if suggestion.kind is SuggestionKind.RITUAL_RECIPE
    }

    assert "Review Editor + Workspace ritual" in ritual_titles
    assert "Review Browser + portal example domain ritual" in ritual_titles
    assert all(suggestion.status.value == "new" for suggestion in suggestions)

    serialized = str([suggestion.to_dict() for suggestion in suggestions])
    assert "portal.example.com" not in serialized
    assert "https://" not in serialized
    assert "C:/Users/alice" not in serialized
    assert "sequence" not in serialized.casefold()


def test_miner_detects_ritual_shortcut_and_room_usage_clusters() -> None:
    events = [
        {
            "event_type": "recipe_run_finished",
            "source_id": "ritualist_journal",
            "payload": {
                "run_id": "support-run-1",
                "room_id": "support_desk",
                "recipe_id": "support_shift",
                "shortcut_id": "ticket_queue",
                "status": "finished",
            },
        },
        {
            "event_type": "recipe_run_finished",
            "source_id": "ritualist_journal",
            "payload": {
                "run_id": "support-run-2",
                "room_id": "support_desk",
                "recipe_id": "support_shift",
                "shortcut_id": "ticket_queue",
                "status": "finished",
            },
        },
        {
            "event_type": "room_opened",
            "source_id": "ritualist_journal",
            "payload": {"room_id": "minimal_desktop", "app_label": "Internal Fixture"},
        },
        {
            "event_type": "room_opened",
            "source_id": "ritualist_journal",
            "payload": {"room_id": "minimal_desktop", "app_label": "Internal Fixture"},
        },
    ]

    suggestions = mine_suggestions(events)

    assert any(
        suggestion.kind is SuggestionKind.RITUAL_RECIPE
        and suggestion.title == "Review support shift + ticket queue ritual"
        for suggestion in suggestions
    )
    room_suggestions = [
        suggestion for suggestion in suggestions if suggestion.kind is SuggestionKind.ROOM_CANVAS
    ]
    assert [suggestion.title for suggestion in room_suggestions] == ["Review Support Desk canvas"]
    assert room_suggestions[0].proposed_actions == (
        {
            "action": "review_room_canvas",
            "kind": "room_canvas",
            "room_id": "support_desk",
            "label": "Support Desk",
            "description": "Review only Room canvas suggestion; no Room is created.",
        },
    )

    serialized = str([suggestion.to_dict() for suggestion in suggestions])
    assert "minimal_desktop" not in serialized
    assert "Internal Fixture" not in serialized


def test_miner_suppresses_forbidden_sources_capture_metadata_and_sensitive_labels() -> None:
    suggestions = mine_suggestions(
        [
            {
                "kind": "journal_event",
                "source_id": "browser_history",
                "label": "history",
                "value": "shortcut_opened",
                "metadata": {"event_type": "shortcut_opened", "domain": "docs.example.com"},
            },
            {
                "event_type": "shortcut_opened",
                "source_id": "ritualist_journal",
                "payload": {
                    "folder_label": "Safe Project",
                    "coordinates": "10,20",
                },
            },
            {
                "event_type": "shortcut_opened",
                "source_id": "ritualist_journal",
                "payload": {
                    "folder_label": "Safe Project",
                    "keylogger": "enabled",
                },
            },
            {
                "event_type": "shortcut_opened",
                "source_id": "ritualist_journal",
                "payload": {
                    "folder_label": "Safe Project",
                    "key logger": "enabled",
                },
            },
            {
                "event_type": "shortcut_opened",
                "source_id": "ritualist_journal",
                "payload": {
                    "folder_label": "Safe Project",
                    "watch_me": "enabled",
                },
            },
            {
                "event_type": "shortcut_opened",
                "source_id": "ritualist_journal",
                "payload": {
                    "folder_label": "Safe Project",
                    "teach_by_watching": "enabled",
                },
            },
            {
                "event_type": "shortcut_opened",
                "source_id": "ritualist_journal",
                "payload": {
                    "folder_label": "C:/Users/alice/PrivateVault",
                    "domain": "secret.example.com",
                },
            },
            {
                "event_type": "shortcut_opened",
                "source_id": "ritualist_journal",
                "payload": {
                    "folder_label": "C:/Users/alice/PrivateVault",
                    "domain": "secret.example.com",
                },
            },
        ]
    )

    assert suggestions == ()


def test_miner_suppresses_forbidden_open_window_capture_app_labels() -> None:
    suggestions = mine_suggestions(
        [
            process_name_signal("Screen Recorder.exe"),
            process_name_signal("Screen Recorder.exe"),
            process_name_signal("Recorder.exe"),
            process_name_signal("Recorder.exe"),
            process_name_signal("Windows Recall.exe"),
            process_name_signal("Windows Recall.exe"),
            process_name_signal("WindowsRecall.exe"),
            process_name_signal("WindowsRecall.exe"),
            process_name_signal("Teach By Watching.exe"),
            process_name_signal("Teach By Watching.exe"),
            process_name_signal("TeachByWatching.exe"),
            process_name_signal("TeachByWatching.exe"),
            process_name_signal("ScreenRecorder.exe"),
            process_name_signal("ScreenRecorder.exe"),
            process_name_signal("ScreenCapture.exe"),
            process_name_signal("ScreenCapture.exe"),
            process_name_signal("Keylogger.exe"),
            process_name_signal("Keylogger.exe"),
            process_name_signal("Keylog.exe"),
            process_name_signal("Keylog.exe"),
            process_name_signal("Key Log.exe"),
            process_name_signal("Key Log.exe"),
            process_name_signal("Key Logger.exe"),
            process_name_signal("Key Logger.exe"),
            process_name_signal("Keyboard Logger.exe"),
            process_name_signal("Keyboard Logger.exe"),
        ]
    )

    assert suggestions == ()


def test_miner_rejects_nested_label_metadata_before_stringifying() -> None:
    suggestions = mine_suggestions(
        [
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"app_name": {"url": "www.example.dev/customer-a"}},
            },
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"app_name": {"url": "www.example.dev/customer-a"}},
            },
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"folder_label": {"path": "C:/Users/alice/Secret/customer-a"}},
            },
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"folder_label": {"path": "C:/Users/alice/Secret/customer-a"}},
            },
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"domain_label": ["www.example.dev/customer-a"]},
            },
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"domain_label": ["www.example.dev/customer-a"]},
            },
        ]
    )

    assert suggestions == ()


def test_miner_rejects_bytes_label_metadata_before_stringifying() -> None:
    suggestions = mine_suggestions(
        [
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"app_name": b"www.example.dev/customer-a"},
            },
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"app_name": b"www.example.dev/customer-a"},
            },
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"folder_label": bytearray(b"C:/Users/alice/Secret/customer-a")},
            },
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"folder_label": bytearray(b"C:/Users/alice/Secret/customer-a")},
            },
        ]
    )

    assert suggestions == ()


def test_miner_rejects_schemeless_url_text_for_app_and_folder_labels() -> None:
    suggestions = mine_suggestions(
        [
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"app_name": "www.example.dev/customer-a"},
            },
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"app_name": "www.example.dev/customer-a"},
            },
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"folder_label": "project.example.test/raw"},
            },
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"folder_label": "project.example.test/raw"},
            },
        ]
    )

    assert suggestions == ()


def test_miner_rejects_bare_dotted_hosts_for_app_and_folder_labels() -> None:
    suggestions = mine_suggestions(
        [
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"app_name": "project.example.test"},
            },
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"app_name": "project.example.test"},
            },
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"folder_label": "project.example.test"},
            },
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"folder_label": "project.example.test"},
            },
        ]
    )

    assert suggestions == ()


def test_miner_rejects_ipv4_locators_for_app_and_folder_labels() -> None:
    suggestions = mine_suggestions(
        [
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"app_name": "127.0.0.1"},
            },
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"app_name": "127.0.0.1"},
            },
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"folder_label": "192.168.1.5:8080"},
            },
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"folder_label": "192.168.1.5:8080"},
            },
        ]
    )

    assert suggestions == ()


def test_miner_rejects_unbracketed_ipv6_for_app_and_folder_labels() -> None:
    suggestions = mine_suggestions(
        [
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"app_name": "::1"},
            },
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"app_name": "::1"},
            },
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"folder_label": "2001:db8::1/admin"},
            },
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"folder_label": "2001:db8::1/admin"},
            },
        ]
    )

    assert suggestions == ()


def test_miner_rejects_scoped_ipv6_for_app_folder_and_domain_labels() -> None:
    suggestions = mine_suggestions(
        [
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"app_name": "[fe80::1%25eth0]:443"},
            },
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"app_name": "[fe80::1%25eth0]:443"},
            },
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"folder_label": "fe80::1%eth0"},
            },
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"folder_label": "fe80::1%eth0"},
            },
            {
                "event_type": "shortcut_opened",
                "source_id": "ritualist_journal",
                "payload": {"domain": "[fe80::1%25eth0]:443"},
            },
            {
                "event_type": "shortcut_opened",
                "source_id": "ritualist_journal",
                "payload": {"domain": "[fe80::1%25eth0]:443"},
            },
        ]
    )

    assert suggestions == ()


def test_miner_rejects_single_label_and_encoded_domain_hosts() -> None:
    suggestions = mine_suggestions(
        [
            {
                "event_type": "shortcut_opened",
                "source_id": "ritualist_journal",
                "payload": {"domain_label": "http://2130706433/admin"},
            },
            {
                "event_type": "shortcut_opened",
                "source_id": "ritualist_journal",
                "payload": {"domain_label": "http://2130706433/admin"},
            },
            {
                "event_type": "shortcut_opened",
                "source_id": "ritualist_journal",
                "payload": {"domain_label": "http://0x7f000001/admin"},
            },
            {
                "event_type": "shortcut_opened",
                "source_id": "ritualist_journal",
                "payload": {"domain_label": "http://0x7f000001/admin"},
            },
            {
                "event_type": "shortcut_opened",
                "source_id": "ritualist_journal",
                "payload": {"domain_label": "http://printer/admin"},
            },
            {
                "event_type": "shortcut_opened",
                "source_id": "ritualist_journal",
                "payload": {"domain_label": "http://printer/admin"},
            },
        ]
    )

    assert suggestions == ()


def test_miner_rejects_backslash_schemeless_url_text_for_app_and_folder_labels() -> None:
    suggestions = mine_suggestions(
        [
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"app_name": r"www.example.dev\customer-a"},
            },
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"app_name": r"www.example.dev\customer-a"},
            },
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"folder_label": r"project.example.test\raw"},
            },
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"folder_label": r"project.example.test\raw"},
            },
        ]
    )

    assert suggestions == ()


def test_miner_rejects_query_schemeless_url_text_for_app_and_folder_labels() -> None:
    suggestions = mine_suggestions(
        [
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"app_name": "www.example.dev?customer=a"},
            },
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"app_name": "www.example.dev?customer=a"},
            },
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"folder_label": "project.example.test?raw=1"},
            },
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"folder_label": "project.example.test?raw=1"},
            },
        ]
    )

    assert suggestions == ()


def test_miner_rejects_localhost_url_text_for_app_and_folder_labels() -> None:
    suggestions = mine_suggestions(
        [
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"app_name": "localhost/admin"},
            },
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"app_name": "localhost/admin"},
            },
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"folder_label": "localhost?token=a"},
            },
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"folder_label": "localhost?token=a"},
            },
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"app_name": "localhost:3000"},
            },
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"app_name": "localhost:3000"},
            },
        ]
    )

    assert suggestions == ()


def test_miner_rejects_bracketed_ipv6_url_text_for_app_and_folder_labels() -> None:
    suggestions = mine_suggestions(
        [
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"app_name": "[::1]/admin"},
            },
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"app_name": "[::1]/admin"},
            },
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"folder_label": "[fe80::1]/raw"},
            },
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"folder_label": "[fe80::1]/raw"},
            },
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"app_name": "[::1]:8000"},
            },
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"app_name": "[::1]:8000"},
            },
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"folder_label": "[fe80::1]:9000"},
            },
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"folder_label": "[fe80::1]:9000"},
            },
        ]
    )

    assert suggestions == ()


def test_miner_rejects_non_http_uri_text_for_app_and_folder_labels() -> None:
    suggestions = mine_suggestions(
        [
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"app_name": "ftp://project.example.test/raw"},
            },
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"app_name": "ftp://project.example.test/raw"},
            },
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"folder_label": "file://server/share/raw"},
            },
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"folder_label": "file://server/share/raw"},
            },
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"app_name": "x://server/share/raw"},
            },
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"app_name": "x://server/share/raw"},
            },
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"folder_label": "x:server/share/raw"},
            },
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"folder_label": "x:server/share/raw"},
            },
        ]
    )

    assert suggestions == ()


def test_miner_fail_closes_malformed_bracketed_uri_like_labels() -> None:
    for unsafe_label in (
        "[x://server/share/raw]",
        "[ftp://project.example.test/raw]",
        "[mailto:alice@example.com]",
        "[not-ip]/raw",
    ):
        suggestions = mine_suggestions(
            [
                journal_event_signal(
                    label="event",
                    value="shortcut_opened",
                    metadata={"event_type": "shortcut_opened", "app_name": unsafe_label},
                ),
                journal_event_signal(
                    label="event",
                    value="shortcut_opened",
                    metadata={"event_type": "shortcut_opened", "app_name": unsafe_label},
                ),
            ]
        )

        assert suggestions == ()


def test_miner_rejects_embedded_non_http_uri_tokens_before_path_cleanup() -> None:
    for unsafe_label in (
        "prefix x://server/share/raw",
        "prefix x:server/share/raw",
        "App - file://server/share/raw",
        "prefix [x://server/share/raw]",
    ):
        suggestions = mine_suggestions(
            [
                journal_event_signal(
                    label="event",
                    value="shortcut_opened",
                    metadata={"event_type": "shortcut_opened", "app_name": unsafe_label},
                ),
                journal_event_signal(
                    label="event",
                    value="shortcut_opened",
                    metadata={"event_type": "shortcut_opened", "app_name": unsafe_label},
                ),
                journal_event_signal(
                    label="event",
                    value="shortcut_opened",
                    metadata={"event_type": "shortcut_opened", "folder_label": unsafe_label},
                ),
                journal_event_signal(
                    label="event",
                    value="shortcut_opened",
                    metadata={"event_type": "shortcut_opened", "folder_label": unsafe_label},
                ),
            ]
        )

        assert suggestions == ()


def test_miner_rejects_html_and_javascript_label_markers() -> None:
    for unsafe_label in (
        "<img src=x onerror=alert(1)>",
        "<svg onload=alert(1)>",
        "javascript alert(1)",
    ):
        suggestions = mine_suggestions(
            [
                journal_event_signal(
                    label="event",
                    value="shortcut_opened",
                    metadata={"event_type": "shortcut_opened", "app_name": unsafe_label},
                ),
                journal_event_signal(
                    label="event",
                    value="shortcut_opened",
                    metadata={"event_type": "shortcut_opened", "app_name": unsafe_label},
                ),
                journal_event_signal(
                    label="event",
                    value="shortcut_opened",
                    metadata={"event_type": "shortcut_opened", "folder_label": unsafe_label},
                ),
                journal_event_signal(
                    label="event",
                    value="shortcut_opened",
                    metadata={"event_type": "shortcut_opened", "folder_label": unsafe_label},
                ),
            ]
        )

        assert suggestions == ()


def test_miner_rejects_protocol_relative_url_text_for_app_and_folder_labels() -> None:
    suggestions = mine_suggestions(
        [
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"app_name": "//project.example.test/raw"},
            },
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"app_name": "//project.example.test/raw"},
            },
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"folder_label": "//project.example.test/raw"},
            },
            {
                "event_type": "component_clicked",
                "source_id": "ritualist_journal",
                "payload": {"folder_label": "//project.example.test/raw"},
            },
        ]
    )

    assert suggestions == ()


def test_miner_outputs_stable_review_only_suggestions_compatible_with_storage(tmp_path) -> None:
    signals = (
        recent_reference_signal(reference_type="folder", label="Workspace", target="Workspace"),
        recent_reference_signal(reference_type="folder", label="Workspace", target="Workspace"),
    )

    first = mine_suggestions(ActivityCollectionResult(signals=signals))
    second = mine_suggestions(ActivityCollectionResult(signals=signals))
    store = SuggestionStore(path=tmp_path / "suggestions.jsonl")
    store.save_many(first)
    store.save_many(second)

    restored = store.list()

    assert [suggestion.id for suggestion in first] == [suggestion.id for suggestion in second]
    assert len(restored) == len(first) == 1
    assert restored[0].kind is SuggestionKind.SHORTCUT_COMPONENT
    assert restored[0].privacy_level is SuggestionPrivacyLevel.LOW
    assert "auto" not in str(restored[0].to_dict()).casefold()
