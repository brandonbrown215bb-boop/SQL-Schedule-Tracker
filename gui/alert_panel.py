# gui/alert_panel.py
"""Alert Panel — per-detailer alert dashboard widget with drill-down.

Shows units sorted by alert severity (OVERDUE → URGENT → APPROACHING →
ON_TRACK → COMPLETE → UNSET) for a selected detailer.  Stale units are
excluded.  Clicking a row emits `unit_selected(Unit)` so the MainWindow
can open the edit form.

Usage:
    panel = AlertPanel(units)
    panel.unit_selected.connect(main_window.on_unit_selected)
    panel.set_units(all_units)          # initial load
    panel.refresh()                     # rebuild from current units
    panel.set_detailer("Jane Smith")    # filter to one detailer
"""

from __future__ import annotations

from datetime import date

from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtGui import QBrush, QColor, QFont, QPainter, QPixmap
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from data.models import Unit

# ─── Color Map ────────────────────────────────────────────────────────
# Same mapping as list_panel.py STATUS_COLORS_FALLBACK

STATUS_COLORS: dict[str, QColor] = {
    "gray":   QColor(148, 163, 184),
    "yellow": QColor(234, 179, 8),
    "purple": QColor(168, 85, 247),
    "orange": QColor(249, 115, 22),
    "green":  QColor(34, 197, 94),
    "red":    QColor(239, 68, 68),
}

# ─── Alert Severity Order ─────────────────────────────────────────────

ALERT_SEVERITY_ORDER: dict[str, int] = {
    "OVERDUE":     0,
    "URGENT":      1,
    "APPROACHING": 2,
    "ON_TRACK":    3,
    "COMPLETE":    4,
    "UNSET":       5,
}

# ─── Capacity Threshold ───────────────────────────────────────────────

CAPACITY_HOURS_THRESHOLD: float = 160.0  # 4 weeks × 40 hrs/week


# ─── Helpers ──────────────────────────────────────────────────────────

def _alert_badge_stylesheet(color_name: str) -> str:
    """Return a stylesheet string for an alert-level badge."""
    c = STATUS_COLORS.get(color_name, STATUS_COLORS["gray"])
    # Use a slightly darker text color for readability
    text_color = "#ffffff" if color_name in ("red", "orange", "purple", "gray") else "#1e293b"
    return (
        f"QLabel {{"
        f"  background-color: {c.name()};"
        f"  color: {text_color};"
        f"  border-radius: 8px;"
        f"  padding: 2px 8px;"
        f"  font-weight: bold;"
        f"  font-size: 11px;"
        f"}}"
    )


def _status_color_name(unit: Unit) -> str:
    """Return the color name for a unit, preferring calculated_status_color."""
    color = unit.calculated_status_color
    if isinstance(color, tuple):
        color = color[0] if color else "gray"
    return color


