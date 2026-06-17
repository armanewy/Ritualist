from __future__ import annotations

import sys

from ritualist.e2e import record_event
from ritualist.errors import DependencyMissingError


def run_gui() -> None:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:
        raise DependencyMissingError("GUI requires PySide6; install ritualist[gui]") from exc

    from .main_window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow()
    window.resize(900, 600)
    window.show()
    record_event("classic_gui.ready", window_title=window.windowTitle())
    app.exec()
