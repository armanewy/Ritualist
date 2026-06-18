from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import Thread
from typing import Any

from ritualist.overlay import ConfirmationRequest, ScreenRect, format_confirmation_request


@dataclass(frozen=True)
class DialogPlacement:
    x: int
    y: int


class InlineConfirmationPresenter:
    """Test/simple presenter that delegates to an in-Home decision callback."""

    def __init__(self, callback: Callable[[ConfirmationRequest | str, Callable[[bool], None]], None]) -> None:
        self._callback = callback

    def request_confirmation(
        self,
        request: ConfirmationRequest | str,
        *,
        on_decision: Callable[[bool], None],
    ) -> None:
        self._callback(request, on_decision)


def create_qt_confirmation_presenter() -> Any:
    """Create the top-level Home confirmation presenter.

    PySide imports stay inside this factory so importing Home model/controller
    helpers remains safe in CLI and non-GUI test environments.
    """

    from PySide6.QtCore import QPoint, QTimer, Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import (
        QDialog,
        QDialogButtonBox,
        QLabel,
        QPushButton,
        QVBoxLayout,
    )

    class QtHomeConfirmationPresenter:
        def __init__(self) -> None:
            self._dialog: QDialog | None = None

        def request_confirmation(
            self,
            request: ConfirmationRequest | str,
            *,
            on_decision: Callable[[bool], None],
        ) -> None:
            try:
                self._request_qt_confirmation(request, on_decision=on_decision)
            except Exception:  # noqa: BLE001 - preserve safety if Qt cannot present the dialog.
                self._discard_dialog()
                if _is_windows():
                    _show_win32_confirmation_async(request, on_decision=on_decision)
                else:
                    on_decision(False)

        def _request_qt_confirmation(
            self,
            request: ConfirmationRequest | str,
            *,
            on_decision: Callable[[bool], None],
        ) -> None:
            if self._dialog is not None:
                self._dialog.close()
                self._dialog.deleteLater()

            dialog = QDialog()
            self._dialog = dialog
            dialog.setWindowTitle("Ritualist Confirmation Required")
            dialog.setModal(False)
            dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
            dialog.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
            dialog.setWindowFlag(Qt.WindowType.Window, True)
            dialog.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, True)
            dialog.setMinimumWidth(460)

            layout = QVBoxLayout(dialog)
            title = QLabel("Confirmation required")
            title.setObjectName("ritualistConfirmationTitle")
            title.setStyleSheet("font-weight: 700; font-size: 15px;")
            layout.addWidget(title)

            body = QLabel(format_confirmation_request(request))
            body.setObjectName("ritualistConfirmationBody")
            body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            body.setWordWrap(True)
            layout.addWidget(body)

            buttons = QDialogButtonBox()
            proceed = QPushButton(_proceed_label(request))
            proceed.setObjectName("ritualistProceedButton")
            skip = QPushButton("Skip if supported")
            skip.setObjectName("ritualistSkipButton")
            skip.setEnabled(False)
            skip.setToolTip("This step cannot be skipped safely in v0.1.")
            cancel = QPushButton("Cancel")
            cancel.setObjectName("ritualistCancelButton")
            buttons.addButton(proceed, QDialogButtonBox.ButtonRole.AcceptRole)
            buttons.addButton(skip, QDialogButtonBox.ButtonRole.ActionRole)
            buttons.addButton(cancel, QDialogButtonBox.ButtonRole.RejectRole)
            layout.addWidget(buttons)

            answered = False

            def answer(value: bool) -> None:
                nonlocal answered
                if answered:
                    return
                answered = True
                on_decision(value)
                dialog.close()

            proceed.clicked.connect(lambda: answer(True))
            cancel.clicked.connect(lambda: answer(False))
            dialog.rejected.connect(lambda: answer(False))
            dialog.finished.connect(lambda _result: self._clear_dialog(dialog))

            dialog.adjustSize()
            _place_dialog(dialog, request, QGuiApplication, QPoint)
            dialog.show()
            _force_dialog_foreground(dialog)
            QTimer.singleShot(150, lambda active_dialog=dialog: _force_dialog_foreground(active_dialog))
            QTimer.singleShot(700, lambda active_dialog=dialog: _force_dialog_foreground(active_dialog))

        def _clear_dialog(self, dialog: QDialog) -> None:
            if self._dialog is dialog:
                self._dialog = None
            dialog.deleteLater()

        def _discard_dialog(self) -> None:
            if self._dialog is None:
                return
            dialog = self._dialog
            self._dialog = None
            try:
                dialog.close()
                dialog.deleteLater()
            except RuntimeError:
                return

    return QtHomeConfirmationPresenter()