def _make_dot_pixmap(color: QColor, size: int = 10) -> QPixmap:
    """Create a small colored circle pixmap for the status indicator."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QBrush(color))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(0, 0, size - 1, size - 1)
    painter.end()
    return pm


# ─── Criticality Labels (for badge text + summary) ──────────────────
CRITICALITY_LABELS: dict[str, str] = {
    "red": "CRITICAL", "orange": "CHECKED",
    "purple": "CHECKING", "yellow": "IN PROGRESS",
    "gray": "UNASSIGNED", "green": "COMPLETE",
}

# ─── Criticality Order (matches calculated_status_color severity) ────
# Red = most critical, then orange, purple, yellow, gray, green
CRITICALITY_ORDER: dict[str, int] = {
    "red":    0,
    "orange": 1,
    "purple": 2,
    "yellow": 3,
    "gray":   4,
    "green":  5,
}


# ─── Checking Surge Detection ───────────────────────────────────────
CHECKING_OVERHEAD_WD = 4  # working days in checking pipeline
CHECKING_SURGE_THRESHOLD = 3  # 3+ units needing checking in same window = surge


def _detect_checking_surge(units: list) -> set[str]:
    """Return set of com_numbers that are part of a checking surge.

    A surge occurs when CHECKING_SURGE_THRESHOLD or more units that still
    need checking (not yet entered checking, not yet complete) share the
    same due date.  The checker is a single bottleneck — too many units
    entering checking in the same window means some won't clear in time.
    """
    from collections import defaultdict
    by_due = defaultdict(list)
    for u in units:
        if (u.detailing_due_date is not None
                and u.unit_moved_to_checking_date is None
                and u.unit_detailing_completion_date is None):
            by_due[u.detailing_due_date].append(u)

    surge_coms: set[str] = set()
    for _due, due_units in by_due.items():
        if len(due_units) >= CHECKING_SURGE_THRESHOLD:
            for u in due_units:
                surge_coms.add(u.com_number)
    return surge_coms


def _sort_key_for_alert(unit: Unit) -> tuple[int, date]:
    """Sort key: criticality (computed status color) first, then due date (earliest first)."""
    color = _status_color_name(unit)
    severity = CRITICALITY_ORDER.get(color, 99)
    due = unit.detailing_due_date if unit.detailing_due_date else date.max
    return (severity, due)


# ─── AlertPanel Widget ────────────────────────────────────────────────

class AlertPanel(QWidget):
    """Per-detailer alert dashboard with drill-down signal.

    Emits `unit_selected(Unit)` — same signal contract as ListPanel
    and CalendarPanel.
    """

    unit_selected = pyqtSignal(object)  # Unit

    def __init__(self, units: list[Unit] | None = None, parent=None):
        super().__init__(parent)
        self._all_units: list[Unit] = list(units) if units else []
        self._filtered_units: list[Unit] = []
        self._current_detailer: str = "All Detailers"
        self._surge_coms: set[str] = set()
        self._needs_rebuild: bool = False
        self._build_ui()

        if units:
            self.set_units(units)

    # ── Public API ───────────────────────────────────────────────────

    def set_units(self, units: list[Unit]) -> None:
        """Load units into the panel (initial load)."""
        self._all_units = list(units)
        self._populate_detailer_combo()
        if self.isVisible():
            self._rebuild()
        else:
            self._needs_rebuild = True

    def set_detailer(self, name: str) -> None:
        """Filter to a specific detailer ("All" for everyone)."""
        self._current_detailer = name
        # Sync combo box without re-emitting signals
        idx = self.detailer_combo.findText(name)
        if idx >= 0:
            self.detailer_combo.blockSignals(True)
            self.detailer_combo.setCurrentIndex(idx)
            self.detailer_combo.blockSignals(False)
        self._rebuild()

    def refresh(self) -> None:
        """Rebuild from current units (e.g. after external data change)."""
        self._rebuild()

    # ── Visibility handling ──────────────────────────────────────────

    def showEvent(self, event) -> None:
        """Rebuild list when panel becomes visible if data was loaded while hidden."""
        super().showEvent(event)
        if self._needs_rebuild:
            self._needs_rebuild = False
            self._rebuild()

    # ── UI Construction ──────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # ── Top row: detailer selector + refresh button ──
        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("Detailer:"))
        self.detailer_combo = QComboBox()
        self.detailer_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.detailer_combo.addItem("All Detailers")
        self.detailer_combo.currentTextChanged.connect(self._on_detailer_changed)
        top_row.addWidget(self.detailer_combo, stretch=1)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setToolTip("Rebuild alert list from current data")
        self.refresh_btn.clicked.connect(self.refresh)
        top_row.addWidget(self.refresh_btn)
        layout.addLayout(top_row)

        # ── Unit list ──
        self.list_widget = QListWidget()
        self.list_widget.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.list_widget.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list_widget.setAlternatingRowColors(True)
        self.list_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.list_widget.itemSelectionChanged.connect(self._on_selection_changed)
        self.list_widget.itemDoubleClicked.connect(self._on_double_clicked)
        self.list_widget.setSpacing(2)
        layout.addWidget(self.list_widget, stretch=1)

        # ── Capacity warning label ──
        self.capacity_label = QLabel("")
        self.capacity_label.setFont(QFont("Sans", 11, QFont.Bold))
        self.capacity_label.setStyleSheet("color: #ef4444; padding: 2px 4px;")
        self.capacity_label.hide()
        layout.addWidget(self.capacity_label)

        # ── Summary bar ──
        self.summary_label = QLabel("No alerts")
        self.summary_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.summary_label.setStyleSheet(
            "QLabel {"
            "  border-top: 1px solid palette(mid);"
            "  padding: 4px 6px;"
            "  font-size: 12px;"
            "}"
        )
        layout.addWidget(self.summary_label)

    # ── Internal: populate detailer combo ───────────────────────────

    def _populate_detailer_combo(self) -> None:
        """Refill the detailer combo from all units."""
        detailers = set()
        for u in self._all_units:
            if u.detailer and u.detailer.strip():
                detailers.add(u.detailer.strip())
        sorted_detailers = sorted(detailers, key=str.lower)

        self.detailer_combo.blockSignals(True)
        self.detailer_combo.clear()
        self.detailer_combo.addItem("All Detailers")
        for d in sorted_detailers:
            self.detailer_combo.addItem(d)
        self.detailer_combo.blockSignals(False)

    # ── Internal: filtering + sorting ───────────────────────────────

    def _rebuild(self) -> None:
        """Filter, sort, and populate the list widget."""
        # Filter: non-stale, matching detailer
        units = [u for u in self._all_units if not u.is_stale]

        if self._current_detailer and self._current_detailer != "All Detailers":
            units = [u for u in units if u.detailer == self._current_detailer]

        # Detect checking surge (multi-unit bottleneck)
        self._surge_coms = _detect_checking_surge(units)

        # Sort by alert severity then due date
        units.sort(key=_sort_key_for_alert)

        self._filtered_units = units
        self._populate_list()
        self._update_summary()
        self._update_capacity_warning()

    def _populate_list(self) -> None:
        """Populate the QListWidget from self._filtered_units."""
        self.list_widget.clear()

        for unit in self._filtered_units:
            color_name = _status_color_name(unit)
            qcolor = STATUS_COLORS.get(color_name, STATUS_COLORS["gray"])

            # Build display text parts
            com = unit.com_number or "—"
            desc = unit.description or ""
            if len(desc) > 40:
                desc = desc[:37] + "..."
            due_str = unit.detailing_due_date.strftime(
                "%m/%d/%y") if unit.detailing_due_date else "—"
            pct_str = f"{unit.percent_complete:.0f}%"
            alert = unit.alert_level

            # Create a custom widget for the row
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(6, 4, 6, 4)
            row_layout.setSpacing(8)

            # Colored dot
            dot_label = QLabel()
            dot_label.setPixmap(_make_dot_pixmap(qcolor, 12))
            dot_label.setFixedSize(QSize(16, 16))
            row_layout.addWidget(dot_label)

            # COM number
            com_label = QLabel(com)
            com_label.setFont(QFont("Sans", 10, QFont.Bold))
            com_label.setMinimumWidth(60)
            row_layout.addWidget(com_label)

            # Description (stretches)
            desc_label = QLabel(desc)
            desc_label.setFont(QFont("Sans", 10))
            desc_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            desc_label.setStyleSheet("color: palette(text);")
            row_layout.addWidget(desc_label, stretch=1)

            # Due date
            due_label = QLabel(due_str)
            due_label.setFont(QFont("Sans", 10))
            due_label.setMinimumWidth(55)
            row_layout.addWidget(due_label)

            # % complete
            pct_display = QLabel(pct_str)
            pct_display.setFont(QFont("Sans", 10))
            pct_display.setMinimumWidth(35)
            row_layout.addWidget(pct_display)

            # Alert badge — text reflects criticality (computed status color)
            is_surge = unit.com_number in self._surge_coms
            badge_color = color_name
            if is_surge:
                badge_text = "CHECK SURGE"
                badge_color = "red"
            else:
                badge_text = CRITICALITY_LABELS.get(color_name, alert)
            badge = QLabel(badge_text)
            badge.setStyleSheet(_alert_badge_stylesheet(badge_color))
            badge.setFont(QFont("Sans", 9, QFont.Bold))
            if is_surge and unit.detailing_due_date:
                badge.setToolTip(
                    f"Checking surge: {CHECKING_SURGE_THRESHOLD}+ units due "
                    f"{unit.detailing_due_date.strftime('%m/%d/%Y')} — "
                    f"checker bottleneck risk"
                )
            row_layout.addWidget(badge)

            # Add to list widget
            item = QListWidgetItem()
            item.setSizeHint(row_widget.sizeHint())
            item.setData(Qt.UserRole, unit)
            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, row_widget)

    def _update_summary(self) -> None:
        """Update the summary bar at the bottom."""
        counts: dict[str, int] = {
            "CRITICAL": 0, "CHECKED": 0, "CHECKING": 0,
            "IN PROGRESS": 0, "UNASSIGNED": 0, "COMPLETE": 0,
        }
        for u in self._filtered_units:
            color = _status_color_name(u)
            label = CRITICALITY_LABELS.get(color, "COMPLETE")
            if label in counts:
                counts[label] += 1

        surge_count = len(self._surge_coms)
        total = len(self._filtered_units)

        if total == 0:
            self.summary_label.setText("No actionable alerts")
        else:
            parts = []
            for key in ("CRITICAL", "CHECKED", "CHECKING", "IN PROGRESS", "UNASSIGNED", "COMPLETE"):
                if counts[key] > 0:
                    parts.append(f"{key}: {counts[key]}")
            if surge_count > 0:
                parts.append(f"CHECK SURGE: {surge_count}")
            parts.append(f"Total: {total}")
            self.summary_label.setText(" | ".join(parts))

    def _update_capacity_warning(self) -> None:
        """Show warning if selected detailer is over capacity."""
        if not self._current_detailer or self._current_detailer == "All Detailers":
            self.capacity_label.hide()
            return

        total_hours = 0.0
        for u in self._all_units:
            if u.detailer == self._current_detailer and not u.is_stale:
                remaining_pct = max(0.0, 1.0 - u.percent_complete / 100.0)
                total_hours += u.department_hours * remaining_pct

        if total_hours > CAPACITY_HOURS_THRESHOLD:
            self.capacity_label.setText(
                f"⚠️ OVERLOADED — {self._current_detailer} has "
                f"{total_hours:.0f} hrs remaining "
                f"(threshold: {CAPACITY_HOURS_THRESHOLD:.0f} hrs)"
            )
            self.capacity_label.show()
        else:
            self.capacity_label.hide()

    # ── Signal Handlers ──────────────────────────────────────────────

    def _on_detailer_changed(self, text: str) -> None:
        """Handle detailer combo selection."""
        name = text if text != "All Detailers" else "All Detailers"
        self._current_detailer = name
        self._rebuild()

    def _on_selection_changed(self) -> None:
        """Emit unit_selected when a row is clicked."""
        items = self.list_widget.selectedItems()
        if items:
            unit = items[0].data(Qt.UserRole)
            if unit is not None:
                self.unit_selected.emit(unit)

    def _on_double_clicked(self, item: QListWidgetItem) -> None:
        """Emit unit_selected on double-click."""
        unit = item.data(Qt.UserRole)
        if unit is not None:
            self.unit_selected.emit(unit)
