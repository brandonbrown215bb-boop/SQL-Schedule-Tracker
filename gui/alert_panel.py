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


def _sort_key_for_alert(unit: Unit) -> tuple[int, date]:
    """Sort key: severity first, then due date (earliest first)."""
    severity = ALERT_SEVERITY_ORDER.get(unit.alert_level, 99)
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
        self._current_detailer: str = "All"
        self._build_ui()

        if units:
            self.set_units(units)

    # ── Public API ───────────────────────────────────────────────────

    def set_units(self, units: list[Unit]) -> None:
        """Load units into the panel (initial load)."""
        self._all_units = list(units)
        self._populate_detailer_combo()
        self._rebuild()

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

            # Alert badge
            badge_color = color_name  # map alert to badge via status color
            badge = QLabel(alert)
            badge.setStyleSheet(_alert_badge_stylesheet(badge_color))
            badge.setFont(QFont("Sans", 9, QFont.Bold))
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
            "OVERDUE": 0,
            "URGENT": 0,
            "APPROACHING": 0,
            "ON_TRACK": 0,
            "COMPLETE": 0,
            "UNSET": 0,
        }
        for u in self._filtered_units:
            level = u.alert_level
            if level in counts:
                counts[level] += 1

        total = len(self._filtered_units)

        if total == 0:
            self.summary_label.setText("No actionable alerts")
        else:
            parts = []
            for key in ("OVERDUE", "URGENT", "APPROACHING", "ON_TRACK", "COMPLETE", "UNSET"):
                if counts[key] > 0:
                    parts.append(f"{key.capitalize()}: {counts[key]}")
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
