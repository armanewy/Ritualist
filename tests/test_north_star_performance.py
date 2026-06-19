from __future__ import annotations

import json
from pathlib import Path
from statistics import median
from time import perf_counter
from typing import Any
import warnings

from setpiece.activity_collectors import (
    ActivityCollectionContext,
    FakeActivityCollector,
    collect_activity_signals,
)
from setpiece.activity_journal import ActivityJournal
from setpiece.activity_signals import (
    ActivityCollectionResult,
    ActivitySignal,
    journal_event_signal,
    process_name_signal,
    recent_reference_signal,
)
from setpiece.canvas import (
    CanvasRuntimeContext,
    build_canvas_runtime_model,
    load_bundled_canvas,
    validate_canvas_structure,
)
from setpiece.canvas.edit_ui import CanvasSuggestionsReviewBridge
from setpiece.learning_service import enable_learning
from setpiece.rooms import list_rooms
from setpiece.suggestions.miner import mine_suggestions
from setpiece.suggestions.models import Suggestion
from setpiece.suggestions.storage import SuggestionStore


PERFORMANCE_EVIDENCE_SCHEMA = "setpiece.north_star.performance_evidence.v1"
SIGNAL_COUNTS = (100, 1_000, 10_000)
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
ADVISORY_SIGNAL_COLLECTION_BUDGET_MS = 500.0
ADVISORY_SUGGESTION_MINING_BUDGET_MS = 2_500.0
ADVISORY_JOURNAL_WRITE_BUDGET_MS = 2_500.0
ADVISORY_JOURNAL_READ_BUDGET_MS = 250.0
ADVISORY_HERO_ROOM_BUDGET_MS = 100.0
ADVISORY_RUNTIME_UPDATE_P95_BUDGET_MS = 25.0
ADVISORY_SUGGESTION_UI_WORKER_BODY_BUDGET_MS = 500.0
BROAD_SANITY_LIMIT_MS = 30_000.0


def test_fake_activity_signal_scale_records_advisory_evidence(record_property: Any) -> None:
    rows: list[dict[str, Any]] = []

    for count in SIGNAL_COUNTS:
        signals = _fake_activity_signals(count)
        collector = FakeActivityCollector("north_star_fake", signals=signals)
        started = perf_counter()
        result = collect_activity_signals(
            (collector,),
            context=ActivityCollectionContext(max_signals=count),
        )
        duration_ms = _elapsed_ms(started)
        row = _evidence_row(
            f"fake-activity-signals:{count}",
            duration_ms,
            ADVISORY_SIGNAL_COLLECTION_BUDGET_MS,
            extra={
                "signal_count": count,
                "collected_signal_count": len(result.signals),
                "collector_count": collector.collect_count,
                "warning_codes": [warning.code for warning in result.warnings],
                "worker_boundary": "fake collectors only; no Windows desktop session, hooks, OCR, browser history, or capture",
            },
        )
        rows.append(row)
        _warn_if_over_budget(row)

        assert collector.collect_count == 1
        assert len(result.signals) == count
        assert result.warnings == ()
        _assert_broad_sanity(row)

    record_property("north_star_fake_activity_signal_scale", _json_evidence(rows))


def test_suggestion_mining_10000_signals_records_advisory_evidence(record_property: Any) -> None:
    signals = _fake_activity_signals(10_000)

    started = perf_counter()
    suggestions = mine_suggestions(
        ActivityCollectionResult(signals=signals),
        max_suggestions=20,
    )
    duration_ms = _elapsed_ms(started)
    serialized = [suggestion.to_dict() for suggestion in suggestions]
    row = _evidence_row(
        "suggestion-mining:10000-signals",
        duration_ms,
        ADVISORY_SUGGESTION_MINING_BUDGET_MS,
        extra={
            "signal_count": len(signals),
            "suggestion_count": len(suggestions),
            "suggestion_kinds": sorted({item["kind"] for item in serialized}),
            "review_only": True,
            "worker_boundary": "pure miner over already-consented fake local signals",
        },
    )
    _warn_if_over_budget(row)
    record_property("north_star_suggestion_mining", _json_evidence([row]))

    assert suggestions
    assert all(action.get("action", "").startswith("review_") for item in serialized for action in item["proposed_actions"])
    assert all(item["status"] == "new" for item in serialized)
    assert all("created_artifact" not in item for item in serialized)
    assert all("ran" not in item for item in serialized)
    assert _forbidden_markers_absent(serialized)
    _assert_broad_sanity(row)


