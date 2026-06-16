from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QInputDialog,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ritualist.errors import RecipeValidationError
from ritualist.recipe_step_builder import (
    RecipeStepBuilder,
    RecipeStepCatalog,
    filter_variable_updates_for_step,
    side_effect_label,
)



BOOL_FIELDS = {
    "exact",
    "keep_open",
    "loop",
    "muted",
    "new_window",
    "optional",
    "play",
    "requires_confirmation",
    "wait",
}
TEXT_AREA_FIELDS = {"args", "env", "keys"}


class AddStepDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        catalog: RecipeStepCatalog | None = None,
        builder: RecipeStepBuilder | None = None,
        capture_controller: object | None = None,
        recipe: object | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Step")
        self.catalog = catalog or RecipeStepCatalog.default()
        self.builder = builder or RecipeStepBuilder(self.catalog)
        self.capture_controller = capture_controller
        self.recipe = recipe
        self._field_widgets: dict[str, QWidget] = {}
        self._required_fields: tuple[str, ...] = ()
        self._optional_fields: tuple[str, ...] = ()
        self._step_data: dict[str, Any] | None = None
        self._variable_updates: dict[str, str] = {}

        layout = QVBoxLayout(self)

        picker_row = QHBoxLayout()
        self.category_combo = QComboBox()
        self.category_combo.addItems(self.catalog.categories())
        self.category_combo.currentTextChanged.connect(self._populate_actions)
        self.action_combo = QComboBox()
        self.action_combo.currentTextChanged.connect(self._rebuild_fields)
        picker_row.addWidget(QLabel("Category"))
        picker_row.addWidget(self.category_combo)
        picker_row.addWidget(QLabel("Action"))
        picker_row.addWidget(self.action_combo)
        layout.addLayout(picker_row)

        self.safety_label = QLabel("")
        self.safety_label.setWordWrap(True)
        layout.addWidget(self.safety_label)

        self.required_form = QFormLayout()
        layout.addLayout(self.required_form)

        self.optional_toggle = QPushButton("Show optional fields")
        self.optional_toggle.setCheckable(True)
        self.optional_toggle.toggled.connect(self._toggle_optional_fields)
        layout.addWidget(self.optional_toggle)

        self.optional_fields_container = QWidget()
        self.optional_form = QFormLayout(self.optional_fields_container)
        self.optional_fields_container.setVisible(False)
        layout.addWidget(self.optional_fields_container)

        self.error_label = QLabel("")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        if self.category_combo.count():
            self._populate_actions(self.category_combo.currentText())

    @property
    def step_data(self) -> dict[str, Any] | None:
        return self._step_data

    @property
    def variable_updates(self) -> dict[str, str]:
        if self._step_data is not None:
            return filter_variable_updates_for_step(self._step_data, self._variable_updates)
        return dict(self._variable_updates)

    def accept(self) -> None:
        try:
            self._step_data = self.builder.build_step(
                self.action_combo.currentText(),
                self._collect_values(self._required_fields),
                self._collect_values(self._optional_fields),
            )
        except (RecipeValidationError, ValueError, TypeError) as exc:
            self.error_label.setText(str(exc))
            QMessageBox.warning(self, "Invalid Step", str(exc))
            return
        self.error_label.setText("")
        super().accept()

    def _populate_actions(self, category: str) -> None:
        current = self.action_combo.currentText()
        self.action_combo.blockSignals(True)
        self.action_combo.clear()
        for entry in self.catalog.actions(category=category):
            self.action_combo.addItem(entry.action_name)
        index = self.action_combo.findText(current)
        if index >= 0:
            self.action_combo.setCurrentIndex(index)
        self.action_combo.blockSignals(False)
        self._rebuild_fields(self.action_combo.currentText())

    def _rebuild_fields(self, action_name: str) -> None:
        self._clear_form(self.required_form)
        self._clear_form(self.optional_form)
        self._field_widgets.clear()
        if not action_name:
            return
        entry = self.catalog.entry(action_name)
        self._required_fields = entry.required_fields
        self._optional_fields = entry.optional_fields
        self.safety_label.setText(side_effect_label(entry))
        for field_name in self._required_fields:
            self._add_field(self.required_form, field_name, action_name=action_name)
        for field_name in self._optional_fields:
            self._add_field(self.optional_form, field_name, action_name=action_name)
        self._set_play_confirmation_hint(action_name)

    def _add_field(self, form: QFormLayout, field_name: str, *, action_name: str) -> None:
        widget: QWidget
        if field_name in BOOL_FIELDS:
            widget = QCheckBox()
        elif field_name in TEXT_AREA_FIELDS:
            editor = QPlainTextEdit()
            editor.setFixedHeight(64)
            widget = editor
        else:
            widget = QLineEdit()
        self._field_widgets[field_name] = widget
        helper = self._helper_button(field_name, widget, action_name=action_name)
        if helper is None:
            form.addRow(field_name, widget)
            return
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(widget)
        layout.addWidget(helper)
        form.addRow(field_name, row)

    def _collect_values(self, field_names: tuple[str, ...]) -> dict[str, object]:
        values: dict[str, object] = {}
        for field_name in field_names:
            widget = self._field_widgets.get(field_name)
            if widget is None:
                continue
            if isinstance(widget, QCheckBox):
                values[field_name] = widget.isChecked()
            elif isinstance(widget, QPlainTextEdit):
                values[field_name] = widget.toPlainText().strip()
            elif isinstance(widget, QLineEdit):
                values[field_name] = widget.text().strip()
        return values

    def _toggle_optional_fields(self, checked: bool) -> None:
        self.optional_fields_container.setVisible(checked)
        self.optional_toggle.setText("Hide optional fields" if checked else "Show optional fields")

    def _set_play_confirmation_hint(self, action_name: str) -> None:
        widget = self._field_widgets.get("requires_confirmation")
        if not isinstance(widget, QCheckBox):
            return
        if action_name == "desktop.click_text":
            widget.setToolTip(
                "Clicking visible text exactly equal to Play is saved with explicit confirmation."
            )

    def _helper_button(
        self,
        field_name: str,
        widget: QWidget,
        *,
        action_name: str,
    ) -> QPushButton | None:
        if not isinstance(widget, QLineEdit):
            return None
        if field_name == "command" and action_name == "app.launch":
            button = QPushButton("Browse App")
            button.clicked.connect(lambda: self._capture_path(widget, "app"))
            return button
        if field_name == "path":
            button = QPushButton("Browse Folder" if action_name == "assert.path_exists" else "Browse File")
            kind = "folder" if action_name == "assert.path_exists" else "file"
            button.clicked.connect(lambda: self._capture_path(widget, kind))
            return button
        if field_name == "cwd":
            button = QPushButton("Browse Folder")
            button.clicked.connect(lambda: self._capture_path(widget, "folder"))
            return button
        if field_name in {"title_contains", "window_title_contains"}:
            button = QPushButton("Use Foreground")
            button.clicked.connect(lambda: self._capture_foreground_title(widget))
            return button
        if field_name == "text" and action_name == "desktop.click_text":
            button = QPushButton("Inspect Text")
            button.clicked.connect(lambda: self._inspect_text(widget))
            return button
        return None

    def _capture_path(self, widget: QLineEdit, kind: str) -> None:
        try:
            controller = self._capture_controller()
            if kind == "app":
                capture = controller.browse_app_path(recipe=self.recipe)
            elif kind == "folder":
                capture = controller.browse_folder_path(recipe=self.recipe)
            else:
                capture = controller.browse_file_path(recipe=self.recipe)
        except Exception as exc:  # noqa: BLE001 - helper failures are user-facing, not fatal.
            QMessageBox.warning(self, "Capture Failed", str(exc))
            return
        if capture is None:
            return
        widget.setText(capture.recipe_value)
        self._variable_updates.update(capture.variable_update)

    def _capture_foreground_title(self, widget: QLineEdit) -> None:
        try:
            capture = self._capture_controller().pick_foreground_window_title(recipe=self.recipe)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Capture Failed", str(exc))
            return
        widget.setText(capture.recipe_value)
        self._variable_updates.update(capture.variable_update)

    def _inspect_text(self, widget: QLineEdit) -> None:
        window_widget = self._field_widgets.get("window_title_contains")
        window_title = window_widget.text().strip() if isinstance(window_widget, QLineEdit) else ""
        control_widget = self._field_widgets.get("control_type")
        control_type = control_widget.text().strip() if isinstance(control_widget, QLineEdit) else ""
        try:
            inspection = self._capture_controller().inspect_window_text(
                window_title_contains=window_title or None,
                recipe=self.recipe,
                control_type=control_type or None,
            )
            labels = list(inspection.labels)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Inspection Failed", str(exc))
            return
        if not labels:
            QMessageBox.information(self, "Inspection", "No visible labels were found.")
            return
        selected, accepted = QInputDialog.getItem(
            self,
            "Choose Visible Text",
            "Visible text",
            labels,
            0,
            False,
        )
        if not accepted:
            return
        choice = self._capture_controller().choose_visible_text(
            inspection,
            text=selected,
            recipe=self.recipe,
        )
        widget.setText(choice.recipe_text)
        self._variable_updates.update(choice.variable_update)
        confirmation_widget = self._field_widgets.get("requires_confirmation")
        if (
            choice.text.strip().casefold() == "play"
            and isinstance(confirmation_widget, QCheckBox)
        ):
            confirmation_widget.setChecked(True)
        if isinstance(window_widget, QLineEdit) and not window_widget.text().strip():
            window_widget.setText(choice.window_title_contains)

    def _capture_controller(self):
        if self.capture_controller is None:
            from ritualist.adapters import create_default_adapters
            from ritualist.capture_helpers import CaptureHelperController

            from .capture_helpers import QtPathPicker

            self.capture_controller = CaptureHelperController(
                create_default_adapters(),
                path_picker=QtPathPicker(self),
            )
        return self.capture_controller

    def _clear_form(self, form: QFormLayout) -> None:
        while form.count():
            item = form.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
