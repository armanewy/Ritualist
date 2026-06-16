from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from ritualist.doctor import DoctorCheck
from ritualist.models import Recipe
from ritualist.ui import main_window
from ritualist.ui.diagnostics_dialog import DiagnosticsDialog
from ritualist.ui.runner_thread import RunnerThread


def test_main_window_has_personal_app_controls_and_loads_selected_recipe(tmp_path, monkeypatch):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    recipe_path = tmp_path / "gaming_mode.yaml"
    recipe = Recipe.model_validate(
        {
            "id": "gaming_mode",
            "name": "Gaming Mode",
            "steps": [{"action": "app.launch", "command": "demo.exe"}],
        }
    )
    monkeypatch.setattr(main_window, "reconcile_running_runs", lambda: [])
    monkeypatch.setattr(main_window, "discover_recipes", lambda: [(recipe_path, recipe, None)])
    monkeypatch.setattr(main_window, "load_recipe", lambda path: recipe)

    window = main_window.MainWindow()

    assert app is not None
    assert window.init_button.text() == "Initialize App"
    assert window.refresh_button.text() == "Refresh Recipes"
    assert window.run_button.text() == "Run"
    assert window.dry_run_button.text() == "Dry Run"
    assert window.doctor_button.text() == "Doctor"
    assert window.add_step_button.text() == "Add Step"
    assert window.pause_button.text() == "Pause"
    assert window.resume_button.text() == "Resume"
    assert window.stop_button.text() == "Stop"
    assert window.pause_button.isEnabled() is False
    assert window.resume_button.isEnabled() is False
    assert window.run_state_label.text() == "Run state: stopped"
    assert window.waiting_label.text() == "Waiting: inactive"
    assert window.keep_open_label.text() == "Keep-open: inactive"
    assert window.recipe is recipe
    assert window.path_edit.text() == str(recipe_path)
    assert window.status_label.text() == "Loaded gaming_mode"

    window.close()


def test_main_window_add_step_uses_append_controller_without_running_recipe(tmp_path, monkeypatch):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    recipe_path = tmp_path / "gaming_mode.yaml"
    recipe = Recipe.model_validate(
        {
            "id": "gaming_mode",
            "name": "Gaming Mode",
            "steps": [{"action": "wait.seconds", "seconds": 1.0}],
        }
    )
    updated_recipe = Recipe.model_validate(
        {
            "id": "gaming_mode",
            "name": "Gaming Mode",
            "steps": [
                {"action": "wait.seconds", "seconds": 1.0},
                {"action": "wait.for_user", "prompt": "Ready?"},
            ],
        }
    )
    appended = {}

    class FakeDialog:
        step_data = {"action": "wait.for_user", "prompt": "Ready?"}
        variable_updates = {}

        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def exec(self):
            return main_window.QDialog.DialogCode.Accepted

    class FakeAppendController:
        def append_step(self, path, step_data, *, variable_updates=None):
            appended["path"] = path
            appended["step_data"] = step_data
            appended["variable_updates"] = variable_updates
            return updated_recipe

    monkeypatch.setattr(main_window, "reconcile_running_runs", lambda: [])
    monkeypatch.setattr(main_window, "discover_recipes", lambda: [(recipe_path, recipe, None)])
    monkeypatch.setattr(main_window, "load_recipe", lambda path: recipe)
    monkeypatch.setattr(main_window, "AddStepDialog", FakeDialog)

    window = main_window.MainWindow()
    window.step_append_controller = FakeAppendController()
    window.add_step()

    assert app is not None
    assert appended == {
        "path": recipe_path,
        "step_data": {"action": "wait.for_user", "prompt": "Ready?"},
        "variable_updates": {},
    }
    assert window.recipe is updated_recipe
    assert window.steps_table.rowCount() == 2

    window.close()


def test_main_window_doctor_prints_checks_without_running_recipe(tmp_path, monkeypatch):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    recipe_path = tmp_path / "gaming_mode.yaml"
    recipe = Recipe.model_validate(
        {
            "id": "gaming_mode",
            "name": "Gaming Mode",
            "steps": [{"action": "app.launch", "command": "demo.exe"}],
        }
    )
    monkeypatch.setattr(main_window, "reconcile_running_runs", lambda: [])
    monkeypatch.setattr(main_window, "discover_recipes", lambda: [(recipe_path, recipe, None)])
    monkeypatch.setattr(main_window, "load_recipe", lambda path: recipe)
    monkeypatch.setattr(
        main_window,
        "diagnose_recipe",
        lambda loaded: [DoctorCheck("ok", "recipe", f"loaded {loaded.id}")],
    )

    window = main_window.MainWindow()
    window.doctor_recipe()

    assert app is not None
    assert "Doctor: Gaming Mode (gaming_mode)" in window.log.toPlainText()
    assert "ok: recipe - loaded gaming_mode" in window.log.toPlainText()

    window.close()


