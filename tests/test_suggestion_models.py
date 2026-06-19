from __future__ import annotations

from setpiece.suggestions.models import (
    Suggestion,
    SuggestionApproval,
    SuggestionKind,
    SuggestionPrivacyLevel,
    SuggestionStatus,
)


def test_suggestion_model_normalizes_required_contract_fields() -> None:
    suggestion = Suggestion.create(
        kind="shortcut_component",
        title="  Open Project\nFolder  ",
        description="Repeated local project folder use",
        confidence=1.5,
        evidence_summary="Opened Project several times",
        evidence_count=3,
        sources=(
            "recent_items",
            "recent_items",
            "setpiece_journal",
            "https://secret.example/raw",
        ),
        proposed_actions=(
            {
                "kind": "shortcut.folder",
                "label": "Project Folder",
                "path_label": "Project",
            },
        ),
        missing_inputs=("folder_path",),
        privacy_level="low",
    )

    assert suggestion.kind is SuggestionKind.SHORTCUT_COMPONENT
    assert suggestion.title == "Open Project Folder"
    assert suggestion.confidence == 1.0
    assert suggestion.evidence_count == 3
    assert suggestion.sources == ("recent_items", "setpiece_journal")
    assert suggestion.privacy_level is SuggestionPrivacyLevel.LOW
    assert suggestion.status is SuggestionStatus.NEW
    assert suggestion.to_dict()["schema_version"] == "setpiece.suggestion.v1"


def test_suggestion_model_contains_no_executable_code_fields() -> None:
    suggestion = Suggestion.create(
        kind="ritual_recipe",
        title="Draft setup",
        description="Repeated app and folder use",
        confidence=0.75,
        evidence_summary="App plus folder cluster",
        evidence_count=4,
        sources=("open_windows", "recent_items"),
        proposed_actions=(
            {
                "action": "open_app",
                "python": "print('no')",
                "shell_command": "rm -rf /",
                "cmd": "calc.exe",
                "url": "https://secret.example/private",
                "path": "C:/Users/alice/Secret",
                "target": "C:/Users/alice/Secret",
                "screenshot_path": "C:/private.png",
                "ocr_result": "captured",
                "keystroke_count": 2,
                "coordinate": "10,20",
                "recording_file": "capture.mp4",
                "watch_me": True,
                "nested": {"javascript": "alert(1)", "label": "safe label"},
            },
        ),
    )

    payload = suggestion.to_dict()
    text = str(payload)
    assert "python" not in text
    assert "shell_command" not in text
    assert "javascript" not in text
    assert "cmd" not in text
    assert "secret.example" not in text
    assert "screenshot" not in text
    assert "ocr" not in text
    assert "keystroke" not in text
    assert "coordinate" not in text
    assert "recording" not in text
    assert "watch_me" not in text
    assert payload["proposed_actions"] == [{"action": "open_app"}]


def test_suggestion_text_fields_redact_raw_locators_and_command_text() -> None:
    suggestion = Suggestion.create(
        kind="shortcut_component",
        title="Open C:/Users/alice/Secret",
        description="Visited https://secret.example/private with powershell notes",
        confidence=0.4,
        evidence_summary="Opened /home/alice/private and ran cmd.exe",
        evidence_count=2,
        sources=("recent_items",),
        proposed_actions=(
            {
                "label": "https://secret.example/private",
                "description": "Use C:/Users/alice/Secret",
                "notes": "run powershell later",
                "placeholder": "folder_path",
            },
        ),
        missing_inputs=(
            "folder_path",
            "https://secret.example/private",
            "C:/Users/alice/Secret",
            "run powershell",
            "Start-Process calc",
        ),
    )

    payload = suggestion.to_dict()
    text = str(payload)
    assert "secret.example" not in text
    assert "C:/Users/alice" not in text
    assert "/home/alice" not in text
    assert "powershell" not in text
    assert "cmd.exe" not in text
    assert "[redacted]" in text
    assert payload["missing_inputs"] == ["folder_path"]
    assert payload["proposed_actions"] == [
        {
            "label": "[redacted]",
            "description": "Use [redacted]",
            "notes": "[redacted]",
            "placeholder": "folder_path",
        }
    ]


