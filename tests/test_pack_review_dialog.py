from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from setpiece.home.pack_review import PackImportReview, PackReviewAction, PackReviewDecision
from setpiece.ui.pack_review_dialog import PackImportReviewDialog


def test_pack_review_dialog_shows_review_data_and_blocks_enable() -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    review = PackImportReview(
        pack_name="Blocked Pack",
        pack_version="1.0.0",
        author="Local Author",
        actions=(
            PackReviewAction(
                action_name="desktop.click_text",
                side_effect_level="risky",
                side_effect_label="Risky",
                required_capabilities=("windows_uia",),
                safety_warnings=("Requires window_title_contains",),
                blocked_by_policy=True,
            ),
        ),
        required_variables=("target_window",),
        required_capabilities=("windows_uia",),
        safety_warnings=("Requires window_title_contains",),
        readme="# Blocked Pack\nManual review required.",
        policy_failures=(
            "Action 'desktop.click_text' is blocked by primitive policy "
            "(uia.element.click_text: blocked).",
        ),
    )

    dialog = PackImportReviewDialog(review)

    assert app is not None
    assert dialog.run_doctor_button.text() == "Run Doctor"
    assert dialog.dry_run_button.text() == "Dry Run"
    assert dialog.enable_button.text() == "Enable"
    assert dialog.cancel_button.text() == "Cancel"
    assert dialog.enable_button.isEnabled() is False
    assert dialog.actions_table.rowCount() == 1
    assert dialog.actions_table.item(0, 0).text() == "desktop.click_text"
    assert dialog.actions_table.item(0, 1).text() == "Risky"
    assert "target_window" in dialog.variables_text.toPlainText()
    assert "windows_uia" in dialog.capabilities_text.toPlainText()
    assert "Requires window_title_contains" in dialog.warnings_text.toPlainText()
    assert "blocked by primitive policy" in dialog.warnings_text.toPlainText()
    assert "# Blocked Pack" in dialog.readme_text.toPlainText()

    dialog.enable_button.click()

    assert dialog.selected_action is PackReviewDecision.CANCEL

    dialog.close()


@pytest.mark.parametrize(
    ("button_name", "expected"),
    [
        ("run_doctor_button", PackReviewDecision.RUN_DOCTOR),
        ("dry_run_button", PackReviewDecision.DRY_RUN),
        ("enable_button", PackReviewDecision.ENABLE),
        ("cancel_button", PackReviewDecision.CANCEL),
    ],
)
def test_pack_review_dialog_records_selected_button(
    button_name: str,
    expected: PackReviewDecision,
) -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    review = PackImportReview(
        pack_name="Safe Pack",
        actions=(
            PackReviewAction(
                action_name="wait.seconds",
                side_effect_level="read_only",
                side_effect_label="Read only",
            ),
        ),
    )
    dialog = PackImportReviewDialog(review)

    assert app is not None
    getattr(dialog, button_name).click()

    assert dialog.selected_action is expected
    if expected is PackReviewDecision.CANCEL:
        assert dialog.result() == QtWidgets.QDialog.DialogCode.Rejected
    else:
        assert dialog.result() == QtWidgets.QDialog.DialogCode.Accepted

    dialog.close()
