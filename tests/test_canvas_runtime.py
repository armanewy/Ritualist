from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from ritualist.canvas import (
    CanvasBindingKind,
    CanvasComponent,
    CanvasComponentBinding,
    CanvasDocument,
    CanvasHostMode,
    CanvasTaskbarPolicy,
    CanvasRuntimeContext,
    CanvasRuntimeController,
    build_canvas_runtime_model,
    build_canvas_view_model,
    canvas_to_home_model,
    default_canvas_for_host,
    resolve_canvas_host_config,
)
from ritualist.canvas.app import _apply_canvas_host
from ritualist.cli import app
from ritualist.canvas.controller import dispatch_canvas_action
from ritualist.canvas.runtime import CanvasComponentActionResult
from ritualist.errors import RitualistError
from ritualist.home.actions import HomeActionService
from ritualist.run_logs import RunRecord
from ritualist.runtime_control import RuntimeControl
from ritualist.target_resolution import resolve_target


def _canvas() -> CanvasDocument:
    return CanvasDocument(
        id="runtime_canvas",
        name="Runtime Canvas",
        components=(
            CanvasComponent(
                id="card",
                type="ritual.card",
                width=320,
                height=180,
                props={"title": "Gaming", "recipe_id": "gaming_mode"},
            ),
            CanvasComponent(
                id="status",
                type="ritual.status",
                width=320,
                height=90,
                props={"recipe_id": "gaming_mode"},
                binding=CanvasComponentBinding(
                    kind=CanvasBindingKind.RECIPE,
                    recipe_id="gaming_mode",
                ),
            ),
            CanvasComponent(
                id="controller",
                type="ritual.controller",
                width=320,
                height=90,
                binding=CanvasComponentBinding(
                    kind=CanvasBindingKind.RECIPE,
                    recipe_id="gaming_mode",
                ),
            ),
            CanvasComponent(
                id="target",
                type="target.card",
                width=320,
                height=180,
                props={"title": "Diablo", "target": "diablo_iv"},
            ),
            CanvasComponent(
                id="target_status",
                type="target.status",
                width=320,
                height=90,
                props={"target": "diablo_iv"},
            ),
            CanvasComponent(
                id="doctor",
                type="doctor.badge",
                width=180,
                height=80,
                props={"recipe_id": "gaming_mode"},
                binding=CanvasComponentBinding(
                    kind=CanvasBindingKind.RECIPE,
                    recipe_id="gaming_mode",
                ),
            ),
            CanvasComponent(id="activity", type="recent.activity", width=320, height=120),
            CanvasComponent(id="dock", type="category.dock", width=200, height=240),
            CanvasComponent(
                id="label",
                type="text.label",
                width=200,
                height=64,
                props={"text": "Hello"},
            ),
            CanvasComponent(
                id="clock",
                type="clock",
                width=180,
                height=80,
                props={"format": "short"},
            ),
        ),
    )


def _run_record(
    run_id: str,
    *,
    recipe_id: str = "gaming_mode",
    status: str = "success",
    message: str = "run completed",
    extra_metadata: dict[str, Any] | None = None,
) -> RunRecord:
    metadata = {
        "recipe_id": recipe_id,
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
                "step_name": "Final step",
                "action": "wait.seconds",
                "status": status,
            }
        ],
    )


class _FakeService(HomeActionService):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, str, bool]] = []

    def run_recipe(self, recipe_ref: str | Path, *, dry_run: bool, **_kwargs: Any) -> dict[str, Any]:
        self.calls.append(("run_recipe", str(recipe_ref), dry_run))
        return {"recipe_ref": str(recipe_ref), "dry_run": dry_run}

    def doctor_recipe(self, recipe_ref: str | Path) -> dict[str, Any]:
        self.calls.append(("doctor_recipe", str(recipe_ref), False))
        return {"compatibility": {"status": "compatible"}}

    def resolve_recipe_path(self, recipe_ref: str | Path) -> Path:
        return Path("recipes") / f"{recipe_ref}.yaml"

    def resolve_runs_path(self) -> Path:
        return Path("runs")


def test_canvas_runtime_model_builds_from_canvas_without_executing_actions() -> None:
    model = build_canvas_runtime_model(
        _canvas(),
        context=CanvasRuntimeContext(
            recipe_ids={"gaming_mode"},
            target_ids={"diablo_iv"},
            recent_runs=(_run_record("run1"),),
        ),
    )

    assert model.canvas_id == "runtime_canvas"
    assert model.component_state("card").enabled_actions == (
        "run",
        "dry_run",
        "doctor",
        "edit_recipe",
        "open_logs",
    )
    assert model.component_state("label").enabled_actions == ()
    assert model.component_state("activity").enabled_actions == ("open_logs",)
    assert model.component_state("activity").data["items"][0]["status"] == "success"