def create_win32_confirmation_presenter() -> Any:
    """Create a topmost native Windows confirmation fallback."""

    class Win32ConfirmationPresenter:
        def request_confirmation(
            self,
            request: ConfirmationRequest | str,
            *,
            on_decision: Callable[[bool], None],
        ) -> None:
            _show_win32_confirmation_async(request, on_decision=on_decision)

    return Win32ConfirmationPresenter()


def placement_for_dialog(
    *,
    dialog_width: int,
    dialog_height: int,
    target_rect: ScreenRect | None,
    screen_left: int,
    screen_top: int,
    screen_width: int,
    screen_height: int,
    margin: int = 16,
) -> DialogPlacement:
    max_x = screen_left + max(0, screen_width - dialog_width)
    max_y = screen_top + max(0, screen_height - dialog_height)

    if target_rect is not None and target_rect.is_valid:
        right_x = target_rect.x + target_rect.width + margin
        left_x = target_rect.x - dialog_width - margin
        x = right_x if right_x <= max_x else left_x
        y = target_rect.y
    else:
        x = screen_left + (screen_width - dialog_width) // 2
        y = screen_top + (screen_height - dialog_height) // 2

    return DialogPlacement(
        x=max(screen_left, min(max_x, x)),
        y=max(screen_top, min(max_y, y)),
    )


def _place_dialog(dialog: Any, request: ConfirmationRequest | str, app: Any, point_type: Any) -> None:
    rect = request.target_rect if isinstance(request, ConfirmationRequest) else None
    screen = None
    if rect is not None and rect.is_valid:
        screen = app.screenAt(point_type(rect.x + rect.width // 2, rect.y + rect.height // 2))
    if screen is None:
        screen = app.primaryScreen()
    if screen is None:
        return
    available = screen.availableGeometry()
    placement = placement_for_dialog(
        dialog_width=max(1, dialog.width()),
        dialog_height=max(1, dialog.height()),
        target_rect=rect,
        screen_left=available.x(),
        screen_top=available.y(),
        screen_width=available.width(),
        screen_height=available.height(),
    )
    dialog.move(placement.x, placement.y)


def _force_dialog_foreground(dialog: Any) -> None:
    if dialog is None:
        return
    try:
        dialog.raise_()
        dialog.activateWindow()
    except RuntimeError:
        return
    if not _is_windows():
        return
    try:
        hwnd = int(dialog.winId())
    except Exception:  # noqa: BLE001 - foreground forcing is best-effort.
        return
    _force_hwnd_foreground(hwnd)


def _show_win32_confirmation(request: ConfirmationRequest | str) -> bool:
    import ctypes

    text = format_confirmation_request(request)
    title = "Ritualist Confirmation Required"
    flags = 0x00000001 | 0x00000030 | 0x00000100 | 0x00040000 | 0x00010000
    try:
        result = ctypes.windll.user32.MessageBoxW(None, text, title, flags)
    except Exception:  # noqa: BLE001 - if the fallback cannot show, preserve safety by declining.
        return False
    return result == 1


def _show_win32_confirmation_async(
    request: ConfirmationRequest | str,
    *,
    on_decision: Callable[[bool], None],
) -> None:
    def decide() -> None:
        on_decision(_show_win32_confirmation(request))

    Thread(target=decide, name="ritualist-win32-confirmation", daemon=True).start()


def _force_hwnd_foreground(hwnd: int) -> None:
    import ctypes

    user32 = ctypes.windll.user32
    hwnd_topmost = -1
    sw_shownormal = 1
    swp_nosize = 0x0001
    swp_nomove = 0x0002
    swp_showwindow = 0x0040
    try:
        user32.ShowWindow(hwnd, sw_shownormal)
        user32.SetWindowPos(
            hwnd,
            hwnd_topmost,
            0,
            0,
            0,
            0,
            swp_nomove | swp_nosize | swp_showwindow,
        )
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    except Exception:  # noqa: BLE001 - topmost promotion must never break confirmation.
        return


def _is_windows() -> bool:
    import sys

    return sys.platform == "win32"


def _proceed_label(request: ConfirmationRequest | str) -> str:
    if isinstance(request, ConfirmationRequest):
        return "Allow once"
    return "Proceed"
