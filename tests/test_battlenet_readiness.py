from __future__ import annotations

from collections.abc import Sequence

from ritualist.canvas.models import (
    CanvasBindingKind,
    CanvasComponent,
    CanvasComponentBinding,
    CanvasDocument,
)
from ritualist.canvas.runtime import CanvasRuntimeContext, build_canvas_runtime_model
from ritualist.integrations.battlenet_readiness import (
    BattleNetReadinessProvider,
    BattleNetReadinessState,
    ReadOnlyControlSnapshot,
    ReadOnlyWindowSnapshot,
)
from ritualist.target_resolution import (
    TargetDiscoveryContext,
    TargetState,
    build_target_plan_summary,
    builtin_target_catalog,
    compile_target_start_plan,
    resolve_target,
)


class FakeInspector:
    def __init__(self, windows: Sequence[ReadOnlyWindowSnapshot]) -> None:
        self.windows = tuple(windows)
        self.calls: list[tuple[str, int]] = []

    def inspect_windows(self, *, title_contains: str, limit: int = 200):
        self.calls.append((title_contains, limit))
        return self.windows


def _target():
    target, _matched = builtin_target_catalog().resolve("diablo_iv")
    assert target is not None
    return target


def _window(
    *controls: ReadOnlyControlSnapshot,
    title: str = "Battle.net",
) -> ReadOnlyWindowSnapshot:
    return ReadOnlyWindowSnapshot(title=title, controls=controls)


def _button(name: str, *, enabled: bool = True) -> ReadOnlyControlSnapshot:
    return ReadOnlyControlSnapshot(name=name, control_type="Button", enabled=enabled)


def _text(name: str) -> ReadOnlyControlSnapshot:
    return ReadOnlyControlSnapshot(name=name, control_type="Text")


def _resolve_with(*windows: ReadOnlyWindowSnapshot):
    inspector = FakeInspector(windows)
    result = resolve_target(
        "diablo_iv",
        providers=(BattleNetReadinessProvider(inspector),),
        context=TargetDiscoveryContext(),
    )
    assert inspector.calls == [("Battle.net", 200)]
    return result


def _readiness_state(result) -> str:
    return result.candidates[0].details["readiness"]["state"]


def test_battlenet_readiness_is_non_windows_safe_without_injected_inspector(monkeypatch) -> None:
    monkeypatch.setattr("ritualist.integrations.battlenet_readiness.sys.platform", "linux")

    discovery = BattleNetReadinessProvider().discover(_target(), TargetDiscoveryContext())

    assert discovery.candidates == ()
    assert discovery.diagnostics == ("Battle.net readiness inspection is currently Windows-only",)


def test_battlenet_readiness_scopes_to_battlenet_window() -> None:
    result = _resolve_with(_window(_text("Diablo IV"), _button("Play"), title="Other Window"))

    assert result.state is TargetState.LAUNCHER_MISSING
    assert _readiness_state(result) == BattleNetReadinessState.LAUNCHER_NOT_RUNNING.value
    assert "No scoped Battle.net window" in result.candidates[0].evidence[0]


def test_battlenet_readiness_detects_login_required() -> None:
    result = _resolve_with(_window(_text("Email or Phone"), _text("Password"), _button("Log In")))

    assert result.state is TargetState.LOGIN_REQUIRED
    assert _readiness_state(result) == BattleNetReadinessState.LOGIN_REQUIRED.value
    assert "Log in to Battle.net manually" in result.candidates[0].details["recommendation"]


def test_battlenet_readiness_detects_game_not_selected() -> None:
    result = _resolve_with(_window(_text("World of Warcraft"), _button("Play")))

    assert result.state is TargetState.BLOCKED
    assert _readiness_state(result) == BattleNetReadinessState.GAME_NOT_SELECTED.value
    assert "Diablo IV is not the selected" in result.candidates[0].label


