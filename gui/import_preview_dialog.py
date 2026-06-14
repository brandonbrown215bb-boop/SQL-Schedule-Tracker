# gui/import_preview_dialog.py
"""Import preview dialog — shows what an import will change before applying.

Sprint 2: Data Integrity & Audit — Import safety: diff + staging.
"""
from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class ImportPreviewDialog(QDialog):
    """Modal dialog showing import diff before applying.

    Displays:
    - Summary of new/updated/unchanged rows
    - Scrollable list of changes grouped by COM number
    - Import / Cancel buttons

    Attributes:
        approved: True if user clicked Import.
    """

    def __init__(self, diff, parent=None):
        """
        Args:
            diff: An ImportDiff object from automation.import_preview.
            parent: Parent widget.
        """
        super().__init__(parent)
        self.approved = False
        self._diff = diff
        self._setup_ui()

    def _setup_ui(self):
        self.setWindowTitle("Import Preview")
        self.setMinimumSize(600, 500)
        self.resize(800, 600)

        layout = QVBoxLayout(self)

        # Header
        header = QLabel(f"Import Preview — {self._diff.summary}")
        header.setFont(QFont("", 12, QFont.Bold))
        layout.addWidget(header)

        # File info
        file_label = QLabel(f"Source: {self._diff.csv_path}")
        file_label.setStyleSheet("color: gray;")
        layout.addWidget(file_label)

        # Splitter: left = change list, right = detail panel
        splitter = QSplitter(Qt.Horizontal)

        # Left: change summary list
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setAlignment(Qt.AlignTop)

        # New rows
        if self._diff.new_rows:
            section_label = QLabel(f"New Units ({len(self._diff.new_rows)})")
            section_label.setStyleSheet("font-weight: bold; color: green; padding-top: 8px;")
            scroll_layout.addWidget(section_label)

            for row_diff in self._diff.new_rows:
                row_widget = self._create_row_widget(row_diff, QColor(220, 255, 220))
                scroll_layout.addWidget(row_widget)

        # Updated rows
        if self._diff.updated_rows:
            section_label = QLabel(f"Updated Units ({len(self._diff.updated_rows)})")
            section_label.setStyleSheet("font-weight: bold; color: #B8860B; padding-top: 8px;")
            scroll_layout.addWidget(section_label)

            for row_diff in self._diff.updated_rows:
                row_widget = self._create_row_widget(row_diff, QColor(255, 255, 200))
                scroll_layout.addWidget(row_widget)

        # Unchanged rows (collapsed)
        if self._diff.unchanged_rows:
            section_label = QLabel(f"Unchanged ({len(self._diff.unchanged_rows)})")
            section_label.setStyleSheet("font-weight: bold; color: gray; padding-top: 8px;")
            scroll_layout.addWidget(section_label)

            # Show first 10 only
            shown = self._diff.unchanged_rows[:10]
            for row_diff in shown:
                row_label = QLabel(f"  COM {row_diff.com_number}")
                row_label.setStyleSheet("color: gray;")
                scroll_layout.addWidget(row_label)
            if len(self._diff.unchanged_rows) > 10:
                more = QLabel(f"  ... and {len(self._diff.unchanged_rows) - 10} more")
                more.setStyleSheet("color: gray; font-style: italic;")
                scroll_layout.addWidget(more)

        # Errors
        if self._diff.errors:
            section_label = QLabel(f"Errors ({len(self._diff.errors)})")
            section_label.setStyleSheet("font-weight: bold; color: red; padding-top: 8px;")
            scroll_layout.addWidget(section_label)

            for row_diff in self._diff.errors:
                row_widget = self._create_row_widget(row_diff, QColor(255, 220, 220))
                scroll_layout.addWidget(row_widget)

        # If no changes at all
        if not self._diff.new_rows and not self._diff.updated_rows and not self._diff.errors:
            no_changes = QLabel("No changes detected — import would not modify any data.")
            no_changes.setStyleSheet("padding: 20px; color: gray; font-style: italic;")
            scroll_layout.addWidget(no_changes)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        left_layout.addWidget(scroll)

        splitter.addWidget(left_widget)

        # Right: detail panel (shows changes for selected row)
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(8, 0, 0, 0)

        self._detail_label = QLabel("Select a row to see details")
        self._detail_label.setFont(QFont("", 10, QFont.Bold))
        right_layout.addWidget(self._detail_label)

        self._detail_text = QTextEdit()
        self._detail_text.setReadOnly(True)
        self._detail_text.setPlaceholderText("Click a row on the left to view its changes.")
        right_layout.addWidget(self._detail_text)

        splitter.addWidget(right_widget)
        splitter.setSizes([400, 300])

        layout.addWidget(splitter, 1)

        # Button bar
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        total_changes = self._diff.total_changes
        import_btn = QPushButton(f"Import ({total_changes} changes)")
        import_btn.setDefault(True)
        import_btn.clicked.connect(self._on_import)
        if total_changes == 0:
            import_btn.setEnabled(False)
        btn_layout.addWidget(import_btn)

        layout.addLayout(btn_layout)

    def _create_row_widget(self, row_diff, bg_color: QColor) -> QWidget:
        """Create a clickable widget for a single row diff."""
        widget = QWidget()
        widget.setStyleSheet(
            f"background-color: rgb({bg_color.red()},{bg_color.green()},{bg_color.blue()}); "
            "border-radius: 3px; margin: 2px;"
        )
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(8, 4, 8, 4)

        # COM number
        com_label = QLabel(f"COM {row_diff.com_number}")
        com_label.setFont(QFont("", 10, QFont.Bold))
        com_label.setFixedWidth(120)
        layout.addWidget(com_label)

        # Change count / status
        if row_diff.status == "new":
            status_label = QLabel("NEW")
            status_label.setStyleSheet("color: green; font-weight: bold;")
        elif row_diff.status == "updated":
            status_label = QLabel(f"{row_diff.change_count} field(s)")
            status_label.setStyleSheet("color: #B8860B; font-weight: bold;")
        elif row_diff.status == "error":
            status_label = QLabel("ERROR")
            status_label.setStyleSheet("color: red; font-weight: bold;")
        else:
            status_label = QLabel("unchanged")
            status_label.setStyleSheet("color: gray;")
        layout.addWidget(status_label)

        layout.addStretch()

        # Clickable: store row_diff for detail panel
        widget.mousePressEvent = lambda e, rd=row_diff: self._show_row_detail(rd)
        widget.setCursor(Qt.PointingHandCursor)

        return widget

    def _show_row_detail(self, row_diff):
        """Show detailed changes for a row in the detail panel."""
        self._detail_label.setText(f"COM {row_diff.com_number} — {row_diff.status}")

        if row_diff.status == "unchanged":
            self._detail_text.setPlainText(f"COM {row_diff.com_number} has no changes.")
            return

        lines = []
        for change in row_diff.changes:
            field = change["field"]
            old = change["old"]
            new = change["new"]
            if old is None or (isinstance(old, str) and old.strip() == ""):
                lines.append(f"  + {field}: (empty) → {new}")
            elif new is None or (isinstance(new, str) and new.strip() == ""):
                lines.append(f"  - {field}: {old} → (empty)")
            else:
                lines.append(f"  ~ {field}: {old} → {new}")

        self._detail_text.setPlainText(
            f"COM {row_diff.com_number}\n\n" + "\n".join(lines) if lines else "No changes."
        )

    def _on_import(self):
        """User approved the import."""
        self.approved = True
        self.accept()
