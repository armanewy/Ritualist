from __future__ import annotations

from pathlib import Path

from ritualist.suggestions.sanitize import (
    HISTORY_OMITTED,
    REDACTED,
    sanitize_app_name,
    sanitize_evidence_items,
    sanitize_evidence_summary,
    sanitize_local_path,
    sanitize_url,
    sanitize_window_title,
)


def test_url_sanitization_keeps_domain_and_safe_title_only() -> None:
    assert (
        sanitize_url(
            "https://docs.example.com/workspace/secret?access_token=abc123",
            title="Project Plan - Shared Doc",
        )
        == REDACTED
    )
    assert sanitize_url("https://www.example.com/private/path?token=abc") == REDACTED
    assert "secret" not in sanitize_url("https://example.com/secret/customer-a")
    assert sanitize_url("http://2130706433/admin") == REDACTED
    assert sanitize_url("http://0x7f000001/admin") == REDACTED
    assert sanitize_url("http://printer/admin") == REDACTED


def test_url_sanitization_redacts_credentials_and_private_markers() -> None:
    assert sanitize_url("https://alice:hunter2@example.com/project") == REDACTED
    assert sanitize_url("https://example.com/project", title="Example - Incognito") == REDACTED


def test_local_path_sanitization_returns_minimal_labels_without_ancestors() -> None:
    assert sanitize_local_path(r"C:\Users\alice\Documents\Ritualist\deck.md") == "deck.md"
    assert sanitize_local_path("/home/alice/projects/ritualist") == "ritualist"
    assert sanitize_local_path(r"C:\Users\alice") == "user folder"
    assert sanitize_local_path(r"\\fileserver\team\Plans\launch.xlsx") == "launch.xlsx"
    assert sanitize_local_path(r"C:\Users\alice\PrivateVault\notes.txt") == REDACTED
    assert sanitize_local_path("file://server/share/raw") == REDACTED
    assert sanitize_local_path("ssh://user@example.com/project") == REDACTED
    assert sanitize_local_path("x://server/share/raw") == REDACTED
    assert sanitize_local_path("x:server/share/raw") == REDACTED

    summary = sanitize_evidence_summary(
        r"Opened C:\Users\alice\Documents\Ritualist\deck.md and /home/alice/projects/notes.txt"
    )
    assert "alice" not in summary
    assert "Documents" not in summary
    assert "deck.md" in summary
    assert "notes.txt" in summary


def test_window_title_and_app_name_sanitization_reject_sensitive_context() -> None:
    assert (
        sanitize_window_title(
            "Project Board - https://workflow.example.com/team?utm=1 - Browser"
        )
        == "Project Board - workflow.example.com - Browser"
    )
    assert sanitize_window_title("Customer email - Private browsing") == REDACTED
    assert (
        sanitize_window_title("From: Alice\nTo: Bob\nSubject: Payroll\nPlease review numbers")
        == REDACTED
    )

    assert sanitize_app_name(r"C:\Program Files\Ritualist\Ritualist.exe") == "Ritualist"
    assert sanitize_app_name("Code.exe") == "Code"
    assert sanitize_app_name("project.example.test") == REDACTED
    assert sanitize_app_name("file://server/share/raw") == REDACTED
    assert sanitize_app_name("ssh://user@example.com/project") == REDACTED
    assert sanitize_app_name("x://server/share/raw") == REDACTED
    assert sanitize_app_name("x:server/share/raw") == REDACTED
    assert sanitize_app_name("localhost:3000") == REDACTED
    assert sanitize_app_name("[::1]:8000") == REDACTED
    assert sanitize_app_name("127.0.0.1") == REDACTED
    assert sanitize_app_name("192.168.1.5:8080") == REDACTED
    assert sanitize_app_name("::1") == REDACTED
    assert sanitize_app_name("2001:db8::1") == REDACTED
    assert sanitize_app_name("[fe80::1%25eth0]:443") == REDACTED
    assert sanitize_app_name("fe80::1%eth0") == REDACTED
    assert sanitize_app_name("PowerShell.exe -NoProfile -EncodedCommand token") == REDACTED