def test_main_window_shows_waiting_details_and_keeps_run_controls(tmp_path, monkeypatch):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    recipe_path = tmp_path / "gaming_mode.yaml"
    recipe = Recipe.model_validate(
        {
            "id": "gaming_mode",
            "name": "Gaming Mode",
            "steps": [
                {
                    "action": "wait.for_window",
                    "title_contains": "Battle.net",
                    "timeout_seconds": 30,
                }
            ],
        }
    )
    monkeypatch.setattr(main_window, "reconcile_running_runs", lambda: [])
    monkeypatch.setattr(main_window, "discover_recipes", lambda: [(recipe_path, recipe, None)])
    monkeypatch.setattr(main_window, "load_recipe", lambda path: recipe)

    window = main_window.MainWindow()
    window.on_run_state_changed("waiting")
    window.on_step_event(
        SimpleNamespace(
            index=1,
            action="wait.for_window",
            status="running",
            wait_action="wait.for_window",
            wait_target="window Battle.net",
            wait_elapsed_seconds=4,
            wait_timeout_seconds=30,
            keep_open_active=False,
        )
    )

    assert app is not None
    assert window.stop_button.isEnabled() is True
    assert window.pause_button.isEnabled() is True
    assert window.resume_button.isEnabled() is False
    assert "Waiting: wait.for_window" in window.waiting_label.text()
    assert "Target: window Battle.net" in window.waiting_label.text()
    assert "Elapsed: 4s" in window.waiting_label.text()
    assert "Timeout: 30s" in window.waiting_label.text()

    window.on_step_event(SimpleNamespace(index=1, action="wait.for_window", status="success"))

    assert window.waiting_label.text() == "Waiting: inactive"

    window.close()


def test_main_window_marks_keep_open_active_on_reached_browser_step(tmp_path, monkeypatch):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    recipe_path = tmp_path / "gaming_mode.yaml"
    recipe = Recipe.model_validate(
        {
            "id": "gaming_mode",
            "name": "Gaming Mode",
            "steps": [
                {
                    "action": "browser.open",
                    "url": "https://example.test",
                    "keep_open": True,
                }
            ],
        }
    )
    monkeypatch.setattr(main_window, "reconcile_running_runs", lambda: [])
    monkeypatch.setattr(main_window, "discover_recipes", lambda: [(recipe_path, recipe, None)])
    monkeypatch.setattr(main_window, "load_recipe", lambda path: recipe)

    window = main_window.MainWindow()
    window.on_step_event(SimpleNamespace(index=1, action="browser.open", status="success"))

    assert app is not None
    assert window.keep_open_label.text() == "Keep-open: active"

    window.close()


def test_main_window_starts_when_overlay_controller_fails(monkeypatch):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    class BrokenOverlay:
        def __init__(self) -> None:
            raise RuntimeError("overlay unavailable")

    monkeypatch.setattr(main_window, "reconcile_running_runs", lambda: [])
    monkeypatch.setattr(main_window, "discover_recipes", lambda: [])
    monkeypatch.setattr(main_window, "QtOverlayController", BrokenOverlay)

    window = main_window.MainWindow()

    assert app is not None
    assert "Action overlay unavailable: overlay unavailable" in window.log.toPlainText()

    window.close()


class _FakeCloseEvent:
    def __init__(self) -> None:
        self.accepted = False
        self.ignored = False

    def accept(self) -> None:
        self.accepted = True

    def ignore(self) -> None:
        self.ignored = True


class _FakeRunner:
    def __init__(self) -> None:
        self.requested = False
        self.answered = None
        self.stopped = False

    def isRunning(self) -> bool:
        return True

    def stop(self) -> None:
        self.stopped = True
        self.requestInterruption()
        self.answer_confirmation(False)

    def requestInterruption(self) -> None:
        self.requested = True

    def answer_confirmation(self, accepted: bool) -> None:
        self.answered = accepted


def test_close_event_stop_and_exit_requests_cancellation(tmp_path, monkeypatch):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    monkeypatch.setattr(main_window, "reconcile_running_runs", lambda: [])
    monkeypatch.setattr(main_window, "discover_recipes", lambda: [])
    window = main_window.MainWindow()
    runner = _FakeRunner()
    window.runner = runner
    monkeypatch.setattr(window, "confirm_close_while_running", lambda: "stop")
    event = _FakeCloseEvent()

    window.closeEvent(event)

    assert app is not None
    assert event.ignored is True
    assert event.accepted is False
    assert runner.stopped is True
    assert runner.requested is True
    assert runner.answered is False
    assert window._close_after_run_stops is True

    window.runner = None
    window.close()


