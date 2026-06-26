# gui/pivot_chart.py
"""Pivot chart dialog — shows scheduling dashboard with segmented bars and PNG export."""

import sqlite3
from datetime import date, timedelta

from PyQt5.QtCore import QDate, QRect, QSize, Qt
from PyQt5.QtGui import QBrush, QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import (
    QDateEdit,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

# ── Segment color keys (computed from theme in _load_theme_colors) ────
# These are theme-relative token names resolved at runtime so dark mode
# and CVD settings are respected automatically.
COLOR_KEYS: dict[str, str] = {
    "allocated": "accent",  # remaining hours  (theme accent)
    "pct_complete": "text_success",  # completed hours  (theme success)
    "completed": "green",  # units completed  (status green)
    "not_completed": "yellow",  # units not completed (status yellow)
}


class PivotTableView(QWidget):
    """Custom-painted horizontal segmented bar chart for weekly scheduling data."""

    BAR_HEIGHT = 28
    BAR_GAP = 8
    LABEL_WIDTH = 170
    HALF_GAP = 2  # gap between the two halves of a bar
    TEXT_PADDING = 4

    def __init__(self, parent=None, theme_name: str = "light", cvd_mode: str = "none"):
        super().__init__(parent)
        self._data: list[dict] = []
        self._max_hours = 0.0
        self._max_units = 0
        self._theme_name = theme_name
        self._cvd_mode = cvd_mode
        self._load_theme_colors()
        self.setFont(QFont("Segoe UI", 9))

    def _load_theme_colors(self) -> None:
        from gui.theme import THEMES, get_status_colors

        t = THEMES.get(self._theme_name, THEMES["light"])
        self._bg = QColor(t["bg_primary"])
        self._text_primary = QColor(t["text_primary"])
        self._text_secondary = QColor(t["text_secondary"])
        self._border = QColor(t["border"])
        self._empty_bar = QColor(t["bg_tertiary"])

        # Resolve chart segment colors from theme tokens + status colors
        status_colors = get_status_colors(self._theme_name, self._cvd_mode)
        self._segment_colors: dict[str, QColor] = {}
        for segment, token in COLOR_KEYS.items():
            # Try theme token first, fall back to status color, then hardcoded default
            hex_color = t.get(token) or status_colors.get(token, "#888888")
            self._segment_colors[segment] = QColor(hex_color)

    def set_data(self, data: list[dict]) -> None:
        self._data = data
        if data:
            self._max_hours = max(row["allocated_hours"] for row in data) or 1.0
            self._max_units = (
                max((row["unit_completed"] or 0) + (row["unit_not_completed"] or 0) for row in data)
                or 1
            )
        else:
            self._max_hours = 1.0
            self._max_units = 1
        self.updateGeometry()
        self.update()

    # ── Sizing ────────────────────────────────────────────────────────

    def minimumSizeHint(self) -> QSize:
        rows = max(len(self._data), 1)
        h = rows * (self.BAR_HEIGHT + self.BAR_GAP) + 60  # room for legend
        return QSize(self.fontMetrics().boundingRect("2026-06-26").width(), h)

    # ── Painting ──────────────────────────────────────────────────────

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()

        if not self._data:
            p.setPen(QPen(self._text_secondary))
            p.drawText(QRect(0, 0, w, h), Qt.AlignCenter, "No data available")
            p.end()
            return

        # ── Layout constants ──
        label_w = self.LABEL_WIDTH
        bar_area_x = label_w + 8
        bar_area_w = w - bar_area_x - 16  # margin right
        gap = 4
        rows = len(self._data)
        total_rows_h = rows * (self.BAR_HEIGHT + self.BAR_GAP)
        start_y = 8

        # ── Draw bars ──
        for i, row in enumerate(self._data):
            y = start_y + i * (self.BAR_HEIGHT + self.BAR_GAP)

            alloc = row["allocated_hours"] or 0.0
            pct = row["pct_hours_complete"] or 0.0  # 0-100
            completed_units = row["unit_completed"] or 0
            not_completed_units = row["unit_not_completed"] or 0

            # Define formatters for clean labels
            def format_hours(h: float) -> str:
                if h.is_integer():
                    return f"{int(h)}"
                return f"{h:.2f}".rstrip('0').rstrip('.')

            def format_pct(pr: float) -> str:
                if pr.is_integer():
                    return f"{int(pr)}%"
                return f"{pr:.1f}%"

            # Date label (left-aligned)
            label = str(row["week_label"])
            p.setPen(QPen(self._text_primary))
            p.drawText(
                QRect(8, y, 80, self.BAR_HEIGHT), Qt.AlignVCenter | Qt.AlignLeft, label
            )

            # Total hours label (right-aligned, immediately to the left of the bar start)
            hours_str = f"{format_hours(alloc)} hrs"
            p.setPen(QPen(self._text_secondary))
            p.drawText(
                QRect(92, y, label_w - 92, self.BAR_HEIGHT), Qt.AlignVCenter | Qt.AlignRight, hours_str
            )

            # Proportional widths within bar_area_w
            # Hours column gets 50%, Units column gets 50%
            hours_area_w = (bar_area_w - gap) // 2
            units_area_w = bar_area_w - hours_area_w - gap

            # Compute Hours segment widths
            hours_bar_total_w = hours_area_w * (alloc / self._max_hours) if self._max_hours else 0
            completed_w = hours_bar_total_w * (pct / 100.0)
            remaining_w = hours_bar_total_w - completed_w

            # Compute Units segment widths
            total_units = completed_units + not_completed_units
            units_bar_total_w = (
                units_area_w * (total_units / self._max_units) if self._max_units else 0
            )
            done_w = units_bar_total_w * (completed_units / total_units) if total_units else 0
            left_w = units_bar_total_w - done_w

            completed_hrs = alloc * (pct / 100.0)

            # Combine all 4 segments in sequential order
            combined_segments = [
                # 1. Completed Hours (Blue)
                (
                    completed_w,
                    self._segment_colors["allocated"],  # Blue
                    f"{format_hours(completed_hrs)} hrs",
                    format_hours(completed_hrs),
                ),
                # 2. Remaining Hours / Completion % (Cyan)
                (
                    remaining_w,
                    self._segment_colors["pct_complete"],  # Cyan
                    format_pct(pct),
                    format_pct(pct),
                ),
                # 3. Completed Units (Green)
                (
                    done_w,
                    self._segment_colors["completed"],  # Green
                    f"{completed_units} units",
                    str(completed_units),
                ),
                # 4. Uncompleted Units (Yellow/Brown)
                (
                    left_w,
                    self._segment_colors["not_completed"],  # Yellow
                    f"{not_completed_units} left",
                    str(not_completed_units),
                ),
            ]

            total_bar_w = hours_bar_total_w + units_bar_total_w
            self._draw_stacked_bar(
                p,
                bar_area_x,
                y,
                total_bar_w,
                self.BAR_HEIGHT,
                combined_segments,
                fallback_text=f"{format_hours(completed_hrs)} / {format_hours(alloc)} hrs" if total_bar_w > 0 else "",
            )

        # ── Draw legend (color box + label to the right) ──
        legend_y = start_y + total_rows_h + 10
        self._draw_legend(p, bar_area_x, legend_y)

        p.end()

    def _draw_stacked_bar(
        self,
        p: QPainter,
        x: float,
        y: float,
        width: float,
        height: int,
        segments: list[tuple[float, QColor, str, str]],
        fallback_text: str = "",
    ) -> None:
        """Draws a stacked bar with rounded corners for the entire group, using clipping."""
        if width < 1:
            return

        # 1. Create a clip path for the entire bar
        path = QPainterPath()
        path.addRoundedRect(x, y, width, height, 4, 4)

        p.save()
        p.setClipPath(path)

        # 2. Draw segments and save their positions for text rendering
        cur_x = x
        segment_rects = []
        for seg_w, color, text_full, text_short in segments:
            if seg_w <= 0:
                continue
            # Ensure the drawing does not exceed the total width
            draw_w = seg_w
            if cur_x + draw_w > x + width:
                draw_w = (x + width) - cur_x

            # Draw the segment background
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(color))
            p.drawRect(QRect(int(cur_x), int(y), int(draw_w + 0.5), height))

            segment_rects.append((cur_x, draw_w, color, text_full, text_short))
            cur_x += draw_w

        # Restore QPainter to clear the clip path for drawing text (so text isn't clipped at edges)
        p.restore()

        # 3. Draw text labels inside the segments
        fm = p.fontMetrics()
        any_text_drawn = False

        for seg_x, seg_w, color, text_full, text_short in segment_rects:
            if seg_w < 10:
                continue

            fit_text = ""
            for txt in [text_full, text_short]:
                if not txt:
                    continue
                txt_w = fm.horizontalAdvance(txt) if hasattr(fm, "horizontalAdvance") else fm.width(txt)
                if seg_w >= txt_w + self.TEXT_PADDING * 2:
                    fit_text = txt
                    break

            if fit_text:
                any_text_drawn = True
                # Choose text color based on brightness
                brightness = (color.red() * 299 + color.green() * 587 + color.blue() * 114) / 1000
                text_color = QColor("#ffffff") if brightness < 160 else QColor("#1e293b")
                p.setPen(QPen(text_color))
                p.drawText(QRect(int(seg_x), int(y), int(seg_w), height), Qt.AlignCenter, fit_text)

        # 4. Fallback to combined text across the whole bar if no segment text fit
        if not any_text_drawn and fallback_text:
            fallback_w = (
                fm.horizontalAdvance(fallback_text)
                if hasattr(fm, "horizontalAdvance")
                else fm.width(fallback_text)
            )
            if width >= fallback_w + self.TEXT_PADDING * 2:
                # Find which segment contains the center of the bar
                center_x = x + width / 2.0
                match_color = QColor("#888888")
                for seg_x, seg_w, color, _, _ in segment_rects:
                    if seg_x <= center_x <= seg_x + seg_w:
                        match_color = color
                        break
                brightness = (
                    match_color.red() * 299 + match_color.green() * 587 + match_color.blue() * 114
                ) / 1000
                text_color = QColor("#ffffff") if brightness < 160 else QColor("#1e293b")
                p.setPen(QPen(text_color))
                p.drawText(QRect(int(x), int(y), int(width), height), Qt.AlignCenter, fallback_text)

    def _draw_legend(self, p: QPainter, x: int, y: int) -> None:
        """Draw the color legend below the bars."""
        items = [
            (self._segment_colors["allocated"], "COMPLETED HOURS"),
            (self._segment_colors["pct_complete"], "REMAINING HOURS"),
            (self._segment_colors["completed"], "UNITS COMPLETED"),
            (self._segment_colors["not_completed"], "UNITS NOT COMPLETED"),
        ]
        fm = QFontMetrics(QFont("Segoe UI", 9))
        p.setFont(QFont("Segoe UI", 9))
        cur_x = x
        box_size = 14
        text_color = QColor("#f1f5f9") if self._theme_name == "dark" else QColor("#1e293b")
        for color, label in items:
            # Color box
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(color))
            p.drawRoundedRect(cur_x, y, box_size, box_size, 2, 2)
            cur_x += box_size + 5
            # Label text
            p.setPen(QPen(text_color))
            tw = (
                fm.horizontalAdvance(label) if hasattr(fm, "horizontalAdvance") else fm.width(label)
            )
            p.drawText(QRect(cur_x, y, tw, box_size), Qt.AlignVCenter, label)
            cur_x += tw + 20