def test_evidence_summary_redacts_tokens_collection_markers_and_body_text() -> None:
    assert sanitize_evidence_summary("API token=abc123 appeared in a note") == REDACTED
    assert sanitize_evidence_summary("OCR result from screenshot") == REDACTED
    assert (
        sanitize_evidence_summary("email body: hello team, here is the private customer note")
        == REDACTED
    )
    assert (
        sanitize_evidence_summary("Visited https://support.example.com/tickets/123")
        == "Visited support.example.com"
    )
    assert (
        sanitize_evidence_summary("Visited //support.example.com/tickets/123")
        == "Visited support.example.com"
    )
    typed_summary = sanitize_evidence_summary(
        {
            "app_name": "project.example.test",
            "folder_label": "[fe80::1%25eth0]:443",
        }
    )
    assert "project.example.test" not in typed_summary
    assert "fe80" not in typed_summary
    assert "eth0" not in typed_summary
    assert sanitize_evidence_summary("Opened [::1]/admin for docs") == "Opened [redacted] for docs"
    assert sanitize_evidence_summary("Visited secret.internal/private during setup") == REDACTED
    assert (
        sanitize_evidence_summary("Opened www.example.dev/path for docs")
        == "Opened example.dev for docs"
    )
    assert (
        sanitize_evidence_summary("Opened www.example.dev?customer=a for docs")
        == "Opened example.dev for docs"
    )
    assert sanitize_evidence_summary("Saw file://server/share/raw") == "Saw [redacted]"
    assert sanitize_evidence_summary("Saw ssh://user@example.com/project") == "Saw [redacted]"
    assert sanitize_evidence_summary("Saw mailto:alice@example.com") == "Saw [redacted]"
    assert sanitize_evidence_summary("Saw ftp://project.example.test/raw") == "Saw [redacted]"
    assert sanitize_evidence_summary("Saw x://server/share/raw") == "Saw [redacted]"
    assert sanitize_evidence_summary("Saw x:server/share/raw") == "Saw [redacted]"
    assert sanitize_evidence_summary("Saw [mailto:alice@example.com]") == "Saw [redacted]"
    assert sanitize_evidence_summary("Saw [ftp://project.example.test/raw]") == "Saw [redacted]"
    assert (
        sanitize_evidence_summary("Saw data:text/html,<script>alert(1)</script>")
        == REDACTED
    )
    assert (
        sanitize_evidence_summary("Saw data:text/html;charset=utf-8,<script>alert(1)</script>")
        == REDACTED
    )
    assert (
        sanitize_evidence_summary("Saw data:text/html,<img src=x onerror=alert(1)>")
        == REDACTED
    )
    assert (
        sanitize_evidence_summary("Saw data:text/html,<svg onload=alert(1)>")
        == REDACTED
    )
    assert sanitize_app_name("[mailto:alice@example.com]") == REDACTED
    assert sanitize_app_name("App - file://server/share/raw") == REDACTED
    assert sanitize_evidence_summary("Opened localhost/admin for docs") == "Opened [redacted] for docs"
    assert (
        sanitize_evidence_summary(r"Opened www.example.dev\path for docs")
        == "Opened example.dev for docs"
    )
    assert sanitize_evidence_summary("key logger output was present") == REDACTED
    assert sanitize_evidence_summary("watch-me preview was present") == REDACTED
    assert sanitize_evidence_summary("coordinates 10,20 were present") == REDACTED
    assert sanitize_evidence_summary("Screen Recorder was open") == REDACTED
    assert sanitize_evidence_summary("ScreenRecorder was open") == REDACTED
    assert sanitize_evidence_summary("ScreenCapture was open") == REDACTED
    assert sanitize_evidence_summary("Windows Recall was open") == REDACTED
    assert sanitize_evidence_summary("WindowsRecall was open") == REDACTED
    assert sanitize_evidence_summary("Saw <img src=x onerror=alert(1)>") == REDACTED
    assert sanitize_evidence_summary("Saw <svg onload=alert(1)>") == REDACTED
    assert sanitize_evidence_summary("Saw javascript alert(1)") == REDACTED
    assert sanitize_evidence_summary("teach_by_watching was open") == REDACTED
    assert sanitize_evidence_summary("TeachByWatching was open") == REDACTED
    assert sanitize_evidence_summary("Keylog was open") == REDACTED
    assert sanitize_evidence_summary("Keyboard Logger was open") == REDACTED
    assert sanitize_evidence_summary("KeyboardLogger was open") == REDACTED
    assert sanitize_evidence_summary("BrowserHistory was present") == REDACTED
    assert sanitize_app_name("Screen Recorder.exe") == REDACTED
    assert sanitize_app_name("ScreenRecorder.exe") == REDACTED
    assert sanitize_app_name("ScreenCapture.exe") == REDACTED
    assert sanitize_app_name("Windows Recall.exe") == REDACTED
    assert sanitize_app_name("WindowsRecall.exe") == REDACTED
    assert sanitize_app_name("Teach By Watching.exe") == REDACTED
    assert sanitize_app_name("TeachByWatching.exe") == REDACTED
    assert sanitize_app_name("Keylog.exe") == REDACTED
    assert sanitize_app_name("Keyboard Logger.exe") == REDACTED
    assert sanitize_app_name("KeyboardLogger.exe") == REDACTED


