from __future__ import annotations

import json
from concurrent.futures import Future
from types import SimpleNamespace
from typing import Any

from setpiece.canvas import (
    CanvasComponent,
    CanvasComponentActionResult,
    CanvasDocument,
    resolve_canvas_host_config,
)
from setpiece.canvas.app import (
    _record_canvas_component_clicked,
    _record_canvas_room_opened,
    _record_canvas_shortcut_opened,
)
from setpiece.home.actions import (
    ActivityJournalHook,
    HomeActionDispatcher,
    HomeActionService,
    HomeCardAction,
    create_activity_journal_hook,
)
from setpiece.learning_config import LearningConsentRecord, LocalLearningConfig


class _FakeJournal:
    def __init__(self, *, enabled: bool = True, fail: bool = False) -> None:
        self._enabled = enabled
        self.fail = fail
        self.events: list[tuple[str, dict[str, Any]]] = []

    @property
    def enabled(self) -> bool:
        return self._enabled

    def write(self, event_type: str, **payload: Any) -> bool:
        if self.fail:
            raise OSError("journal unavailable")
        self.events.append((event_type, payload))
        return True


class _ImmediateExecutor:
    def submit(self, fn: Any, *args: Any, **kwargs: Any) -> Future[Any]:
        future: Future[Any] = Future()
        try:
            future.set_result(fn(*args, **kwargs))
        except Exception as exc:  # noqa: BLE001 - tests assert hook nonfatal behavior.
            future.set_exception(exc)
        return future


class _CapturingExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, tuple[Any, ...], dict[str, Any]]] = []

    def submit(self, fn: Any, *args: Any, **kwargs: Any) -> object:
        self.calls.append((fn, args, kwargs))
        return object()


def _enabled_learning() -> LocalLearningConfig:
    return LocalLearningConfig(
        enabled=True,
        source_ids=("setpiece_journal",),
        consent=LearningConsentRecord(
            timestamp="2026-06-17T12:00:00+00:00",
            source_ids=("setpiece_journal",),
        ),
    )


def _event_payloads(journal: _FakeJournal) -> list[dict[str, Any]]:
    return [payload for _event_type, payload in journal.events]


def test_create_activity_journal_hook_respects_local_learning_config(tmp_path) -> None:
    disabled_path = tmp_path / "disabled.jsonl"
    disabled = create_activity_journal_hook(LocalLearningConfig(), journal_path=disabled_path)

    assert disabled.record("room_opened", room_id="gaming") is False
    disabled.flush()

    assert not disabled_path.exists()

    enabled_path = tmp_path / "enabled.jsonl"
    enabled = create_activity_journal_hook(_enabled_learning(), journal_path=enabled_path)

    assert enabled.record("room_opened", room_id="gaming") is True
    enabled.flush()
    enabled.shutdown(wait=False)

    rows = [json.loads(line) for line in enabled_path.read_text(encoding="utf-8").splitlines()]
    assert [row["event_type"] for row in rows] == ["room_opened"]
    assert rows[0]["payload"]["room_id"] == "gaming"


def test_production_activity_journal_hook_rechecks_learning_config(
    monkeypatch,
    tmp_path,
) -> None:
    enabled = False

    def fake_config() -> LocalLearningConfig:
        return _enabled_learning() if enabled else LocalLearningConfig()

    monkeypatch.setattr("setpiece.home.actions._load_local_learning_config", fake_config)
    path = tmp_path / "activity.jsonl"
    hook = create_activity_journal_hook(journal_path=path)

    assert hook.record("room_opened", room_id="project") is False
    enabled = True
    assert hook.record("room_opened", room_id="project") is True
    hook.flush()
    enabled = False
    assert hook.record("room_opened", room_id="project") is False
    hook.shutdown(wait=False)

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [row["event_type"] for row in rows] == ["room_opened"]


def test_activity_journal_hook_submits_write_without_blocking_caller() -> None:
    journal = _FakeJournal(enabled=True)
    executor = _CapturingExecutor()
    hook = ActivityJournalHook(journal=journal, executor=executor)

    assert hook.record("component_clicked", component_id="card", action_id="run") is True

    assert journal.events == []
    assert len(executor.calls) == 1

    fn, args, kwargs = executor.calls[0]
    assert kwargs == {}
    assert fn(*args) is True
    assert journal.events == [
        (
            "component_clicked",
            {"component_id": "card", "action_id": "run"},
        )
    ]


