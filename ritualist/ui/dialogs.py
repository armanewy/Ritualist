from __future__ import annotations

from PySide6.QtWidgets import QMessageBox, QWidget


def show_error(parent: QWidget, title: str, message: str) -> None:
    QMessageBox.critical(parent, title, message)


def ask_confirmation(parent: QWidget, prompt: str) -> bool:
    result = QMessageBox.question(
        parent,
        "Confirm Action",
        prompt,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return result == QMessageBox.StandardButton.Yes
