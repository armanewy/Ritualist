from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from setpiece.home.pack_review import PackImportReview, PackReviewDecision


class PackImportReviewDialog(QDialog):
    def __init__(self, review: PackImportReview, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.review = review
        self.selected_action = PackReviewDecision.CANCEL

        self.setWindowTitle("Review Recipe Pack")
        self.resize(860, 680)

        layout = QVBoxLayout(self)
        layout.addWidget(_metadata_group(review))

        self.actions_table = _actions_table(review)
        layout.addWidget(self.actions_table)

        details_row = QHBoxLayout()
        self.variables_text = _readonly_text(_list_text(review.required_variables) or "None")
        self.variables_text.setMinimumHeight(120)
        details_row.addWidget(_text_group("Required Variables", self.variables_text))
        self.capabilities_text = _readonly_text(_list_text(review.required_capabilities) or "None")
        self.capabilities_text.setMinimumHeight(120)
        details_row.addWidget(
            _text_group("Required Capabilities", self.capabilities_text)
        )
        layout.addLayout(details_row)

        warning_text = _list_text((*review.safety_warnings, *review.enable_blockers))
        self.warnings_text = _readonly_text(warning_text or "No safety warnings reported.")
        warnings_group = QGroupBox("Safety Warnings")
        warnings_layout = QVBoxLayout(warnings_group)
        warnings_layout.addWidget(self.warnings_text)
        layout.addWidget(warnings_group)

        self.readme_text = _readonly_text(review.readme or "No README provided.")
        readme_group = QGroupBox("README")
        readme_layout = QVBoxLayout(readme_group)
        readme_layout.addWidget(self.readme_text)
        layout.addWidget(readme_group)

        self.button_box = QDialogButtonBox()
        self.run_doctor_button = QPushButton("Run Doctor")
        self.dry_run_button = QPushButton("Dry Run")
        self.enable_button = QPushButton("Enable")
        self.cancel_button = QPushButton("Cancel")
        self.enable_button.setEnabled(review.enable_allowed)
        if not review.enable_allowed:
            self.enable_button.setToolTip("Resolve validation or policy failures before enabling.")

        self.button_box.addButton(self.run_doctor_button, QDialogButtonBox.ButtonRole.ActionRole)
        self.button_box.addButton(self.dry_run_button, QDialogButtonBox.ButtonRole.ActionRole)
        self.button_box.addButton(self.enable_button, QDialogButtonBox.ButtonRole.AcceptRole)
        self.button_box.addButton(self.cancel_button, QDialogButtonBox.ButtonRole.RejectRole)
        self.run_doctor_button.clicked.connect(
            lambda: self._choose(PackReviewDecision.RUN_DOCTOR)
        )
        self.dry_run_button.clicked.connect(lambda: self._choose(PackReviewDecision.DRY_RUN))
        self.enable_button.clicked.connect(lambda: self._choose(PackReviewDecision.ENABLE))
        self.cancel_button.clicked.connect(lambda: self._choose(PackReviewDecision.CANCEL))
        layout.addWidget(self.button_box)

    def _choose(self, decision: PackReviewDecision) -> None:
        self.selected_action = decision
        if decision is PackReviewDecision.CANCEL:
            self.reject()
            return
        self.accept()


def _metadata_group(review: PackImportReview) -> QGroupBox:
    group = QGroupBox("Pack")
    layout = QFormLayout(group)
    layout.addRow("Name", QLabel(review.pack_name))
    layout.addRow("Version", QLabel(review.pack_version or "Not specified"))
    layout.addRow("Author", QLabel(review.author or "Not specified"))
    status = "Ready to enable" if review.enable_allowed else "Enable blocked"
    layout.addRow("Status", QLabel(status))
    return group


def _actions_table(review: PackImportReview) -> QTableWidget:
    table = QTableWidget(0, 5)
    table.setHorizontalHeaderLabels(["Action", "Side Effect", "Capabilities", "Policy", "Warnings"])
    table.horizontalHeader().setStretchLastSection(True)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    for action in review.actions:
        row = table.rowCount()
        table.insertRow(row)
        values = [
            action.action_name,
            action.side_effect_label or action.side_effect_level or "Not specified",
            ", ".join(action.required_capabilities) or "None",
            "Blocked" if action.blocked_by_policy else "Allowed",
            "; ".join(action.safety_warnings) or "None",
        ]
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(row, column, item)
    table.resizeColumnsToContents()
    return table


def _text_group(title: str, widget: QPlainTextEdit) -> QGroupBox:
    group = QGroupBox(title)
    layout = QVBoxLayout(group)
    layout.addWidget(widget)
    return group


def _readonly_text(text: str) -> QPlainTextEdit:
    widget = QPlainTextEdit()
    widget.setReadOnly(True)
    widget.setPlainText(text)
    return widget


def _list_text(values: tuple[str, ...]) -> str:
    return "\n".join(f"- {value}" for value in values)
