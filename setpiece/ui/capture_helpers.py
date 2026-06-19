from __future__ import annotations

from pathlib import Path


class QtPathPicker:
    def __init__(self, parent=None) -> None:
        self.parent = parent

    def browse_app_path(self) -> str | None:
        from PySide6.QtWidgets import QFileDialog

        filename, _ = QFileDialog.getOpenFileName(
            self.parent,
            "Choose Application",
            str(Path.cwd()),
            "Applications (*.exe);;All files (*.*)",
        )
        return filename or None

    def browse_file_path(self) -> str | None:
        from PySide6.QtWidgets import QFileDialog

        filename, _ = QFileDialog.getOpenFileName(
            self.parent,
            "Choose File",
            str(Path.cwd()),
            "All files (*.*)",
        )
        return filename or None

    def browse_folder_path(self) -> str | None:
        from PySide6.QtWidgets import QFileDialog

        folder = QFileDialog.getExistingDirectory(
            self.parent,
            "Choose Folder",
            str(Path.cwd()),
        )
        return folder or None
