# gui/timeline_panel.py
from datetime import date, timedelta

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget

from data.models import Unit


class TimelineWidget(QWidget):
    """Renders a horizontal milestone timeline bar with readable labels."""

    BAR_HEIGHT = 36
    BAR_Y = 55
    MARKER_AREA_TOP = None  # computed at paint time
    ROW_HEIGHT = 22
    LEFT_MARGIN = 16
    RIGHT_MARGIN = 16
    FONT_FAMILY = "Segoe UI"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.unit: Unit | None = None
        self.setMinimumHeight(220)
        self._theme_name = "light"
        self._cvd_mode = "none"
        self._layout_cache: dict | None = None
        self._dirty = True
        self._width_dirty = False

    def _font(self, size: int, bold: bool = False) -> QFont:
        weight = QFont.Bold if bold else QFont.Normal
        f = QFont(self.FONT_FAMILY, size, weight)
        f.setStyleStrategy(QFont.PreferAntialias)
        return f

    def set_unit(self, unit: Unit | None):
        self.unit = unit
        self._dirty = True
        self._layout_cache = None
        # Dynamically resize to fit content
        if unit:
            milestones = [(n, d) for n, d in unit.milestones if d is not None]
            n_rows = max(len(milestones), 1)
            needed = self.BAR_Y + self.BAR_HEIGHT + 20 + n_rows * self.ROW_HEIGHT + 50
            self.setMinimumHeight(max(needed, 220))
            self.setMaximumHeight(max(needed, 220))
        else:
            self.setMinimumHeight(220)
            self.setMaximumHeight(220)
        self.update()

    def set_theme(self, theme_name: str, cvd_mode: str = "none") -> None:
        self._theme_name = theme_name
        self._cvd_mode = cvd_mode
        self._dirty = True
        self._layout_cache = None
        self.update()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        self._width_dirty = True
        super().resizeEvent(event)

    def _recompute_layout(self) -> dict:
        """Compute and cache all layout geometry. Returns a dict of computed values."""
        if self.unit is None:
            return {}
        milestones = [(name, d) for name, d in self.unit.milestones if d is not None]
        if not milestones:
            return {"milestones": [], "dates": []}

        dates = [d for _, d in milestones]
        min_date = min(dates)
        max_date = max(dates)

        date_range = (max_date - min_date).days
        if date_range < 30:
            padding = (30 - date_range) // 2 + 1
            min_date -= timedelta(days=padding)
            max_date += timedelta(days=padding)

        total_days = max((max_date - min_date).days, 1)
        width = self.width()
        bar_x = self.LEFT_MARGIN
        bar_width = width - self.LEFT_MARGIN - self.RIGHT_MARGIN
        bar_y = self.BAR_Y
        marker_area_top = bar_y + self.BAR_HEIGHT + 12

        # Pre-compute milestone positions
        milestone_positions = []
        for i, (name, d) in enumerate(milestones):
            row_y = marker_area_top + i * self.ROW_HEIGHT
            offset_days = (d - min_date).days
            x = bar_x + int((offset_days / total_days) * bar_width)
            x = max(bar_x + 2, min(x, bar_x + bar_width - 2))
            milestone_positions.append(
                {
                    "name": name,
                    "date": d,
                    "row_y": row_y,
                    "x": x,
                }
            )

        # Pre-compute axis ticks
        axis_y = marker_area_top + len(milestones) * self.ROW_HEIGHT + 12
        axis_ticks = []
        current = min_date.replace(day=1)
        if current < min_date:
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1, day=1)
            else:
                current = current.replace(month=current.month + 1, day=1)
        while current <= max_date:
            offset_days = (current - min_date).days
            tick_x = bar_x + int((offset_days / total_days) * bar_width)
            axis_ticks.append({"x": tick_x, "label": current.strftime("%b %Y")})
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1, day=1)
            else:
                current = current.replace(month=current.month + 1, day=1)

        # Today line position
        today = date.today()
        today_x = None
        if min_date <= today <= max_date:
            today_offset = (today - min_date).days
            today_x = bar_x + int((today_offset / total_days) * bar_width)

        return {
            "milestones": milestone_positions,
            "milestones_raw": milestones,
            "min_date": min_date,
            "max_date": max_date,
            "total_days": total_days,
            "bar_x": bar_x,
            "bar_width": bar_width,
            "bar_y": bar_y,
            "marker_area_top": marker_area_top,
            "axis_y": axis_y,
            "axis_ticks": axis_ticks,
            "today_x": today_x,
        }

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        from gui.theme import THEMES, get_status_colors, STATUS_SHAPES
        tokens = THEMES.get(self._theme_name, THEMES["light"])
        colors = get_status_colors(self._theme_name, self._cvd_mode)

        # --- Background ---
        painter.fillRect(self.rect(), QBrush(QColor(tokens.get("bg_secondary", "#f8fafc"))))

        if self.unit is None:
            painter.setPen(QPen(QColor(tokens.get("text_muted", "#94a3b8"))))
            painter.setFont(self._font(11))
            painter.drawText(self.rect(), Qt.AlignCenter, "Select a unit to view its timeline")
            painter.end()
            return

        milestones = [(name, d) for name, d in self.unit.milestones if d is not None]
        if not milestones:
            painter.setPen(QPen(QColor(tokens.get("text_muted", "#94a3b8"))))
            painter.setFont(self._font(11))
            painter.drawText(self.rect(), Qt.AlignCenter, "No milestone dates available")
            painter.end()
            return

        # --- Use cached layout or recompute ---
        if self._dirty or self._layout_cache is None or self._width_dirty:
            self._layout_cache = self._recompute_layout()
            self._dirty = False
            self._width_dirty = False

        lc = self._layout_cache
        bar_x = lc["bar_x"]
        bar_width = lc["bar_width"]
        bar_y = lc["bar_y"]

        # --- Status color bar ---
        bar_color = QColor(colors.get(self.unit.calculated_status_color, colors["gray"]))

        # Add icon to bar text
        icon = STATUS_SHAPES.get(self.unit.calculated_status_color, "")

        # Bar border
        painter.setPen(QPen(QColor(tokens.get("border_strong", "#cbd5e1")), 1))
        painter.setBrush(QBrush(bar_color))
        painter.drawRoundedRect(bar_x, bar_y, bar_width, self.BAR_HEIGHT, 4, 4)

        # Status text on the bar (contrast calculated from background luminance)
        luminance = (0.299 * bar_color.red() + 0.587 * bar_color.green() + 0.114 * bar_color.blue()) / 255.0
        status_text_color = (
            QColor(tokens.get("text_primary", "#1e293b"))
            if luminance > 0.5
            else QColor(tokens.get("text_on_accent", "#ffffff"))
        )
        painter.setPen(QPen(status_text_color))
        painter.setFont(self._font(9, bold=True))
        status_text = f"{icon} {self.unit.percent_complete:.0f}%  —  {self.unit.checking_status}"
        painter.drawText(
            bar_x + 10,
            bar_y + 2,
            bar_width - 20,
            self.BAR_HEIGHT - 4,
            Qt.AlignVCenter | Qt.AlignLeft,
            status_text,  # type: ignore[reportAttributeAccessIssue]
        )

        # --- Draw thin horizontal grid lines behind milestones ---
        marker_area_top = lc["marker_area_top"]
        marker_area_top + len(milestones) * self.ROW_HEIGHT

        # --- Milestone rows ---
        painter.setFont(self._font(9))

        for i, pos in enumerate(lc["milestones"]):
            row_y = pos["row_y"]
            x = pos["x"]
            name = pos["name"]
            d = pos["date"]

            # Alternating row background for readability
            if i % 2 == 0:
                painter.fillRect(
                    bar_x,
                    row_y,
                    bar_width,
                    self.ROW_HEIGHT,
                    QBrush(QColor(tokens.get("bg_tertiary", "#f1f5f9"))),
                )

            # Vertical guide line (faint)
            painter.setPen(QPen(QColor(tokens.get("border", "#e2e8f0")), 1, Qt.DotLine))  # type: ignore[reportAttributeAccessIssue]
            painter.drawLine(x, bar_y + self.BAR_HEIGHT, x, row_y + self.ROW_HEIGHT)

            # Tick from bar to row
            painter.setPen(QPen(QColor(tokens.get("border_strong", "#cbd5e1")), 1))
            painter.drawLine(x, bar_y + self.BAR_HEIGHT, x, row_y + 2)

            # Milestone dot (larger, more visible)
            dot_r = 5
            painter.setBrush(QBrush(QColor(tokens.get("accent", "#3b82f6"))))
            painter.setPen(QPen(QColor(tokens.get("accent_active", "#1d4ed8")), 1))
            painter.drawEllipse(
                x - dot_r, row_y + self.ROW_HEIGHT // 2 - dot_r, dot_r * 2, dot_r * 2
            )

            # Milestone name (left-aligned after the dot)
            painter.setPen(QPen(QColor(tokens.get("text_primary", "#1e293b"))))
            painter.setFont(self._font(9))
            label_x = bar_x + 14
            label_w = bar_width - 30
            painter.drawText(
                label_x,
                row_y,
                label_w,
                self.ROW_HEIGHT,
                Qt.AlignVCenter | Qt.AlignLeft,
                name,  # type: ignore[reportAttributeAccessIssue]
            )

            # Date label (right-aligned)
            painter.setPen(QPen(QColor(tokens.get("text_secondary", "#64748b"))))
            painter.setFont(self._font(8))
            date_str = d.strftime("%b %d, %Y")
            painter.drawText(
                bar_x,
                row_y,
                bar_width - 10,
                self.ROW_HEIGHT,
                Qt.AlignVCenter | Qt.AlignRight,
                date_str,  # type: ignore[reportAttributeAccessIssue]
            )

        # --- Axis / range labels at the bottom ---
        axis_y = lc["axis_y"]
        painter.setPen(QPen(QColor(tokens.get("border_strong", "#cbd5e1"))))
        painter.setFont(self._font(8))

        # Axis line
        painter.drawLine(bar_x, axis_y, bar_x + bar_width, axis_y)

        # Draw cached axis ticks
        painter.setFont(self._font(7))
        painter.setPen(QPen(QColor(tokens.get("border_strong", "#cbd5e1"))))
        for tick in lc["axis_ticks"]:
            painter.drawLine(tick["x"], axis_y, tick["x"], axis_y + 5)
            painter.drawText(
                tick["x"] - 30, axis_y + 7, 60, 14, Qt.AlignCenter, tick["label"]
            )  # type: ignore[reportAttributeAccessIssue]

        # --- Today line ---
        if lc["today_x"] is not None:
            today_x = lc["today_x"]
            painter.setPen(QPen(QColor(tokens.get("text_error", "#dc2626")), 2, Qt.DashLine))  # type: ignore[reportAttributeAccessIssue]
            painter.drawLine(today_x, bar_y - 4, today_x, axis_y)

            # "TODAY" label
            painter.setPen(QPen(QColor(tokens.get("text_error", "#dc2626"))))
            painter.setFont(self._font(7, bold=True))
            painter.drawText(
                today_x + 4,
                bar_y - 6,
                40,
                12,
                Qt.AlignLeft | Qt.AlignVCenter,
                "TODAY",  # type: ignore[reportAttributeAccessIssue]
            )

        painter.end()

    def _draw_date_axis(
        self,
        painter: QPainter,
        min_date: date,
        max_date: date,
        total_days: int,
        bar_x: int,
        bar_width: int,
        axis_y: int,
    ) -> None:
        """Draw month-start tick marks and labels along the bottom axis."""
        current = min_date.replace(day=1)
        if current < min_date:
            # Advance to next month start
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1, day=1)
            else:
                current = current.replace(month=current.month + 1, day=1)

        from gui.theme import THEMES
        tokens = THEMES.get(self._theme_name, THEMES["light"])

        painter.setFont(self._font(7))
        painter.setPen(QPen(QColor(tokens.get("border_strong", "#cbd5e1"))))

        while current <= max_date:
            offset_days = (current - min_date).days
            x = bar_x + int((offset_days / total_days) * bar_width)

            # Tick
            painter.drawLine(x, axis_y, x, axis_y + 5)

            # Label
            label = current.strftime("%b %Y")
            painter.drawText(x - 30, axis_y + 7, 60, 14, Qt.AlignCenter, label)  # type: ignore[reportAttributeAccessIssue]

            # Next month
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1, day=1)
            else:
                current = current.replace(month=current.month + 1, day=1)


