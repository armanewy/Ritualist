from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from typer.testing import CliRunner

from ritualist.adapters.fake import FakeAdapters
from ritualist.cli import app
from ritualist.errors import RitualistError
from ritualist.models import Recipe
from ritualist.watch_me import (
    WatchMeService,
    WatchMeSignalType,
    WatchMeStatus,
    redact_url,
)


def test_watch_me_captures_safe_fake_window_signals(tmp_path: Path) -> None:
    fakes = FakeAdapters()
    fakes.browser.responses["page_context"] = {}
    service = WatchMeService(
        store_dir=tmp_path,
        adapters=fakes.bundle(),
        process_provider=lambda: [],
        clock=_clock(),
    )

    session = service.start()

    assert session.status is WatchMeStatus.RECORDING
    assert {event.type for event in session.events} >= {
        WatchMeSignalType.FOREGROUND_WINDOW,
        WatchMeSignalType.WINDOW_LAYOUT,
        WatchMeSignalType.MONITOR_LAYOUT,
    }
    assert fakes.desktop.calls == []
    assert fakes.input.calls == []


def test_watch_me_url_redaction_removes_credentials_query_and_sensitive_path() -> None:
    redacted, notes = redact_url(
        "https://user:pass@example.test/reset/password-token?token=secret#section"
    )

    assert redacted == "https://example.test/[redacted]"
    assert "user" not in redacted
    assert "pass" not in redacted
    assert "token" not in redacted
    assert set(notes) >= {
        "removed URL userinfo",
        "removed URL query",
        "removed URL fragment",
        "redacted sensitive URL path",
    }


def test_watch_me_drops_forbidden_event_fields(tmp_path: Path) -> None:
    service = WatchMeService(store_dir=tmp_path, process_provider=lambda: [], clock=_clock())
    session = service.start()

    updated = service.record_event(
        session.session_id,
        WatchMeSignalType.NOTE,
        {
            "summary": "safe note",
            "password": "secret",
            "screenshot_path": "screen.png",
            "clipboard_contents": "copied text",
        },
    )

    text = json.dumps(updated.model_dump(mode="json"))
    assert "safe note" in text
    assert "secret" not in text
    assert "screen.png" not in text
    assert "copied text" not in text
    assert "dropped forbidden field: password" in updated.redaction_summary
    assert "dropped forbidden field: screenshot_path" in updated.redaction_summary
    assert "dropped forbidden field: clipboard_contents" in updated.redaction_summary


def test_watch_me_redacts_sensitive_string_values(tmp_path: Path) -> None:
    service = WatchMeService(store_dir=tmp_path, process_provider=lambda: [], clock=_clock())
    session = service.start()

    updated = service.record_event(
        session.session_id,
        WatchMeSignalType.FOREGROUND_WINDOW,
        {"title": "Password reset token page"},
    )

    event = updated.events[-1]
    assert event.data["title"] == "[redacted]"
    assert "redacted sensitive text value" in updated.redaction_summary


def test_watch_me_skips_private_browser_urls(tmp_path: Path) -> None:
    service = WatchMeService(store_dir=tmp_path, process_provider=lambda: [], clock=_clock())
    session = service.start()

    updated = service.record_event(
        session.session_id,
        WatchMeSignalType.BROWSER_URL,
        {"url": "https://example.test/private", "incognito": True},
    )

    assert not [event for event in updated.events if event.type is WatchMeSignalType.BROWSER_URL]
    assert "skipped private/incognito browser URL" in updated.redaction_summary


