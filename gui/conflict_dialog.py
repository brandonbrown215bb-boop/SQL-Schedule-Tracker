# gui/conflict_dialog.py
"""Conflict resolution dialog for multi-user revision conflicts.

Shows a side-by-side diff of local vs. remote unit values when
:class:`sync.revision_store.RevisionConflictError` is raised during save.
"""

from __future__ import annotations

from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

# Fields displayed in the conflict diff — same set as unit_fingerprint payload.
_CONFLICT_FIELDS = [
    ("Job Name", "job_name"),
    ("Contract Number", "contract_number"),
    ("Description", "description"),
    ("Detailer", "detailer"),
    ("Checking Status", "checking_status"),
    ("Dept Hours", "department_hours"),
    ("Actual Hours", "actual_hours"),
    ("Target Dept Hours", "target_department_hours"),
    ("IEC Internal Hours", "iec_internal_hours"),
    ("Percent Complete", "percent_complete"),
    ("Detailing Start Date", "unit_detailing_start_date"),
    ("Moved to Checking Date", "unit_moved_to_checking_date"),
    ("Detailing Completion Date", "unit_detailing_completion_date"),
    ("Dept Due Date (prev)", "dept_due_date_previous"),
    ("Detailing Due Date", "detailing_due_date"),
    ("Build Date", "build_date"),
]


class ConflictDialog(QDialog):
    """Shows a side-by-side diff of local vs. remote unit values.

    The user may choose:
      - **Overwrite**: ignore the remote revision and force-save local values.
      - **Reload**: discard local changes and reload the unit from cache.
      - **Cancel**: keep the local form as-is.

    Results are communicated via the instance attributes :attr:`overwrite`
    and :attr:`reload`.
    """

    overwrite: bool = False
    reload: bool = False

    def __init__(
        self,
        com_number: str,
        local_values: dict,
        remote_values: dict,
        modified_by: str,
        modified_at: str,
        parent=None,
        theme_name: str = "light",
    ):
        super().__init__(parent)
        self._theme_name = theme_name
        from gui.theme import apply_theme
        apply_theme(self, theme_name)
        self.setWindowTitle(f"Save Conflict — COM {com_number}")
        self.setMinimumSize(650, 450)
        self.setModal(True)

        self.overwrite = False
        self.reload = False

        layout = QVBoxLayout(self)

        # ── Header ────────────────────────────────────────────────────
        header = QLabel(
            f"<b>COM {com_number}</b> was modified by "
            f"<b>{modified_by}</b> at {modified_at}.<br><br>"
            "Your local changes conflict with the saved version. "
            "Choose how to resolve:"
        )
        header.setWordWrap(True)
        layout.addWidget(header)

        # ── Diff table ────────────────────────────────────────────────
        table = QTableWidget()
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(["Field", "Your Value (Local)", f"Saved by {modified_by}"])
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionMode(QTableWidget.NoSelection)

        # Populate rows — only show fields that differ or both have values
        rows: list[tuple[str, str, str]] = []
        for label, key in _CONFLICT_FIELDS:
            local_val = _format_value(local_values.get(key))
            remote_val = _format_value(remote_values.get(key))
            if local_val != remote_val:
                rows.append((label, local_val, remote_val))

        if not rows:
            # Fallback: show all fields
            for label, key in _CONFLICT_FIELDS:
                local_val = _format_value(local_values.get(key))
                remote_val = _format_value(remote_values.get(key))
                rows.append((label, local_val, remote_val))

        table.setRowCount(len(rows))
        for i, (label, local_val, remote_val) in enumerate(rows):
            table.setItem(i, 0, QTableWidgetItem(label))
            item_local = QTableWidgetItem(local_val)
            item_remote = QTableWidgetItem(remote_val)
            if local_val != remote_val:
                from PyQt5.QtGui import QBrush

                from gui.theme import THEMES
                tokens = THEMES.get(self._theme_name, THEMES["light"])
                item_local.setBackground(QBrush(QColor(tokens["bg_selected"])))
                item_remote.setBackground(QBrush(QColor(tokens["bg_selected"])))
                item_local.setForeground(QBrush(QColor(tokens["text_primary"])))
                item_remote.setForeground(QBrush(QColor(tokens["text_primary"])))
            table.setItem(i, 1, item_local)
            table.setItem(i, 2, item_remote)

        layout.addWidget(table)

        # ── Buttons ───────────────────────────────────────────────────
        btn_box = QDialogButtonBox(self)

        overwrite_btn = QPushButton("Overwrite with My Changes")
        overwrite_btn.setToolTip("Ignore the remote revision and save your values over the top.")
        btn_box.addButton(overwrite_btn, QDialogButtonBox.ActionRole)

        reload_btn = QPushButton("Reload Remote Version")
        reload_btn.setToolTip(
            "Discard your local changes and reload the unit from the shared workbook."
        )
        btn_box.addButton(reload_btn, QDialogButtonBox.ActionRole)

        cancel_btn = QPushButton("Cancel")
        btn_box.addButton(cancel_btn, QDialogButtonBox.RejectRole)

        # Connect via clicked signal to distinguish which button was pressed.
        # NOTE: Do NOT connect btn_box.accepted — we use ActionRole (not AcceptRole)
        # for overwrite/reload so the button box's accepted/rejected signals
        # are only triggered by the RejectRole cancel button.
        overwrite_btn.clicked.connect(self._on_overwrite)
        reload_btn.clicked.connect(self._on_reload)
        cancel_btn.clicked.connect(self.reject)

        layout.addWidget(btn_box)

    def _on_overwrite(self):
        """User chose to force-save their local values."""
        ret = QMessageBox.question(
            self,
            "Confirm Overwrite",
            "This will overwrite the remote version of this unit. "
            "The other user's changes will be lost.\n\nContinue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ret == QMessageBox.Yes:
            self.overwrite = True
            self.accept()

    def _on_reload(self):
        """User chose to discard local changes and reload from remote."""
        ret = QMessageBox.question(
            self,
            "Confirm Reload",
            "Your local changes will be discarded and the remote version loaded.\n\nContinue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ret == QMessageBox.Yes:
            self.reload = True
            self.accept()


def _format_value(val: object) -> str:
    """Format a field value for display in the diff table."""
    if val is None:
        return "—"
    if isinstance(val, float):
        return f"{val:.2f}"
    if isinstance(val, bool):
        return "Yes" if val else "No"
    return str(val)