def test_suggestion_text_fields_redact_schemeless_urls() -> None:
    suggestion = Suggestion.create(
        kind="shortcut_component",
        title="Open [::1]?token=abc",
        description=r"Visited www.example.dev\path before work",
        confidence=0.4,
        evidence_summary="Saw //project.example.test/raw history",
        evidence_count=2,
        proposed_actions=(
            {
                "label": "[fe80::1]/raw",
                "description": "localhost/admin",
                "notes": r"www.example.dev\path",
                "placeholder": "folder_path",
            },
        ),
    )

    payload = suggestion.to_dict()
    text = str(payload)
    assert "secret.internal" not in text
    assert "www.example.dev" not in text
    assert "project.example.test" not in text
    assert "customer=a" not in text
    assert "localhost" not in text
    assert "token=abc" not in text
    assert "fe80" not in text
    assert payload["title"] == "Open [redacted]"
    assert payload["description"] == "Visited [redacted] before work"
    assert payload["evidence_summary"] == "Saw [redacted] history"
    assert payload["proposed_actions"] == [
        {
            "label": "[redacted]",
            "description": "[redacted]",
            "notes": "[redacted]",
            "placeholder": "folder_path",
        }
    ]


def test_suggestion_text_fields_redact_non_http_uri_schemes() -> None:
    suggestion = Suggestion.create(
        kind="shortcut_component",
        title="Open x://server/share/raw",
        description="Saw x:server/share/raw",
        confidence=0.4,
        evidence_summary="Saw [file://server/share/raw] and [mailto:alice@example.com]",
        evidence_count=2,
        proposed_actions=(
            {
                "label": "x://server/share/raw",
                "description": "Use x:server/share/raw",
                "notes": "ssh://user@example.com/project",
                "placeholder": "folder_path",
            },
        ),
        missing_inputs=("x://server/share/raw", "folder_path"),
    )

    payload = suggestion.to_dict()
    text = str(payload)
    assert "x://server" not in text
    assert "x:server" not in text
    assert "file://server" not in text
    assert "mailto:" not in text
    assert "ssh://user" not in text
    assert payload["title"] == "[redacted]"
    assert payload["description"] == "[redacted]"
    assert payload["evidence_summary"] == "[redacted]"
    assert payload["missing_inputs"] == ["folder_path"]
    assert payload["proposed_actions"] == [
        {
            "label": "[redacted]",
            "description": "[redacted]",
            "notes": "[redacted]",
            "placeholder": "folder_path",
        }
    ]


def test_suggestion_text_fields_redact_non_http_uri_parameter_tails() -> None:
    payloads = (
        "ssh://user@example.com/project;token=abc123",
        "ssh://user@example.com/project,password=abc123",
        "ftp://project.example.test/raw;customer=a",
        "mailto:alice@example.com;subject=SecretProject",
    )

    for payload_value in payloads:
        suggestion = Suggestion.create(
            kind=SuggestionKind.CLEANUP_HINT,
            title=f"Review {payload_value}",
            description=f"Saw {payload_value}",
            confidence=0.5,
            evidence_summary=f"Saw {payload_value}",
            evidence_count=2,
            proposed_actions=(
                {
                    "action": "review_cleanup_hint",
                    "kind": "cleanup_hint",
                    "label": payload_value,
                },
            ),
            privacy_level=SuggestionPrivacyLevel.REVIEW,
        )

        payload = suggestion.to_dict()
        text = str(payload)
        assert "ssh://" not in text
        assert "ftp://" not in text
        assert "mailto:" not in text
        assert "token=abc123" not in text
        assert "password=abc123" not in text
        assert "customer=a" not in text
        assert "SecretProject" not in text
        assert payload["title"] == "[redacted]"
        assert payload["description"] == "[redacted]"
        assert payload["evidence_summary"] == "[redacted]"
        assert payload["proposed_actions"] == [
            {
                "action": "review_cleanup_hint",
                "kind": "cleanup_hint",
                "label": "[redacted]",
            }
        ]


