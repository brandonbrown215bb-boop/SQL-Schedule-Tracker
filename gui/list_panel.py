# gui/list_panel.py
"""List Panel — sortable, filterable table view of all units.

Emits the same `unit_selected(Unit)` signal as CalendarPanel,
so the rest of the app (timeline, edit form) works unchanged.

Toggle between calendar and list views from MainWindow using a
QStackedWidget — both panels live side-by-side and receive the
same refresh() calls.

Usage:
    panel = ListPanel(units)
    panel.unit_selected.connect(main_window.on_unit_selected)
    panel.set_units(all_units)          # initial load
    panel.refresh(all_units)            # after data reload
"""

from __future__ import annotations

from datetime import date, timedelta

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QBrush, QColor, QFont
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from data.models import Unit
from data.loader import unit_fingerprint

# ─── Column Definitions ─────────────────────────────────────────────
# (key, header, width, default_visible)

COLUMN_DEFS: list[tuple[str, str, int, bool]] = [
    ("com_number",              "COM",              70,  True),
    ("detailing_due_date",      "Due Date",         80,  True),
    ("job_name",                "Job Name",         180, True),
    ("detailer",                "Detailer",         100, True),
    ("status_color",            "Status",           50,  True),
    ("percent_complete",        "% Complete",       70,  True),
    ("department_hours",        "Dept Hours",       70,  False),
    ("actual_hours",            "Actual Hours",     70,  False),
    ("target_department_hours", "Target Hrs",       70,  False),
    ("checking_status",         "Checking",         80,  False),
    ("contract_number",         "Contract #",       90,  False),
    ("build_date",              "Build Date",       80,  False),
    ("unit_detailing_start_date", "Start Date",     80,  False),
]


# ─── Status Color Map ───────────────────────────────────────────────

STATUS_COLORS_FALLBACK: dict[str, QColor] = {
    "gray":   QColor(148, 163, 184),
    "yellow": QColor(234, 179, 8),
    "purple": QColor(168, 85, 247),
    "orange": QColor(249, 115, 22),
    "green":  QColor(34, 197, 94),
    "red":    QColor(239, 68, 68),
}

STATUS_LABELS: dict[str, str] = {
    "All": "All Statuses",
    "gray":   "Unassigned",
    "yellow": "In Progress",
    "purple": "Ready for Checking",
    "orange": "Checked & Returned",
    "green":  "Released",
    "red":    "Overdue",
}

SEVERITY_ORDER: dict[str, int] = {
    "red": 0, "orange": 1, "purple": 2, "yellow": 3, "gray": 4, "green": 5,
}


# ─── Filter Presets ─────────────────────────────────────────────────

DATE_FILTER_PRESETS: list[tuple[str, str | None]] = [
    ("All",          None),
    ("Overdue",      "overdue"),
    ("Today",        "today"),
    ("Next 3 Days",  "next_3_days"),
    ("Next 7 Days",  "next_7_days"),
    ("Next 30 Days", "next_30_days"),
    ("This Month",   "this_month"),
    ("Next Month",   "next_month"),
    ("Past 30 Days", "past_30_days"),
]


# ─── UnitListModel ──────────────────────────────────────────────────

