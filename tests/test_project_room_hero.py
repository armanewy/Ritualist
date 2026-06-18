from __future__ import annotations

from pathlib import Path
from typing import Any

from ritualist.adapters.fake import FakeAdapters
from ritualist.canvas import (
    CanvasBindingKind,
    CanvasRuntimeContext,
    CanvasRuntimeController,
    build_canvas_runtime_model,
    load_bundled_canvas,
    validate_canvas,
)
from ritualist.doctor import build_doctor_report
from ritualist.executor import WorkflowExecutor
from ritualist.recipe_loader import load_recipe, load_recipe_for_diagnostics, read_recipe_document
from ritualist.run_logs import RunRecord
from ritualist.runtime_control import RuntimeControl
from ritualist.shortcuts import ShortcutResult


ROOT = Path(__file__).resolve().parents[1]
CANVAS_PATH = ROOT / "ritualist" / "sample_canvases" / "project_room.yaml"
RECIPE_PATH = ROOT / "ritualist" / "sample_recipes" / "coding_mode.yaml"


class _FailingActionService:
    def __getattr__(self, name: str) -> object:
        raise AssertionError(f"shortcut dispatch must not call action service: {name}")


class _FakeShortcutService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def open(self, request: object) -> ShortcutResult:
        kind = getattr(request, "kind")
        action_id = str(getattr(request, "action_id"))
        target = str(getattr(request, "target"))
        self.calls.append((str(kind.value), action_id, target))
        return ShortcutResult(
            kind,
            "success",
            "fake shortcut opened",
            target_label=Path(target).name or target,
        )


def test_project_room_canvas_validates_and_binds_hero_loop() -> None:
    canvas = load_bundled_canvas("project_room")
    result = validate_canvas(CANVAS_PATH)
    components = {component.id: component for component in canvas.components}

    assert result.valid, result.errors
    assert components["coding_mode_card"].type == "ritual.card"
    assert components["coding_mode_card"].binding is not None
    assert components["coding_mode_card"].binding.kind is CanvasBindingKind.RECIPE
    assert components["coding_mode_card"].binding.recipe_id == "coding_mode"
    assert components["coding_mode_card"].props_dict()["primary_action"] == "run"
    assert components["coding_status"].type == "ritual.status"
    assert components["coding_controller"].type == "ritual.controller"
    assert components["recent_activity"].type == "recent.activity"
    assert components["project_folder"].type == "shortcut.folder"
    assert components["editor_shortcut"].type == "shortcut.app"
    assert components["terminal_shortcut"].type == "shortcut.app"
    assert components["docs_shortcut"].type == "shortcut.url"
    assert components["tracker_shortcut"].type == "shortcut.url"
    assert not any(component.type == "app.launcher" for component in canvas.components)


def test_coding_mode_recipe_stays_within_safe_workspace_actions() -> None:
    raw = read_recipe_document(RECIPE_PATH)
    variables = raw["variables"]
    actions = {step["action"] for step in _all_steps(raw)}
    text = RECIPE_PATH.read_text(encoding="utf-8").casefold()

    assert {
        "editor_path",
        "terminal_path",
        "project_path",
        "docs_url",
        "tracker_url",
    } <= set(variables)
    assert raw["steps"][0]["action"] == "confirm.ask"
    assert actions <= {
        "app.launch",
        "assert.file_exists",
        "assert.path_exists",
        "browser.open",
        "confirm.ask",
        "wait.for_user",
    }
    assert "shell.run" not in text
    assert "powershell" not in text
    assert "javascript" not in text
    assert "screenshot" not in text
    assert "watch me" not in text


def test_coding_mode_doctor_identifies_missing_local_app_paths(tmp_path: Path) -> None:
    missing_editor = tmp_path / "missing-code.exe"
    missing_terminal = tmp_path / "missing-terminal.exe"
    project = tmp_path / "project"
    project.mkdir()

    recipe, _raw, missing_variables = load_recipe_for_diagnostics(
        RECIPE_PATH,
        {
            "editor_path": str(missing_editor),
            "terminal_path": str(missing_terminal),
            "project_path": str(project),
        },
    )
    report = build_doctor_report(recipe, missing_variables=missing_variables)
    missing_app_paths = {
        str(check.details.get("path"))
        for check in report.checks
        if check.section == "App paths"
        and check.name == "app.launch"
        and check.status == "error"
    }

    assert missing_variables == []
    assert str(missing_editor) in missing_app_paths
    assert str(missing_terminal) in missing_app_paths


