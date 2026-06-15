from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ritualist.adapters import create_default_adapters
from ritualist.errors import RitualistError
from ritualist.executor import WorkflowExecutor
from ritualist.logging_setup import setup_logging
from ritualist.recipe_loader import load_recipe

from .dialogs import ask_confirmation, show_error
from .runner_thread import RunnerThread


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Ritualist")
        self.recipe_path: Path | None = None
        self.recipe = None
        self.runner: RunnerThread | None = None

        root = QWidget()
        layout = QVBoxLayout(root)

        file_row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Choose a ritual YAML file")
        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(self.choose_file)
        load_button = QPushButton("Load")
        load_button.clicked.connect(self.load_current_recipe)
        file_row.addWidget(QLabel("Recipe"))
        file_row.addWidget(self.path_edit)
        file_row.addWidget(browse_button)
        file_row.addWidget(load_button)
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
        button_row.addWidget(self.run_button)
        button_row.addWidget(self.dry_run_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log)

        self.setCentralWidget(root)

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
        self.append_log(f"Loaded {self.recipe.name}")

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

        self.run_button.setEnabled(False)
        self.dry_run_button.setEnabled(False)
        logger = setup_logging()
        executor = WorkflowExecutor(
            adapters=create_default_adapters(),
            dry_run=dry_run,
            logger=logger,
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
        show_error(self, "Run Failed", message)
        self.run_button.setEnabled(True)
        self.dry_run_button.setEnabled(True)

    def on_finished(self, summary) -> None:
        for result in summary.results:
            self.append_log(f"{result.status}: {result.step_name} - {result.message}")
        self.append_log("Run finished" if summary.success else "Run stopped")
        self.run_button.setEnabled(True)
        self.dry_run_button.setEnabled(True)

    def append_log(self, message: str) -> None:
        self.log.appendPlainText(message)