def test_suggestion_text_fields_redact_data_uri_payloads() -> None:
    payloads = (
        "data:text/html,<script>alert(1)</script>",
        "data:text/html;charset=utf-8,<script>alert(1)</script>",
        "data:text/html,<img src=x onerror=alert(1)>",
        "data:text/html,<svg onload=alert(1)>",
    )

    for payload_value in payloads:
        suggestion = Suggestion.create(
            kind=SuggestionKind.CLEANUP_HINT,
            title=f"Review {payload_value}",
            description=f"Saw {payload_value}",
            confidence=0.5,
            evidence_summary=f"Saw {payload_value}",
            evidence_count=2,
            proposed_actions=(
                {
                    "action": "review_cleanup_hint",
                    "kind": "cleanup_hint",
                    "label": payload_value,
                },
            ),
            privacy_level=SuggestionPrivacyLevel.REVIEW,
        )

        payload = suggestion.to_dict()
        text = str(payload)
        assert "data:text" not in text
        assert "<script>" not in text
        assert "<img" not in text
        assert "<svg" not in text
        assert "onerror" not in text
        assert "onload" not in text
        assert "alert(1)" not in text
        assert payload["title"] == "[redacted]"
        assert payload["description"] == "[redacted]"
        assert payload["evidence_summary"] == "[redacted]"
        assert payload["proposed_actions"] == [
            {
                "action": "review_cleanup_hint",
                "kind": "cleanup_hint",
                "label": "[redacted]",
            }
        ]


def test_suggestion_text_fields_redact_html_and_javascript_markers() -> None:
    payloads = (
        "<img src=x onerror=alert(1)>",
        "<svg onload=alert(1)>",
        "javascript alert(1)",
    )

    for payload_value in payloads:
        suggestion = Suggestion.create(
            kind=SuggestionKind.CLEANUP_HINT,
            title=f"Review {payload_value}",
            description=f"Saw {payload_value}",
            confidence=0.5,
            evidence_summary=f"Saw {payload_value}",
            evidence_count=2,
            proposed_actions=(
                {
                    "action": "review_cleanup_hint",
                    "kind": "cleanup_hint",
                    "label": payload_value,
                },
            ),
            privacy_level=SuggestionPrivacyLevel.REVIEW,
        )

        payload = suggestion.to_dict()
        text = str(payload)
        assert "<img" not in text
        assert "<svg" not in text
        assert "onerror" not in text
        assert "onload" not in text
        assert "javascript" not in text
        assert "alert(1)" not in text
        assert payload["title"] == "[redacted]"
        assert payload["description"] == "[redacted]"
        assert payload["evidence_summary"] == "[redacted]"
        assert payload["proposed_actions"] == [
            {
                "action": "review_cleanup_hint",
                "kind": "cleanup_hint",
                "label": "[redacted]",
            }
        ]


def test_suggestion_text_fields_redact_bare_dotted_hosts() -> None:
    suggestion = Suggestion.create(
        kind="shortcut_component",
        title="Open project.example.test",
        description="Repeated project.example.test use",
        confidence=0.4,
        evidence_summary="Saw project.example.test",
        evidence_count=2,
        proposed_actions=(
            {
                "label": "project.example.test",
                "description": "Use project.example.test",
                "notes": "project.example.test",
                "placeholder": "folder_path",
            },
        ),
    )

    payload = suggestion.to_dict()
    text = str(payload)
    assert "project.example.test" not in text
    assert payload["title"] == "Open [redacted]"
    assert payload["description"] == "Repeated [redacted] use"
    assert payload["evidence_summary"] == "Saw [redacted]"
    assert payload["proposed_actions"] == [
        {
            "label": "[redacted]",
            "description": "Use [redacted]",
            "notes": "[redacted]",
            "placeholder": "folder_path",
        }
    ]


