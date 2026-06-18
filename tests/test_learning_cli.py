from __future__ import annotations

import json

import yaml
from typer.testing import CliRunner

from ritualist.activity_journal import ActivityJournal
from ritualist.cli import app
from ritualist.paths import config_file_path, learning_journal_path, learning_suggestions_path


def _use_app_data(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("RITUALIST_E2E", "1")
    monkeypatch.setenv("RITUALIST_E2E_APP_DATA_DIR", str(tmp_path))


def test_learning_status_defaults_disabled_and_local(monkeypatch, tmp_path) -> None:
    _use_app_data(monkeypatch, tmp_path)

    result = CliRunner().invoke(app, ["learning", "status", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["enabled"] is False
    assert data["effective_enabled"] is False
    assert data["enabled_sources"] == []
    assert data["local_only"] is True
    assert data["background_collection"] is False


def test_learning_enable_requires_explicit_source_selection(monkeypatch, tmp_path) -> None:
    _use_app_data(monkeypatch, tmp_path)

    result = CliRunner().invoke(app, ["learning", "enable"])

    assert result.exit_code == 1
    assert "explicit source selection" in result.output
    assert not config_file_path().exists()


def test_learning_enable_rejects_forbidden_sources(monkeypatch, tmp_path) -> None:
    _use_app_data(monkeypatch, tmp_path)

    result = CliRunner().invoke(app, ["learning", "enable", "--source", "browser_history"])

    assert result.exit_code == 1
    assert "forbidden Local Learning source" in result.output
    assert not config_file_path().exists()


def test_learning_enable_writes_source_consent_and_explains_local_only(
    monkeypatch, tmp_path
) -> None:
    _use_app_data(monkeypatch, tmp_path)

    result = CliRunner().invoke(
        app,
        ["learning", "enable", "--source", "ritualist_journal", "--source", "recent-items"],
    )

    assert result.exit_code == 0
    assert "Local Learning stays on this device" in result.output
    assert "No Watch Me" in result.output
    config = yaml.safe_load(config_file_path().read_text(encoding="utf-8"))
    assert config["learning"]["enabled"] is True
    assert config["learning"]["sources"] == ["ritualist_journal", "recent_items"]
    assert config["learning"]["consent"]["sources"] == ["ritualist_journal", "recent_items"]
    assert config["learning"]["background_collection"] is False


def test_learning_disable_preserves_existing_data_and_consent(monkeypatch, tmp_path) -> None:
    _use_app_data(monkeypatch, tmp_path)
    assert CliRunner().invoke(
        app,
        ["learning", "enable", "--source", "ritualist_journal", "--json"],
    ).exit_code == 0
    journal = ActivityJournal(enabled=True)
    assert journal.write("room_opened", room_id="gaming_desktop") is True

    result = CliRunner().invoke(app, ["learning", "disable", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["enabled"] is False
    assert data["effective_enabled"] is False
    assert data["selected_sources"] == ["ritualist_journal"]
    assert data["consented_sources"] == ["ritualist_journal"]
    assert learning_journal_path().exists()


def test_learning_sources_lists_only_allowed_v1_sources(monkeypatch, tmp_path) -> None:
    _use_app_data(monkeypatch, tmp_path)

    result = CliRunner().invoke(app, ["learning", "sources", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    source_ids = [source["id"] for source in data["sources"]]
    assert source_ids == ["ritualist_journal", "open_windows", "recent_items"]
    assert "browser_history" not in source_ids
    assert all(source["requires_explicit_selection"] is True for source in data["sources"])
    assert all(source["background_collection"] is False for source in data["sources"])


def test_learning_scan_is_on_demand_and_uses_selected_recent_items(
    monkeypatch, tmp_path
) -> None:
    _use_app_data(monkeypatch, tmp_path)
    recipes = tmp_path / "recipes"
    recipes.mkdir()
    (recipes / "alpha_setup.yaml").write_text("id: alpha_setup\n", encoding="utf-8")
    assert CliRunner().invoke(
        app,
        ["learning", "enable", "--source", "recent_items", "--json"],
    ).exit_code == 0

    result = CliRunner().invoke(app, ["learning", "scan", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["on_demand"] is True
    assert data["background_collection"] is False
    assert data["enabled_sources"] == ["recent_items"]
    signals = data["collection"]["signals"]
    assert signals[0]["kind"] == "recent_reference"
    assert signals[0]["source_id"] == "recent_items"
    assert signals[0]["label"] == "alpha setup"


def test_learning_journal_json_reads_local_activity_journal(monkeypatch, tmp_path) -> None:
    _use_app_data(monkeypatch, tmp_path)
    journal = ActivityJournal(enabled=True)
    assert journal.write("recipe_dry_run", recipe_id="support_triage") is True

    result = CliRunner().invoke(app, ["learning", "journal", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["count"] == 1
    assert data["events"] == [
        {
            "event_type": "recipe_dry_run",
            "payload": {"recipe_id": "support_triage"},
        }
    ]


def test_learning_delete_data_removes_existing_paths_and_handles_missing_safely(
    monkeypatch, tmp_path
) -> None:
    _use_app_data(monkeypatch, tmp_path)
    journal = ActivityJournal(enabled=True)
    assert journal.write("shortcut_opened", component_id="launch") is True
    learning_suggestions_path().write_text("{}\n", encoding="utf-8")

    result = CliRunner().invoke(app, ["learning", "delete-data", "--yes", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["deleted_count"] == 2
    assert data["paths"]["journal"]["deleted"] is True
    assert data["paths"]["suggestions"]["deleted"] is True
    assert not learning_journal_path().exists()
    assert not learning_suggestions_path().exists()

    second = CliRunner().invoke(app, ["learning", "delete-data", "--yes", "--json"])
    assert second.exit_code == 0
    second_data = json.loads(second.output)
    assert second_data["deleted_count"] == 0
    assert second_data["paths"]["suggestions"]["existed"] is False

