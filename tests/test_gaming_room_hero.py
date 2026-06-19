from __future__ import annotations

from pathlib import Path
from typing import Any

from setpiece.canvas import (
    CanvasBackgroundType,
    CanvasRuntimeContext,
    CanvasRuntimeController,
    build_canvas_runtime_model,
    load_bundled_canvas,
    resolve_canvas_host_config,
)
from setpiece.recipe_loader import load_recipe
from setpiece.run_logs import RunRecord
from setpiece.target_resolution import (
    TargetCandidate,
    TargetResolutionResult,
    TargetState,
    builtin_target_catalog,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
GAMING_MODE_PATH = REPO_ROOT / "setpiece" / "sample_recipes" / "gaming_mode.yaml"


def test_gaming_room_hero_exposes_ritual_target_activity_and_recovery() -> None:
    canvas = load_bundled_canvas("gaming_desktop")

    model = build_canvas_runtime_model(
        canvas,
        context=CanvasRuntimeContext(
            recipe_ids={"gaming_mode"},
            target_ids={"diablo_iv"},
            runtime_state={
                "gaming_mode": {
                    "status": "confirming",
                    "message": "Awaiting explicit Play confirmation",
                    "current_step": "Ask before clicking Play",
                    "confirmation": {
                        "required": True,
                        "action": "desktop.click_text",
                        "target": "Play",
                        "target_type": "text",
                        "message": "Clicking Play requires confirmation",
                    },
                }
            },
            recent_runs=(
                _run_record(
                    "20260618T010000Z_gaming_mode",
                    status="interrupted",
                    message="Setpiece exited before finalizing this run.",
                    extra_metadata={"interrupted_at": "2026-06-18T01:00:00+00:00"},
                ),
                _run_record(
                    "20260618T005000Z_gaming_mode",
                    status="stopped",
                    message="Confirmation declined",
                    extra_metadata={"stopped_reason": "stopped_user_declined_confirmation"},
                ),
            ),
        ),
    )

    components = {component.id: component for component in canvas.components}
    card = model.component_state("diablo_night")
    status = model.component_state("run_status")
    controller = model.component_state("run_controller")
    target = model.component_state("diablo_target")
    activity = model.component_state("recent_activity")

    assert canvas.name == "Gaming Room"
    assert canvas.background.type is CanvasBackgroundType.SYSTEM_WALLPAPER
    assert components["diablo_night"].type == "ritual.card"
    assert card.data["recipe_id"] == "gaming_mode"
    assert {"doctor", "dry_run", "run"} <= set(card.enabled_actions)
    assert status.state == "confirming"
    assert status.message == "Ask before clicking Play"
    assert {"pause", "resume", "stop"} <= set(controller.enabled_actions)
    assert components["run_controller"].props_dict()["controls"] == ["pause", "resume", "stop"]
    assert target.data["target_id"] == "diablo_iv"
    assert target.enabled_actions == ("preview_plan",)
    assert components["diablo_target"].props_dict()["title"] == "Diablo IV"

    activity_items = activity.data["items"]
    assert [item["status"] for item in activity_items[:2]] == ["interrupted", "stopped"]
    assert activity_items[1]["stopped_reason"] == "stopped_user_declined_confirmation"

    ritual_state = model.ritual_states["gaming_mode"]
    assert ritual_state["active_run"]["confirmation"]["required"] is True
    assert ritual_state["active_run"]["confirmation"]["target"] == "Play"
    assert ritual_state["last_run"]["state"] == "interrupted"
    assert ritual_state["recovery"]["interrupted"] is True
    assert ritual_state["recovery"]["safe_next_actions"] == ("inspect_run", "doctor", "start_fresh")


def test_gaming_room_target_preview_is_side_effect_free_plan_preview() -> None:
    canvas = load_bundled_canvas("gaming_desktop")
    target = builtin_target_catalog().resolve("diablo_iv")[0]
    resolver_calls: list[str] = []

    def resolve_fake_target(query: str) -> TargetResolutionResult:
        resolver_calls.append(query)
        return TargetResolutionResult(
            query=query,
            target=target,
            state=TargetState.LAUNCHABLE,
            candidates=(
                TargetCandidate(
                    candidate_id="shortcut_diablo",
                    target_id="diablo_iv",
                    provider="start_menu_shortcut",
                    state=TargetState.LAUNCHABLE,
                    label="Diablo IV",
                    path="C:/Users/example/Desktop/Diablo IV.lnk",
                    command="C:/Users/example/Desktop/Diablo IV.lnk",
                ),
            ),
        )

    controller = CanvasRuntimeController(
        context=CanvasRuntimeContext(
            recipe_ids={"gaming_mode"},
            target_ids={"diablo_iv"},
            target_resolver=resolve_fake_target,
        )
    )

    result = controller.dispatch(canvas, "diablo_target", "preview_plan")

    assert resolver_calls == ["diablo_iv"]
    assert result.status == "success"
    assert result.action_id == "preview_plan"
    assert result.data["target_plan"]["plan"]["intent"]["kind"] == "target.start"
    assert result.data["target_plan"]["plan"]["steps"][0]["primitive_id"] == "app.process.launch"


def test_gaming_room_desktop_work_area_preserves_wallpaper_passthrough() -> None:
    canvas = load_bundled_canvas("gaming_desktop")
    host_config = resolve_canvas_host_config("desktop-work-area")

    assert canvas.background.type is CanvasBackgroundType.SYSTEM_WALLPAPER
    assert host_config.mode.value == "desktop_work_area"
    assert host_config.to_dict()["background_passthrough"] is True
    assert host_config.to_dict()["background_mode"] == "system_wallpaper"
    assert host_config.to_dict()["taskbar_policy"] == "respect"
    assert host_config.to_dict()["click_through_implemented"] is False


def test_gaming_mode_keeps_play_confirmation_and_avoids_unconfirmed_game_control() -> None:
    recipe = load_recipe(GAMING_MODE_PATH)
    actions_after_launch = _actions_after(recipe.execution_steps, "app.launch")
    desktop_clicks_after_launch = [step for step in actions_after_launch if step.action == "desktop.click_text"]
    play_steps = [step for step in desktop_clicks_after_launch if step.text == "Play"]

    assert [step.name for step in play_steps] == ["Ask before clicking Play"]
    assert all(step.requires_confirmation for step in play_steps)
    assert all(step.text == "Play" for step in desktop_clicks_after_launch)
    assert not any(_is_forbidden_action(step.action) for step in recipe.execution_steps)


def _run_record(
    run_id: str,
    *,
    status: str,
    message: str,
    extra_metadata: dict[str, Any] | None = None,
) -> RunRecord:
    metadata = {
        "recipe_id": "gaming_mode",
        "final_state": status,
        "final_message": message,
    }
    metadata.update(extra_metadata or {})
    return RunRecord(
        run_id=run_id,
        path=Path("runs") / run_id,
        metadata=metadata,
        steps=[
            {
                "index": 1,
                "step_name": "Ask before clicking Play",
                "action": "desktop.click_text",
                "status": status,
            }
        ],
    )


def _actions_after(steps: list[Any], action: str) -> list[Any]:
    for index, step in enumerate(steps):
        if step.action == action:
            return steps[index + 1 :]
    return []


def _is_forbidden_action(action: str) -> bool:
    lowered = action.casefold()
    return any(marker in lowered for marker in ("python", "javascript", "powershell", "shell"))