def test_coding_mode_dry_run_lists_setup_and_has_no_fake_adapter_side_effects() -> None:
    recipe = load_recipe(RECIPE_PATH)
    fakes = FakeAdapters()
    confirmations: list[object] = []

    summary = WorkflowExecutor(
        adapters=fakes.bundle(),
        dry_run=True,
        confirmer=lambda request: confirmations.append(request) or False,
    ).run(recipe)

    assert summary.success
    assert [result.status for result in summary.results] == ["dry-run"] * len(summary.results)
    assert [result.step_name for result in summary.results] == [
        "Editor path is configured",
        "Project path exists",
        "Confirm coding workspace",
        "Open project in editor",
        "Launch optional terminal",
        "Open documentation",
        "Open tracker",
        "Wait for manual readiness",
        "Project path remains available",
    ]
    assert fakes.shell.calls == []
    assert fakes.browser.calls == []
    assert fakes.window.calls == []
    assert fakes.desktop.calls == []
    assert fakes.input.calls == []
    assert confirmations == []


def test_project_room_shortcuts_dispatch_without_creating_run_logs(tmp_path: Path) -> None:
    canvas = load_bundled_canvas("project_room")
    shortcuts = _FakeShortcutService()
    controller = CanvasRuntimeController(
        action_service=_FailingActionService(),  # type: ignore[arg-type]
        shortcut_service=shortcuts,  # type: ignore[arg-type]
    )

    for component_id, action in (
        ("project_folder", "open"),
        ("editor_shortcut", "launch"),
        ("terminal_shortcut", "launch"),
        ("docs_shortcut", "open"),
        ("tracker_shortcut", "open"),
    ):
        result = controller.dispatch(canvas, component_id, action)
        assert result.ok

    assert [call[0:2] for call in shortcuts.calls] == [
        ("folder", "open"),
        ("app", "launch"),
        ("app", "launch"),
        ("url", "open"),
        ("url", "open"),
    ]
    assert not (tmp_path / "runs").exists()


def test_project_room_status_recent_activity_and_controller_state_work() -> None:
    canvas = load_bundled_canvas("project_room")
    model = build_canvas_runtime_model(
        canvas,
        context=CanvasRuntimeContext(
            recipe_ids={"coding_mode"},
            runtime_state={
                "coding_mode": {
                    "status": "running",
                    "current_step": "Open documentation",
                    "message": "workspace opening",
                }
            },
            recent_runs=(
                _run_record(
                    "coding-run",
                    status="stopped",
                    message="Confirmation declined",
                ),
            ),
        ),
    )
    control = RuntimeControl()
    controller = CanvasRuntimeController(
        runtime_controls={"coding_mode": control},
        context=CanvasRuntimeContext(recipe_ids={"coding_mode"}),
    )

    status = model.component_state("coding_status")
    run_controller = model.component_state("coding_controller")
    recent = model.component_state("recent_activity")

    assert status.state == "running"
    assert status.message == "Open documentation"
    assert {"pause", "resume", "stop"} <= set(run_controller.enabled_actions)
    assert recent.data["items"][0]["recipe_id"] == "coding_mode"
    assert recent.data["items"][0]["status"] == "stopped"

    assert controller.dispatch(canvas, "coding_controller", "pause").ok
    assert control.is_paused()
    assert controller.dispatch(canvas, "coding_controller", "resume").ok
    assert not control.is_paused()
    assert controller.dispatch(canvas, "coding_controller", "stop").ok
    assert control.is_stopping()


def _run_record(
    run_id: str,
    *,
    status: str,
    message: str,
) -> RunRecord:
    return RunRecord(
        run_id=run_id,
        path=Path("runs") / run_id,
        metadata={
            "recipe_id": "coding_mode",
            "final_state": status,
            "final_message": message,
        },
        steps=[
            {
                "index": 1,
                "step_name": "Final step",
                "action": "wait.for_user",
                "status": status,
            }
        ],
    )


def _all_steps(raw: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        step
        for section in ("preflight", "steps", "verify")
        for step in raw.get(section, [])
    ]