def test_suggestion_text_fields_redact_host_port_locators() -> None:
    suggestion = Suggestion.create(
        kind="shortcut_component",
        title="Open localhost:3000 and 127.0.0.1 and ::1",
        description="Repeated [::1]:8000 use with 192.168.1.5:8080",
        confidence=0.4,
        evidence_summary="Saw [fe80::1%25eth0]:443 and 2001:db8::1/admin",
        evidence_count=2,
        proposed_actions=(
            {
                "label": "127.0.0.1",
                "description": "Use 2001:db8::1/admin",
                "notes": "fe80::1%eth0",
                "placeholder": "folder_path",
            },
        ),
    )

    payload = suggestion.to_dict()
    text = str(payload)
    assert "localhost:3000" not in text
    assert "127.0.0.1" not in text
    assert "192.168.1.5" not in text
    assert "::1" not in text
    assert "2001:db8" not in text
    assert "fe80" not in text
    assert "eth0" not in text
    assert payload["title"] == "Open [redacted] and [redacted] and [redacted]"
    assert payload["description"] == "Repeated [redacted] use with [redacted]"
    assert payload["evidence_summary"] == "Saw [redacted] and [redacted]"
    assert payload["proposed_actions"] == [
        {
            "label": "[redacted]",
            "description": "Use [redacted]",
            "notes": "[redacted]",
            "placeholder": "folder_path",
        }
    ]


def test_suggestion_public_text_redacts_command_like_values() -> None:
    for command_text in (
        "launch calc.exe",
        "use reg add HKCU\\Software\\Test",
        "run rm -rf /tmp/example",
        "Invoke-WebRequest https://secret.example/private",
        "iwr https://secret.example/private",
        "Start-Process calc",
        "Remove-Item C:/Users/alice/Secret -Recurse",
        "Set-ExecutionPolicy Bypass",
    ):
        suggestion = Suggestion.create(
            kind="cleanup_hint",
            title=command_text,
            description=command_text,
            confidence=0.2,
            evidence_summary=command_text,
            evidence_count=1,
            proposed_actions=({"label": command_text, "notes": command_text},),
        )

        payload = suggestion.to_dict()
        assert command_text not in str(payload)
        assert payload["title"] == "[redacted]"
        assert payload["description"] == "[redacted]"
        assert payload["evidence_summary"] == "[redacted]"
        assert payload["proposed_actions"] == [{"label": "[redacted]", "notes": "[redacted]"}]


def test_suggestion_public_text_redacts_forbidden_capture_app_labels() -> None:
    for forbidden_text in (
        "Screen Recorder",
        "ScreenRecorder",
        "ScreenCapture",
        "Recorder",
        "Windows Recall",
        "WindowsRecall",
        "Teach By Watching",
        "TeachByWatching",
        "teach_by_watching",
        "Keylog",
        "Keylogger",
        "Keyboard Logger",
        "KeyboardLogger",
        "BrowserHistory",
    ):
        suggestion = Suggestion.create(
            kind="cleanup_hint",
            title=forbidden_text,
            description=f"Observed {forbidden_text}",
            confidence=0.2,
            evidence_summary=forbidden_text,
            evidence_count=1,
            proposed_actions=({"label": forbidden_text, "notes": forbidden_text},),
            missing_inputs=(forbidden_text,),
        )

        payload = suggestion.to_dict()
        assert forbidden_text not in str(payload)
        assert payload["title"] == "[redacted]"
        assert payload["evidence_summary"] == "[redacted]"
        assert payload["proposed_actions"] == [{"label": "[redacted]", "notes": "[redacted]"}]
        assert payload["missing_inputs"] == []


def test_suggestion_values_redact_forbidden_capture_source_names() -> None:
    suggestion = Suggestion.create(
        kind="cleanup_hint",
        title="Safe",
        description="Safe",
        confidence=0.2,
        evidence_summary="Safe",
        evidence_count=1,
        proposed_actions=(
            {
                "label": "watch_me",
                "notes": "browser_history",
                "source_id": "screenshot",
                "placeholder": "ocr_result",
                "description": "click_coordinates",
            },
        ),
        missing_inputs=(
            "keylogging",
            "keylogger",
            "key logger",
            "key_logger",
            "click_coordinates",
            "coordinates",
            "folder_path",
        ),
    )

    payload = suggestion.to_dict()
    text = str(payload)
    assert "watch_me" not in text
    assert "browser_history" not in text
    assert "screenshot" not in text
    assert "ocr_result" not in text
    assert "click_coordinates" not in text
    assert "coordinates" not in text
    assert "keylogging" not in text
    assert "key_logger" not in text
    assert payload["missing_inputs"] == ["folder_path"]
    assert payload["proposed_actions"] == [
        {
            "label": "[redacted]",
            "notes": "[redacted]",
            "source_id": "[redacted]",
            "placeholder": "[redacted]",
            "description": "[redacted]",
        }
    ]


