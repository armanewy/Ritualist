from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from ritualist.adapters.fake import FakeAdapters
from ritualist.executor import WorkflowExecutor
from ritualist.integrations.battlenet_readiness import BattleNetReadinessState
from ritualist.recipe_loader import load_recipe
from ritualist.target_resolution import (
    TargetCandidate,
    TargetResolutionResult,
    TargetState,
    builtin_target_catalog,
)


READINESS_TARGET_STATES = {
    BattleNetReadinessState.LAUNCHER_NOT_RUNNING: TargetState.LAUNCHER_MISSING,
    BattleNetReadinessState.LOGIN_REQUIRED: TargetState.LOGIN_REQUIRED,
    BattleNetReadinessState.GAME_NOT_SELECTED: TargetState.BLOCKED,
    BattleNetReadinessState.INSTALL_AVAILABLE: TargetState.INSTALL_AVAILABLE,
    BattleNetReadinessState.LOCATE_GAME_AVAILABLE: TargetState.INSTALL_SOURCE_AVAILABLE,
    BattleNetReadinessState.UPDATE_AVAILABLE: TargetState.UPDATE_AVAILABLE,
    BattleNetReadinessState.UPDATING: TargetState.UPDATING,
    BattleNetReadinessState.PLAY_AVAILABLE_ENABLED: TargetState.READY,
    BattleNetReadinessState.PLAY_VISIBLE_BUT_DISABLED: TargetState.BLOCKED,
    BattleNetReadinessState.LAUNCHING: TargetState.LAUNCHING,
    BattleNetReadinessState.GAME_RUNNING: TargetState.RUNNING,
    BattleNetReadinessState.BLOCKED_UNKNOWN: TargetState.BLOCKED,
}


@pytest.mark.parametrize(
    ("readiness_state", "expected_step"),
    [
        (BattleNetReadinessState.LAUNCHER_NOT_RUNNING, "Battle.net launcher not ready"),
        (BattleNetReadinessState.LOGIN_REQUIRED, "Manual Battle.net login required"),
        (BattleNetReadinessState.GAME_NOT_SELECTED, "Select Diablo IV manually"),
        (BattleNetReadinessState.INSTALL_AVAILABLE, "Manual install review required"),
        (BattleNetReadinessState.LOCATE_GAME_AVAILABLE, "Manual locate review required"),
        (BattleNetReadinessState.UPDATE_AVAILABLE, "Manual update review required"),
        (BattleNetReadinessState.UPDATING, "Diablo IV update in progress"),
        (BattleNetReadinessState.PLAY_VISIBLE_BUT_DISABLED, "Play button disabled"),
        (BattleNetReadinessState.BLOCKED_UNKNOWN, "Battle.net readiness unknown"),
        (BattleNetReadinessState.LAUNCHING, "Diablo IV launch already in progress"),
    ],
)
def test_gaming_mode_branches_for_non_play_readiness_states(
    monkeypatch,
    readiness_state: BattleNetReadinessState,
    expected_step: str,
) -> None:
    fakes = FakeAdapters()
    _install_resolver(monkeypatch, _static_resolver(_readiness_resolution(readiness_state)))

    summary = WorkflowExecutor(
        adapters=fakes.bundle(),
        confirmer=lambda _request: True,
    ).run(_gaming_recipe())

    assert summary.success
    assert expected_step in _successful_steps(summary)
    assert "Ask before clicking Play" not in _successful_steps(summary)
    assert "click_text" not in _called_names(fakes.desktop.calls)
    assert _called_names(fakes.browser.calls).isdisjoint({"open_url", "media_playing"})
    assert [call[0] for call in fakes.native_browser.calls] == ["open_url"]


def test_gaming_mode_launches_battlenet_when_launcher_window_is_absent(monkeypatch) -> None:
    fakes = FakeAdapters()
    fakes.window.responses["window_exists"] = False
    _install_resolver(
        monkeypatch,
        _static_resolver(_readiness_resolution(BattleNetReadinessState.LOGIN_REQUIRED)),
    )

    summary = WorkflowExecutor(
        adapters=fakes.bundle(),
        confirmer=lambda _request: True,
    ).run(_gaming_recipe())

    assert summary.success
    assert "Launch Battle.net if needed" in _successful_steps(summary)
    assert [call[0] for call in fakes.shell.calls] == ["launch"]
    assert any(call[0] == "wait" for call in fakes.window.calls)


def test_gaming_mode_focuses_already_running_diablo_without_launcher_or_play(monkeypatch) -> None:
    fakes = FakeAdapters()
    _install_resolver(monkeypatch, _static_resolver(_running_resolution()))

    summary = WorkflowExecutor(
        adapters=fakes.bundle(),
        confirmer=lambda _request: True,
    ).run(_gaming_recipe())

    assert summary.success
    assert "Focus Diablo IV if already running" in _successful_steps(summary)
    assert fakes.shell.calls == []
    assert "click_text" not in _called_names(fakes.desktop.calls)


