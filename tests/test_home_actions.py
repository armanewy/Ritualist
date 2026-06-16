from __future__ import annotations

from types import SimpleNamespace

from ritualist.adapters.fake import FakeAdapters
from ritualist.config import AppConfig, UIConfig
from ritualist.home.actions import (
    HomeActionDispatcher,
    HomeActionService,
    HomeCardAction,
    home_event_from_runtime,
)
from ritualist.home.models import HomeCardStatus, HomeLastRunStatus
from ritualist.overlay import ActionPreview


class RecordingOverlay:
    def __init__(self) -> None:
        self.previews: list[ActionPreview] = []

    def show_preview(self, preview: ActionPreview, *, duration_ms: int) -> None:
        self.previews.append(preview)

    def start_wait(self, label: str):
        return SimpleNamespace(close=lambda: None)


def test_home_run_action_dispatches_to_runtime():
    calls: list[tuple[object, dict[str, object]]] = []

    def runtime_runner(recipe_ref, **kwargs):
        calls.append((recipe_ref, kwargs))
        return "started"

    dispatcher = HomeActionDispatcher(
        service=HomeActionService(runtime_runner=runtime_runner),
        recipe_refs={"card-1": "gaming_mode"},
    )

    outcome = dispatcher.dispatch(HomeCardAction.RUN, "card-1")

    assert outcome.action is HomeCardAction.RUN
    assert outcome.result == "started"
    assert calls[0][0] == "gaming_mode"
    assert calls[0][1]["dry_run"] is False


def test_home_dry_run_action_dispatches_safely():
    calls: list[tuple[object, bool]] = []

    def runtime_runner(recipe_ref, **kwargs):
        calls.append((recipe_ref, bool(kwargs["dry_run"])))
        return "dry-run"

    dispatcher = HomeActionDispatcher(
        service=HomeActionService(runtime_runner=runtime_runner),
    )

    outcome = dispatcher.dispatch("dry_run", "gaming_mode")

    assert outcome.action is HomeCardAction.DRY_RUN
    assert outcome.dry_run is True
    assert calls == [("gaming_mode", True)]


def test_home_runtime_service_uses_visual_overlay(monkeypatch, tmp_path):
    recipe_path = tmp_path / "focus.yaml"
    recipe_path.write_text(
        """
version: "0.1"
id: focus_recipe
name: Focus Recipe
steps:
  - name: Focus Battle.net
    action: window.focus
    title_contains: Battle.net
""".strip(),
        encoding="utf-8",
    )
    fakes = FakeAdapters()
    overlay = RecordingOverlay()
    monkeypatch.setattr("ritualist.adapters.create_default_adapters", lambda: fakes.bundle())
    monkeypatch.setattr("ritualist.run_logs.RunLogWriter", lambda: None)
    monkeypatch.setattr(
        "ritualist.config.load_app_config",
        lambda: AppConfig(ui=UIConfig(show_action_overlay=True)),
    )

    summary = HomeActionService(overlay_controller=overlay).run_recipe(
        recipe_path,
        dry_run=False,
    )

    assert summary.success
    assert overlay.previews
    assert overlay.previews[0].action == "window.focus"


def test_home_doctor_action_does_not_run_side_effect_runtime():
    runtime_calls: list[object] = []
    doctor_calls: list[object] = []

    def runtime_runner(recipe_ref, **_kwargs):
        runtime_calls.append(recipe_ref)

    def doctor_runner(recipe_ref):
        doctor_calls.append(recipe_ref)
        return SimpleNamespace(compatibility="compatible", errors_count=0, warnings_count=0)

    dispatcher = HomeActionDispatcher(
        service=HomeActionService(
            runtime_runner=runtime_runner,
            doctor_runner=doctor_runner,
        ),
    )

    outcome = dispatcher.dispatch(HomeCardAction.DOCTOR, "gaming_mode")

    assert runtime_calls == []
    assert doctor_calls == ["gaming_mode"]
    assert outcome.result.compatibility == "compatible"


def test_home_edit_recipe_action_resolves_recipe_path(tmp_path):
    recipe_path = tmp_path / "gaming_mode.yaml"
    dispatcher = HomeActionDispatcher(
        service=HomeActionService(recipe_path_resolver=lambda _ref: recipe_path),
    )

    outcome = dispatcher.dispatch(HomeCardAction.EDIT_RECIPE, "gaming_mode")

    assert outcome.path == recipe_path


def test_home_open_logs_action_resolves_runs_folder(tmp_path):
    runs_path = tmp_path / "runs"
    dispatcher = HomeActionDispatcher(
        service=HomeActionService(runs_path_resolver=lambda: runs_path),
    )

    outcome = dispatcher.dispatch(HomeCardAction.OPEN_LOGS, "gaming_mode")

    assert outcome.path == runs_path


def test_home_runtime_events_update_card_state():
    event = SimpleNamespace(type="run.finished", state="success", message="run completed")

    home_event = home_event_from_runtime("gaming_mode", event)

    assert home_event is not None
    assert home_event.card_id == "gaming_mode"
    assert home_event.status is HomeCardStatus.SUCCESS
    assert home_event.last_run_status is HomeLastRunStatus.SUCCESS
