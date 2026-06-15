# gui/calendar_panel.py
from collections import defaultdict

from PyQt5.QtCore import QDate, QEvent, QRect, Qt, pyqtSignal
from PyQt5.QtGui import QBrush, QColor, QPainter
from PyQt5.QtWidgets import (
    QCalendarWidget,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from data.models import Unit


class EventCalendarWidget(QCalendarWidget):
    """Calendar that paints colored dots on dates that have COM events."""

    date_clicked = pyqtSignal(QDate)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.events_by_date: dict[QDate, list[Unit]] = defaultdict(list)
        self.setGridVisible(True)
        self.setHorizontalHeaderFormat(QCalendarWidget.ShortDayNames)
        self.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        self.clicked.connect(self._emit_date_clicked)
        self._theme_name = "light"
        self._cvd_mode = "none"
        self._show_stale = False
        # Fix: install event filter to reposition month/year QMenu popups
        self.installEventFilter(self)

    def _emit_date_clicked(self, date: QDate):
        self.date_clicked.emit(date)

    def eventFilter(self, obj, event):
        """Reposition calendar popup menus that appear at wrong screen location."""
        if event.type() == QEvent.Type.ChildAdded:
            child = event.child()
            if isinstance(child, QMenu):
                child.aboutToShow.connect(lambda menu=child: self._reposition_calendar_menu(menu))
        return super().eventFilter(obj, event)

    def _reposition_calendar_menu(self, menu: QMenu) -> None:
        """Move a QCalendarWidget month/year QMenu below its trigger button."""
        month_name = self.monthName(self.currentPage(), self.monthShown())
        for btn in self.findChildren(QToolButton):
            if btn.text() == month_name:
                pos = btn.mapToGlobal(btn.rect().bottomLeft())
                menu.move(pos)
                return

    def set_show_stale(self, show: bool) -> None:
        self._show_stale = show

    def set_events(self, units: list[Unit]):
        """Build the date→units map — only the detailing due date."""
        self.events_by_date.clear()
        for unit in units:
            if not self._show_stale and unit.is_stale:
                continue
            if unit.detailing_due_date is not None:
                qdate = QDate(
                    unit.detailing_due_date.year,
                    unit.detailing_due_date.month,
                    unit.detailing_due_date.day,
                )
                self.events_by_date[qdate].append(unit)
        self.updateCells()

    def set_theme(self, theme_name: str, cvd_mode: str = "none") -> None:
        self._theme_name = theme_name
        self._cvd_mode = cvd_mode
        self.updateCells()

    def paintCell(self, painter: QPainter, rect: QRect, date: QDate) -> None:
        super().paintCell(painter, rect, date)

        try:
            if date not in self.events_by_date:
                return

            units = self.events_by_date[date]

            from gui.theme import get_status_colors

            status_colors = get_status_colors(self._theme_name, self._cvd_mode)
            hex_to_qcolor = {k: QColor(v) for k, v in status_colors.items()}

            # Assign each unit its own dot color based on calculated status
            # (status_color field is always "gray" for DB-loaded units;
            #  calculated_status_color computes the real status)
            severity = {"red": 0, "orange": 1, "purple": 2, "yellow": 3, "gray": 4, "green": 5}
            sorted_units = sorted(units, key=lambda u: severity.get(u.calculated_status_color, 99))

            painter.save()
            try:
                painter.setRenderHint(QPainter.Antialiasing)
                painter.setPen(Qt.NoPen)  # type: ignore[reportAttributeAccessIssue]
                # Default dot color for badge (will be updated per-unit below)
                dot_color = hex_to_qcolor.get(
                    sorted_units[0].calculated_status_color, QColor("#94a3b8")
                )
                painter.setBrush(QBrush(dot_color))

                dot_radius = 3
                dot_diameter = dot_radius * 2
                spacing = 2
                num_dots = min(len(units), 6)
                total_width = num_dots * dot_diameter + (num_dots - 1) * spacing
                start_x = rect.left() + (rect.width() - total_width) // 2
                start_y = rect.bottom() - dot_diameter - 4

                for i in range(num_dots):
                    unit = sorted_units[i]
                    unit_dot_color = hex_to_qcolor.get(
                        unit.calculated_status_color, QColor("#94a3b8")
                    )
                    painter.setBrush(QBrush(unit_dot_color))
                    px = int(start_x + i * (dot_diameter + spacing))
                    py = int(start_y)
                    painter.drawEllipse(px, py, dot_diameter, dot_diameter)

                    # Track last dot color for badge background
                    dot_color = unit_dot_color

                # US-008: Draw count badge
                count = len(units)
                if count > 0:
                    badge_text = "99+" if count > 99 else str(count)
                    # Badge font
                    from PyQt5.QtGui import QFont

                    badge_font = QFont("Segoe UI", 7, QFont.Bold)
                    painter.setFont(badge_font)
                    # Measure text for badge background
                    fm = painter.fontMetrics()
                    if hasattr(fm, "horizontalAdvance"):
                        text_width = fm.horizontalAdvance(badge_text)
                    else:
                        text_width = fm.width(badge_text)
                    text_height = fm.height()
                    # Badge position: top-right corner of cell
                    badge_padding = 3
                    badge_w = text_width + badge_padding * 2
                    badge_h = text_height + badge_padding * 2
                    badge_x = rect.right() - badge_w - 2
                    badge_y = rect.top() + 2
                    # Badge background (contrasts with dot_color)
                    _r = dot_color.red()
                    _g = dot_color.green()
                    _b = dot_color.blue()
                    brightness = (_r * 299 + _g * 587 + _b * 114) / 1000
                    text_color = QColor(0, 0, 0) if brightness > 128 else QColor(255, 255, 255)
                    # Draw rounded badge background
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(QBrush(dot_color))
                    painter.drawRoundedRect(badge_x, badge_y, badge_w, badge_h, 4.0, 4.0)
                    # Draw count text
                    painter.setPen(text_color)
                    painter.drawText(badge_x, badge_y, badge_w, badge_h, Qt.AlignCenter, badge_text)
            finally:
                painter.restore()
        except Exception:
            pass  # Defensive: don't crash on paint errors


class CalendarPanel(QWidget):
    """Left panel: calendar + event list for selected date."""

    unit_selected = pyqtSignal(Unit)

    def __init__(self, units: list[Unit], parent=None):
        super().__init__(parent)
        self.setObjectName("calendar_panel")
        self.units = units
        self.selected_date: QDate | None = None
        self._theme_name = "light"
        self._cvd_mode = "none"

        layout = QVBoxLayout(self)

        header = QHBoxLayout()
        header.addWidget(QLabel("<b>Calendar</b>"))
        header.addStretch()
        self.today_btn = QPushButton("Today")
        self.today_btn.clicked.connect(self._go_today)
        header.addWidget(self.today_btn)
        layout.addLayout(header)

        self.calendar = EventCalendarWidget()
        self.calendar.set_events(units)
        self.calendar.date_clicked.connect(self._on_date_clicked)
        layout.addWidget(self.calendar)

        layout.addWidget(QLabel("<b>Events on date:</b>"))
        self.event_list = QListWidget()
        self.event_list.itemClicked.connect(self._on_event_clicked)
        layout.addWidget(self.event_list)

    def set_theme(self, theme_name: str, cvd_mode: str = "none") -> None:
        self._theme_name = theme_name
        self._cvd_mode = cvd_mode
        self.calendar.set_theme(theme_name, cvd_mode)
        self._refresh_event_list()

    def _refresh_event_list(self) -> None:
        """Rebuild the event list with current theme colors."""
        if self.selected_date is None:
            return
        self.event_list.clear()
        for unit in self.calendar.events_by_date.get(self.selected_date, []):
            self._add_event_item(unit)

    def _add_event_item(self, unit: Unit) -> None:
        from gui.theme import status_style

        hex_color, icon, _label = status_style(
            self._theme_name, unit.calculated_status_color, self._cvd_mode
        )
        suffix = " ⚠ Due changed" if unit.due_date_changed else ""
        item = QListWidgetItem(f"{icon} COM {unit.com_number} — {unit.job_name}{suffix}")
        item.setData(Qt.UserRole, unit)
        bg = QColor(hex_color)
        bg.setAlpha(80)
        item.setBackground(QBrush(bg))
        if unit.due_date_changed:
            prev = unit.previous_detailing_due_date
            prev_str = prev.strftime("%m/%d/%Y") if prev else "—"
            item.setToolTip(f"Due date changed from {prev_str}")
        self.event_list.addItem(item)

    def refresh(self, units: list[Unit]):
        """Reload data and refresh the visible event list."""
        self.units = units
        self.calendar.set_events(units)
        self._refresh_event_list()

    def _on_date_clicked(self, date: QDate) -> None:
        self.selected_date = date
        self.event_list.clear()
        for unit in self.calendar.events_by_date.get(date, []):
            self._add_event_item(unit)

    def _on_event_clicked(self, item: QListWidgetItem):
        unit = item.data(Qt.UserRole)  # type: ignore[reportAttributeAccessIssue]
        if unit:
            self.unit_selected.emit(unit)

    def _go_today(self):
        self.calendar.setSelectedDate(QDate.currentDate())
