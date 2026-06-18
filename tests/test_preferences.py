from __future__ import annotations

import pytest

from ritualist.preferences import (
    CleanupPreferenceScope,
    RememberedApprovalScope,
    approval_matches,
    can_remember_approval,
    cleanup_choice_for,
    list_remembered_approvals,
    remember_approval,
    remember_cleanup_choice,
    revoke_remembered_approval,
)
from ritualist.run_logs import KEEP_SETUP_OPEN, STOPPED_USER_DECLINED_CONFIRMATION


def test_remembered_cleanup_stored_only_after_user_choice(tmp_path):
    path = tmp_path / "preferences.json"
    scope = CleanupPreferenceScope(
        recipe_or_intent_id="gaming_mode",
        stop_reason=STOPPED_USER_DECLINED_CONFIRMATION,
        local_user="tester",
    )

    assert cleanup_choice_for(scope, path=path) is None

    remember_cleanup_choice(scope, KEEP_SETUP_OPEN, path=path)

    assert cleanup_choice_for(scope, path=path) == KEEP_SETUP_OPEN


def test_remembered_approval_matches_exact_target_scope(tmp_path):
    path = tmp_path / "preferences.json"
    scope = RememberedApprovalScope(
        recipe_or_intent_id="gaming_mode",
        content_hash="hash-1",
        step_id="steps:7",
        action_or_primitive_id="desktop.click_text",
        resolved_target_identity="battle_net",
        target_context="Battle.net",
        target_text="Update",
        target_control="Button",
        target_scope="desktop",
        target_application="Battle.net",
        risk_level="risky",
        local_user="tester",
        local_device="device-1",
    )

    remember_approval(scope, path=path)

    assert not approval_matches(scope, path=path)
    assert approval_matches(scope, path=path, local_user_approved_source=True)
    assert not approval_matches(
        RememberedApprovalScope(
            recipe_or_intent_id="gaming_mode",
            content_hash="hash-2",
            step_id="steps:7",
            action_or_primitive_id="desktop.click_text",
            resolved_target_identity="battle_net",
            target_context="Battle.net",
            target_text="Update",
            target_control="Button",
            target_scope="desktop",
            target_application="Battle.net",
            risk_level="risky",
            local_user="tester",
            local_device="device-1",
        ),
        path=path,
        local_user_approved_source=True,
    )
    assert not approval_matches(
        RememberedApprovalScope(
            recipe_or_intent_id="gaming_mode",
            content_hash="hash-1",
            step_id="steps:7",
            action_or_primitive_id="desktop.click_text",
            resolved_target_identity="battle_net",
            target_context="Battle.net",
            target_text="Play",
            target_control="Button",
            target_scope="desktop",
            target_application="Battle.net",
            risk_level="risky",
            local_user="tester",
            local_device="device-1",
        ),
        path=path,
        local_user_approved_source=True,
    )


def test_high_risk_tokens_cannot_be_casually_remembered(tmp_path):
    scope = RememberedApprovalScope(
        recipe_or_intent_id="checkout",
        content_hash="hash-1",
        step_id="steps:2",
        action_or_primitive_id="browser.click_text",
        resolved_target_identity="store",
        target_context="Example Store",
        target_text="Confirm Order",
        target_control="Button",
        target_scope="browser",
        target_application="https://example.test/checkout",
        risk_level="risky",
        local_user="tester",
        local_device="device-1",
    )

    assert not can_remember_approval(scope)
    with pytest.raises(ValueError, match="high-risk"):
        remember_approval(scope, path=tmp_path / "preferences.json")


def test_imported_source_cannot_activate_remembered_approval(tmp_path):
    path = tmp_path / "preferences.json"
    local_scope = RememberedApprovalScope(
        recipe_or_intent_id="gaming_mode",
        content_hash="hash-1",
        step_id="steps:7",
        action_or_primitive_id="desktop.click_text",
        resolved_target_identity="battle_net",
        target_context="Battle.net",
        target_text="Update",
        target_control="Button",
        target_scope="desktop",
        target_application="Battle.net",
        risk_level="risky",
        local_user="tester",
        local_device="device-1",
        source_trust="local_user",
    )
    imported_scope = RememberedApprovalScope(
        recipe_or_intent_id="gaming_mode",
        content_hash="hash-1",
        step_id="steps:7",
        action_or_primitive_id="desktop.click_text",
        resolved_target_identity="battle_net",
        target_context="Battle.net",
        target_text="Update",
        target_control="Button",
        target_scope="desktop",
        target_application="Battle.net",
        risk_level="risky",
        local_user="tester",
        local_device="device-1",
        source_trust="imported_pack",
    )

    remember_approval(local_scope, path=path)

    assert not can_remember_approval(imported_scope)
    assert not approval_matches(imported_scope, path=path, local_user_approved_source=True)
    assert not approval_matches(local_scope, path=path, local_user_approved_source=False)


def test_remembered_approval_revocation_removes_match(tmp_path):
    path = tmp_path / "preferences.json"
    scope = RememberedApprovalScope(
        recipe_or_intent_id="gaming_mode",
        content_hash="hash-1",
        step_id="steps:7",
        action_or_primitive_id="desktop.click_text",
        resolved_target_identity="battle_net",
        target_context="Battle.net",
        target_text="Update",
        target_control="Button",
        target_scope="desktop",
        target_application="Battle.net",
        risk_level="risky",
        local_user="tester",
        local_device="device-1",
    )
    entry = remember_approval(scope, path=path)

    assert len(list_remembered_approvals(path=path)) == 1
    assert revoke_remembered_approval(str(entry["id"]), path=path) is True
    assert list_remembered_approvals(path=path) == []
    assert not approval_matches(scope, path=path, local_user_approved_source=True)


def test_ambiguous_target_cannot_be_remembered(tmp_path):
    scope = RememberedApprovalScope(
        recipe_or_intent_id="gaming_mode",
        content_hash="hash-1",
        step_id="steps:7",
        action_or_primitive_id="desktop.click_text",
        resolved_target_identity="battle_net",
        target_context="Battle.net",
        target_text="Update",
        target_control="Button",
        target_scope="desktop",
        target_application="Battle.net",
        risk_level="risky",
        local_user="tester",
        local_device="device-1",
        target_ambiguous=True,
    )

    assert not can_remember_approval(scope)
    with pytest.raises(ValueError, match="ambiguous"):
        remember_approval(scope, path=tmp_path / "preferences.json")