def test_canvas_use_view_model_includes_layout_and_runtime_state() -> None:
    model = build_canvas_view_model(
        _canvas(),
        context=CanvasRuntimeContext(
            recipe_ids={"gaming_mode"},
            target_ids={"diablo_iv"},
            runtime_state={
                "gaming_mode": {
                    "status": "running",
                    "current_step": "Ask before clicking Play",
                }
            },
            recent_runs=(),
        ),
    )

    payload = model.to_dict()
    components = {component["id"]: component for component in payload["components"]}

    assert payload["schema_version"] == "ritualist.canvas.view_model.v1"
    assert payload["canvas"]["id"] == "runtime_canvas"
    assert components["card"]["width"] == 320
    assert components["status"]["state"] == "running"
    assert components["status"]["message"] == "Ask before clicking Play"
    assert components["label"]["display_only"] is True
    assert components["card"]["enabled_actions"] == [
        "run",
        "dry_run",
        "doctor",
        "edit_recipe",
        "open_logs",
    ]


def test_canvas_use_view_model_covers_required_component_types() -> None:
    model = build_canvas_view_model(
        _canvas(),
        context=CanvasRuntimeContext(
            recipe_ids={"gaming_mode"},
            target_ids={"diablo_iv"},
            recent_runs=(),
        ),
    )

    component_types = {component.type for component in model.components}

    assert {
        "ritual.card",
        "ritual.status",
        "ritual.controller",
        "target.card",
        "target.status",
        "doctor.badge",
        "recent.activity",
        "category.dock",
        "text.label",
        "clock",
    } <= component_types


def test_canvas_runtime_model_reports_unresolved_recipe_and_target() -> None:
    canvas = CanvasDocument(
        id="unresolved_canvas",
        name="Unresolved",
        components=(
            CanvasComponent(
                id="recipe",
                type="ritual.card",
                width=320,
                height=180,
                props={"title": "Missing", "recipe_id": "missing_recipe"},
            ),
            CanvasComponent(
                id="target",
                type="target.card",
                width=320,
                height=180,
                props={"title": "Missing", "target": "missing_target"},
            ),
        ),
    )

    model = build_canvas_runtime_model(
        canvas,
        context=CanvasRuntimeContext(recipe_ids={"gaming_mode"}, target_ids={"diablo_iv"}, recent_runs=()),
    )

    assert model.component_state("recipe").enabled_actions == ()
    assert any("missing_recipe" in warning for warning in model.unresolved_binding_warnings)
    assert any("missing_target" in warning for warning in model.unresolved_binding_warnings)


def test_ritual_status_reflects_active_runtime_state() -> None:
    model = build_canvas_runtime_model(
        _canvas(),
        context=CanvasRuntimeContext(
            recipe_ids={"gaming_mode"},
            target_ids={"diablo_iv"},
            runtime_state={
                "gaming_mode": {
                    "status": "paused",
                    "current_step": "Wait for user",
                }
            },
            recent_runs=(),
        ),
    )

    state = model.component_state("status")

    assert state.state == "paused"
    assert state.message == "Wait for user"


def test_target_card_preview_uses_fake_target_resolver() -> None:
    model = build_canvas_runtime_model(
        _canvas(),
        context=CanvasRuntimeContext(
            recipe_ids={"gaming_mode"},
            target_ids={"diablo_iv"},
            recent_runs=(),
            resolve_targets=True,
            target_resolver=lambda query: resolve_target(query, providers=()),
        ),
    )

    state = model.component_state("target")

    assert state.data["summary"]["state"] == "not_found"
    assert state.enabled_actions == ("preview_plan",)


def test_doctor_badge_uses_cached_side_effect_free_summary() -> None:
    model = build_canvas_runtime_model(
        _canvas(),
        context=CanvasRuntimeContext(
            recipe_ids={"gaming_mode"},
            target_ids={"diablo_iv"},
            doctor_summaries={"gaming_mode": {"status": "compatible", "message": "ready"}},
            recent_runs=(),
        ),
    )

    state = model.component_state("doctor")

    assert state.status == "compatible"
    assert state.message == "ready"