def test_evidence_summary_omits_huge_raw_histories() -> None:
    urls = [f"https://example.com/raw/{index}?q=secret" for index in range(25)]

    assert sanitize_evidence_items(urls) == (HISTORY_OMITTED,)
    assert sanitize_evidence_summary({"raw_history": urls}) == HISTORY_OMITTED

    repeated_history = "history:\n" + "\n".join(urls)
    assert sanitize_evidence_summary(repeated_history) == HISTORY_OMITTED


def test_evidence_mapping_outputs_only_sanitized_labels() -> None:
    summary = sanitize_evidence_summary(
        {
            "url": "https://project.example.com/a/b?refresh_token=secret",
            "window_title": "Project Room - Browser",
            "path": r"C:\Users\alice\Projects\Ritualist\README.md",
            "app_name": r"C:\Program Files\Ritualist\Ritualist.exe",
            "message_body": "From: Alice\nTo: Bob\nSubject: Private",
        }
    )

    assert summary == "[redacted]; Project Room - Browser; README.md; Ritualist"
    assert "alice" not in summary
    assert "refresh_token" not in summary
    assert "message_body" not in summary


def test_evidence_mapping_blocks_schemeless_urls_and_coordinate_keys() -> None:
    summary = sanitize_evidence_summary(
        {
            "app_name": "www.example.dev/customer-a",
            "process_name": "localhost/admin",
            "path": "[fe80::1]/raw",
            "coordinate_label": "10,20",
            "window_title": "Project Room",
        }
    )

    assert summary == "[redacted]; Project Room"
    assert "customer-a" not in summary
    assert "raw" not in summary
    assert "secret.internal" not in summary
    assert "10,20" not in summary


def test_sanitizer_module_has_no_collection_or_execution_imports() -> None:
    source = Path("ritualist/suggestions/sanitize.py").read_text(encoding="utf-8")

    forbidden_imports = (
        "import keyboard",
        "import mss",
        "import os",
        "import PIL",
        "import pyautogui",
        "import pywinauto",
        "import subprocess",
        "import win32",
        "from keyboard",
        "from mss",
        "from os",
        "from PIL",
        "from pyautogui",
        "from pywinauto",
        "from subprocess",
        "from win32",
    )
    assert all(import_text not in source for import_text in forbidden_imports)
