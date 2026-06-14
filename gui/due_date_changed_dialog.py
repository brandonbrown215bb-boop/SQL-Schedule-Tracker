# gui/due_date_changed_dialog.py
"""Dialog showing units whose detailing_due_date changed during import."""
from datetime import date

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from data.models import Unit


class DueDateChangedDialog(QDialog):
    """Modal dialog listing units whose due date changed after an import."""

    def __init__(
        self,
        changed_units: list[tuple[Unit, date | None]],
        parent=None,
    ):
        """
        Args:
            changed_units: List of (unit, previous_due_date) tuples.
        """
        super().__init__(parent)
        self.setWindowTitle("⚠ Due Dates Changed")
        self.setMinimumSize(650, 400)
        self.resize(700, 450)

        layout = QVBoxLayout(self)

        heading = QLabel(
            "<b>The following units had their detailing due dates changed:</b>"
        )
        heading.setWordWrap(True)
        layout.addWidget(heading)

        # ── Table ──────────────────────────────────────────────────────
        cols = [
            "COM #",
            "Job Name",
            "Detailer",
            "Previous Due Date",
            "New Due Date",
        ]
        self.table = QTableWidget(len(changed_units), len(cols))
        self.table.setHorizontalHeaderLabels(cols)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)

        for row, (unit, prev_date) in enumerate(changed_units):
            # COM
            com_item = QTableWidgetItem(unit.com_number)
            com_item.setData(Qt.UserRole, unit)
            self.table.setItem(row, 0, com_item)

            # Job Name
            self.table.setItem(row, 1, QTableWidgetItem(unit.job_name))

            # Detailer
            detailer = unit.detailer if unit.detailer else "—"
            self.table.setItem(row, 2, QTableWidgetItem(detailer))

            # Previous Due Date
            prev_str = (
                prev_date.strftime("%m/%d/%Y") if prev_date else "—"
            )
            prev_item = QTableWidgetItem(prev_str)
            self.table.setItem(row, 3, prev_item)

            # New Due Date
            new_str = (
                unit.detailing_due_date.strftime("%m/%d/%Y")
                if unit.detailing_due_date
                else "—"
            )
            new_item = QTableWidgetItem(new_str)
            if unit.detailing_due_date != prev_date:
                new_item.setToolTip(
                    f"Changed from {prev_str} to {new_str}"
                )
            self.table.setItem(row, 4, new_item)

        layout.addWidget(self.table)

        # ── Buttons ────────────────────────────────────────────────────
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok)
        btn_box.accepted.connect(self.accept)
        layout.addWidget(btn_box)

        self.changed_units = changed_units
