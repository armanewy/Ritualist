from __future__ import annotations

from pathlib import Path

from ritualist.activity_journal import ActivityJournal
from ritualist.home import app as home_app
from ritualist.onboarding import (
    LOCAL_LEARNING_ENABLED,
    LOCAL_LEARNING_UNDECIDED,
    load_onboarding_state,
)
from ritualist.paths import learning_journal_path, learning_suggestions_path


REPO_ROOT = Path(__file__).resolve().parents[1]
HOME_QML = REPO_ROOT / "ritualist" / "home" / "qml" / "Home.qml"


def _use_app_data(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("RITUALIST_E2E", "1")
    monkeypatch.setenv("RITUALIST_E2E_APP_DATA_DIR", str(tmp_path))


def test_home_qml_surfaces_learning_privacy_without_forbidden_options() -> None:
    qml = HOME_QML.read_text(encoding="utf-8")

    assert "Local Learning & Privacy" in qml
    assert "Local Learning On" in qml
    assert "Local Learning Off" in qml
    assert "View Activity Journal" in qml
    assert "Delete Learning Data" in qml
    assert "Local only, no keystrokes, no screenshots, review before creation." in qml
    assert "Suggestions never auto-create or auto-run." in qml
    assert "Enable" in qml
    assert "Customize Sources" in qml
    assert "Not Now" in qml
    assert "learningSourceModel" in qml
    assert "enableLocalLearning(selectedLearningSources())" in qml
    assert "property var onboardingState" in qml
    assert "should_show_first_run" in qml
    assert "customizeLearningSources" in qml
    assert "skipLearningOnboarding" in qml
    assert "requestDeleteLearningData" in qml
    assert "confirmDeleteLearningData" in qml

    forbidden_options = (
        "Watch Me",
        "watch_me",
        "watch-me",
        "browser_history",
        "browser-history",
        "Recall",
        "recording mode",
        "teach by watching",
    )
    for term in forbidden_options:
        assert term not in qml


def test_home_qml_keeps_exactly_three_promoted_hero_rooms() -> None:
    qml = HOME_QML.read_text(encoding="utf-8")

    assert 'property var promotedRoomIds: ["gaming", "project", "support_desk"]' in qml
    assert "minimal_desktop" not in qml
    assert qml.count("roomModel.append(room)") == 1


def test_home_learning_bridge_uses_existing_config_sources_and_disable_path(
    monkeypatch, tmp_path
) -> None:
    _use_app_data(monkeypatch, tmp_path)

    default_status = home_app._home_learning_status_payload()
    assert default_status["enabled"] is False
    assert default_status["effective_enabled"] is False

    enabled = home_app._enable_home_learning(["ritualist_journal", "recent-items"])
    assert enabled["enabled"] is True
    assert enabled["enabled_sources"] == ["ritualist_journal", "recent_items"]
    assert enabled["local_only"] is True
    assert enabled["background_collection"] is False

    sources = home_app._home_learning_sources_payload()["sources"]
    assert [source["id"] for source in sources] == [
        "ritualist_journal",
        "open_windows",
        "recent_items",
    ]
    assert "browser_history" not in {source["id"] for source in sources}
    assert {source["id"] for source in sources if source["enabled"] is True} == {
        "ritualist_journal",
        "recent_items",
    }

    disabled = home_app._disable_home_learning()
    assert disabled["enabled"] is False
    assert disabled["effective_enabled"] is False
    assert disabled["selected_sources"] == ["ritualist_journal", "recent_items"]
    assert disabled["consented_sources"] == ["ritualist_journal", "recent_items"]


def test_home_learning_onboarding_helpers_persist_explicit_choices(
    monkeypatch, tmp_path
) -> None:
    _use_app_data(monkeypatch, tmp_path)

    initial = home_app._home_onboarding_state_payload()
    assert initial["should_show_first_run"] is True
    assert initial["local_learning_decision"] == LOCAL_LEARNING_UNDECIDED

    enabled = home_app._complete_home_learning_onboarding("enabled", ("ritualist_journal",))
    loaded = load_onboarding_state()

    assert enabled["should_show_first_run"] is False
    assert loaded.completed is True
    assert loaded.local_learning_decision == LOCAL_LEARNING_ENABLED
    assert loaded.local_learning_enabled is True
    assert loaded.selected_recommended_source_ids == ("ritualist_journal",)

    skipped = home_app._skip_home_learning_onboarding()
    loaded_skipped = load_onboarding_state()

    assert skipped["should_show_first_run"] is False
    assert loaded_skipped.completed is False
    assert loaded_skipped.skipped is True
    assert loaded_skipped.local_learning_decision == LOCAL_LEARNING_UNDECIDED
    assert loaded_skipped.local_learning_enabled is False


def test_home_learning_bridge_views_and_deletes_existing_local_data(
    monkeypatch, tmp_path
) -> None:
    _use_app_data(monkeypatch, tmp_path)
    journal = ActivityJournal(enabled=True)
    assert journal.write("recipe_dry_run", recipe_id="support_triage") is True
    learning_suggestions_path().write_text("{}\n", encoding="utf-8")

    journal_payload = home_app._home_learning_journal_payload()
    assert journal_payload["path"] == str(learning_journal_path())
    assert journal_payload["count"] == 1
    assert journal_payload["events"] == [
        {
            "event_type": "recipe_dry_run",
            "payload": {"recipe_id": "support_triage"},
        }
    ]

    deleted = home_app._delete_home_learning_data()
    assert deleted["deleted_count"] == 2
    assert deleted["paths"]["journal"]["deleted"] is True
    assert deleted["paths"]["suggestions"]["deleted"] is True
    assert not learning_journal_path().exists()
    assert not learning_suggestions_path().exists()