class UnitListModel:
    """In-memory model: holds all units, applies filters + sort."""

    def __init__(self, units: list[Unit]):
        self._all_units: list[Unit] = list(units)
        self._filtered_units: list[Unit] = list(units)
        self._visible_columns: list[str] = [
            key for key, _, _, visible in COLUMN_DEFS if visible
        ]

    @property
    def all_units(self) -> list[Unit]:
        return self._all_units

    @property
    def filtered_units(self) -> list[Unit]:
        return self._filtered_units

    @property
    def visible_columns(self) -> list[str]:
        return self._visible_columns

    def set_visible_columns(self, keys: list[str]) -> None:
        if keys:
            self._visible_columns = keys

    # ── Filtering ───────────────────────────────────────────────────

    def apply_filters(
        self,
        status: str = "All",
        detailer: str = "All",
        date_preset: str | None = None,
        com_search: str = "",
    ) -> None:
        """Apply all active filters with AND logic."""
        today = date.today()
        result = list(self._all_units)

        if status != "All":
            result = [u for u in result if u.status_color == status]

        if detailer != "All":
            result = [u for u in result if u.detailer == detailer]

        if date_preset and date_preset != "All":
            result = self._filter_by_date(result, date_preset, today)

        if com_search:
            query = com_search.lower().strip()
            result = [
                u for u in result
                if query in u.com_number.lower()
                or query in u.job_name.lower()
            ]

        self._filtered_units = result

    def _filter_by_date(
        self, units: list[Unit], preset: str, today: date
    ) -> list[Unit]:
        if preset == "overdue":
            return [
                u for u in units
                if u.detailing_due_date is not None
                and u.detailing_due_date < today
            ]
        if preset == "today":
            return [
                u for u in units
                if u.detailing_due_date is not None
                and u.detailing_due_date == today
            ]
        if preset == "next_3_days":
            end = today + timedelta(days=3)
            return [
                u for u in units
                if u.detailing_due_date is not None
                and today <= u.detailing_due_date <= end
            ]
        if preset == "next_7_days":
            end = today + timedelta(days=7)
            return [
                u for u in units
                if u.detailing_due_date is not None
                and today <= u.detailing_due_date <= end
            ]
        if preset == "next_30_days":
            end = today + timedelta(days=30)
            return [
                u for u in units
                if u.detailing_due_date is not None
                and today <= u.detailing_due_date <= end
            ]
        if preset == "this_month":
            return [
                u for u in units
                if u.detailing_due_date is not None
                and u.detailing_due_date.month == today.month
                and u.detailing_due_date.year == today.year
            ]
        if preset == "next_month":
            if today.month < 12:
                next_m = today.month + 1
                next_y = today.year
            else:
                next_m = 1
                next_y = today.year + 1
            return [
                u for u in units
                if u.detailing_due_date is not None
                and u.detailing_due_date.month == next_m
                and u.detailing_due_date.year == next_y
            ]
        if preset == "past_30_days":
            start = today - timedelta(days=30)
            return [
                u for u in units
                if u.detailing_due_date is not None
                and start <= u.detailing_due_date <= today
            ]
        return units

    # ── Sorting ─────────────────────────────────────────────────────

    def sort_by(self, column_key: str, ascending: bool = True) -> None:
        """Sort filtered units in-place by the given column key."""
        if column_key == "status_color":
            def key_func(unit: Unit) -> int:
                return SEVERITY_ORDER.get(unit.status_color, 99)
        elif column_key == "detailing_due_date":
            def key_func(unit: Unit):
                d = unit.detailing_due_date
                return (0, d) if d is not None else (1, date.max)
        elif column_key == "percent_complete":
            def key_func(unit: Unit) -> float:
                return unit.percent_complete
        elif column_key in ("department_hours", "actual_hours",
                            "target_department_hours"):
            def key_func(unit: Unit) -> float:
                return getattr(unit, column_key, 0.0)
        else:
            # String sort for text columns
            def key_func(unit: Unit):
                val = getattr(unit, column_key, None)
                return str(val).lower() if val is not None else ""

        self._filtered_units.sort(key=key_func, reverse=not ascending)

    # ── Metadata ─────────────────────────────────────────────────────

    def get_unique_detailers(self) -> list[str]:
        """Sorted unique detailer strings from all units."""
        detailers = set()
        for u in self._all_units:
            if u.detailer:
                detailers.add(u.detailer)
        return sorted(detailers)


# ─── ListPanel Widget ───────────────────────────────────────────────

