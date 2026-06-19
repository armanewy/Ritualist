from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter
from typing import Any
import warnings

from setpiece.canvas import (
    CanvasBindingKind,
    CanvasComponent,
    CanvasComponentBinding,
    CanvasDocument,
    CanvasRuntimeContext,
    build_canvas_runtime_model,
    canvas_performance_diagnostics,
    create_mock_canvas,
    load_bundled_canvas,
    validate_canvas_structure,
)
from setpiece.run_logs import RunRecord
from setpiece.rooms import list_rooms


HERO_ROOM_IDS = ("gaming", "project", "support_desk")
HERO_CANVAS_IDS = ("gaming_desktop", "project_room", "helpdesk_desktop")
HERO_RECIPE_IDS = {
    "gaming_mode",
    "coding_mode",
    "support_triage_workspace",
    "collect_basic_diagnostics",
    "meeting_audio_troubleshooting",
    "vpn_repair_placeholder",
    "new_hire_setup_draft",
}
HERO_TARGET_IDS = {"diablo_iv"}
ADVISORY_MODEL_BUILD_BUDGET_MS = 75.0
ADVISORY_STRESS_BUILD_BUDGET_MS = 250.0
ADVISORY_STATE_UPDATE_BUDGET_MS = 25.0
PERFORMANCE_EVIDENCE_SCHEMA = "setpiece.hero_room.performance_evidence.v1"


def test_hero_room_model_builds_record_advisory_evidence(record_property: Any) -> None:
    room_index = {room.room_id: room for room in list_rooms()}

    assert tuple(room_index) == HERO_ROOM_IDS
    assert tuple(room.canvas_id for room in room_index.values()) == HERO_CANVAS_IDS

    rows: list[dict[str, Any]] = []
    for room_id in HERO_ROOM_IDS:
        room = room_index[room_id]
        document = load_bundled_canvas(room.canvas_id)
        validation = validate_canvas_structure(document)
        model, duration_ms = _measure_model(
            document,
            CanvasRuntimeContext(
                recipe_ids=HERO_RECIPE_IDS,
                target_ids=HERO_TARGET_IDS,
                recent_runs=(),
                resolve_targets=False,
            ),
        )
        diagnostics = canvas_performance_diagnostics(document)
        row = _evidence_row(
            f"hero-room:{room.name}",
            duration_ms,
            ADVISORY_MODEL_BUILD_BUDGET_MS,
            component_count=len(document.components),
            warnings=[
                *validation.warnings,
                *model.unresolved_binding_warnings,
                *diagnostics["warnings"],
            ],
            extra={
                "room_id": room.room_id,
                "canvas_id": document.id,
                "canvas_name": document.name,
                "diagnostic_cost": diagnostics["estimated_cost"],
                "live_widgets": diagnostics["live_widgets"],
                "worker_boundary": "model-only; no adapters, desktop scans, screenshots, hooks, or recording",
            },
        )
        rows.append(row)
        _warn_if_over_budget(row)

        assert validation.errors == ()
        assert model.canvas_id == document.id
        assert row["side_effects"] == "none"

    record_property("hero_room_model_builds", _json_evidence(rows))


def test_state_transition_updates_record_advisory_cost(record_property: Any) -> None:
    document = load_bundled_canvas("gaming_desktop")
    transitions = (
        ("idle", {}),
        ("running", {"status": "running", "message": "Opening Battle.net"}),
        ("waiting", {"status": "waiting", "current_step": "Wait for launcher"}),
        (
            "confirming",
            {
                "status": "confirming",
                "current_step": "Ask before clicking Play",
                "confirmation": {
                    "required": True,
                    "target": "Play",
                    "target_type": "text",
                },
            },
        ),
        ("paused", {"status": "paused", "message": "Paused by operator"}),
        ("stopped", {"status": "stopped", "message": "Confirmation declined"}),
    )
    rows: list[dict[str, Any]] = []

    for state_name, runtime_state in transitions:
        context = CanvasRuntimeContext(
            recipe_ids=HERO_RECIPE_IDS,
            target_ids=HERO_TARGET_IDS,
            runtime_state={"gaming_mode": runtime_state} if runtime_state else {},
            recent_runs=(),
            resolve_targets=False,
        )
        model, duration_ms = _measure_model(document, context)
        status = model.component_state("run_status")
        controller = model.component_state("run_controller")
        expected_status = runtime_state.get("status", "idle") if runtime_state else "idle"
        row = _evidence_row(
            f"state-transition:{state_name}",
            duration_ms,
            ADVISORY_STATE_UPDATE_BUDGET_MS,
            component_count=len(model.component_states),
            warnings=model.unresolved_binding_warnings,
            extra={
                "canvas_id": document.id,
                "status_state": status.state,
                "controller_enabled_actions": list(controller.enabled_actions),
                "runtime_state_build_ms": model.performance_counters["runtime_state_build_ms"],
                "worker_boundary": "runtime event state only; no UI-thread adapter work",
            },
        )
        rows.append(row)
        _warn_if_over_budget(row)

        assert status.state == expected_status
        assert row["side_effects"] == "none"

    record_property("state_transition_update_cost", _json_evidence(rows))