def test_activity_journal_hook_is_nonfatal_and_dedupes_exact_events() -> None:
    failing = _FakeJournal(enabled=True, fail=True)
    failing_hook = ActivityJournalHook(journal=failing, executor=_ImmediateExecutor())

    assert failing_hook.record("component_clicked", component_id="card") is True
    failing_hook.flush()

    journal = _FakeJournal(enabled=True)
    hook = ActivityJournalHook(journal=journal, executor=_ImmediateExecutor())

    assert hook.record("component_clicked", component_id="card", action_id="run") is True
    assert hook.record("component_clicked", component_id="card", action_id="run") is False
    hook.flush()

    assert [event_type for event_type, _payload in journal.events] == ["component_clicked"]


def test_home_actions_record_recipe_events_without_confirmation_payload() -> None:
    journal = _FakeJournal(enabled=True)
    hook = ActivityJournalHook(
        journal=journal,
        executor=_ImmediateExecutor(),
        dedupe_seconds=0,
    )

    def runtime_runner(recipe_ref: object, **kwargs: Any) -> str:
        callback = kwargs["runtime_event_callback"]
        callback(
            SimpleNamespace(
                type="run.started",
                recipe_id=str(recipe_ref),
                recipe_name="Gaming Mode",
                run_id="run-1",
                dry_run=kwargs["dry_run"],
                steps_total=2,
            )
        )
        callback(
            SimpleNamespace(
                type="confirmation.requested",
                prompt="secret confirmation text",
                run_id="run-1",
            )
        )
        callback(
            SimpleNamespace(
                type="run.finished",
                state="success",
                success=True,
                run_id="run-1",
                duration_seconds=1.25,
                message="secret confirmation text",
            )
        )
        return "ok"

    dispatcher = HomeActionDispatcher(
        service=HomeActionService(
            runtime_runner=runtime_runner,
            doctor_runner=lambda recipe_ref: {"recipe_ref": recipe_ref},
            journal_hook=hook,
        ),
        recipe_refs={"card": "gaming_mode"},
    )

    dispatcher.dispatch(HomeCardAction.DRY_RUN, "card")
    dispatcher.dispatch(HomeCardAction.DOCTOR, "card")
    hook.flush()

    assert [event_type for event_type, _payload in journal.events] == [
        "component_clicked",
        "recipe_dry_run",
        "recipe_run_started",
        "recipe_run_finished",
        "component_clicked",
        "recipe_doctor_run",
    ]
    assert "secret confirmation text" not in repr(_event_payloads(journal))
    assert not any("prompt" in payload for payload in _event_payloads(journal))


def test_canvas_helpers_record_room_component_and_shortcut_events_without_targets() -> None:
    journal = _FakeJournal(enabled=True)
    hook = ActivityJournalHook(
        journal=journal,
        executor=_ImmediateExecutor(),
        dedupe_seconds=0,
    )
    document = CanvasDocument(
        id="gaming_desktop",
        name="Gaming Room",
        components=(
            CanvasComponent(
                id="card",
                type="ritual.card",
                width=320,
                height=180,
                props={"recipe_id": "gaming_mode"},
            ),
            CanvasComponent(
                id="docs",
                type="shortcut.url",
                width=240,
                height=96,
                props={"url": "https://example.com/private?token=secret"},
            ),
        ),
    )

    assert _record_canvas_room_opened(
        hook,
        document,
        host_config=resolve_canvas_host_config("windowed"),
        mock=False,
    )
    assert _record_canvas_component_clicked(hook, document, "card", "run")
    assert _record_canvas_component_clicked(hook, document, "docs", "open")
    assert _record_canvas_shortcut_opened(
        hook,
        document,
        "docs",
        CanvasComponentActionResult(
            "docs",
            "open",
            "success",
            data={"shortcut": {"kind": "url", "target_label": "example.com"}},
        ),
    )
    assert not _record_canvas_shortcut_opened(
        hook,
        document,
        "docs",
        CanvasComponentActionResult(
            "docs",
            "open",
            "needs_setup",
            data={"shortcut": {"kind": "url", "target_label": "example.com"}},
        ),
    )
    hook.flush()

    assert [event_type for event_type, _payload in journal.events] == [
        "room_opened",
        "component_clicked",
        "component_clicked",
        "shortcut_opened",
    ]
    payloads = _event_payloads(journal)
    assert payloads[0]["room_id"] == "gaming"
    assert payloads[1]["recipe_id"] == "gaming_mode"
    assert "url" not in payloads[2]
    assert "https://example.com/private?token=secret" not in repr(payloads)