def test_recent_activity_shows_stopped_failed_and_interrupted_runs() -> None:
    model = build_canvas_runtime_model(
        _canvas(),
        context=CanvasRuntimeContext(
            recipe_ids={"gaming_mode"},
            target_ids={"diablo_iv"},
            recent_runs=(
                _run_record("stopped", status="stopped", message="declined confirmation"),
                _run_record("failed", status="failed", message="path missing"),
                _run_record("interrupted", status="interrupted", message="process exited"),
            ),
        ),
    )

    statuses = [item["status"] for item in model.component_state("activity").data["items"]]

    assert statuses == ["stopped", "failed", "interrupted"]
    assert "declined confirmation" in model.last_run_messages["gaming_mode"]


def test_recent_activity_exposes_cleanup_state() -> None:
    model = build_canvas_runtime_model(
        _canvas(),
        context=CanvasRuntimeContext(
            recipe_ids={"gaming_mode"},
            target_ids={"diablo_iv"},
            recent_runs=(
                _run_record(
                    "stopped",
                    status="stopped",
                    message="Confirmation declined",
                    extra_metadata={
                        "stopped_reason": "stopped_user_declined_confirmation",
                        "cleanup_offer": {
                            "options": [
                                {
                                    "id": "clean_up_ritualist_opened",
                                    "available": True,
                                }
                            ]
                        },
                        "cleanup_choice": {"choice": "keep_setup_open"},
                        "ownership_ledger": [{"kind": "browser"}],
                    },
                ),
            ),
        ),
    )

    item = model.component_state("activity").data["items"][0]

    assert item["stopped_reason"] == "stopped_user_declined_confirmation"
    assert item["cleanup_available"] is True
    assert item["cleanup_choice"] == "keep_setup_open"
    assert item["ownership_count"] == 1


def test_canvas_to_home_model_consumes_runtime_model() -> None:
    runtime_model = build_canvas_runtime_model(
        _canvas(),
        context=CanvasRuntimeContext(
            recipe_ids={"gaming_mode"},
            target_ids={"diablo_iv"},
            runtime_state={"gaming_mode": {"status": "running", "message": "active"}},
            recent_runs=(),
        ),
    )

    home_model = canvas_to_home_model(_canvas(), runtime_model=runtime_model)

    assert home_model.get_card("card").status.value == "running"


def test_canvas_action_dry_run_does_not_call_service() -> None:
    service = _FakeService()
    controller = CanvasRuntimeController(
        action_service=service,
        context=CanvasRuntimeContext(recipe_ids={"gaming_mode"}),
    )

    result = controller.dispatch(_canvas(), "card", "run", dry_run=True)

    assert result.status == "dry-run"
    assert service.calls == []


def test_ritual_card_actions_route_through_fake_service() -> None:
    service = _FakeService()
    controller = CanvasRuntimeController(
        action_service=service,
        context=CanvasRuntimeContext(recipe_ids={"gaming_mode"}),
    )

    dry_run = controller.dispatch(_canvas(), "card", "dry_run")
    run = controller.dispatch(_canvas(), "card", "run")
    doctor = controller.dispatch(_canvas(), "card", "doctor")

    assert dry_run.ok and run.ok and doctor.ok
    assert service.calls == [
        ("run_recipe", "gaming_mode", True),
        ("run_recipe", "gaming_mode", False),
        ("doctor_recipe", "gaming_mode", False),
    ]


def test_doctor_badge_action_routes_through_fake_service() -> None:
    service = _FakeService()
    controller = CanvasRuntimeController(
        action_service=service,
        context=CanvasRuntimeContext(recipe_ids={"gaming_mode"}),
    )

    result = controller.dispatch(_canvas(), "doctor", "doctor")

    assert result.ok
    assert service.calls == [("doctor_recipe", "gaming_mode", False)]


def test_unresolved_recipe_prevents_run_dispatch() -> None:
    controller = CanvasRuntimeController(
        action_service=_FakeService(),
        context=CanvasRuntimeContext(recipe_ids={"other_recipe"}),
    )

    with pytest.raises(RitualistError, match="unresolved"):
        controller.dispatch(_canvas(), "card", "run")


def test_ritual_controller_pause_resume_stop_routes_to_runtime_control() -> None:
    control = RuntimeControl()
    controller = CanvasRuntimeController(
        action_service=_FakeService(),
        runtime_controls={"gaming_mode": control},
    )

    paused = controller.dispatch(_canvas(), "controller", "pause")
    assert paused.ok
    assert control.is_paused()

    resumed = controller.dispatch(_canvas(), "controller", "resume")
    assert resumed.ok
    assert not control.is_paused()

    stopped = controller.dispatch(_canvas(), "controller", "stop")
    assert stopped.ok
    assert control.is_stopping()