def test_mock_100_300_component_builds_record_advisory_evidence(record_property: Any) -> None:
    rows: list[dict[str, Any]] = []

    for count in (100, 300):
        document = create_mock_canvas(count)
        validation_started = perf_counter()
        validation = validate_canvas_structure(document)
        validation_duration_ms = _elapsed_ms(validation_started)
        model, runtime_duration_ms = _measure_model(
            document,
            CanvasRuntimeContext(
                recipe_ids=HERO_RECIPE_IDS,
                target_ids=HERO_TARGET_IDS,
                recent_runs=(),
                resolve_targets=False,
            ),
        )
        diagnostics = canvas_performance_diagnostics(document)
        row = _evidence_row(
            f"mock-components:{count}",
            runtime_duration_ms,
            ADVISORY_STRESS_BUILD_BUDGET_MS,
            component_count=len(model.component_states),
            warnings=[
                *validation.warnings,
                *model.unresolved_binding_warnings,
                *diagnostics["warnings"],
            ],
            extra={
                "canvas_id": document.id,
                "validation_duration_ms": round(validation_duration_ms, 3),
                "diagnostic_cost": diagnostics["estimated_cost"],
                "live_widgets": diagnostics["live_widgets"],
                "worker_boundary": "synthetic model path only; no adapters or desktop state",
            },
        )
        rows.append(row)
        _warn_if_over_budget(row)

        assert validation.errors == ()
        assert model.performance_counters["component_count"] == count
        assert row["side_effects"] == "none"

    record_property("mock_100_300_component_evidence", _json_evidence(rows))


def test_shortcut_heavy_room_records_advisory_evidence(tmp_path: Path, record_property: Any) -> None:
    folder = tmp_path / "project"
    folder.mkdir()
    app = tmp_path / "editor.exe"
    app.write_text("fake local executable placeholder", encoding="utf-8")
    document = _shortcut_heavy_room(folder=folder, app=app, count=120)

    model, duration_ms = _measure_model(document, CanvasRuntimeContext(recent_runs=()))
    diagnostics = canvas_performance_diagnostics(document)
    shortcut_states = [state for state in model.component_states if state.component_type.startswith("shortcut.")]
    row = _evidence_row(
        "shortcut-heavy-room:120",
        duration_ms,
        ADVISORY_STRESS_BUILD_BUDGET_MS,
        component_count=len(model.component_states),
        warnings=[*model.unresolved_binding_warnings, *diagnostics["warnings"]],
        extra={
            "shortcut_count": len(shortcut_states),
            "enabled_shortcut_actions": sorted(
                {action for state in shortcut_states for action in state.enabled_actions}
            ),
            "diagnostic_cost": diagnostics["estimated_cost"],
            "worker_boundary": "shortcuts modeled as single-step actions, not rituals or run logs",
        },
    )
    _warn_if_over_budget(row)
    record_property("shortcut_heavy_room_evidence", _json_evidence([row]))

    assert len(shortcut_states) == 120
    assert {state.component_type for state in shortcut_states} == {
        "shortcut.app",
        "shortcut.folder",
        "shortcut.url",
    }
    assert {action for state in shortcut_states for action in state.enabled_actions} == {"launch", "open"}
    assert not any("run" in state.enabled_actions for state in shortcut_states)
    assert row["side_effects"] == "none"