def test_close_event_exit_anyway_accepts_without_stopping(tmp_path, monkeypatch):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    monkeypatch.setattr(main_window, "reconcile_running_runs", lambda: [])
    monkeypatch.setattr(main_window, "discover_recipes", lambda: [])
    window = main_window.MainWindow()
    runner = _FakeRunner()
    window.runner = runner
    monkeypatch.setattr(window, "confirm_close_while_running", lambda: "exit")
    event = _FakeCloseEvent()

    window.closeEvent(event)

    assert app is not None
    assert event.accepted is True
    assert event.ignored is False
    assert runner.requested is False

    window.runner = None
    window.close()


class _SpyRuntimeControl:
    def __init__(self) -> None:
        self.pause_calls = 0
        self.resume_calls = 0
        self.stop_calls = 0

    def pause(self) -> None:
        self.pause_calls += 1

    def resume(self) -> None:
        self.resume_calls += 1

    def stop(self) -> None:
        self.stop_calls += 1


def test_runner_pause_calls_runtime_control_pause():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    control = _SpyRuntimeControl()
    runner = RunnerThread(SimpleNamespace(), None, control)

    runner.pause()

    assert app is not None
    assert control.pause_calls == 1


def test_runner_resume_calls_runtime_control_resume():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    control = _SpyRuntimeControl()
    runner = RunnerThread(SimpleNamespace(), None, control)

    runner.resume()

    assert app is not None
    assert control.resume_calls == 1


def test_runner_stop_calls_runtime_control_stop():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    control = _SpyRuntimeControl()
    runner = RunnerThread(SimpleNamespace(), None, control)

    runner.stop()

    assert app is not None
    assert control.stop_calls == 1


def test_runner_treats_wait_actions_as_waiting_state():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    runner = RunnerThread(SimpleNamespace(), None, _SpyRuntimeControl())

    state = runner._run_state_for_event(
        SimpleNamespace(status="running", action="wait.seconds")
    )

    assert app is not None
    assert state == "waiting"


class _FakeSignal:
    def connect(self, _callback) -> None:
        pass


class _FakeRunnerThread:
    def __init__(self, executor, recipe, control) -> None:
        self.executor = executor
        self.recipe = recipe
        self.control = control
        self.log_message = _FakeSignal()
        self.step_event = _FakeSignal()
        self.run_state_changed = _FakeSignal()
        self.stopped = _FakeSignal()
        self.failed = _FakeSignal()
        self.finished_result = _FakeSignal()
        self.confirmation_requested = _FakeSignal()
        self.started = False

    def start(self) -> None:
        self.started = True


def test_gui_run_passes_same_runtime_control_to_executor_and_runner(tmp_path, monkeypatch):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    recipe_path = tmp_path / "gaming_mode.yaml"
    recipe = Recipe.model_validate(
        {
            "id": "gaming_mode",
            "name": "Gaming Mode",
            "steps": [{"action": "wait.seconds", "seconds": 0.01}],
        }
    )
    captured = {}

    class CapturingRuntimeControl:
        def is_stopping(self) -> bool:
            return False

    class CapturingExecutor:
        def __init__(self, **kwargs) -> None:
            captured["executor_kwargs"] = kwargs

    monkeypatch.setattr(main_window, "reconcile_running_runs", lambda: [])
    monkeypatch.setattr(main_window, "discover_recipes", lambda: [(recipe_path, recipe, None)])
    monkeypatch.setattr(main_window, "load_recipe", lambda path: recipe)
    monkeypatch.setattr(main_window, "create_default_adapters", lambda: object())
    monkeypatch.setattr(main_window, "setup_logging", lambda: object())
    monkeypatch.setattr(main_window, "load_app_config", lambda: object())
    monkeypatch.setattr(main_window, "RuntimeControl", CapturingRuntimeControl)
    monkeypatch.setattr(main_window, "WorkflowExecutor", CapturingExecutor)
    monkeypatch.setattr(main_window, "RunnerThread", _FakeRunnerThread)

    window = main_window.MainWindow()
    window.run_recipe(dry_run=False)

    assert app is not None
    assert window.runner is not None
    assert captured["executor_kwargs"]["runtime_control"] is window.runner.control
    assert captured["executor_kwargs"]["stop_requested"].__self__ is window.runner.control
    assert window.runner.started is True

    window.runner = None
    window.close()


def test_diagnostics_dialog_copies_text_to_clipboard():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    dialog = DiagnosticsDialog()

    dialog.copy_diagnostics()

    assert app is not None
    assert "App version:" in dialog.text.toPlainText()
    assert QtWidgets.QApplication.clipboard().text() == dialog.text.toPlainText()

    dialog.close()
