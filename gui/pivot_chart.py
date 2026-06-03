# gui/pivot_chart.py
"""Pivot chart dialog — shows scheduling dashboard with segmented bars and PNG export."""
import sqlite3
from datetime import date, timedelta

from PyQt5.QtCore import QDate, QRect, QSize, Qt
from PyQt5.QtGui import QBrush, QColor, QFont, QFontMetrics, QPainter, QPen
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

# ── Segment colors ────────────────────────────────────────────────────
COLORS = {
    "allocated":   "#4472C4",  # remaining hours  (blue)
    "pct_complete": "#00BCD4",  # completed hours  (cyan)
    "completed":   "#A9D18E",  # units completed  (light green)
    "not_completed": "#FFC000",  # units not completed (yellow)
}


class PivotTableView(QWidget):
    """Custom-painted horizontal segmented bar chart for weekly scheduling data."""

    BAR_HEIGHT = 28
    BAR_GAP = 8
    LABEL_WIDTH = 100
    HALF_GAP = 2  # gap between the two halves of a bar
    TEXT_PADDING = 4

    def __init__(self, parent=None, theme_name: str = "light",
                 cvd_mode: str = "none"):
        super().__init__(parent)
        self._data: list[dict] = []
        self._max_hours = 0.0
        self._max_units = 0
        self._theme_name = theme_name
        self._cvd_mode = cvd_mode
        self._load_theme_colors()
        self.setFont(QFont("Segoe UI", 9))

    def _load_theme_colors(self) -> None:
        from gui.theme import THEMES
        t = THEMES.get(self._theme_name, THEMES["light"])
        self._bg = QColor(t["bg_primary"])
        self._text_primary = QColor(t["text_primary"])
        self._text_secondary = QColor(t["text_secondary"])
        self._border = QColor(t["border"])
        self._empty_bar = QColor(t["bg_tertiary"])

    def set_data(self, data: list[dict]) -> None:
        self._data = data
        if data:
            self._max_hours = max(
                row["allocated_hours"] for row in data
            ) or 1.0
            self._max_units = max(
                (row["unit_completed"] or 0) + (row["unit_not_completed"] or 0)
                for row in data
            ) or 1
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
        # 4 columns:  alloc | %complete || units_done | units_not_done
        gap = 4
        col_w = (bar_area_w - gap * 3) // 4  # 3 gaps between 4 columns
        rows = len(self._data)
        total_rows_h = rows * (self.BAR_HEIGHT + self.BAR_GAP)
        start_y = 8

        # ── Draw bars (proportional widths) ──
        for i, row in enumerate(self._data):
            y = start_y + i * (self.BAR_HEIGHT + self.BAR_GAP)

            # Week label
            label = str(row["week_label"])
            p.setPen(QPen(self._text_primary))
            p.drawText(QRect(0, y, label_w, self.BAR_HEIGHT),
                       Qt.AlignVCenter | Qt.AlignRight, label)

            alloc = row["allocated_hours"] or 0.0
            pct = row["pct_hours_complete"] or 0.0  # 0-100
            completed_units = row["unit_completed"] or 0
            not_completed_units = row["unit_not_completed"] or 0

            # Proportional widths within bar_area_w
            # Hours column gets 50%, Units column gets 50%
            hours_area_w = (bar_area_w - gap) // 2
            units_area_w = bar_area_w - hours_area_w - gap

            # Hours: alloc bar fills hours_area_w proportionally
            alloc_w = hours_area_w * (alloc / self._max_hours) if self._max_hours else 0
            # % bar fills the remaining space in hours_area_w
            pct_w = hours_area_w * (pct / 100.0)

            # Units: proportional
            done_w = units_area_w * (completed_units / self._max_units) if self._max_units else 0
            left_w = units_area_w * (not_completed_units / self._max_units) if self._max_units else 0

            # ── Hours half (left 50%) ──
            hours_x = bar_area_x
            # Allocated hours bar (blue)
            self._draw_segment(
                p, hours_x, y, alloc_w, self.BAR_HEIGHT,
                alloc, self._max_hours,
                QColor(COLORS["allocated"]),
                f"{alloc:.0f} hrs",
            )
            # % complete bar (cyan) — fills remaining space in hours area
            pct_max_w = max(hours_area_w - alloc_w - 4, 8)  # at least 8px for 0%
            pct_bar_w = max(pct_max_w * (pct / 100.0), 8 if pct >= 0 else 0)
            hours_remaining = alloc * (1.0 - pct / 100.0)
            self._draw_segment(
                p, hours_x + alloc_w + 2, y, pct_bar_w, self.BAR_HEIGHT,
                pct, 100.0,
                QColor(COLORS["pct_complete"]),
                f"{hours_remaining:.0f} hrs left",
            )

            # ── Units half (right 50%) ──
            units_x = bar_area_x + hours_area_w + gap
            # Units completed (green) — always starts at units_x
            self._draw_segment(
                p, units_x, y, done_w, self.BAR_HEIGHT,
                completed_units, self._max_units,
                QColor(COLORS["completed"]),
                str(completed_units),
            )
            # Units not completed (yellow) — strictly after done bar
            self._draw_segment(
                p, units_x + done_w + 2, y, left_w, self.BAR_HEIGHT,
                not_completed_units, self._max_units,
                QColor(COLORS["not_completed"]),
                str(not_completed_units),
            )

        # ── Draw separator line between hours and units halves ──
        sep_x = bar_area_x + (bar_area_w - gap) // 2 + gap // 2
        p.setPen(QPen(self._border, 1, Qt.DashLine))
        bottom_y = start_y + total_rows_h - self.BAR_GAP
        p.drawLine(sep_x, start_y, sep_x, bottom_y)

        # ── Draw legend (color box + label to the right) ──
        legend_y = start_y + total_rows_h + 10
        self._draw_legend(p, bar_area_x, legend_y)

        p.end()

    def _draw_segment(self, p: QPainter, x: float, y: float,
                      width: float, height: int,
                      value: float, max_val: float,
                      color: QColor, text: str) -> None:
        """Draw a single colored bar segment with centered text."""
        if width < 1:
            return
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(color))
        p.drawRoundedRect(int(x), y, max(int(width), 2), height, 3, 3)

        # Text (only if segment is wide enough)
        fm = p.fontMetrics()
        text_w = fm.horizontalAdvance(text) if hasattr(fm, "horizontalAdvance") else fm.width(text)
        if width >= text_w + self.TEXT_PADDING * 2:
            # Choose text color based on brightness
            brightness = (color.red() * 299 + color.green() * 587 + color.blue() * 114) / 1000
            text_color = QColor("#ffffff") if brightness < 160 else QColor("#1e293b")
            p.setPen(QPen(text_color))
            p.drawText(QRect(int(x), y, int(width), height),
                       Qt.AlignCenter, text)

    def _draw_legend(self, p: QPainter, x: int, y: int) -> None:
        """Draw the color legend below the bars."""
        items = [
            (COLORS["allocated"],   "ALLOCATED HRS"),
            (COLORS["pct_complete"], "% HOURS COMPLETE"),
            (COLORS["completed"],   "UNITS COMPLETED"),
            (COLORS["not_completed"], "UNITS NOT COMPLETED"),
        ]
        fm = QFontMetrics(QFont("Segoe UI", 9))
        p.setFont(QFont("Segoe UI", 9))
        cur_x = x
        box_size = 14
        text_color = QColor("#f1f5f9") if self._theme_name == "dark" else QColor("#1e293b")
        for color_hex, label in items:
            # Color box
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(QColor(color_hex)))
            p.drawRoundedRect(cur_x, y, box_size, box_size, 2, 2)
            cur_x += box_size + 5
            # Label text — use proper width so it's visible
            p.setPen(QPen(text_color))
            tw = fm.horizontalAdvance(label) if hasattr(fm, "horizontalAdvance") else fm.width(label)
            p.drawText(QRect(cur_x, y, tw, box_size), Qt.AlignVCenter, label)
            cur_x += tw + 20