def test_controller_actions_disabled_without_active_run() -> None:
    model = build_canvas_runtime_model(
        _canvas(),
        context=CanvasRuntimeContext(recipe_ids={"gaming_mode"}, target_ids={"diablo_iv"}, recent_runs=()),
    )

    state = model.component_state("controller")

    assert "stop" in state.disabled_actions


def test_target_card_action_preview_is_plan_only() -> None:
    controller = CanvasRuntimeController(
        action_service=_FakeService(),
        context=CanvasRuntimeContext(target_resolver=lambda query: resolve_target(query, providers=())),
    )

    result = controller.dispatch(_canvas(), "target", "preview_plan")

    assert result.ok
    assert result.data["target_summary"]["state"] == "not_found"


def test_unknown_and_unsupported_canvas_actions_are_rejected() -> None:
    controller = CanvasRuntimeController(action_service=_FakeService())

    with pytest.raises(RitualistError, match="not found"):
        controller.dispatch(_canvas(), "missing", "run")
    with pytest.raises(RitualistError, match="unsupported"):
        controller.dispatch(_canvas(), "label", "run")
    with pytest.raises(RitualistError, match="unsupported"):
        controller.dispatch(_canvas(), "card", "shell")


def test_missing_binding_rejected_for_action() -> None:
    canvas = CanvasDocument(
        id="missing_binding",
        name="Missing Binding",
        components=(
            CanvasComponent(
                id="card",
                type="ritual.card",
                width=320,
                height=180,
                props={"title": "Missing"},
            ),
        ),
    )

    controller = CanvasRuntimeController(action_service=_FakeService())

    with pytest.raises(RitualistError, match="recipe binding"):
        controller.dispatch(canvas, "card", "run")


def test_dispatch_canvas_action_module_function_loads_canvas(tmp_path: Path, monkeypatch) -> None:
    canvas_path = tmp_path / "canvas.yaml"
    from ritualist.canvas.storage import save_canvas

    save_canvas(_canvas(), canvas_path)
    service = _FakeService()
    controller = CanvasRuntimeController(
        action_service=service,
        context=CanvasRuntimeContext(recipe_ids={"gaming_mode"}),
    )

    result = dispatch_canvas_action(canvas_path, "card", "doctor", controller=controller)

    assert isinstance(result, CanvasComponentActionResult)
    assert result.ok
    assert service.calls == [("doctor_recipe", "gaming_mode", False)]


def test_canvas_runtime_build_does_not_call_low_level_adapters(monkeypatch) -> None:
    def fail_adapters() -> None:
        raise AssertionError("Canvas runtime build must not create adapters")

    monkeypatch.setattr("ritualist.adapters.create_default_adapters", fail_adapters)

    model = build_canvas_runtime_model(
        _canvas(),
        context=CanvasRuntimeContext(recipe_ids={"gaming_mode"}, target_ids={"diablo_iv"}, recent_runs=()),
    )

    assert model.component_state("card").status == "ready"


def test_canvas_use_view_model_does_not_call_low_level_adapters(monkeypatch) -> None:
    def fail_adapters() -> None:
        raise AssertionError("Canvas Use model build must not create adapters")

    monkeypatch.setattr("ritualist.adapters.create_default_adapters", fail_adapters)

    model = build_canvas_view_model(
        _canvas(),
        context=CanvasRuntimeContext(
            recipe_ids={"gaming_mode"},
            target_ids={"diablo_iv"},
            recent_runs=(),
            resolve_targets=False,
        ),
    )

    assert model.components


def test_canvas_runtime_and_action_cli_json(tmp_path: Path) -> None:
    canvas_path = tmp_path / "canvas.yaml"
    from ritualist.canvas.storage import save_canvas

    save_canvas(_canvas(), canvas_path)
    runner = CliRunner()

    runtime_result = runner.invoke(app, ["canvas", "runtime", str(canvas_path), "--json"])
    action_result = runner.invoke(
        app,
        ["canvas", "action", str(canvas_path), "card", "doctor", "--dry-run", "--json"],
    )

    assert runtime_result.exit_code == 0
    assert action_result.exit_code == 0
    assert "ritualist.canvas.runtime.v1" in runtime_result.output
    assert "would dispatch canvas action doctor" in action_result.output