def test_watch_me_draft_validates_and_is_not_enabled_automatically(tmp_path: Path) -> None:
    app_path = tmp_path / "Demo.exe"
    snapshots = [
        [{"name": "explorer.exe", "path": "C:\\Windows\\explorer.exe"}],
        [
            {"name": "explorer.exe", "path": "C:\\Windows\\explorer.exe"},
            {"name": "Demo.exe", "path": str(app_path)},
        ],
    ]

    def process_provider() -> list[dict[str, object]]:
        if len(snapshots) > 1:
            return snapshots.pop(0)
        return snapshots[0]

    service = WatchMeService(store_dir=tmp_path, process_provider=process_provider, clock=_clock())
    session = service.start()
    raw_session = (tmp_path / session.session_id / "session.json").read_text(encoding="utf-8")
    assert "explorer.exe" not in raw_session
    assert "Windows" not in raw_session
    assert session.baseline_process_keys
    stopped = service.stop(session.session_id)
    service.record_event(
        stopped.session_id,
        WatchMeSignalType.BROWSER_URL,
        {"url": "https://example.test/dashboard?token=secret"},
    )

    draft = service.create_draft(stopped.session_id)
    loaded = service.load(stopped.session_id)

    assert draft.enabled is False
    assert draft.review_required is True
    assert draft.doctor_recommended is True
    assert draft.dry_run_recommended is True
    Recipe.model_validate(draft.recipe)
    assert {"action": "app.launch", "command": str(app_path)} in draft.recipe["steps"]
    assert any(step["action"] == "browser.open" for step in draft.recipe["steps"])
    assert draft.canvas_card["enabled"] is False
    preview_text = "\n".join(draft.preview)
    assert "app.launch" in preview_text
    assert "browser.open" in preview_text
    assert "https://example.test/dashboard" in preview_text
    assert "token" not in preview_text
    assert "secret" not in preview_text
    assert loaded.status is WatchMeStatus.DRAFT_CREATED
    assert loaded.draft_path is not None
    assert Path(loaded.draft_path).is_file()
    assert not (tmp_path / "recipes").exists()


def test_watch_me_preview_includes_window_suggestions_and_todo_without_secrets(tmp_path: Path) -> None:
    service = WatchMeService(store_dir=tmp_path, process_provider=lambda: [], clock=_clock())
    session = service.start()
    stopped = service.stop(session.session_id)
    service.record_event(
        stopped.session_id,
        WatchMeSignalType.WINDOW_LAYOUT,
        {
            "windows": [
                {
                    "title": "Vendor App",
                    "bounds": {"x": 10, "y": 20, "width": 640, "height": 480},
                    "cookie": "secret",
                }
            ]
        },
    )

    draft = service.create_draft(stopped.session_id)
    preview_text = "\n".join(draft.preview)

    assert "window: Vendor App at 10,20 640x480" in preview_text
    assert "TODO:" in preview_text
    assert "secret" not in json.dumps(draft.model_dump(mode="json"))
    assert "cookie" not in json.dumps(draft.window_layout_suggestions)


def test_watch_me_create_draft_requires_stopped_session(tmp_path: Path) -> None:
    service = WatchMeService(store_dir=tmp_path, process_provider=lambda: [], clock=_clock())
    session = service.start()

    try:
        service.create_draft(session.session_id)
    except RitualistError as exc:
        assert "must be stopped" in str(exc)
    else:
        raise AssertionError("create_draft should reject active Watch Me sessions")


def test_watch_me_cli_help_exposes_commands() -> None:
    result = CliRunner().invoke(app, ["watch-me", "--help"])

    assert result.exit_code == 0
    assert "start" in result.output
    assert "stop" in result.output
    assert "create-draft" in result.output
    assert "discard" in result.output


def test_canvas_use_qml_exposes_watch_me_controls() -> None:
    qml = Path("ritualist/canvas/qml/CanvasUse.qml").read_text(encoding="utf-8")

    for snippet in (
        "Create from what I do",
        "Stop Watch Me",
        "Create Draft",
        "watchMeRecording",
        "watchMeDraftAvailable",
        "watchMeDraftSummary",
        "watchMeDraftPreview",
        "startWatchMe()",
        "stopWatchMe()",
        "createWatchMeDraft()",
        "discardWatchMe()",
    ):
        assert snippet in qml


def _clock():
    current = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def tick() -> datetime:
        return current

    return tick