class PivotChartWidget(QDialog):
    """Dialog: horizontal bar chart showing weekly scheduling status with PNG export."""

    def __init__(self, db_path: str, theme_name: str = "light",
                 cvd_mode: str = "none", parent=None):
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
        cur.execute("""
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
        """, (start, end))
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows

    def _apply_theme(self, theme_name: str) -> None:
        """Apply background/foreground colors from the active theme."""
        from gui.theme import THEMES
        t = THEMES.get(theme_name, THEMES["light"])
        self.setStyleSheet(f"""
            QDialog {{
                background: {t['bg_primary']};
                color: {t['text_primary']};
            }}
            QLabel {{
                color: {t['text_primary']};
            }}
            QPushButton {{
                background: {t['bg_tertiary']};
                color: {t['text_primary']};
                border: 1px solid {t['border']};
                border-radius: 6px;
                padding: 6px 14px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background: {t['bg_hover']};
            }}
            QDateEdit {{
                background: {t['bg_primary']};
                color: {t['text_primary']};
                border: 1px solid {t['border']};
                border-radius: 5px;
                padding: 3px 8px;
            }}
            QScrollArea {{
                border: none;
                background: {t['bg_primary']};
            }}
        """)

    def _export_png(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Chart as PNG", "scheduling_dashboard.png",
            "PNG Image (*.png);;All Files (*)",
        )
        if not path:
            return
        pixmap = self.table_view.grab()
        pixmap.save(path, "PNG")
