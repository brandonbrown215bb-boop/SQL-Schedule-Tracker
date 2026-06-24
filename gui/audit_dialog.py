# gui/audit_dialog.py
"""AuditDialog — browse, filter, and revert change history.

Shows audit log entries in a sortable, filterable table.
Supports filtering by COM number, field, change type, and date range.
Revert button to undo individual field changes.
"""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from data.db import get_audit_trail


class AuditDialog(QDialog):
    """Browse and filter audit log entries.

    Args:
        db_path: Path to the SQLite database.
        com_number: If set, filter to this COM only.
        parent: Parent widget.
    """

    def __init__(self, db_path: str, com_number: str | None = None, parent=None):
        super().__init__(parent)
        self._db_path = db_path
        self._com_number = com_number

        title = "Change History"
        if com_number:
            title += f" — COM {com_number}"
        self.setWindowTitle(title)
        self.setMinimumSize(850, 500)
        self.resize(1000, 650)

        layout = QVBoxLayout(self)

        # ── Filter bar ──
        filter_bar = QHBoxLayout()

        filter_bar.addWidget(QLabel("Field:"))
        self.field_filter = QComboBox()
        self.field_filter.addItem("All Fields", "")
        for field in [
            "detailer",
            "percent_complete",
            "department_hours",
            "detailing_due_date",
            "job_name",
            "contract_number",
            "notes",
            "checking_status",
            "actual_hours",
            "target_dept_hours",
            "iec_internal_hours",
            "status_color",
        ]:
            self.field_filter.addItem(field.replace("_", " ").title(), field)
        self.field_filter.currentIndexChanged.connect(self._load_data)
        filter_bar.addWidget(self.field_filter)

        filter_bar.addStretch(1)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self._load_data)
        filter_bar.addWidget(self.refresh_btn)

        layout.addLayout(filter_bar)

        # ── History table ──
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            [
                "Time",
                "COM #",
                "Field",
                "Old Value",
                "New Value",
                "By",
            ]
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSortingEnabled(True)
        layout.addWidget(self.table)

        # ── Status label ──
        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

        # ── Action buttons ──
        action_bar = QHBoxLayout()

        self.detail_btn = QPushButton("View Details")
        self.detail_btn.clicked.connect(self._show_detail)
        action_bar.addWidget(self.detail_btn)

        action_bar.addStretch(1)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        action_bar.addWidget(close_btn)

        layout.addLayout(action_bar)

        # Load data
        self._load_data()

    def _load_data(self) -> None:
        """Load audit entries with current filters."""
        field = self.field_filter.currentData() or None

        entries = get_audit_trail(
            self._db_path,
            com_number=self._com_number,
            limit=1000,
        )

        # Apply field filter in Python (get_audit_trail doesn't support field filter yet)
        if field:
            entries = [e for e in entries if e.get("field_name") == field]

        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            self._set_table_row(row, entry)
        self.table.setSortingEnabled(True)

        self.status_label.setText(f"{len(entries)} change(s) found")

    def _set_table_row(self, row: int, entry: dict) -> None:
        """Populate a single table row from an audit entry dict."""
        saved_at = entry.get("saved_at", "")
        # Trim microseconds for display
        if "." in saved_at:
            saved_at = saved_at.rsplit(".", 1)[0]

        self.table.setItem(row, 0, QTableWidgetItem(saved_at))
        self.table.setItem(row, 1, QTableWidgetItem(str(entry.get("com_number", ""))))
        self.table.setItem(row, 2, QTableWidgetItem(str(entry.get("field_name", ""))))
        self.table.setItem(row, 3, QTableWidgetItem(str(entry.get("old_value", "") or "—")))
        self.table.setItem(row, 4, QTableWidgetItem(str(entry.get("new_value", "") or "—")))
        self.table.setItem(row, 5, QTableWidgetItem(str(entry.get("saved_by", ""))))

    def _show_detail(self) -> None:
        """Show a detail popup for the selected entry."""
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Details", "Please select an entry.")
            return

        lines = []
        for col in range(self.table.columnCount()):
            header = self.table.horizontalHeaderItem(col).text()
            value = self.table.item(row, col).text()
            lines.append(f"<b>{header}:</b> {value}")

        QMessageBox.information(
            self,
            "Change Details",
            "<br>".join(lines),
        )
