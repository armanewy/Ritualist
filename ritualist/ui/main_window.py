from __future__ import annotations

from pathlib import Path
from time import monotonic

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ritualist.adapters import create_default_adapters
from ritualist.app_setup import initialize_app
from ritualist.config import load_app_config
from ritualist.doctor import diagnose_recipe
from ritualist.errors import RitualistError
from ritualist.executor import WorkflowExecutor
from ritualist.logging_setup import setup_logging
from ritualist.overlay import NullOverlayController
from ritualist.paths import config_file, recipes_dir, runs_dir
from ritualist.recipe_loader import discover_recipes, load_recipe
from ritualist.recipe_step_builder import RecipeStepAppendController
from ritualist.run_logs import RunLogWriter, reconcile_running_runs
from ritualist.runtime_control import RuntimeControl
from ritualist.watch_me import WatchMeService

from .dialogs import ask_confirmation, show_error
from .diagnostics_dialog import DiagnosticsDialog
from .overlay import QtOverlayController
from .runner_thread import RunnerThread
from .step_wizard import AddStepDialog


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Ritualist")
        self.recipe_path: Path | None = None
        self.recipe = None
        self.discovered_recipes: dict[str, Path] = {}
        self.runner: RunnerThread | None = None
        self._close_after_run_stops = False
        self._wait_status: dict[str, object] | None = None
        self.step_append_controller = RecipeStepAppendController()
        self.overlay_controller, self._overlay_warning = self._create_overlay_controller()
        self._diagnostics_dialog: DiagnosticsDialog | None = None
        self._watch_me_service = WatchMeService(adapters=create_default_adapters())
        self._watch_me_session_id: str | None = None

        root = QWidget()
        layout = QVBoxLayout(root)

        file_row = QHBoxLayout()
        self.recipe_combo = QComboBox()
        self.recipe_combo.currentIndexChanged.connect(lambda _index: self.on_recipe_selected())
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Choose a ritual YAML file")
        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(self.choose_file)
        load_button = QPushButton("Load")
        load_button.clicked.connect(self.load_current_recipe)
        new_recipe_button = QPushButton("New Recipe")
        new_recipe_button.clicked.connect(self.new_recipe)
        self.init_button = QPushButton("Initialize App")
        self.init_button.clicked.connect(self.initialize_app)
        self.refresh_button = QPushButton("Refresh Recipes")
        self.refresh_button.clicked.connect(self.refresh_recipes)
        file_row.addWidget(QLabel("Recipe"))
        file_row.addWidget(self.recipe_combo)
        file_row.addWidget(self.path_edit)
        file_row.addWidget(browse_button)
        file_row.addWidget(load_button)
        file_row.addWidget(new_recipe_button)
        file_row.addWidget(self.init_button)
        file_row.addWidget(self.refresh_button)
        layout.addLayout(file_row)

        self.steps_table = QTableWidget(0, 5)
        self.steps_table.setHorizontalHeaderLabels(["#", "Step", "Action", "Optional", "Confirm"])
        self.steps_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.steps_table)

        button_row = QHBoxLayout()
        self.run_button = QPushButton("Run")
        self.run_button.clicked.connect(lambda: self.run_recipe(dry_run=False))
        self.dry_run_button = QPushButton("Dry Run")
        self.dry_run_button.clicked.connect(lambda: self.run_recipe(dry_run=True))
        self.doctor_button = QPushButton("Doctor")
        self.doctor_button.clicked.connect(self.doctor_recipe)
        self.add_step_button = QPushButton("Add Step")
        self.add_step_button.clicked.connect(self.add_step)
        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self.stop_run)
        self.stop_button.setEnabled(False)
        self.close_browser_button = QPushButton("Close Browser")
        self.close_browser_button.clicked.connect(self.close_keep_open_browser)
        self.watch_start_button = QPushButton("Create from what I do")
        self.watch_start_button.clicked.connect(self.start_watch_me)
        self.watch_stop_button = QPushButton("Stop Watch Me")
        self.watch_stop_button.clicked.connect(self.stop_watch_me)
        self.watch_stop_button.setEnabled(False)
        self.watch_draft_button = QPushButton("Create Draft")
        self.watch_draft_button.clicked.connect(self.create_watch_me_draft)
        self.watch_draft_button.setEnabled(False)
        self.watch_discard_button = QPushButton("Discard Watch Me")
        self.watch_discard_button.clicked.connect(self.discard_watch_me)
        self.watch_discard_button.setEnabled(False)
        self.pause_button = QPushButton("Pause")
        self.pause_button.clicked.connect(self.pause_run)
        self.pause_button.setEnabled(False)
        self.resume_button = QPushButton("Resume")
        self.resume_button.clicked.connect(self.resume_run)
        self.resume_button.setEnabled(False)
        button_row.addWidget(self.run_button)
        button_row.addWidget(self.dry_run_button)
        button_row.addWidget(self.doctor_button)
        button_row.addWidget(self.add_step_button)
        button_row.addWidget(self.pause_button)
        button_row.addWidget(self.resume_button)
        button_row.addWidget(self.stop_button)
        button_row.addWidget(self.close_browser_button)
        button_row.addWidget(self.watch_start_button)
        button_row.addWidget(self.watch_stop_button)
        button_row.addWidget(self.watch_draft_button)
        button_row.addWidget(self.watch_discard_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)

        folder_row = QHBoxLayout()
        recipes_button = QPushButton("Open Recipes Folder")
        recipes_button.clicked.connect(lambda: self.open_path(recipes_dir()))
        config_button = QPushButton("Open Config File")
        config_button.clicked.connect(lambda: self.open_path(config_file()))
        logs_button = QPushButton("Open Logs/Runs Folder")
        logs_button.clicked.connect(lambda: self.open_path(runs_dir()))
        diagnostics_button = QPushButton("About / Diagnostics")
        diagnostics_button.clicked.connect(self.show_diagnostics)
        folder_row.addWidget(recipes_button)
        folder_row.addWidget(config_button)
        folder_row.addWidget(logs_button)
        folder_row.addWidget(diagnostics_button)
        folder_row.addStretch(1)
        layout.addLayout(folder_row)

        self.status_label = QLabel("Ready")
        layout.addWidget(self.status_label)
        self.run_state_label = QLabel("Run state: stopped")
        layout.addWidget(self.run_state_label)
        self.waiting_label = QLabel("Waiting: inactive")
        layout.addWidget(self.waiting_label)
        self.keep_open_label = QLabel("Keep-open: inactive")
        layout.addWidget(self.keep_open_label)
        self._wait_timer = QTimer(self)
        self._wait_timer.setInterval(1000)
        self._wait_timer.timeout.connect(self._refresh_waiting_label)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log)

        self.setCentralWidget(root)
        if self._overlay_warning:
            self.append_log(f"Action overlay unavailable: {self._overlay_warning}")
        self.reconcile_runs()
        self.refresh_recipes()

    def choose_file(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Open Ritual Recipe",
            str(Path.cwd()),
            "YAML files (*.yaml *.yml);;All files (*.*)",
        )
        if filename:
            self.path_edit.setText(filename)
            self.load_current_recipe()

    def on_recipe_selected(self) -> None:
        recipe_id = self.recipe_combo.currentData()
        if not recipe_id:
            return
        path = self.discovered_recipes.get(recipe_id)
        if path is not None:
            self.path_edit.setText(str(path))
            self.load_current_recipe()

    def initialize_app(self) -> None:
        report = initialize_app()
        if report.changed:
            for name, path in report.created_dirs.items():
                self.append_log(f"Created {name}: {path}")
            if report.config_created:
                self.append_log("Created config file")
            if report.sample_copied:
                self.append_log(f"Copied gaming_mode sample: {report.migration.recipe_path}")
            for change in report.migration.changes:
                self.append_log(f"Migrated {report.migration.recipe_path}: {change}")
        else:
            self.append_log("Initialization is already up to date")
        self.refresh_recipes()

    def refresh_recipes(self) -> None:
        self.reconcile_runs()
        current = self.recipe_combo.currentData()
        self.recipe_combo.blockSignals(True)
        self.recipe_combo.clear()
        self.discovered_recipes.clear()
        for path, recipe, error in discover_recipes():
            if recipe is None:
                self.recipe_combo.addItem(f"{path.stem} (invalid)", None)
                self.append_log(f"Invalid recipe {path}: {error}")
                continue
            self.discovered_recipes[recipe.id] = path
            self.recipe_combo.addItem(f"{recipe.id} - {recipe.name}", recipe.id)
        if current:
            index = self.recipe_combo.findData(current)
            if index >= 0:
                self.recipe_combo.setCurrentIndex(index)
        self.recipe_combo.blockSignals(False)
        if self.recipe_combo.count():
            self.on_recipe_selected()
        else:
            self.recipe = None
            self.recipe_path = None
            self.steps_table.setRowCount(0)
        self.append_log("Recipes refreshed")

    def start_watch_me(self) -> None:
        try:
            session = self._watch_me_service.start()
        except Exception as exc:  # noqa: BLE001 - show GUI-safe error.
            show_error(self, "Watch Me Failed", str(exc))
            return
        self._watch_me_session_id = session.session_id
        self.watch_start_button.setEnabled(False)
        self.watch_stop_button.setEnabled(True)
        self.watch_draft_button.setEnabled(False)
        self.watch_discard_button.setEnabled(True)
        self.status_label.setText("Watch Me recording")
        self.append_log(f"Watch Me started: {session.session_id}")
        self.append_log("Recording indicator active. Stop Watch Me before creating a draft.")

    def stop_watch_me(self) -> None:
        if not self._watch_me_session_id:
            return
        try:
            session = self._watch_me_service.stop(self._watch_me_session_id)
        except Exception as exc:  # noqa: BLE001
            show_error(self, "Watch Me Failed", str(exc))
            return
        self.watch_stop_button.setEnabled(False)
        self.watch_start_button.setEnabled(True)
        self.watch_draft_button.setEnabled(True)
        self.watch_discard_button.setEnabled(True)
        self.status_label.setText("Watch Me stopped")
        self.append_log(f"Watch Me stopped: {session.session_id} ({len(session.events)} events)")

    def create_watch_me_draft(self) -> None:
        if not self._watch_me_session_id:
            return
        try:
            draft = self._watch_me_service.create_draft(self._watch_me_session_id)
            session = self._watch_me_service.load(self._watch_me_session_id)
        except Exception as exc:  # noqa: BLE001
            show_error(self, "Watch Me Failed", str(exc))
            return
        self.watch_draft_button.setEnabled(False)
        self.status_label.setText("Watch Me draft created")
        self.append_log(f"Watch Me draft created: {session.draft_path}")
        self.append_log(
            f"Draft recipe {draft.recipe.get('id')} is disabled until you review and save it."
        )
        if draft.preview:
            self.append_log("Draft preview:")
            for item in draft.preview:
                self.append_log(f"- {item}")
        self.append_log("Run Doctor and dry-run before using the draft.")

    def discard_watch_me(self) -> None:
        if not self._watch_me_session_id:
            return
        try:
            session = self._watch_me_service.discard(self._watch_me_session_id)
        except Exception as exc:  # noqa: BLE001
            show_error(self, "Watch Me Failed", str(exc))
            return
        self._watch_me_session_id = None
        self.watch_start_button.setEnabled(True)
        self.watch_stop_button.setEnabled(False)
        self.watch_draft_button.setEnabled(False)
        self.watch_discard_button.setEnabled(False)
        self.status_label.setText("Watch Me discarded")
        self.append_log(f"Watch Me discarded: {session.session_id}")

    def load_current_recipe(self) -> None:
        text = self.path_edit.text().strip()
        if not text:
            return
        path = Path(text)
        try:
            self.recipe = load_recipe(path)
            self.recipe_path = path
        except RitualistError as exc:
            show_error(self, "Invalid Recipe", str(exc))
            return
        self.populate_steps()
        self.status_label.setText(f"Loaded {self.recipe.id}")
        self.append_log(f"Loaded {self.recipe.name}")

    def new_recipe(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Create Ritual Recipe",
            str(recipes_dir() / "new_recipe.yaml"),
            "YAML files (*.yaml *.yml);;All files (*.*)",
        )
        if not filename:
            return
        dialog = AddStepDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.step_data is None:
            return
        try:
            self.recipe = self.step_append_controller.create_recipe_with_step(
                filename,
                dialog.step_data,
                variable_updates=dialog.variable_updates,
            )
            self.recipe_path = Path(filename)
            self.path_edit.setText(str(self.recipe_path))
        except RitualistError as exc:
            show_error(self, "Could Not Create Recipe", str(exc))
            return
        self.populate_steps()
        self.status_label.setText(f"Created {self.recipe.id}")
        self.append_log(f"Created {self.recipe.name}")
        self.discovered_recipes[self.recipe.id] = self.recipe_path
        combo_label = f"{self.recipe.id} - {self.recipe.name}"
        combo_index = self.recipe_combo.findData(self.recipe.id)
        if combo_index < 0:
            self.recipe_combo.addItem(combo_label, self.recipe.id)
            combo_index = self.recipe_combo.findData(self.recipe.id)
        self.recipe_combo.blockSignals(True)
        self.recipe_combo.setCurrentIndex(combo_index)
        self.recipe_combo.blockSignals(False)

    def add_step(self) -> None:
        if self.recipe is None:
            self.load_current_recipe()
        if self.recipe is None or self.recipe_path is None:
            show_error(self, "No Recipe Loaded", "Load or create a recipe before adding a step.")
            return
        dialog = AddStepDialog(self, recipe=self.recipe)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.step_data is None:
            return
        try:
            self.recipe = self.step_append_controller.append_step(
                self.recipe_path,
                dialog.step_data,
                variable_updates=dialog.variable_updates,
            )
        except RitualistError as exc:
            show_error(self, "Could Not Add Step", str(exc))
            return
        self.populate_steps()
        self.status_label.setText(f"Updated {self.recipe.id}")
        self.append_log(f"Added {dialog.step_data['action']} to {self.recipe.name}")

    def doctor_recipe(self) -> None:
        if self.recipe is None:
            self.load_current_recipe()
        if self.recipe is None:
            return
        self.append_log(f"Doctor: {self.recipe.name} ({self.recipe.id})")
        try:
            checks = diagnose_recipe(self.recipe)
        except RitualistError as exc:
            self.append_log(f"doctor error: {exc}")
            show_error(self, "Doctor Failed", str(exc))
            return
        current_section = None
        for check in checks:
            if check.section != current_section:
                current_section = check.section
                self.append_log(f"{current_section}:")
            self.append_log(f"  {check.status}: {check.name} - {check.message}")

    def populate_steps(self) -> None:
        self.steps_table.setRowCount(0)
        if self.recipe is None:
            return
        for index, step in enumerate(self.recipe.execution_steps, start=1):
            row = self.steps_table.rowCount()
            self.steps_table.insertRow(row)
            values = [
                str(index),
                step.display_name,
                step.action,
                "yes" if step.optional else "no",
                "yes" if step.requires_confirmation else "no",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.steps_table.setItem(row, column, item)
        self.steps_table.resizeColumnsToContents()

    def run_recipe(self, *, dry_run: bool) -> None:
        if self.recipe is None:
            self.load_current_recipe()
        if self.recipe is None:
            return

        self.set_run_controls_enabled(False)
        self.set_run_state("running")
        self.status_label.setText("Running")
        self._clear_wait_status()
        self.keep_open_label.setText("Keep-open: inactive")
        logger = setup_logging()
        config = load_app_config()
        control = RuntimeControl()
        executor = WorkflowExecutor(
            adapters=create_default_adapters(),
            dry_run=dry_run,
            logger=logger,
            run_logger=RunLogWriter(),
            runtime_control=control,
            stop_requested=control.is_stopping,
            config=config,
            overlay=self.overlay_controller,
        )
        self.runner = RunnerThread(executor, self.recipe, control)
        self.runner.log_message.connect(self.append_log)
        self.runner.step_event.connect(self.on_step_event)
        self.runner.run_state_changed.connect(self.on_run_state_changed)
        self.runner.stopped.connect(self.on_stopped)
        self.runner.failed.connect(self.on_failed)
        self.runner.finished_result.connect(self.on_finished)
        self.runner.confirmation_requested.connect(self.on_confirmation_requested)
        self.runner.start()

    def on_step_event(self, event) -> None:
        step = self._step_by_index(event.index)
        if getattr(event, "wait_action", "") or (
            event.status == "running" and _is_wait_action(event.action)
        ):
            self._set_wait_status(event, step)
        elif event.status != "running" and _is_wait_action(event.action):
            self._clear_wait_status()

        if getattr(event, "keep_open_active", False) or (
            event.status == "success"
            and event.action == "browser.open"
            and step is not None
            and getattr(step, "keep_open", False)
        ):
            self.keep_open_label.setText("Keep-open: active")

    def on_confirmation_requested(self, prompt: object) -> None:
        if self.runner is None:
            return
        self.runner.answer_confirmation(ask_confirmation(self, prompt))

    def on_run_state_changed(self, state: str) -> None:
        self.set_run_state(state)
        if state == "paused":
            self.stop_button.setEnabled(True)
            self.pause_button.setEnabled(False)
            self.resume_button.setEnabled(True)
        elif state in {"running", "waiting", "confirming"}:
            self.stop_button.setEnabled(True)
            self.pause_button.setEnabled(True)
            self.resume_button.setEnabled(False)

    def on_stopped(self, message: str) -> None:
        self.append_log(f"Stopped: {message}")
        self.set_run_state("stopped")
        self.status_label.setText("Run stopped")
        self._clear_wait_status()
        self.set_run_controls_enabled(True)
        if self._close_after_run_stops:
            self._close_after_run_stops = False
            self.close()

    def on_failed(self, message: str) -> None:
        self.append_log(f"Failed: {message}")
        self.set_run_state("failed")
        self.status_label.setText("Run failed")
        self._clear_wait_status()
        show_error(self, "Run Failed", message)
        self.set_run_controls_enabled(True)
        if self._close_after_run_stops:
            self._close_after_run_stops = False
            self.close()

    def on_finished(self, summary) -> None:
        for result in summary.results:
            self.append_log(f"{result.status}: {result.step_name} - {result.message}")
        counts: dict[str, int] = {}
        for result in summary.results:
            counts[result.status] = counts.get(result.status, 0) + 1
        summary_text = ", ".join(f"{count} {status}" for status, count in sorted(counts.items()))
        final_state = self._final_run_state(summary)
        final_text = {
            "success": "Run finished",
            "failed": "Run failed",
            "stopped": "Run stopped",
        }[final_state]
        self.append_log(f"{final_text}: {summary_text}")
        self.set_run_state(final_state)
        self.status_label.setText(final_text)
        self._clear_wait_status()
        keep_open_active = self._summary_requests_keep_open(summary)
        self.keep_open_label.setText(
            "Keep-open: active" if keep_open_active else "Keep-open: inactive"
        )
        self.append_log(
            "Keep-open: active" if keep_open_active else "Keep-open: inactive"
        )
        self.set_run_controls_enabled(True)
        if self._close_after_run_stops:
            self._close_after_run_stops = False
            self.close()

    def stop_run(self) -> None:
        if self.runner is None or not self.runner.isRunning():
            return
        stop = getattr(self.runner, "stop", None)
        if stop is not None:
            stop()
        else:
            self.runner.requestInterruption()
            self.runner.answer_confirmation(False)
        self.append_log("Stop requested; the current step may finish before the run stops")
        self.status_label.setText("Stop requested")
        self._clear_wait_status()
        self.stop_button.setEnabled(False)
        self.pause_button.setEnabled(False)
        self.resume_button.setEnabled(False)
        self.keep_open_label.setText("Keep-open: inactive")

    def close_keep_open_browser(self) -> None:
        executor = getattr(self.runner, "executor", None)
        close = getattr(executor, "close_browser_state", None)
        if close is None:
            self.append_log("No keep-open browser state to close")
            self.keep_open_label.setText("Keep-open: inactive")
            return
        if close():
            self.append_log("Closed keep-open browser state")
        else:
            self.append_log("No keep-open browser state to close")
        self.keep_open_label.setText("Keep-open: inactive")

    def pause_run(self) -> None:
        if self.runner is None or not self.runner.isRunning():
            return
        pause = getattr(self.runner, "pause", None)
        if pause is not None:
            pause()
        self.append_log("Pause requested; the current step may finish before the run pauses")
        self.on_run_state_changed("paused")

    def resume_run(self) -> None:
        if self.runner is None or not self.runner.isRunning():
            return
        resume = getattr(self.runner, "resume", None)
        if resume is not None:
            resume()
        self.append_log("Resume requested")
        self.on_run_state_changed("running")

    def set_run_controls_enabled(self, enabled: bool) -> None:
        self.run_button.setEnabled(enabled)
        self.dry_run_button.setEnabled(enabled)
        self.doctor_button.setEnabled(enabled)
        self.add_step_button.setEnabled(enabled)
        self.stop_button.setEnabled(not enabled)
        self.pause_button.setEnabled(not enabled)
        self.resume_button.setEnabled(False)

    def set_run_state(self, state: str) -> None:
        self.run_state_label.setText(f"Run state: {state}")

    def _set_wait_status(self, event, step) -> None:
        action = str(getattr(event, "wait_action", "") or getattr(event, "action", ""))
        target = str(getattr(event, "wait_target", "") or _wait_target_for_step(step))
        elapsed = _optional_float(getattr(event, "wait_elapsed_seconds", None)) or 0.0
        timeout = _optional_float(getattr(event, "wait_timeout_seconds", None))
        if timeout is None:
            timeout = _wait_timeout_for_step(step)
        self._wait_status = {
            "action": action,
            "target": target,
            "started_monotonic": monotonic() - elapsed,
            "timeout": timeout,
        }
        self._refresh_waiting_label()
        if not self._wait_timer.isActive():
            self._wait_timer.start()

    def _clear_wait_status(self) -> None:
        self._wait_status = None
        self._wait_timer.stop()
        self.waiting_label.setText("Waiting: inactive")

    def _refresh_waiting_label(self) -> None:
        if not self._wait_status:
            self.waiting_label.setText("Waiting: inactive")
            return
        elapsed = max(monotonic() - float(self._wait_status["started_monotonic"]), 0.0)
        parts = [
            f"Waiting: {self._wait_status['action']}",
            f"Target: {self._wait_status['target']}",
            f"Elapsed: {_format_duration(elapsed)}",
        ]
        timeout = self._wait_status.get("timeout")
        if timeout is not None:
            parts.append(f"Timeout: {_format_duration(float(timeout))}")
        self.waiting_label.setText(" | ".join(parts))

    def open_path(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path == config_file() and not path.exists():
            path.write_text("", encoding="utf-8")
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def show_diagnostics(self) -> None:
        try:
            if self._diagnostics_dialog is None:
                self._diagnostics_dialog = DiagnosticsDialog(self)
                self._diagnostics_dialog.finished.connect(self._clear_diagnostics_dialog)
            self._diagnostics_dialog.show()
            self._diagnostics_dialog.raise_()
            self._diagnostics_dialog.activateWindow()
        except Exception as exc:  # noqa: BLE001 - diagnostics must not disappear silently.
            message = f"Diagnostics failed: {exc}"
            self.append_log(message)
            QMessageBox.critical(self, "Ritualist Diagnostics", message)

    def _clear_diagnostics_dialog(self, _result: int | None = None) -> None:
        self._diagnostics_dialog = None

    def reconcile_runs(self) -> None:
        for repaired in reconcile_running_runs():
            self.append_log(f"Marked {repaired.run_id} as interrupted.")

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override.
        if self.runner is None or not self.runner.isRunning():
            event.accept()
            return
        choice = self.confirm_close_while_running()
        if choice == "stop":
            self._close_after_run_stops = True
            self.stop_run()
            event.ignore()
        elif choice == "exit":
            event.accept()
        else:
            event.ignore()

    def confirm_close_while_running(self) -> str:
        box = QMessageBox(self)
        box.setWindowTitle("Ritual Running")
        box.setText("A ritual is currently running. Stop it before exiting?")
        stop_button = box.addButton("Stop and Exit", QMessageBox.ButtonRole.AcceptRole)
        exit_button = box.addButton("Exit Anyway", QMessageBox.ButtonRole.DestructiveRole)
        cancel_button = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(stop_button)
        box.exec()
        clicked = box.clickedButton()
        if clicked == stop_button:
            return "stop"
        if clicked == exit_button:
            return "exit"
        if clicked == cancel_button:
            return "cancel"
        return "cancel"

    def append_log(self, message: str) -> None:
        self.log.appendPlainText(message)

    def _create_overlay_controller(self):
        try:
            return QtOverlayController(), None
        except Exception as exc:  # noqa: BLE001 - overlay must not prevent GUI startup.
            return NullOverlayController(), str(exc)

    def _summary_requests_keep_open(self, summary) -> bool:
        for result in summary.results:
            step = self._step_by_index(result.index)
            if (
                result.action == "browser.open"
                and result.status == "success"
                and step is not None
                and getattr(step, "keep_open", False)
            ):
                return True
        return False

    def _step_by_index(self, index: int):
        if self.recipe is None:
            return None
        steps_by_index = {index: step for index, step in enumerate(self.recipe.execution_steps, start=1)}
        return steps_by_index.get(index)

    def _final_run_state(self, summary) -> str:
        if summary.success:
            return "success"
        if any(result.status == "failed" for result in summary.results):
            return "failed"
        return "stopped"


def _is_wait_action(action: str) -> bool:
    return action == "window.wait" or action.startswith("wait.")


def _wait_target_for_step(step) -> str:
    if step is None:
        return "condition"
    action = getattr(step, "action", "")
    if action == "wait.seconds":
        return f"{getattr(step, 'seconds', 0):g}s"
    if action == "wait.for_user":
        return str(getattr(step, "prompt", "user confirmation"))
    if action == "wait.for_file":
        return f"file {getattr(step, 'path', '')}"
    if action == "wait.for_process":
        return f"process {getattr(step, 'process_name', '')} to start"
    if action == "wait.for_process_exit":
        return f"process {getattr(step, 'process_name', '')} to exit"
    title = getattr(step, "title_contains", None)
    process_name = getattr(step, "process_name", None)
    if action in {"window.wait", "wait.for_window"}:
        return f"window {title or process_name or 'window'}"
    if action == "wait.for_window_gone":
        return f"window {title or process_name or 'window'} to close"
    return getattr(step, "display_name", None) or "condition"


def _wait_timeout_for_step(step) -> float | None:
    if step is None:
        return None
    timeout = getattr(step, "timeout_seconds", None)
    if timeout is not None:
        return float(timeout)
    if getattr(step, "action", "") == "wait.seconds":
        return float(getattr(step, "seconds", 0))
    return None


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_duration(seconds: float) -> str:
    whole_seconds = max(int(seconds), 0)
    if whole_seconds < 60:
        return f"{whole_seconds}s"
    minutes, remainder = divmod(whole_seconds, 60)
    if minutes < 60:
        return f"{minutes}m {remainder}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"
