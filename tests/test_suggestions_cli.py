from __future__ import annotations

import json

from typer.testing import CliRunner

from setpiece.activity_journal import ActivityJournal
from setpiece.cli import app
from setpiece.paths import learning_suggestions_path


def _use_app_data(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SETPIECE_E2E", "1")
    monkeypatch.setenv("SETPIECE_E2E_APP_DATA_DIR", str(tmp_path))


def _enable_journal_learning() -> None:
    result = CliRunner().invoke(
        app,
        ["learning", "enable", "--source", "setpiece_journal", "--json"],
    )
    assert result.exit_code == 0


def _write_repeated_recipe_shortcut_pattern() -> None:
    journal = ActivityJournal(enabled=True)
    assert journal.write(
        "recipe_run_finished",
        recipe_id="support_shift",
        shortcut_id="ticket_queue",
    )
    assert journal.write(
        "recipe_run_finished",
        recipe_id="support_shift",
        shortcut_id="ticket_queue",
    )


def test_suggestions_scan_requires_enabled_local_learning(monkeypatch, tmp_path) -> None:
    _use_app_data(monkeypatch, tmp_path)

    result = CliRunner().invoke(app, ["suggestions", "scan", "--json"])

    assert result.exit_code == 1
    assert "Local Learning must be enabled" in result.output
    assert not learning_suggestions_path().exists()


def test_suggestions_scan_dry_run_mines_without_persisting(monkeypatch, tmp_path) -> None:
    _use_app_data(monkeypatch, tmp_path)
    _enable_journal_learning()
    _write_repeated_recipe_shortcut_pattern()

    result = CliRunner().invoke(app, ["suggestions", "scan", "--dry-run", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["schema_version"] == "setpiece.suggestions.scan.v1"
    assert data["on_demand"] is True
    assert data["background_collection"] is False
    assert data["dry_run"] is True
    assert data["persisted"] is False
    assert data["persisted_count"] == 0
    assert data["suggestion_count"] == 1
    assert data["suggestions"][0]["kind"] == "ritual_recipe"
    assert data["suggestions"][0]["title"] == "Review support shift + ticket queue ritual"
    assert not learning_suggestions_path().exists()


def test_suggestions_scan_list_show_dismiss_and_delete(monkeypatch, tmp_path) -> None:
    _use_app_data(monkeypatch, tmp_path)
    _enable_journal_learning()
    _write_repeated_recipe_shortcut_pattern()

    scan = CliRunner().invoke(app, ["suggestions", "scan", "--json"])
    assert scan.exit_code == 0
    scan_data = json.loads(scan.output)
    suggestion_id = scan_data["suggestions"][0]["id"]
    assert scan_data["persisted"] is True
    assert scan_data["persisted_count"] == 1
    assert learning_suggestions_path().exists()

    listed = CliRunner().invoke(app, ["suggestions", "list", "--json"])
    assert listed.exit_code == 0
    list_data = json.loads(listed.output)
    assert list_data["count"] == 1
    assert list_data["suggestions"][0]["id"] == suggestion_id

    shown = CliRunner().invoke(app, ["suggestions", "show", suggestion_id, "--json"])
    assert shown.exit_code == 0
    show_data = json.loads(shown.output)
    assert show_data["suggestion"]["id"] == suggestion_id
    assert show_data["suggestion"]["drafted_artifact_ref"] == ""

    dismissed = CliRunner().invoke(app, ["suggestions", "dismiss", suggestion_id, "--json"])
    assert dismissed.exit_code == 0
    dismiss_data = json.loads(dismissed.output)
    assert dismiss_data["dismissed"] is True
    assert dismiss_data["suggestion"]["status"] == "dismissed"

    dry_delete = CliRunner().invoke(
        app,
        ["suggestions", "delete-all", "--dry-run", "--json"],
    )
    assert dry_delete.exit_code == 0
    dry_delete_data = json.loads(dry_delete.output)
    assert dry_delete_data["would_delete_count"] == 1
    assert learning_suggestions_path().exists()

    deleted = CliRunner().invoke(app, ["suggestions", "delete-all", "--yes", "--json"])
    assert deleted.exit_code == 0
    delete_data = json.loads(deleted.output)
    assert delete_data["deleted_count"] == 1
    assert not learning_suggestions_path().exists()


def test_suggestions_min_confidence_filters_scan_and_storage(monkeypatch, tmp_path) -> None:
    _use_app_data(monkeypatch, tmp_path)
    _enable_journal_learning()
    _write_repeated_recipe_shortcut_pattern()

    result = CliRunner().invoke(
        app,
        ["suggestions", "scan", "--min-confidence", "0.99", "--json"],
    )

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["mined_count"] == 1
    assert data["suggestion_count"] == 0
    assert data["persisted_count"] == 0
    assert not learning_suggestions_path().exists()


def test_suggestions_scan_excludes_sensitive_suggestions_by_default(
    monkeypatch,
    tmp_path,
) -> None:
    _use_app_data(monkeypatch, tmp_path)
    _enable_journal_learning()

    def fake_scan_payload(**_kwargs):
        return {
            "enabled_sources": ["setpiece_journal"],
            "collection": {
                "signals": [
                    {
                        "event_type": "shortcut_opened",
                        "source_id": "setpiece_journal",
                        "payload": {"domain": "docs.example.com"},
                    },
                    {
                        "event_type": "shortcut_opened",
                        "source_id": "setpiece_journal",
                        "payload": {"domain": "docs.example.com"},
                    },
                ],
                "warnings": [],
            },
        }

    monkeypatch.setattr("setpiece.suggestions.service.learning_scan_payload", fake_scan_payload)

    hidden = CliRunner().invoke(app, ["suggestions", "scan", "--dry-run", "--json"])
    assert hidden.exit_code == 0
    hidden_data = json.loads(hidden.output)
    assert hidden_data["mined_count"] == 1
    assert hidden_data["suggestion_count"] == 0

    included = CliRunner().invoke(
        app,
        ["suggestions", "scan", "--dry-run", "--include-sensitive", "--json"],
    )
    assert included.exit_code == 0
    included_data = json.loads(included.output)
    assert included_data["suggestion_count"] == 1
    assert included_data["suggestions"][0]["privacy_level"] == "sensitive"