def test_journal_read_write_records_advisory_evidence(tmp_path: Path, record_property: Any) -> None:
    path = tmp_path / "activity-journal.jsonl"
    journal = ActivityJournal(path=path, enabled=True)
    write_count = 1_000

    started = perf_counter()
    for index in range(write_count):
        assert journal.write(
            "recipe_run_finished",
            room_id=HERO_ROOM_IDS[index % len(HERO_ROOM_IDS)],
            recipe_id=f"north_star_recipe_{index % 8}",
            status="success",
            component_id=f"component_{index % 16}",
        )
    write_duration_ms = _elapsed_ms(started)

    started = perf_counter()
    events = journal.read(limit=write_count)
    read_duration_ms = _elapsed_ms(started)
    rows = [
        _evidence_row(
            "journal-write:1000-events",
            write_duration_ms,
            ADVISORY_JOURNAL_WRITE_BUDGET_MS,
            extra={
                "event_count": write_count,
                "path": str(path),
                "side_effect_scope": "pytest tmp_path only",
            },
        ),
        _evidence_row(
            "journal-read:bounded-events",
            read_duration_ms,
            ADVISORY_JOURNAL_READ_BUDGET_MS,
            extra={
                "requested_limit": write_count,
                "returned_count": len(events),
                "bounded_reader": True,
                "side_effect_scope": "pytest tmp_path only",
            },
        ),
    ]
    for row in rows:
        _warn_if_over_budget(row)
        _assert_broad_sanity(row)
    record_property("north_star_journal_read_write", _json_evidence(rows))

    assert len(events) == 500
    assert events[-1].payload["recipe_id"] == "north_star_recipe_7"
    assert _forbidden_markers_absent([event.payload for event in events])


def test_three_hero_rooms_record_advisory_evidence(record_property: Any) -> None:
    rooms = list_rooms()
    rows: list[dict[str, Any]] = []

    assert tuple(room.room_id for room in rooms) == HERO_ROOM_IDS
    assert tuple(room.canvas_id for room in rooms) == HERO_CANVAS_IDS

    for room in rooms:
        document = load_bundled_canvas(room.canvas_id)
        validation = validate_canvas_structure(document)
        started = perf_counter()
        model = build_canvas_runtime_model(
            document,
            context=CanvasRuntimeContext(
                recipe_ids=HERO_RECIPE_IDS,
                target_ids=HERO_TARGET_IDS,
                recent_runs=(),
                resolve_targets=False,
            ),
        )
        duration_ms = _elapsed_ms(started)
        row = _evidence_row(
            f"hero-room:{room.room_id}",
            duration_ms,
            ADVISORY_HERO_ROOM_BUDGET_MS,
            extra={
                "room_id": room.room_id,
                "canvas_id": room.canvas_id,
                "component_count": len(document.components),
                "runtime_component_count": len(model.component_states),
                "validation_warning_count": len(validation.warnings),
                "unresolved_binding_warning_count": len(model.unresolved_binding_warnings),
                "worker_boundary": "model-only; no adapters, run-log scan, capture, or desktop automation",
            },
        )
        rows.append(row)
        _warn_if_over_budget(row)

        assert validation.errors == ()
        assert model.canvas_id == document.id
        _assert_broad_sanity(row)

    record_property("north_star_three_hero_rooms", _json_evidence(rows))


