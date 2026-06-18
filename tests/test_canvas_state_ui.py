from __future__ import annotations

from pathlib import Path

from ritualist.canvas import (
    CanvasBindingKind,
    CanvasComponent,
    CanvasComponentBinding,
    CanvasDocument,
    CanvasRuntimeContext,
    build_canvas_runtime_model,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
CANVAS_USE_QML = REPO_ROOT / "ritualist" / "canvas" / "qml" / "CanvasUse.qml"


def _qml() -> str:
    return CANVAS_USE_QML.read_text(encoding="utf-8")


def test_canvas_use_qml_routes_rituals_and_shortcuts_to_state_aware_delegates() -> None:
    qml = _qml()

    for snippet in (
        "function isRitualComponent(typeName)",
        'typeName === "ritual.card"',
        'typeName === "ritual.status"',
        'typeName === "ritual.controller"',
        'typeName === "doctor.badge"',
        "return ritualDelegate",
        "function isShortcutComponent(typeName)",
        'typeName === "shortcut.folder"',
        'typeName === "shortcut.app"',
        'typeName === "shortcut.url"',
        "return shortcutDelegate",
    ):
        assert snippet in qml


def test_canvas_use_qml_renders_structured_ritual_state_hierarchy() -> None:
    qml = _qml()

    for snippet in (
        "id: ritualDelegate",
        "function ritualState(component)",
        "root.activeRun(componentData)",
        "Readiness",
        "root.readinessSummary(componentData)",
        "Current step",
        "root.currentStepTitle(componentData)",
        "Waiting for",
        "root.waitSummary(componentData)",
        "Native confirmation required",
        "root.confirmationSummary(componentData)",
        "Paused:",
        "Failed step",
        "Repaired interrupted run",
        "root.lastRunSummary(componentData)",
        "root.artifactSummary(componentData)",
        'visualState === "running"',
        'visualState === "waiting"',
        'visualState === "confirming"',
        'visualState === "paused"',
        'visualState === "interrupted"',
    ):
        assert snippet in qml


def test_canvas_use_qml_has_quiet_instrument_active_run_layout() -> None:
    qml = _qml()

    for snippet in (
        "function quietInstrumentState(status)",
        "function componentIsQuietInstrument(component)",
        "function quietInstrumentEngaged()",
        'component.type !== "ritual.card"',
        "property bool quietInstrument: root.componentIsQuietInstrument(modelData)",
        "property bool receded: !quietInstrument && root.quietInstrumentEngaged()",
        "property real quietWidth",
        "property real quietHeight",
        "x: quietInstrument ? Math.max(root.spaceLg",
        "z: quietInstrument ? 900 : modelData.z",
        "opacity: componentShell.receded ? 0.46",
        "enabled: root.animationsEnabled && !root.editMode",
    ):
        assert snippet in qml


def test_canvas_use_qml_uses_existing_ritual_actions_with_state_specific_labels() -> None:
    qml = _qml()

    for snippet in (
        'root.actionsFrom(componentData, ["doctor", "dry_run", "run"])',
        'root.actionsFrom(componentData, ["resume", "stop", "open_run_log"])',
        'root.actionsFrom(componentData, ["pause", "resume", "stop", "open_run_log"])',
        'root.actionsFrom(componentData, ["open_logs", "open_run_log"])',
        'root.actionsFrom(componentData, ["open_logs", "open_run_log", "doctor", "run"])',
        'return "Dry Run"',
        'return "Open Logs"',
        'return "Inspect Run"',
        'return "Start Fresh"',
        'return "Resume"',
        "root.dispatch(componentData.id, modelData)",
    ):
        assert snippet in qml

    forbidden_new_action_ids = ("inspect_run", "start_fresh")
    for action_id in forbidden_new_action_ids:
        assert f'"{action_id}"' not in qml


def test_canvas_use_qml_gives_shortcuts_distinct_instant_action_visuals() -> None:
    qml = _qml()

    for snippet in (
        "id: shortcutDelegate",
        'return "Open Folder"',
        'return "Launch App"',
        'return "Open URL"',
        '"DIR"',
        '"APP"',
        '"URL"',
        '"Instant " + kind + " shortcut"',
        "componentData.data.shortcut.target_label",
    ):
        assert snippet in qml


def test_canvas_use_qml_gives_target_cards_dedicated_readiness_surface() -> None:
    qml = _qml()

    for snippet in (
        'if (typeName === "target.card")',
        "return targetDelegate",
        "id: targetDelegate",
        "property var targetData",
        "Target readiness",
        "targetData.status || componentData.status || \"ready\"",
        "targetData.summary || root.detailText(componentData)",
        "text: root.actionLabel(modelData, componentData)",
        "root.dispatch(componentData.id, modelData)",
    ):
        assert snippet in qml


def test_shortcut_components_stay_separate_from_ritual_state_controls(tmp_path: Path) -> None:
    folder = tmp_path / "project"
    folder.mkdir()
    canvas = CanvasDocument(
        id="shortcut_ui_contract",
        name="Shortcut UI Contract",
        components=(
            CanvasComponent(
                id="ritual",
                type="ritual.card",
                width=320,
                height=180,
                props={"title": "Runbook", "recipe_id": "setup"},
                binding=CanvasComponentBinding(kind=CanvasBindingKind.RECIPE, recipe_id="setup"),
            ),
            CanvasComponent(
                id="folder",
                type="shortcut.folder",
                width=240,
                height=96,
                props={"title": "Project", "path": str(folder)},
            ),
        ),
    )

    model = build_canvas_runtime_model(
        canvas,
        context=CanvasRuntimeContext(recipe_ids={"setup"}, recent_runs=()),
    )
    ritual = model.component_state("ritual")
    shortcut = model.component_state("folder")

    assert {"doctor", "dry_run", "run"} <= set(ritual.enabled_actions)
    assert "ritual_state" in ritual.data
    assert shortcut.enabled_actions == ("open",)
    assert "shortcut" in shortcut.data
    assert "ritual_state" not in shortcut.data
    assert not {"doctor", "dry_run", "run"} & set(shortcut.enabled_actions)
