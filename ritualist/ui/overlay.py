from __future__ import annotations

import itertools

from PySide6.QtCore import QObject, QRect, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget

from ritualist.overlay import ActionPreview, ScreenRect


class OverlayWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._label = ""
        self._target_rect: QRect | None = None
        self._elapsed_seconds = 0
        self._is_waiting = False
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        transparent_input = getattr(Qt.WindowType, "WindowTransparentForInput", None)
        if transparent_input is not None:
            flags |= transparent_input
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self._wait_timer = QTimer(self)
        self._wait_timer.setInterval(1000)
        self._wait_timer.timeout.connect(self._tick_wait)

    def show_preview(self, preview: ActionPreview) -> None:
        self._wait_timer.stop()
        self._is_waiting = False
        self._elapsed_seconds = 0
        self._label = preview.label
        rect = preview.region.rect if preview.region else None
        self._position_for_rect(rect)
        self.show()
        self.raise_()
        self.update()

    def show_wait(self, label: str) -> None:
        self._label = label
        self._target_rect = None
        self._elapsed_seconds = 0
        self._is_waiting = True
        self._position_hud()
        self.show()
        self.raise_()
        self.update()
        self._wait_timer.start()

    def hide_overlay(self) -> None:
        self._wait_timer.stop()
        self.hide()

    def _tick_wait(self) -> None:
        self._elapsed_seconds += 1
        self.update()

    def _position_for_rect(self, rect: ScreenRect | None) -> None:
        if rect is None or not rect.is_valid:
            self._position_hud()
            return
        margin = 8
        label_height = 34
        self.setGeometry(
            rect.x - margin,
            rect.y - label_height,
            rect.width + margin * 2,
            rect.height + label_height + margin,
        )
        self._target_rect = QRect(margin, label_height, rect.width, rect.height)

    def _position_hud(self) -> None:
        self._target_rect = None
        screen = QApplication.primaryScreen()
        if screen is None:
            self.setGeometry(80, 80, 360, 80)
            return
        area = screen.availableGeometry()
        width = min(420, max(260, area.width() // 3))
        height = 80
        self.setGeometry(area.x() + (area.width() - width) // 2, area.y() + 32, width, height)

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt override.
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setFont(QFont("Segoe UI", 10))
        pen = QPen(QColor(0, 170, 255), 3)
        painter.setPen(pen)
        if self._target_rect is not None:
            painter.drawRoundedRect(self._target_rect, 4, 4)

        text = self._label
        if self._is_waiting:
            text = f"{text} {self._elapsed_seconds}s"
        label_rect = QRect(0, 0, self.width(), 28 if self._target_rect else self.height())
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(10, 16, 22, 215))
        painter.drawRoundedRect(label_rect.adjusted(1, 1, -1, -1), 6, 6)
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(label_rect.adjusted(10, 0, -10, 0), Qt.AlignmentFlag.AlignVCenter, text)


class QtOverlayController(QObject):
    _preview_requested = Signal(object, int)
    _wait_started = Signal(str, int)
    _wait_stopped = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self._window = OverlayWindow()
        self._ids = itertools.count(1)
        self._preview_ids = itertools.count(1)
        self._active_preview_id: int | None = None
        self._active_wait_id: int | None = None
        self._preview_requested.connect(self._show_preview)
        self._wait_started.connect(self._show_wait)
        self._wait_stopped.connect(self._stop_wait)

    def show_preview(self, preview: ActionPreview, *, duration_ms: int) -> None:
        self._preview_requested.emit(preview, duration_ms)

    def start_wait(self, label: str):
        wait_id = next(self._ids)
        self._wait_started.emit(label, wait_id)
        return _QtWaitOverlayHandle(self, wait_id)

    @Slot(object, int)
    def _show_preview(self, preview: ActionPreview, duration_ms: int) -> None:
        preview_id = next(self._preview_ids)
        self._active_preview_id = preview_id
        self._window.show_preview(preview)
        if duration_ms >= 0:
            QTimer.singleShot(duration_ms, lambda: self._hide_preview(preview_id))

    @Slot(str, int)
    def _show_wait(self, label: str, wait_id: int) -> None:
        self._active_preview_id = None
        self._active_wait_id = wait_id
        self._window.show_wait(label)

    @Slot(int)
    def _stop_wait(self, wait_id: int) -> None:
        if self._active_wait_id != wait_id:
            return
        self._active_wait_id = None
        self._window.hide_overlay()

    def _hide_preview(self, preview_id: int) -> None:
        if self._active_preview_id != preview_id or self._active_wait_id is not None:
            return
        self._active_preview_id = None
        self._window.hide_overlay()


class _QtWaitOverlayHandle:
    def __init__(self, controller: QtOverlayController, wait_id: int) -> None:
        self._controller = controller
        self._wait_id = wait_id
        self._closed = False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._controller._wait_stopped.emit(self._wait_id)