def test_repeated_runtime_state_updates_record_advisory_evidence(record_property: Any) -> None:
    document = load_bundled_canvas("gaming_desktop")
    durations: list[float] = []
    model = None

    for index in range(300):
        state = _runtime_state_for_index(index)
        started = perf_counter()
        model = build_canvas_runtime_model(
            document,
            context=CanvasRuntimeContext(
                recipe_ids=HERO_RECIPE_IDS,
                target_ids=HERO_TARGET_IDS,
                runtime_state={"gaming_mode": state},
                recent_runs=(),
                resolve_targets=False,
            ),
        )
        durations.append(_elapsed_ms(started))

    p95 = _percentile(durations, 95)
    row = _evidence_row(
        "runtime-state-updates:300",
        sum(durations),
        ADVISORY_RUNTIME_UPDATE_P95_BUDGET_MS * len(durations),
        extra={
            "update_count": len(durations),
            "median_ms": round(median(durations), 3),
            "p95_ms": round(p95, 3),
            "max_ms": round(max(durations), 3),
            "advisory_p95_budget_ms": ADVISORY_RUNTIME_UPDATE_P95_BUDGET_MS,
            "over_advisory_p95_budget": p95 > ADVISORY_RUNTIME_UPDATE_P95_BUDGET_MS,
            "worker_boundary": "runtime-state payload rebuild only; adapter execution remains outside UI path",
        },
    )
    if row["over_advisory_p95_budget"]:
        warnings.warn(
            f"{row['label']} exceeded advisory p95 budget: "
            f"{row['p95_ms']} ms > {row['advisory_p95_budget_ms']} ms",
            stacklevel=2,
        )
    record_property("north_star_repeated_runtime_state_updates", _json_evidence([row]))

    assert model is not None
    assert model.component_state("run_status").state == _runtime_state_for_index(299)["status"]
    _assert_broad_sanity(row)


def test_suggestion_ui_worker_path_records_advisory_evidence(
    tmp_path: Path,
    monkeypatch: Any,
    record_property: Any,
) -> None:
    config_path = tmp_path / "config.yaml"
    store = SuggestionStore(path=tmp_path / "suggestions.jsonl")
    enable_learning(("setpiece_journal",), config_path=config_path)
    bridge = CanvasSuggestionsReviewBridge(store=store, config_path=config_path)

    def fake_scan_suggestions_payload(**kwargs: Any) -> dict[str, object]:
        target_store = kwargs["store"]
        suggestions = tuple(_shortcut_suggestion(index) for index in range(20))
        target_store.save_many(suggestions)
        return {
            "schema_version": "setpiece.suggestions.scan.v1",
            "suggestion_count": len(suggestions),
            "persisted_count": len(suggestions),
            "suggestions": [suggestion.to_dict() for suggestion in suggestions],
        }

    monkeypatch.setattr("setpiece.canvas.edit_ui.scan_suggestions_payload", fake_scan_suggestions_payload)

    started = perf_counter()
    model = bridge.find_suggestions()
    duration_ms = _elapsed_ms(started)
    source = Path("setpiece/canvas/app.py").read_text(encoding="utf-8")
    worker_markers = (
        "future = self._ensure_executor().submit(self._suggestions_bridge.find_suggestions)",
        "future.add_done_callback(self._complete_suggestions_future)",
        "self.suggestionsOperationCompleted.connect(self._complete_suggestions_operation)",
        "self._suggestions_busy = True",
        "self._suggestions_busy = False",
    )
    row = _evidence_row(
        "suggestion-ui-worker-body:20",
        duration_ms,
        ADVISORY_SUGGESTION_UI_WORKER_BODY_BUDGET_MS,
        extra={
            "suggestion_count": model["count"],
            "worker_markers_present": all(marker in source for marker in worker_markers),
            "thread_name_prefix_present": 'thread_name_prefix="setpiece-canvas-use"' in source,
            "review_required": model["review_required"],
            "auto_create": model["auto_create"],
            "auto_run": model["auto_run"],
            "worker_boundary": "Canvas UI source routes Find Suggestions through ThreadPoolExecutor",
        },
    )
    _warn_if_over_budget(row)
    record_property("north_star_suggestion_ui_worker_path", _json_evidence([row]))

    assert model["count"] == 20
    assert model["last_message"] == "Found 20 Suggestions; nothing was created or run."
    assert model["review_required"] is True
    assert model["auto_create"] is False
    assert model["auto_run"] is False
    assert all(marker in source for marker in worker_markers)
    assert "PySide6" not in "\n".join(source.splitlines()[:40])
    _assert_broad_sanity(row)