def test_battlenet_readiness_distinguishes_install_locate_update_and_play() -> None:
    cases = (
        (
            _window(_text("Diablo IV"), _button("Install"), _button("Locate the game")),
            TargetState.INSTALL_AVAILABLE,
            BattleNetReadinessState.INSTALL_AVAILABLE.value,
            "Install is available",
        ),
        (
            _window(_text("Diablo IV"), _button("Locate the game")),
            TargetState.INSTALL_SOURCE_AVAILABLE,
            BattleNetReadinessState.LOCATE_GAME_AVAILABLE.value,
            "Locate the game is available",
        ),
        (
            _window(_text("Diablo IV"), _button("Update")),
            TargetState.UPDATE_AVAILABLE,
            BattleNetReadinessState.UPDATE_AVAILABLE.value,
            "Update is available",
        ),
        (
            _window(_text("Diablo IV"), _button("Play")),
            TargetState.READY,
            BattleNetReadinessState.PLAY_AVAILABLE_ENABLED.value,
            "Play is available",
        ),
    )

    for window, target_state, readiness_state, recommendation in cases:
        result = _resolve_with(window)

        assert result.state is target_state
        assert _readiness_state(result) == readiness_state
        assert recommendation in result.candidates[0].details["recommendation"]


def test_battlenet_readiness_detects_disabled_play_updating_launching_and_running() -> None:
    cases = (
        (
            _window(_text("Diablo IV"), _button("Play", enabled=False)),
            TargetState.BLOCKED,
            BattleNetReadinessState.PLAY_VISIBLE_BUT_DISABLED.value,
        ),
        (
            _window(_text("Diablo IV"), _text("Updating 12%")),
            TargetState.UPDATING,
            BattleNetReadinessState.UPDATING.value,
        ),
        (
            _window(_text("Diablo IV"), _text("Launching")),
            TargetState.LAUNCHING,
            BattleNetReadinessState.LAUNCHING.value,
        ),
        (
            _window(_text("Diablo IV"), _text("Game is running")),
            TargetState.RUNNING,
            BattleNetReadinessState.GAME_RUNNING.value,
        ),
    )

    for window, target_state, readiness_state in cases:
        result = _resolve_with(window)

        assert result.state is target_state
        assert _readiness_state(result) == readiness_state


def test_battlenet_ambiguous_ui_blocks_unknown_and_preserves_labels() -> None:
    result = _resolve_with(_window(_text("Diablo IV"), _text("News"), _text("Shop")))
    candidate = result.candidates[0]

    assert result.state is TargetState.BLOCKED
    assert _readiness_state(result) == BattleNetReadinessState.BLOCKED_UNKNOWN.value
    assert candidate.details["readiness"]["candidate_labels"] == ["Diablo IV", "News", "Shop"]
    assert candidate.evidence[:2] == (
        "Inspected scoped Battle.net window: Battle.net",
        "UIA label: Diablo IV",
    )


def test_battlenet_readiness_summary_returns_human_recommendation_without_click_plan() -> None:
    result = _resolve_with(_window(_text("Diablo IV"), _button("Play")))
    plan = compile_target_start_plan("diablo_iv", resolution=result)

    assert plan.steps == ()
    assert plan.unresolved_questions == (
        "Play is available. Require explicit user confirmation before clicking Play.",
    )
    summary = build_target_plan_summary(result, plan)
    assert (
        summary.recommended_next_action
        == "Play is available. Require explicit user confirmation before clicking Play."
    )
    assert summary.readiness["state"] == BattleNetReadinessState.PLAY_AVAILABLE_ENABLED.value


def test_target_card_runtime_summary_exposes_battlenet_readiness() -> None:
    canvas = CanvasDocument(
        id="readiness_canvas",
        name="Readiness Canvas",
        components=(
            CanvasComponent(
                id="diablo_target",
                type="target.card",
                width=320,
                height=180,
                binding=CanvasComponentBinding(
                    kind=CanvasBindingKind.TARGET_START,
                    target="diablo_iv",
                ),
            ),
        ),
    )

    model = build_canvas_runtime_model(
        canvas,
        context=CanvasRuntimeContext(
            target_ids={"diablo_iv"},
            resolve_targets=True,
            target_resolver=lambda _target: _resolve_with(
                _window(_text("Diablo IV"), _button("Update"))
            ),
            recent_runs=[],
        ),
    )
    state = model.component_state("diablo_target")

    assert state.state == TargetState.UPDATE_AVAILABLE.value
    assert (
        state.message
        == "Update is available. Review Battle.net manually before updating Diablo IV."
    )
    assert (
        state.data["summary"]["readiness"]["state"]
        == BattleNetReadinessState.UPDATE_AVAILABLE.value
    )