def test_recent_activity_20_records_records_advisory_evidence(record_property: Any) -> None:
    document = load_bundled_canvas("helpdesk_desktop")
    recent_runs = tuple(
        _run_record(f"support-run-{index:02d}", "support_triage_workspace", _status_for_index(index))
        for index in range(25)
    )

    model, duration_ms = _measure_model(
        document,
        CanvasRuntimeContext(
            recipe_ids=HERO_RECIPE_IDS,
            target_ids=HERO_TARGET_IDS,
            recent_runs=recent_runs,
            resolve_targets=False,
        ),
    )
    items = model.component_state("recent_runs").data["items"]
    row = _evidence_row(
        "recent-activity:20-records",
        duration_ms,
        ADVISORY_MODEL_BUILD_BUDGET_MS,
        component_count=len(model.component_states),
        warnings=model.unresolved_binding_warnings,
        extra={
            "source_records": len(recent_runs),
            "rendered_records": len(items),
            "first_run_id": items[0]["run_id"],
            "last_rendered_run_id": items[-1]["run_id"],
            "worker_boundary": "bounded recent activity input; no run-log scan in test",
        },
    )
    _warn_if_over_budget(row)
    record_property("recent_activity_20_record_evidence", _json_evidence([row]))

    assert len(items) == 20
    assert items[0]["run_id"] == "support-run-00"
    assert items[-1]["run_id"] == "support-run-19"
    assert model.performance_counters["recent_activity_count"] == 20
    assert row["side_effects"] == "none"


def _measure_model(
    document: CanvasDocument,
    context: CanvasRuntimeContext,
) -> tuple[Any, float]:
    started = perf_counter()
    model = build_canvas_runtime_model(document, context=context)
    return model, _elapsed_ms(started)


def _elapsed_ms(started: float) -> float:
    return max(0.0, (perf_counter() - started) * 1000)


def _evidence_row(
    label: str,
    duration_ms: float,
    advisory_budget_ms: float,
    *,
    component_count: int,
    warnings: tuple[str, ...] | list[str],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = {
        "schema_version": PERFORMANCE_EVIDENCE_SCHEMA,
        "label": label,
        "duration_ms": round(duration_ms, 3),
        "advisory_budget_ms": advisory_budget_ms,
        "over_advisory_budget": duration_ms > advisory_budget_ms,
        "component_count": component_count,
        "warnings": list(dict.fromkeys(str(warning) for warning in warnings if str(warning).strip())),
        "side_effects": "none",
    }
    row.update(extra or {})
    return row


def _warn_if_over_budget(row: dict[str, Any]) -> None:
    if row["over_advisory_budget"]:
        warnings.warn(
            f"{row['label']} exceeded advisory budget: "
            f"{row['duration_ms']} ms > {row['advisory_budget_ms']} ms",
            stacklevel=2,
        )


def _json_evidence(rows: list[dict[str, Any]]) -> str:
    return json.dumps(rows, sort_keys=True)


def _shortcut_heavy_room(*, folder: Path, app: Path, count: int) -> CanvasDocument:
    components: list[CanvasComponent] = []
    for index in range(count):
        kind = index % 3
        if kind == 0:
            components.append(
                CanvasComponent(
                    id=f"folder_{index:03d}",
                    type="shortcut.folder",
                    x=float((index % 10) * 160),
                    y=float((index // 10) * 96),
                    width=144,
                    height=72,
                    props={"title": f"Folder {index}", "path": str(folder)},
                    binding=CanvasComponentBinding(
                        kind=CanvasBindingKind.SHORTCUT_FOLDER,
                        path=str(folder),
                    ),
                )
            )
        elif kind == 1:
            components.append(
                CanvasComponent(
                    id=f"app_{index:03d}",
                    type="shortcut.app",
                    x=float((index % 10) * 160),
                    y=float((index // 10) * 96),
                    width=144,
                    height=72,
                    props={"title": f"App {index}", "path": str(app)},
                    binding=CanvasComponentBinding(
                        kind=CanvasBindingKind.SHORTCUT_APP,
                        path=str(app),
                    ),
                )
            )
        else:
            components.append(
                CanvasComponent(
                    id=f"url_{index:03d}",
                    type="shortcut.url",
                    x=float((index % 10) * 160),
                    y=float((index // 10) * 96),
                    width=144,
                    height=72,
                    props={"title": f"Docs {index}", "url": "https://example.com/docs"},
                    binding=CanvasComponentBinding(
                        kind=CanvasBindingKind.SHORTCUT_URL,
                        url="https://example.com/docs",
                    ),
                )
            )
    return CanvasDocument(
        id="shortcut_heavy_room",
        name="Shortcut Heavy Room",
        description="Test-only shortcut density model; not a promoted Room.",
        components=tuple(components),
    )


def _run_record(run_id: str, recipe_id: str, status: str) -> RunRecord:
    return RunRecord(
        run_id=run_id,
        path=Path("runs") / run_id,
        metadata={
            "recipe_id": recipe_id,
            "final_state": status,
            "final_message": f"{status} run",
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


def _status_for_index(index: int) -> str:
    return ("success", "stopped", "failed", "interrupted")[index % 4]