class TimelinePanel(QWidget):
    """Wrapper panel that holds the header + timeline widget."""

    collapse_changed = pyqtSignal(bool)  # collapsed state

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("timeline_panel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._theme_name = "light"
        self._cvd_mode = "none"
        self._collapsed = False

        # ── Header with collapse toggle ──
        header = QHBoxLayout()
        self._toggle_btn = QToolButton()
        self._toggle_btn.setArrowType(Qt.DownArrow)
        self._toggle_btn.setAutoRaise(True)
        self._toggle_btn.setFixedSize(20, 20)
        self._toggle_btn.clicked.connect(self._on_toggle_collapse)
        header.addWidget(self._toggle_btn)

        self.header_label = QLabel("<b>Unit Timeline</b>")
        self.header_label.setFont(QFont("Segoe UI", 11))
        header.addWidget(self.header_label)
        header.addStretch()
        layout.addLayout(header)

        self.timeline = TimelineWidget()
        layout.addWidget(self.timeline)

    def _on_toggle_collapse(self) -> None:
        self._collapsed = not self._collapsed
        self.timeline.setVisible(not self._collapsed)
        self._toggle_btn.setArrowType(Qt.RightArrow if self._collapsed else Qt.DownArrow)
        self.collapse_changed.emit(self._collapsed)

    def set_collapsed(self, collapsed: bool) -> None:
        if self._collapsed != collapsed:
            self._on_toggle_collapse()

    def set_theme(self, theme_name: str, cvd_mode: str = "none") -> None:
        self._theme_name = theme_name
        self._cvd_mode = cvd_mode
        self.timeline.set_theme(theme_name, cvd_mode)

    def set_unit(self, unit: Unit | None):
        if unit:
            self.header_label.setText(
                f"<b>Unit Timeline</b> — COM {unit.com_number} — {unit.job_name}"
            )
        else:
            self.header_label.setText("<b>Unit Timeline</b>")
        self.timeline.set_unit(unit)