def test_canvas_use_cli_help() -> None:
    result = CliRunner().invoke(app, ["canvas", "use", "--help"])

    assert result.exit_code == 0
    assert "Canvas Use Mode" in result.output
    assert "--host" in result.output
    assert "desktop-work-area" in result.output


def test_canvas_host_config_enables_desktop_work_area_without_taskbar_mutation() -> None:
    config = resolve_canvas_host_config(
        "desktop-work-area",
        taskbar_policy="respect",
    )

    assert config.mode is CanvasHostMode.DESKTOP_WORK_AREA
    assert config.taskbar_policy is CanvasTaskbarPolicy.RESPECT
    assert config.to_dict() == {
        "schema_version": "ritualist.canvas.host.v1",
        "mode": "desktop_work_area",
        "taskbar_policy": "respect",
        "implemented": True,
        "taskbar_visible": True,
    }


def test_canvas_host_config_rejects_future_modes_until_implemented() -> None:
    config = resolve_canvas_host_config("windowed")

    assert config.mode is CanvasHostMode.WINDOWED
    assert config.to_dict()["implemented"] is True

    with pytest.raises(RitualistError, match="not implemented yet"):
        resolve_canvas_host_config("desktop-full-monitor-later")


def test_canvas_host_default_canvas_uses_minimal_room_for_desktop_work_area() -> None:
    windowed = resolve_canvas_host_config("windowed")
    desktop_work_area = resolve_canvas_host_config("desktop-work-area")

    assert default_canvas_for_host(None, windowed) == "gaming_desktop"
    assert default_canvas_for_host("", desktop_work_area) == "minimal_desktop"
    assert default_canvas_for_host("gaming_desktop", desktop_work_area) == "gaming_desktop"


@pytest.mark.parametrize("policy", ["hide", "auto-hide", "replace", "kiosk"])
def test_canvas_taskbar_policy_rejects_shell_like_values(policy: str) -> None:
    with pytest.raises(RitualistError, match="only supports 'respect'"):
        resolve_canvas_host_config("windowed", taskbar_policy=policy)


def test_canvas_host_rejects_retired_overlay_name() -> None:
    with pytest.raises(RitualistError, match="desktop_overlay.*retired"):
        resolve_canvas_host_config("desktop-overlay", require_implemented=False)


class _FakeRect:
    def __init__(self, x: int, y: int, width: int, height: int) -> None:
        self._x = x
        self._y = y
        self._width = width
        self._height = height

    def x(self) -> int:
        return self._x

    def y(self) -> int:
        return self._y

    def width(self) -> int:
        return self._width

    def height(self) -> int:
        return self._height


class _FakeScreen:
    def availableGeometry(self) -> _FakeRect:
        return _FakeRect(0, 0, 1920, 1040)

    def geometry(self) -> _FakeRect:
        return _FakeRect(0, 0, 1920, 1080)


class _FakeApplication:
    @staticmethod
    def primaryScreen() -> _FakeScreen:
        return _FakeScreen()


class _FakeWindowType:
    Window = 1
    FramelessWindowHint = 2


class _FakeQt:
    WindowType = _FakeWindowType


class _FakeWindow:
    def __init__(self) -> None:
        self.flags = None
        self.geometry = None
        self.shown = False

    def screen(self) -> None:
        return None

    def setFlags(self, flags: int) -> None:
        self.flags = flags

    def setGeometry(self, geometry: _FakeRect) -> None:
        self.geometry = geometry

    def show(self) -> None:
        self.shown = True


def test_apply_desktop_work_area_host_uses_available_geometry() -> None:
    window = _FakeWindow()
    config = resolve_canvas_host_config("desktop-work-area")

    payload = _apply_canvas_host(window, config, _FakeApplication, _FakeQt)

    assert window.flags == 3
    assert window.geometry is not None
    assert window.shown is True
    assert payload["applied"] == "desktop_work_area"
    assert payload["work_area"] == {"x": 0, "y": 0, "width": 1920, "height": 1040}
    assert payload["screen_geometry"] == {"x": 0, "y": 0, "width": 1920, "height": 1080}
    assert payload["bounds_match_work_area"] is True
    assert payload["taskbar_visible"] is True