class ListPanel(QWidget):
    """Left-panel widget: sortable, filterable QTableWidget of units.

    Emits `unit_selected(Unit)` — same signal as CalendarPanel.
    """

    unit_selected = pyqtSignal(object)  # Unit

    def __init__(self, units: list[Unit] | None = None, parent=None):
        super().__init__(parent)
        self._model: UnitListModel | None = None
        self._sort_column: str = "detailing_due_date"
        self._sort_ascending: bool = True
        self._search_debounce: QTimer | None = None
        self._theme_name: str = "light"
        self._cvd_mode: str = "none"

        self._build_ui()

        if units:
            self.set_units(units)

    def set_theme(self, theme_name: str, cvd_mode: str = "none") -> None:
        self._theme_name = theme_name
        self._cvd_mode = cvd_mode
        self._refresh_table_full()

    # ── UI Construction ──────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # ── Filter bar ──
        filter_group = QGroupBox("Filters")
        filter_group.setStyleSheet(
            "QGroupBox { "
            "  border: 1px solid palette(mid); "
            "  border-radius: 6px; "
            "  margin-top: 10px; "
            "  padding-top: 14px; "
            "} "
            "QGroupBox::title { "
            "  subcontrol-origin: margin; "
            "  left: 10px; "
            "  padding: 0 4px; "
            "}"
        )
        filter_layout = QVBoxLayout()
        filter_layout.setSpacing(4)

        # Row 1: Status + Detailer
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Status:"))
        self.status_combo = QComboBox()
        self.status_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        for key, label in STATUS_LABELS.items():
            self.status_combo.addItem(label, key)
        self.status_combo.currentIndexChanged.connect(self._on_filter_changed)
        row1.addWidget(self.status_combo, 1)

        row1.addWidget(QLabel("Detailer:"))
        self.detailer_combo = QComboBox()
        self.detailer_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.detailer_combo.addItem("All", "All")
        self.detailer_combo.currentIndexChanged.connect(self._on_filter_changed)
        row1.addWidget(self.detailer_combo, 1)
        filter_layout.addLayout(row1)

        # Row 2: Date range + COM search (with debounce)
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Due:"))
        self.date_combo = QComboBox()
        for label, value in DATE_FILTER_PRESETS:
            self.date_combo.addItem(label, value)
        self.date_combo.currentIndexChanged.connect(self._on_filter_changed)
        row2.addWidget(self.date_combo)

        row2.addWidget(QLabel("Search:"))
        self.com_search = QLineEdit()
        self.com_search.setPlaceholderText("COM # or job name...")
        self.com_search.setClearButtonEnabled(True)
        # Debounce: wait 200ms after last keystroke before filtering
        self._search_debounce = QTimer(self)
        self._search_debounce.setSingleShot(True)
        self._search_debounce.setInterval(200)
        self._search_debounce.timeout.connect(self._on_filter_changed)
        self.com_search.textChanged.connect(self._on_search_text_changed)
        row2.addWidget(self.com_search)
        filter_layout.addLayout(row2)

        # Row 3: Clear filters + column chooser
        row3 = QHBoxLayout()
        self.clear_btn = QPushButton("Clear Filters")
        self.clear_btn.clicked.connect(self._clear_filters)
        row3.addWidget(self.clear_btn)
        row3.addStretch()

        self.columns_btn = QPushButton("Columns...")
        self.columns_btn.clicked.connect(self._show_column_chooser)
        row3.addWidget(self.columns_btn)
        filter_layout.addLayout(row3)

        filter_group.setLayout(filter_layout)
        layout.addWidget(filter_group)

        # ── Table ──
        self.table = QTableWidget()
        self.table.setColumnCount(0)
        self.table.setRowCount(0)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionsClickable(True)
        self.table.horizontalHeader().sectionClicked.connect(
            self._on_header_clicked
        )
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.doubleClicked.connect(self._on_double_clicked)
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        layout.addWidget(self.table, stretch=1)

        # ── Status label ──
        self.status_label = QLabel("No units loaded")
        self.status_label.setObjectName("list_status_label")
        layout.addWidget(self.status_label)

    # ── Public API ───────────────────────────────────────────────────

    def set_units(self, units: list[Unit]) -> None:
        """Load units into the model (initial load)."""
        self._model = UnitListModel(units)
        self._populate_detailer_combo()
        self._sort_column = "detailing_due_date"
        self._sort_ascending = True
        self._apply_filters_and_refresh()

    def refresh(self, units: list[Unit]) -> None:
        """Reload data (called after save/external change).

        Preserves filter state, sort selection, scroll position.
        US-020b: Uses incremental diffing to avoid full table rebuild.
        """
        if self._model is None:
            self.set_units(units)
            return

        # Save current selection and scroll position
        selected_com = self._get_selected_com()
        scroll_pos = self.table.verticalScrollBar().value()

        # Save old unit list for diffing
        old_units = list(self._model.filtered_units) if self._model else []

        self._model = UnitListModel(units)
        self._populate_detailer_combo()

        # Apply current filters and sort before diffing
        status = self.status_combo.currentData() or "All"
        detailer = self.detailer_combo.currentData() or "All"
        date_preset = self.date_combo.currentData()
        com_search = self.com_search.text()
        self._model.apply_filters(
            status=status, detailer=detailer,
            date_preset=date_preset, com_search=com_search,
        )
        self._model.sort_by(self._sort_column, self._sort_ascending)

        new_units = self._model.filtered_units

        # US-020b: Use incremental diff for large tables
        if len(old_units) > 50 and len(new_units) > 50:
            self._refresh_table_incremental(old_units, new_units)
        else:
            self._apply_filters_and_refresh()

        # Restore selection and scroll position
        if selected_com:
            self._select_com(selected_com)
        self.table.verticalScrollBar().setValue(scroll_pos)

    def _diff_units(self, old_units: list[Unit], new_units: list[Unit]) -> dict:
        """Compute minimal diff between old and new unit lists.

        Returns a dict with:
          - 'unchanged': set of com_numbers that didn't change
          - 'added': list of new Units not in old
          - 'removed': set of com_numbers no longer present
          - 'changed': dict of com_number -> new_unit for units that changed
        Uses unit_fingerprint() for change detection.
        """
        old_by_com = {u.com_number: u for u in old_units}
        new_by_com = {u.com_number: u for u in new_units}

        old_set = set(old_by_com.keys())
        new_set = set(new_by_com.keys())

        removed = old_set - new_set
        added_coms = new_set - old_set
        common = old_set & new_set

        # Check for changes in common units using fingerprint
        changed = {}
        unchanged = set()
        for com in common:
            old_fp = unit_fingerprint(old_by_com[com])
            new_fp = unit_fingerprint(new_by_com[com])
            if old_fp != new_fp:
                changed[com] = new_by_com[com]
            else:
                unchanged.add(com)

        return {
            "unchanged": unchanged,
            "added": [new_by_com[c] for c in added_coms],
            "removed": removed,
            "changed": changed,
            "old_by_com": old_by_com,
            "new_by_com": new_by_com,
            "old_order": [u.com_number for u in old_units],
            "new_order": [u.com_number for u in new_units],
        }

    def _refresh_table_incremental(self, old_units: list[Unit],
                                    new_units: list[Unit]) -> None:
        """Incrementally update the table using diff (US-020b).

        Matches units by com_number and only updates changed rows,
        inserts new rows, and removes deleted rows.
        Falls back to full rebuild if the diff is too large (>50% changed).
        """
        diff = self._diff_units(old_units, new_units)
        total_old = len(old_units)

        # If too many changes, fall back to full rebuild
        change_count = len(diff["added"]) + len(diff["removed"]) + len(diff["changed"])
        if total_old > 0 and change_count > total_old * 0.5:
            self._apply_filters_and_refresh()
            return

        visible = self._model.visible_columns
        col_keys = [key for key, _, _, _ in COLUMN_DEFS if key in visible]
        width_map = {d[0]: d[2] for d in COLUMN_DEFS}

        # Ensure column headers are set
        col_headers = []
        for key in col_keys:
            header = next((h for k, h, _, _ in COLUMN_DEFS if k == key), key)
            if key == self._sort_column:
                arrow = " \u25b2" if self._sort_ascending else " \u25bc"
                col_headers.append(header + arrow)
            else:
                col_headers.append(header)

        self.table.setColumnCount(len(col_headers))
        self.table.setHorizontalHeaderLabels(col_headers)
        for col_idx, key in enumerate(col_keys):
            self.table.setColumnWidth(col_idx, width_map.get(key, 80))

        # Build new row mapping: com_number -> row_index
        new_order = [u.com_number for u in new_units]
        self.table.setRowCount(len(new_units))

        # Rebuild all rows (QTableWidget doesn't have model signals for granular updates)
        # The key optimization: we skip re-rendering unchanged rows by reusing QTableWidgetItems
        # Build a map of existing items by com_number
        existing_items = {}  # com_number -> {col_key: QTableWidgetItem}
        for row_idx in range(min(total_old, self.table.rowCount())):
            com_item = self.table.item(row_idx, 0)  # First column has com_number
            if com_item:
                unit = com_item.data(Qt.UserRole)
                if unit:
                    existing_items[unit.com_number] = row_idx

        bold_font = QFont()
        bold_font.setBold(True)

        for row_idx, unit in enumerate(new_units):
            com = unit.com_number
            is_changed = com in diff["changed"] or com in {u.com_number for u in diff["added"]}

            for col_idx, key in enumerate(col_keys):
                # Try to reuse existing item if unchanged
                if not is_changed and com in existing_items and row_idx == existing_items.get(com):
                    # Row hasn't moved and unit hasn't changed — skip
                    continue

                value = getattr(unit, key, None)
                display = self._format_cell(key, value)
                item = QTableWidgetItem(display)

                # Alignment
                if key in ("percent_complete", "department_hours",
                           "actual_hours", "target_department_hours"):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                elif key == "status_color":
                    item.setTextAlignment(Qt.AlignCenter)
                else:
                    item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)

                # Status color
                if key == "status_color":
                    from gui.theme import status_style as _theme_status_style
                    hex_color, icon, label = _theme_status_style(
                        self._theme_name, value or "gray", self._cvd_mode)
                    color = QColor(hex_color)
                    item.setBackground(QBrush(color))
                    brightness = (color.red() * 299 + color.green() * 587 + color.blue() * 114) / 1000
                    text_color = QColor("white") if brightness < 160 else QColor("#1e293b")
                    item.setForeground(QBrush(text_color))
                    item.setFont(bold_font)
                    item.setText(icon)
                    item.setToolTip(f"{icon} {label}")

                # Overdue date highlight
                if (key == "detailing_due_date" and value
                        and isinstance(value, date) and value < date.today()):
                    item.setForeground(QBrush(QColor("#dc2626")))
                    item.setFont(bold_font)

                item.setData(Qt.UserRole, unit)
                self.table.setItem(row_idx, col_idx, item)

        # Update status label (final line of _refresh_table_incremental)

    def _format_cell(self, key: str, value) -> str:
        """Format a Unit attribute for display."""
        if value is None:
            return ""

        if key in (
            "detailing_due_date",
            "build_date",
            "unit_detailing_start_date",
            "unit_moved_to_checking_date",
            "unit_detailing_completion_date",
            "dept_due_date_previous",
        ):
            if hasattr(value, "strftime"):
                return value.strftime("%m/%d/%Y")
            return str(value)

        if key == "percent_complete":
            pct = value * 100.0 if isinstance(value, float) and value <= 1.0 else float(value)
            return f"{pct:.0f}%"

        if key in ("department_hours", "actual_hours", "target_department_hours"):
            return f"{value:.2f}"

        if key == "status_color":
            return ""  # Color block — no text

        return str(value)

    # ── Filtering ───────────────────────────────────────────────────

    def _on_search_text_changed(self, text: str) -> None:
        """Debounce the search — don't re-filter on every keystroke."""
        self._search_debounce.start()

    def _on_filter_changed(self) -> None:
        """Called when any filter widget changes (or debounce fires)."""
        if self._model is None:
            return
        self._apply_filters_and_refresh()

    def _apply_filters_and_refresh(self) -> None:
        """Read filter widget state → apply to model → refresh table."""
        if self._model is None:
            return

        status = self.status_combo.currentData() or "All"
        detailer = self.detailer_combo.currentData() or "All"
        date_preset = self.date_combo.currentData()
        com_search = self.com_search.text()

        self._model.apply_filters(
            status=status,
            detailer=detailer,
            date_preset=date_preset,
            com_search=com_search,
        )
        self._model.sort_by(self._sort_column, self._sort_ascending)
        self._refresh_table_full()

    def _refresh_table_full(self) -> None:
        """Rebuild the entire table from scratch (fallback for small tables or large diffs)."""
        if self._model is None:
            return

        units = self._model.filtered_units
        visible = self._model.visible_columns

        col_headers: list[str] = []
        col_keys: list[str] = []
        for key, header, _width, _ in COLUMN_DEFS:
            if key in visible:
                if key == self._sort_column:
                    arrow = " \u25b2" if self._sort_ascending else " \u25bc"
                    col_headers.append(header + arrow)
                else:
                    col_headers.append(header)
                col_keys.append(key)

        self.table.setColumnCount(len(col_headers))
        self.table.setHorizontalHeaderLabels(col_headers)
        self.table.setRowCount(len(units))

        width_map = {d[0]: d[2] for d in COLUMN_DEFS}
        for col_idx, key in enumerate(col_keys):
            self.table.setColumnWidth(col_idx, width_map.get(key, 80))

        bold_font = QFont()
        bold_font.setBold(True)

        for row_idx, unit in enumerate(units):
            for col_idx, key in enumerate(col_keys):
                value = getattr(unit, key, None)
                display = self._format_cell(key, value)
                item = QTableWidgetItem(display)

                if key in ("percent_complete", "department_hours",
                           "actual_hours", "target_department_hours"):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                elif key == "status_color":
                    item.setTextAlignment(Qt.AlignCenter)
                else:
                    item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)

                if key == "status_color":
                    from gui.theme import status_style as _theme_status_style
                    hex_color, icon, label = _theme_status_style(
                        self._theme_name, value or "gray", self._cvd_mode)
                    color = QColor(hex_color)
                    item.setBackground(QBrush(color))
                    brightness = (color.red() * 299 + color.green() * 587 + color.blue() * 114) / 1000
                    text_color = QColor("white") if brightness < 160 else QColor("#1e293b")
                    item.setForeground(QBrush(text_color))
                    item.setFont(bold_font)
                    item.setText(icon)
                    item.setToolTip(f"{icon} {label}")

                if (key == "detailing_due_date" and value
                        and isinstance(value, date) and value < date.today()):
                    item.setForeground(QBrush(QColor("#dc2626")))
                    item.setFont(bold_font)

                item.setData(Qt.UserRole, unit)
                self.table.setItem(row_idx, col_idx, item)

        total = len(self._model.all_units)
        showing = len(units)
        self.status_label.setText(
            f"Showing {showing} of {total} units"
            f" | sorted by {self._sort_column}"
            f" {'asc' if self._sort_ascending else 'desc'}"
        )

    def _clear_filters(self) -> None:
        """Reset all filter widgets to defaults."""
        self.status_combo.setCurrentIndex(0)
        self.detailer_combo.setCurrentIndex(0)
        self.date_combo.setCurrentIndex(0)
        self.com_search.clear()
        # _on_filter_changed fires from com_search.clear()

    def _populate_detailer_combo(self) -> None:
        """Refresh the Detailer dropdown from model data."""
        if self._model is None:
            return
        current = self.detailer_combo.currentData()
        self.detailer_combo.blockSignals(True)
        self.detailer_combo.clear()
        self.detailer_combo.addItem("All", "All")
        for d in self._model.get_unique_detailers():
            self.detailer_combo.addItem(d, d)
        # Restore previous selection if still valid
        idx = self.detailer_combo.findData(current)
        if idx >= 0:
            self.detailer_combo.setCurrentIndex(idx)
        self.detailer_combo.blockSignals(False)

    # ── Sorting ─────────────────────────────────────────────────────

    def _on_header_clicked(self, column_index: int) -> None:
        """Toggle sort on the clicked column."""
        if self._model is None:
            return
        visible = self._model.visible_columns
        if column_index >= len(visible):
            return

        clicked_key = visible[column_index]

        if clicked_key == self._sort_column:
            self._sort_ascending = not self._sort_ascending
        else:
            self._sort_column = clicked_key
            self._sort_ascending = True

        self._model.sort_by(self._sort_column, self._sort_ascending)
        self._refresh_table_full()

    # ── Selection ───────────────────────────────────────────────────

    def _on_selection_changed(self) -> None:
        """Emit unit_selected when the user clicks a row."""
        unit = self._get_selected_unit()
        if unit is not None:
            self.unit_selected.emit(unit)

    def _on_double_clicked(self, index) -> None:
        """Double-click also selects (redundant with single-click but clear)."""
        unit = self._get_selected_unit()
        if unit is not None:
            self.unit_selected.emit(unit)

    def _get_selected_unit(self) -> Unit | None:
        """Return the Unit for the currently selected row, or None."""
        items = self.table.selectedItems()
        if not items:
            return None
        return items[0].data(Qt.UserRole)

    def _get_selected_com(self) -> str:
        """Return the COM number of the currently selected unit."""
        unit = self._get_selected_unit()
        return unit.com_number if unit else ""

    def _select_com(self, com_number: str) -> bool:
        """Select the row with the given COM number. Returns True if found."""
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)  # COM column
            if item and item.text() == com_number:
                self.table.selectRow(row)
                return True
        return False

    # ── Column Chooser ───────────────────────────────────────────────

    def _show_column_chooser(self) -> None:
        """Dialog to toggle visible columns and reorder them."""
        if self._model is None:
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Choose Columns")
        layout = QVBoxLayout(dialog)

        all_checkboxes: list[tuple[str, QCheckBox]] = []

        # Show checkboxes in the order they currently appear
        current_visible = set(self._model.visible_columns)

        for key, header, _, _ in COLUMN_DEFS:
            cb = QCheckBox(header)
            cb.setChecked(key in current_visible)
            cb.setProperty("key", key)
            layout.addWidget(cb)
            all_checkboxes.append((key, cb))

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec_() == QDialog.Accepted:
            new_visible = [
                key for key, cb in all_checkboxes if cb.isChecked()
            ]
            if new_visible:
                self._model.set_visible_columns(new_visible)
                self._refresh_table_full()
