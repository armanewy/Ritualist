from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import Thread
from typing import Any

from ritualist.approvals import ConfirmationDecision
from ritualist.overlay import ConfirmationRequest, ScreenRect, format_confirmation_request
from ritualist.preferences import RememberedApprovalScope, can_remember_approval


DecisionCallback = Callable[[bool | ConfirmationDecision], None]


@dataclass(frozen=True)
class DialogPlacement:
    x: int
    y: int


class InlineConfirmationPresenter:
    """Test/simple presenter that delegates to an in-Home decision callback."""

    def __init__(
        self,
        callback: Callable[[ConfirmationRequest | str, DecisionCallback], None],
    ) -> None:
        self._callback = callback

    def request_confirmation(
        self,
        request: ConfirmationRequest | str,
        *,
        on_decision: DecisionCallback,
        approve_label: str | None = None,
        negative_label: str = "Not now",
        remember_scope_text: str | None = None,
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
            on_decision: DecisionCallback,
            approve_label: str | None = None,
            negative_label: str = "Not now",
            remember_scope_text: str | None = None,
        ) -> None:
            try:
                self._request_qt_confirmation(
                    request,
                    on_decision=on_decision,
                    approve_label=approve_label,
                    negative_label=negative_label,
                    remember_scope_text=remember_scope_text,
                )
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
            on_decision: DecisionCallback,
            approve_label: str | None,
            negative_label: str,
            remember_scope_text: str | None,
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
            dialog.setAccessibleName("Ritualist confirmation")
            dialog.setAccessibleDescription(format_confirmation_request(request))
            dialog.setAutoFillBackground(True)
            dialog.setWindowOpacity(1.0)
            try:
                dialog.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
            except AttributeError:
                pass

            layout = QVBoxLayout(dialog)
            title = QLabel("Confirmation required")
            title.setObjectName("ritualistConfirmationTitle")
            title.setAccessibleName("Confirmation required")
            title.setStyleSheet("font-weight: 700; font-size: 15px;")
            layout.addWidget(title)

            body = QLabel(format_confirmation_request(request))
            body.setObjectName("ritualistConfirmationBody")
            body.setAccessibleName("Confirmation details")
            body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            body.setWordWrap(True)
            layout.addWidget(body)

            if remember_scope_text:
                remember_scope = QLabel(f"Remember scope: {remember_scope_text}")
                remember_scope.setObjectName("ritualistRememberScope")
                remember_scope.setAccessibleName("Remember approval scope")
                remember_scope.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                remember_scope.setWordWrap(True)
                layout.addWidget(remember_scope)

            buttons = QDialogButtonBox()
            proceed = QPushButton(approve_label or _proceed_label(request))
            proceed.setObjectName("ritualistProceedButton")
            proceed.setAccessibleName(proceed.text())
            skip = QPushButton("Skip if supported")
            skip.setObjectName("ritualistSkipButton")
            skip.setEnabled(False)
            skip.setToolTip("This step cannot be skipped safely in v0.1.")
            cancel = QPushButton(negative_label or "Not now")
            cancel.setObjectName("ritualistCancelButton")
            cancel.setAccessibleName(cancel.text())
            buttons.addButton(proceed, QDialogButtonBox.ButtonRole.AcceptRole)
            buttons.addButton(skip, QDialogButtonBox.ButtonRole.ActionRole)
            if remember_scope_text:
                remember = QPushButton("Always allow this exact scope")
                remember.setObjectName("ritualistRememberButton")
                remember.setAccessibleName("Always allow this exact scope")
                remember.setAccessibleDescription(remember_scope_text)
                buttons.addButton(remember, QDialogButtonBox.ButtonRole.ActionRole)
            buttons.addButton(cancel, QDialogButtonBox.ButtonRole.RejectRole)
            layout.addWidget(buttons)

            answered = False

            def answer(value: bool | ConfirmationDecision) -> None:
                nonlocal answered
                if answered:
                    return
                answered = True
                on_decision(value)
                dialog.close()

            proceed.clicked.connect(
                lambda: answer(
                    ConfirmationDecision.allow_once() if remember_scope_text else True
                )
            )
            if remember_scope_text:
                remember.clicked.connect(lambda: answer(ConfirmationDecision.always_allow_local()))
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
            approve_label: str | None = None,
            negative_label: str = "Not now",
            remember_scope_text: str | None = None,
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
    return confirmation_action_label(request)


def confirmation_action_label(request: ConfirmationRequest | str) -> str:
    if isinstance(request, str):
        return _explicit_action_text(request) or "Allow once"

    for candidate in (request.step_name, request.prompt):
        label = _explicit_action_text(candidate)
        if label:
            return label

    action = request.action.strip().casefold()
    if action in {"app.launch", "process.launch"}:
        target = _first_text(
            request.target_text,
            request.window_title,
            request.target_identity,
            request.recipe_name,
        )
        if target:
            return f"Launch {target}"
    if action in {"browser.open", "app.open", "file.open"}:
        target = _first_text(
            request.target_text,
            request.browser_title,
            request.window_title,
            request.target_identity,
        )
        if target:
            return f"Open {target}"
    if action in {"desktop.click_text", "browser.click_text"} and request.target_text:
        return f"Click {_clean_label(request.target_text)}"
    if action in {"desktop.focus_window", "window.focus"}:
        target = _first_text(request.window_title, request.target_identity, request.target_text)
        if target:
            return f"Focus {target}"
    return "Allow once"


def remember_scope_text(scope: RememberedApprovalScope | None) -> str | None:
    if scope is None or not can_remember_approval(scope):
        return None
    data = scope.to_dict()
    keys = (
        "recipe_or_intent_id",
        "content_hash",
        "step_id",
        "action_or_primitive_id",
        "resolved_target_identity",
        "target_context",
        "target_text",
        "target_control",
        "target_role",
        "target_test_id",
        "local_user",
        "local_device",
        "target_scope",
        "target_application",
        "risk_level",
        "target_ambiguous",
        "source_trust",
    )
    return "; ".join(f"{key}={data[key]}" for key in keys if data.get(key) != "")


_VERBS = frozenset(
    {
        "activate",
        "allow",
        "click",
        "close",
        "focus",
        "install",
        "launch",
        "locate",
        "open",
        "press",
        "run",
        "select",
        "start",
        "stop",
        "update",
    }
)
_GENERIC_ACTION_LABELS = frozenset(
    {
        "allow once",
        "click target",
        "click test id",
        "confirm",
        "confirmation required",
        "proceed",
        "review",
        "run step",
        "run this step",
    }
)


def _explicit_action_text(value: str | None) -> str:
    text = _clean_label(value)
    if not text:
        return ""
    normalized = text.casefold()
    if normalized in _GENERIC_ACTION_LABELS:
        return ""
    words = normalized.split()
    if len(words) < 2 or words[0] not in _VERBS:
        return ""
    return text


def _first_text(*values: str | None) -> str:
    for value in values:
        text = _clean_label(value)
        if text:
            return text
    return ""


def _clean_label(value: str | None) -> str:
    return " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split()).rstrip(" .?!:")