def test_canvas_use_cli_launch_path_uses_canvas_app(monkeypatch) -> None:
    calls: list[tuple[str, bool, int, dict[str, object]]] = []

    def fake_run_canvas_use(
        canvas: str,
        *,
        mock: bool,
        mock_components: int,
        host_config: object,
    ) -> int:
        calls.append((canvas, mock, mock_components, host_config.to_dict()))
        return 0

    monkeypatch.setattr("ritualist.canvas.app.run_canvas_use", fake_run_canvas_use)

    result = CliRunner().invoke(
        app,
        ["canvas", "use", "gaming_desktop", "--mock-components", "3"],
    )

    assert result.exit_code == 0
    assert calls == [
        (
            "gaming_desktop",
            False,
            3,
            {
                "schema_version": "ritualist.canvas.host.v1",
                "mode": "windowed",
                "taskbar_policy": "respect",
                "implemented": True,
                "taskbar_visible": True,
            },
        )
    ]


def test_canvas_use_cli_mock_launch_path_uses_mock_components(monkeypatch) -> None:
    calls: list[tuple[str, bool, int, dict[str, object]]] = []

    def fake_run_canvas_use(
        canvas: str,
        *,
        mock: bool,
        mock_components: int,
        host_config: object,
    ) -> int:
        calls.append((canvas, mock, mock_components, host_config.to_dict()))
        return 0

    monkeypatch.setattr("ritualist.canvas.app.run_canvas_use", fake_run_canvas_use)

    result = CliRunner().invoke(
        app,
        ["canvas", "use", "--mock", "--mock-components", "12"],
    )

    assert result.exit_code == 0
    assert calls == [
        (
            "gaming_desktop",
            True,
            12,
            {
                "schema_version": "ritualist.canvas.host.v1",
                "mode": "windowed",
                "taskbar_policy": "respect",
                "implemented": True,
                "taskbar_visible": True,
            },
        )
    ]


def test_canvas_use_cli_launches_desktop_work_area_with_minimal_default(monkeypatch) -> None:
    calls: list[tuple[str, bool, int, dict[str, object]]] = []

    def fake_run_canvas_use(
        canvas: str,
        *,
        mock: bool,
        mock_components: int,
        host_config: object,
    ) -> int:
        calls.append((canvas, mock, mock_components, host_config.to_dict()))
        return 0

    monkeypatch.setattr("ritualist.canvas.app.run_canvas_use", fake_run_canvas_use)

    result = CliRunner().invoke(app, ["canvas", "use", "--host", "desktop-work-area"])

    assert result.exit_code == 0
    assert calls == [
        (
            "minimal_desktop",
            False,
            24,
            {
                "schema_version": "ritualist.canvas.host.v1",
                "mode": "desktop_work_area",
                "taskbar_policy": "respect",
                "implemented": True,
                "taskbar_visible": True,
            },
        )
    ]


def test_canvas_use_cli_rejects_future_desktop_host_before_launch(monkeypatch) -> None:
    def fail_launch(*_args: object, **_kwargs: object) -> int:
        raise AssertionError("future hosts must fail before launching Canvas")

    monkeypatch.setattr("ritualist.canvas.app.run_canvas_use", fail_launch)

    result = CliRunner().invoke(
        app,
        ["canvas", "use", "gaming_desktop", "--host", "desktop-full-monitor-later"],
    )

    assert result.exit_code == 1
    assert "not implemented yet" in " ".join(result.output.split())


def test_canvas_use_cli_rejects_taskbar_hiding_before_launch(monkeypatch) -> None:
    def fail_launch(*_args: object, **_kwargs: object) -> int:
        raise AssertionError("unsupported taskbar policy must fail before launching Canvas")

    monkeypatch.setattr("ritualist.canvas.app.run_canvas_use", fail_launch)

    result = CliRunner().invoke(app, ["canvas", "use", "gaming_desktop", "--taskbar-policy", "hide"])

    assert result.exit_code == 1
    assert "only supports 'respect'" in " ".join(result.output.split())


def test_canvas_runtime_perf_cli_json() -> None:
    result = CliRunner().invoke(
        app,
        ["perf", "canvas-runtime", "--mock-components", "100", "--json"],
    )

    assert result.exit_code == 0
    assert '"operation": "perf.canvas-runtime"' in result.output
    assert '"side_effects": "none"' in result.output


def test_canvas_use_perf_cli_json() -> None:
    result = CliRunner().invoke(
        app,
        ["perf", "canvas-use", "--mock-components", "10", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["operation"] == "perf.canvas-use"
    assert payload["view_summary"]["component_count"] == 10
    assert payload["side_effects"] == "none"