def test_suggestion_round_trip_and_status_approval_metadata() -> None:
    approval = SuggestionApproval(
        reviewed_by="operator",
        reviewed_at="2026-06-17T12:00:00Z",
        review_token="token-1",
        approved=True,
        artifact_summary="Draft shortcut only",
    )
    suggestion = Suggestion.create(
        kind="room_canvas",
        title="Project Room draft",
        description="Create a draft room",
        confidence=0.5,
        evidence_summary="Repeated project cluster",
        evidence_count=8,
    ).with_status(
        SuggestionStatus.APPROVED,
        approval=approval,
        drafted_artifact_ref="drafts/project-room.yaml",
    )

    restored = Suggestion.from_mapping(suggestion.to_dict())

    assert restored == suggestion
    assert restored.approval == approval
    assert restored.drafted_artifact_ref == "drafts/project-room.yaml"

    traversal = suggestion.with_status(
        SuggestionStatus.DRAFTED,
        drafted_artifact_ref="drafts/../../secret.yaml",
    )
    assert traversal.drafted_artifact_ref == ""


def test_suggestion_ids_and_approval_metadata_are_sanitized() -> None:
    suggestion = Suggestion.from_mapping(
        {
            "id": "https://secret.example/private",
            "kind": "shortcut_component",
            "title": "Safe title",
            "description": "Safe description",
            "confidence": 0.5,
            "evidence_summary": "Safe evidence",
            "evidence_count": 1,
            "approval": {
                "reviewed_by": "Operator One",
                "reviewed_at": "2026-06-17T12:00:00Z",
                "review_token": "token-1",
                "approved": True,
                "artifact_summary": "Created C:/Users/alice/Secret with powershell",
            },
        }
    )

    assert "secret.example" not in suggestion.id
    assert suggestion.approval is not None
    assert suggestion.approval.reviewed_by == "operator_one"
    assert suggestion.approval.review_token == "token_1"
    assert "C:/Users/alice" not in suggestion.approval.artifact_summary
    assert "powershell" not in suggestion.approval.artifact_summary
    assert "[redacted]" in suggestion.approval.artifact_summary

    unsafe_approval = SuggestionApproval.from_mapping(
        {
            "reviewed_by": "https://secret.example/private",
            "reviewed_at": "opened C:/Users/alice/Secret",
            "review_token": "Start-Process calc",
            "approved": True,
            "artifact_summary": "Safe",
        }
    )
    assert unsafe_approval is not None
    assert unsafe_approval.reviewed_by == ""
    assert unsafe_approval.reviewed_at == ""
    assert unsafe_approval.review_token == ""


def test_suggestion_created_at_requires_safe_timestamp() -> None:
    for unsafe_value in (
        "https://secret.example/private",
        "C:/Users/alice/Secret",
        "Start-Process calc",
    ):
        suggestion = Suggestion.from_mapping(
            {
                "id": "safe-id",
                "kind": "cleanup_hint",
                "title": "Safe",
                "description": "Safe",
                "confidence": 0.1,
                "evidence_summary": "Safe",
                "evidence_count": 1,
                "created_at": unsafe_value,
            }
        )
        assert suggestion.created_at == ""


def test_suggestion_status_supports_dismissed_persistence_shape() -> None:
    suggestion = Suggestion.create(
        kind="cleanup_hint",
        title="Dismiss me",
        description="Review-only hint",
        confidence=-1,
        evidence_summary="Noisy evidence",
        evidence_count=-3,
    ).with_status("dismissed")

    assert suggestion.status is SuggestionStatus.DISMISSED
    assert suggestion.confidence == 0.0
    assert suggestion.evidence_count == 0
