from __future__ import annotations

from PySide6.QtWidgets import QMessageBox, QWidget

from ritualist.overlay import ConfirmationRequest, format_confirmation_request


def show_error(parent: QWidget, title: str, message: str) -> None:
    QMessageBox.critical(parent, title, message)


def ask_confirmation(parent: QWidget, request: ConfirmationRequest | str) -> bool:
    result = QMessageBox.question(
        parent,
        "Confirm Action",
        format_confirmation_request(request),
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return result == QMessageBox.StandardButton.Yes
