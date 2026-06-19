from __future__ import annotations

from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from setpiece.diagnostics import format_diagnostics


class DiagnosticsDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Setpiece Diagnostics")
        self.resize(720, 420)

        layout = QVBoxLayout(self)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setPlainText(format_diagnostics())
        layout.addWidget(self.text)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.copy_button = QPushButton("Copy Diagnostics")
        buttons.addButton(self.copy_button, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.rejected.connect(self.reject)
        self.copy_button.clicked.connect(self.copy_diagnostics)
        layout.addWidget(buttons)

    def copy_diagnostics(self) -> None:
        QApplication.clipboard().setText(self.text.toPlainText())
