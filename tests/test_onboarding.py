from __future__ import annotations

import json

from ritualist.onboarding import (
    LOCAL_LEARNING_DISABLED,
    LOCAL_LEARNING_ENABLED,
    LOCAL_LEARNING_UNDECIDED,
    ONBOARDING_FLOW_VERSION,
    ONBOARDING_SCHEMA_VERSION,
    OnboardingState,
    complete_onboarding,
    load_onboarding_state,
    mark_settings_reopened,
    onboarding_state_path,
    recommended_learning_source_ids,
    save_onboarding_state,
    skip_onboarding,
)


def test_default_onboarding_state_requires_first_run_and_does_not_enable_learning() -> None:
    state = OnboardingState()

    assert state.completed is False
    assert state.version == ONBOARDING_FLOW_VERSION
    assert state.local_learning_decision == LOCAL_LEARNING_UNDECIDED
    assert state.local_learning_enabled is False
    assert state.selected_recommended_source_ids == ()
    assert state.skipped is False
    assert state.reopen_settings_later is False
    assert state.should_show_first_run is True
    assert "installer_consent" not in state.to_dict()
    assert "consent" not in state.to_dict()


def test_completed_onboarding_persists_version_and_disabled_learning_decision(tmp_path) -> None:
    path = tmp_path / "onboarding.json"
    state = complete_onboarding(
        local_learning_decision=LOCAL_LEARNING_DISABLED,
        selected_recommended_source_ids=["ritualist_journal"],
        version="first-run-v2",
    )
    save_onboarding_state(state, path=path)

    loaded = load_onboarding_state(path=path)

    assert loaded.completed is True
    assert loaded.version == "first-run-v2"
    assert loaded.local_learning_decision == LOCAL_LEARNING_DISABLED
    assert loaded.local_learning_enabled is False
    assert loaded.selected_recommended_source_ids == ()
    assert loaded.skipped is False
    assert loaded.should_show_first_run is False


def test_completed_onboarding_keeps_customized_allowed_sources_only(tmp_path) -> None:
    path = tmp_path / "onboarding.json"
    state = complete_onboarding(
        local_learning_decision=LOCAL_LEARNING_ENABLED,
        selected_recommended_source_ids=[
            "ritualist-journal",
            "open windows",
            "watch_me",
            "browser_history",
            "screenshots",
            "ocr",
            "recent_items",
            "open_windows",
        ],
    )
    save_onboarding_state(state, path=path)

    loaded = load_onboarding_state(path=path)

    assert loaded.local_learning_decision == LOCAL_LEARNING_ENABLED
    assert loaded.local_learning_enabled is True
    assert loaded.selected_recommended_source_ids == (
        "ritualist_journal",
        "open_windows",
        "recent_items",
    )
    assert loaded.has_selected_learning_sources is True
    assert loaded.to_dict()["selected_recommended_sources"] == [
        "ritualist_journal",
        "open_windows",
        "recent_items",
    ]


def test_skip_onboarding_records_skipped_state_without_hidden_learning_choice(tmp_path) -> None:
    path = tmp_path / "onboarding.json"
    state = skip_onboarding(reopen_settings_later=True)
    save_onboarding_state(state, path=path)

    loaded = load_onboarding_state(path=path)

    assert loaded.completed is False
    assert loaded.skipped is True
    assert loaded.should_show_first_run is False
    assert loaded.reopen_settings_later is True
    assert loaded.local_learning_decision == LOCAL_LEARNING_UNDECIDED
    assert loaded.local_learning_enabled is False
    assert loaded.selected_recommended_source_ids == ()


def test_reopen_settings_later_state_can_be_cleared_without_changing_choices() -> None:
    state = complete_onboarding(
        local_learning_decision=LOCAL_LEARNING_DISABLED,
        reopen_settings_later=True,
    )

    reopened = mark_settings_reopened(state)

    assert reopened.reopen_settings_later is False
    assert reopened.completed is True
    assert reopened.local_learning_decision == LOCAL_LEARNING_DISABLED
    assert reopened.selected_recommended_source_ids == ()


def test_invalid_and_obsolete_onboarding_data_falls_back_to_safe_defaults(tmp_path) -> None:
    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text("{not json", encoding="utf-8")

    obsolete_path = tmp_path / "obsolete.json"
    obsolete_path.write_text(
        json.dumps(
            {
                "schema_version": "ritualist.onboarding.v0",
                "completed": True,
                "local_learning_decision": "enabled",
                "selected_recommended_sources": ["ritualist_journal"],
                "installer_consent": True,
            }
        ),
        encoding="utf-8",
    )

    assert load_onboarding_state(path=invalid_path) == OnboardingState()
    assert load_onboarding_state(path=obsolete_path) == OnboardingState()


def test_no_installer_level_hidden_consent_or_forbidden_sources_are_loaded(tmp_path) -> None:
    path = tmp_path / "onboarding.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": ONBOARDING_SCHEMA_VERSION,
                "version": ONBOARDING_FLOW_VERSION,
                "completed": True,
                "installer_consent": True,
                "installer_learning_enabled": True,
                "consent": {
                    "timestamp": "2026-06-18T12:00:00Z",
                    "sources": ["ritualist_journal"],
                },
                "local_learning_decision": True,
                "selected_recommended_sources": {"ritualist_journal": True},
            }
        ),
        encoding="utf-8",
    )

    state = load_onboarding_state(path=path)
    serialized = state.to_dict()

    assert state.completed is True
    assert state.local_learning_decision == LOCAL_LEARNING_UNDECIDED
    assert state.local_learning_enabled is False
    assert state.selected_recommended_source_ids == ()
    assert "installer_consent" not in serialized
    assert "consent" not in serialized
    assert "watch_me" not in serialized["selected_recommended_sources"]


def test_recommended_sources_are_exactly_the_allowed_local_learning_sources() -> None:
    assert recommended_learning_source_ids() == (
        "ritualist_journal",
        "open_windows",
        "recent_items",
    )


def test_onboarding_state_path_supports_explicit_base_dir(tmp_path) -> None:
    assert onboarding_state_path(base_dir=tmp_path) == tmp_path / "onboarding-state.json"