def test_gaming_mode_play_branch_invokes_exact_play_target_and_verifies_launch(
    monkeypatch,
) -> None:
    fakes = FakeAdapters()
    resolver = _AfterPlayResolver()

    original_invoker = fakes.desktop.invoke_resolved_text_region

    def invoke_and_mark_play(**kwargs):
        resolver.play_invoked = True
        return original_invoker(**kwargs)

    fakes.desktop.invoke_resolved_text_region = invoke_and_mark_play
    _install_resolver(monkeypatch, resolver)

    summary = WorkflowExecutor(
        adapters=fakes.bundle(),
        confirmer=lambda _request: True,
    ).run(_gaming_recipe())

    assert summary.success
    assert "Ask before clicking Play" in _successful_steps(summary)
    assert "Verify Diablo IV launch started" in _successful_steps(summary)
    assert [call[0] for call in fakes.desktop.calls] == [
        "find_text_region",
        "invoke_resolved_text_region",
    ]
    invoke_call = fakes.desktop.calls[1]
    assert invoke_call[2]["text"] == "Play"
    assert invoke_call[2]["window_title_contains"] == "Battle.net"
    assert invoke_call[2]["target"].target_text == "Play"


def test_gaming_mode_managed_ambience_uses_playback_wait_and_optional_minimize(
    monkeypatch,
) -> None:
    fakes = FakeAdapters()
    _install_resolver(
        monkeypatch,
        _static_resolver(_readiness_resolution(BattleNetReadinessState.LOGIN_REQUIRED)),
    )

    summary = WorkflowExecutor(
        adapters=fakes.bundle(),
        confirmer=lambda _request: True,
    ).run(
        _gaming_recipe(
            {
                "ambience_browser_mode": "managed",
                "minimize_ambience": True,
            }
        )
    )

    assert summary.success
    assert [call[0] for call in fakes.native_browser.calls] == []
    assert [call[0] for call in fakes.browser.calls] == ["open_url", "media_playing"]
    assert fakes.browser.calls[0][2]["keep_open"] is True
    assert any(call[0] == "minimize" for call in fakes.window.calls)


def test_gaming_mode_loads_default_ambience_variables() -> None:
    recipe = _gaming_recipe()

    assert recipe.variables["ambience_enabled"] is True
    assert recipe.variables["ambience_browser_mode"] == "native"
    assert recipe.variables["minimize_ambience"] is False
    assert "ambience_url" in recipe.variables


def _gaming_recipe(overrides: dict[str, object] | None = None):
    return load_recipe(_gaming_recipe_path(), overrides)


def _gaming_recipe_path() -> Path:
    return Path(__file__).resolve().parents[1] / "ritualist" / "sample_recipes" / "gaming_mode.yaml"


def _install_resolver(monkeypatch, resolver: Callable[[str], TargetResolutionResult]) -> None:
    monkeypatch.setattr("ritualist.predicates.resolve_target", resolver)
    monkeypatch.setattr("ritualist.actions.target_actions.resolve_target", resolver)


def _static_resolver(resolution: TargetResolutionResult) -> Callable[[str], TargetResolutionResult]:
    return lambda _target: resolution


class _AfterPlayResolver:
    def __init__(self) -> None:
        self.play_invoked = False

    def __call__(self, _target: str) -> TargetResolutionResult:
        if self.play_invoked:
            return _readiness_resolution(BattleNetReadinessState.LAUNCHING)
        return _readiness_resolution(BattleNetReadinessState.PLAY_AVAILABLE_ENABLED)


def _readiness_resolution(readiness_state: BattleNetReadinessState) -> TargetResolutionResult:
    target = _diablo_target()
    target_state = READINESS_TARGET_STATES[readiness_state]
    return TargetResolutionResult(
        query="diablo_iv",
        target=target,
        state=target_state,
        candidates=(
            TargetCandidate(
                candidate_id=f"readiness_{readiness_state.value}",
                target_id=target.id,
                provider="battle_net_readiness",
                state=target_state,
                label=f"Battle.net readiness: {readiness_state.value}",
                confidence=0.9,
                window_title="Battle.net",
                evidence=("fake Battle.net readiness",),
                details={
                    "readiness": {
                        "schema_version": "battle_net.readiness.v1",
                        "provider": "battle_net_readiness",
                        "state": readiness_state.value,
                        "recommendation": "fake recommendation",
                        "candidate_labels": ["Diablo IV"],
                        "window_title": "Battle.net",
                    },
                    "recommendation": "fake recommendation",
                },
            ),
        ),
    )


def _running_resolution() -> TargetResolutionResult:
    target = _diablo_target()
    return TargetResolutionResult(
        query="diablo_iv",
        target=target,
        state=TargetState.RUNNING,
        candidates=(
            TargetCandidate(
                candidate_id="running_diablo_iv",
                target_id=target.id,
                provider="running_process",
                state=TargetState.RUNNING,
                label="running process Diablo IV.exe",
                confidence=0.95,
                process_name="Diablo IV.exe",
                window_title="Diablo IV",
                evidence=("fake running process",),
            ),
        ),
    )


def _diablo_target():
    target, _matched = builtin_target_catalog().resolve("diablo_iv")
    assert target is not None
    return target


def _successful_steps(summary) -> list[str]:
    return [result.step_name for result in summary.results if result.status == "success"]


def _called_names(calls) -> set[str]:
    return {name for name, _args, _kwargs in calls}