class PivotChartWidget(QDialog):
    """Dialog: horizontal bar chart showing weekly scheduling status with PNG export."""

    def __init__(
        self, db_path: str, theme_name: str = "light", cvd_mode: str = "none", parent=None
    ):
        super().__init__(parent)
        self.db_path = db_path
        self._theme_name = theme_name
        self._cvd_mode = cvd_mode
        self.setWindowTitle("Scheduling Dashboard")
        self.setMinimumSize(960, 500)
        self._apply_theme(theme_name)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # ── Toolbar ──
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("<b>Detailing Dept. — Scheduling Status</b>"))
        toolbar.addStretch()
        layout.addLayout(toolbar)

        # ── Date range filter ──
        friday = self._current_friday()
        six_weeks = friday + timedelta(weeks=6)
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("From:"))
        self.start_date = QDateEdit()
        self.start_date.setCalendarPopup(True)
        self.start_date.setDate(QDate(friday))
        self.start_date.setDisplayFormat("MM/dd/yyyy")
        filter_layout.addWidget(self.start_date)

        filter_layout.addWidget(QLabel("To:"))
        self.end_date = QDateEdit()
        self.end_date.setCalendarPopup(True)
        self.end_date.setDate(QDate(six_weeks))
        self.end_date.setDisplayFormat("MM/dd/yyyy")
        filter_layout.addWidget(self.end_date)

        filter_btn = QPushButton("🔍 Apply")
        filter_btn.clicked.connect(self.refresh)
        filter_layout.addWidget(filter_btn)
        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        # ── Action buttons ──
        action_layout = QHBoxLayout()
        action_layout.addStretch()
        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.clicked.connect(self.refresh)
        action_layout.addWidget(refresh_btn)
        export_btn = QPushButton("📷 Export PNG")
        export_btn.setObjectName("primary_export_btn")
        export_btn.clicked.connect(self._export_png)
        action_layout.addWidget(export_btn)
        layout.addLayout(action_layout)

        # ── Chart area (scrollable) ──
        self.table_view = PivotTableView(theme_name=theme_name, cvd_mode=cvd_mode)
        scroll = QScrollArea()
        scroll.setWidget(self.table_view)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        layout.addWidget(scroll, 1)

        self.refresh()

    def refresh(self) -> None:
        data = self._query_data()
        self.table_view.set_data(data)

    @staticmethod
    def _current_friday() -> date:
        today = date.today()
        return today + timedelta(days=(4 - today.weekday()) % 7)

    def _query_data(self) -> list:
        start = self.start_date.date().toPyDate().isoformat()
        end = self.end_date.date().toPyDate().isoformat()
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                week_ending_friday as week_label,
                ROUND(SUM(department_hours), 2) as allocated_hours,
                ROUND(AVG(CASE WHEN percent_complete IS NOT NULL
                              THEN percent_complete ELSE 0 END) * 100, 1
                ) as pct_hours_complete,
                SUM(CASE WHEN percent_complete >= 1.0 THEN 1 ELSE 0 END
                ) as unit_completed,
                SUM(CASE WHEN percent_complete < 1.0 OR percent_complete IS NULL
                          THEN 1 ELSE 0 END
                ) as unit_not_completed
            FROM units
            WHERE week_ending_friday IS NOT NULL
              AND week_ending_friday BETWEEN ? AND ?
            GROUP BY week_ending_friday
            ORDER BY week_ending_friday
        """,
            (start, end),
        )
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows

    def _apply_theme(self, theme_name: str) -> None:
        """Apply background/foreground colors from the active theme."""
        from gui.theme import THEMES

        t = THEMES.get(theme_name, THEMES["light"])
        self.setStyleSheet(f"""
            QDialog {{
                background: {t["bg_primary"]};
                color: {t["text_primary"]};
            }}
            QLabel {{
                color: {t["text_primary"]};
            }}
            QPushButton {{
                background: {t["bg_tertiary"]};
                color: {t["text_primary"]};
                border: 1px solid {t["border"]};
                border-radius: 6px;
                padding: 6px 14px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background: {t["bg_hover"]};
            }}
            QDateEdit {{
                background: {t["bg_primary"]};
                color: {t["text_primary"]};
                border: 1px solid {t["border"]};
                border-radius: 5px;
                padding: 3px 8px;
            }}
            QScrollArea {{
                border: none;
                background: {t["bg_primary"]};
            }}
        """)

    def _export_png(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Chart as PNG",
            "scheduling_dashboard.png",
            "PNG Image (*.png);;All Files (*)",
        )
        if not path:
            return
        pixmap = self.table_view.grab()
        pixmap.save(path, "PNG")
