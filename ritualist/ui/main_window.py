from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
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
from ritualist.doctor import diagnose_recipe
from ritualist.errors import RitualistError
from ritualist.executor import WorkflowExecutor
from ritualist.logging_setup import setup_logging
from ritualist.paths import config_file, recipes_dir, runs_dir
from ritualist.recipe_loader import discover_recipes, load_recipe
from ritualist.run_logs import RunLogWriter, reconcile_running_runs

from .dialogs import ask_confirmation, show_error
from .diagnostics_dialog import DiagnosticsDialog
from .runner_thread import RunnerThread


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Ritualist")
        self.recipe_path: Path | None = None
        self.recipe = None
        self.discovered_recipes: dict[str, Path] = {}
        self.runner: RunnerThread | None = None
        self._close_after_run_stops = False

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
        self.init_button = QPushButton("Initialize App")
        self.init_button.clicked.connect(self.initialize_app)
        self.refresh_button = QPushButton("Refresh Recipes")
        self.refresh_button.clicked.connect(self.refresh_recipes)
        file_row.addWidget(QLabel("Recipe"))
        file_row.addWidget(self.recipe_combo)
        file_row.addWidget(self.path_edit)
        file_row.addWidget(browse_button)
        file_row.addWidget(load_button)
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
        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self.stop_run)
        self.stop_button.setEnabled(False)
        button_row.addWidget(self.run_button)
        button_row.addWidget(self.dry_run_button)
        button_row.addWidget(self.doctor_button)
        button_row.addWidget(self.stop_button)
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

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log)

        self.setCentralWidget(root)
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
        for check in checks:
            self.append_log(f"{check.status}: {check.name} - {check.message}")

    def populate_steps(self) -> None:
        self.steps_table.setRowCount(0)
        if self.recipe is None:
            return
        for index, step in enumerate(self.recipe.steps, start=1):
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
        self.status_label.setText("Running")
        logger = setup_logging()
        executor = WorkflowExecutor(
            adapters=create_default_adapters(),
            dry_run=dry_run,
            logger=logger,
            run_logger=RunLogWriter(),
            stop_requested=lambda: bool(self.runner and self.runner.isInterruptionRequested()),
        )
        self.runner = RunnerThread(executor, self.recipe)
        self.runner.log_message.connect(self.append_log)
        self.runner.failed.connect(self.on_failed)
        self.runner.finished_result.connect(self.on_finished)
        self.runner.confirmation_requested.connect(self.on_confirmation_requested)
        self.runner.start()

    def on_confirmation_requested(self, prompt: str) -> None:
        if self.runner is None:
            return
        self.runner.answer_confirmation(ask_confirmation(self, prompt))

    def on_failed(self, message: str) -> None:
        self.append_log(f"Failed: {message}")
        self.status_label.setText("Run failed")
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
        final_text = "Run finished" if summary.success else "Run stopped"
        self.append_log(f"{final_text}: {summary_text}")
        self.status_label.setText(final_text)
        self.set_run_controls_enabled(True)
        if self._close_after_run_stops:
            self._close_after_run_stops = False
            self.close()

    def stop_run(self) -> None:
        if self.runner is None or not self.runner.isRunning():
            return
        self.runner.requestInterruption()
        self.runner.answer_confirmation(False)
        self.append_log("Stop requested; the current step may finish before the run stops")
        self.status_label.setText("Stop requested")
        self.stop_button.setEnabled(False)

    def set_run_controls_enabled(self, enabled: bool) -> None:
        self.run_button.setEnabled(enabled)
        self.dry_run_button.setEnabled(enabled)
        self.doctor_button.setEnabled(enabled)
        self.stop_button.setEnabled(not enabled)

    def open_path(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path == config_file() and not path.exists():
            path.write_text("", encoding="utf-8")
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def show_diagnostics(self) -> None:
        dialog = DiagnosticsDialog(self)
        dialog.exec()

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