def _fake_activity_signals(count: int) -> tuple[ActivitySignal, ...]:
    signals: list[ActivitySignal] = []
    rooms = HERO_ROOM_IDS
    for index in range(count):
        bucket = index % 5
        if bucket == 0:
            signals.append(
                journal_event_signal(
                    label="support_shift",
                    value="recipe_run_finished",
                    metadata={
                        "event_type": "recipe_run_finished",
                        "recipe_id": "support_shift",
                        "shortcut_id": "ticket_queue",
                        "room_id": "support_desk",
                        "context_id": f"context_{index // 5}",
                    },
                )
            )
        elif bucket == 1:
            signals.append(
                recent_reference_signal(
                    reference_type="folder",
                    label="Project Workspace",
                    target="Project Workspace",
                )
            )
        elif bucket == 2:
            signals.append(process_name_signal("Code.exe"))
        elif bucket == 3:
            room_id = rooms[index % len(rooms)]
            signals.append(
                journal_event_signal(
                    label=room_id,
                    value="room_opened",
                    metadata={
                        "event_type": "room_opened",
                        "room_id": room_id,
                        "app_label": "Code",
                        "folder_label": "Project Workspace",
                        "context_id": f"room_{index // 5}",
                    },
                )
            )
        else:
            signals.append(
                journal_event_signal(
                    label="ticket_queue",
                    value="shortcut_opened",
                    metadata={
                        "event_type": "shortcut_opened",
                        "shortcut_id": "ticket_queue",
                        "app_label": "Code",
                        "context_id": f"context_{index // 5}",
                    },
                )
            )
    return tuple(signals)


def _runtime_state_for_index(index: int) -> dict[str, object]:
    status = ("running", "waiting", "confirming", "paused", "stopped")[index % 5]
    state: dict[str, object] = {
        "status": status,
        "message": f"Advisory state {index}",
        "current_step": f"Step {index % 7}",
    }
    if status == "confirming":
        state["confirmation"] = {
            "required": True,
            "target": "Launch",
            "target_type": "text",
        }
    return state


def _shortcut_suggestion(index: int) -> Suggestion:
    return Suggestion.create(
        kind="shortcut_component",
        title=f"Project shortcut {index:02d}",
        description="Review a local shortcut component draft.",
        confidence=0.82,
        evidence_summary="Repeated local shortcut use",
        evidence_count=4,
        sources=("setpiece_journal",),
        proposed_actions=(
            {
                "action": "review_shortcut_component",
                "kind": "shortcut.folder",
                "component_type": "shortcut.folder",
                "label": f"Project Folder {index:02d}",
            },
        ),
        missing_inputs=("folder_path",),
    )


def _elapsed_ms(started: float) -> float:
    return max(0.0, (perf_counter() - started) * 1000)


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((percentile / 100) * (len(ordered) - 1))))
    return ordered[index]


def _evidence_row(
    label: str,
    duration_ms: float,
    advisory_budget_ms: float,
    *,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = {
        "schema_version": PERFORMANCE_EVIDENCE_SCHEMA,
        "label": label,
        "duration_ms": round(duration_ms, 3),
        "advisory_budget_ms": advisory_budget_ms,
        "over_advisory_budget": duration_ms > advisory_budget_ms,
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


def _assert_broad_sanity(row: dict[str, Any]) -> None:
    assert row["duration_ms"] < BROAD_SANITY_LIMIT_MS


def _json_evidence(rows: list[dict[str, Any]]) -> str:
    return json.dumps(rows, sort_keys=True)


def _forbidden_markers_absent(payload: object) -> bool:
    forbidden = (
        "watch_me",
        "recording",
        "ocr",
        "browser_history",
        "coordinate",
        "python",
        "javascript",
        "cloud",
        "remote",
        "marketplace",
        "password",
        "gameplay",
        "taskbar",
        "kiosk",
        "click-through",
    )
    text = json.dumps(payload, sort_keys=True).casefold()
    return all(marker not in text for marker in forbidden)
