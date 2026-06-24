# gui/reference_dialog.py
"""Reference Dialog showing Glossary, Legend, and Keyboard Shortcuts."""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QDialog,
    QTabWidget,
    QWidget,
    QVBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QDialogButtonBox,
    QGroupBox,
    QScrollArea,
)


class ReferenceDialog(QDialog):
    """Reference Guide dialog explaining verbiage, symbols, and shortcuts."""

    def __init__(self, parent=None, theme_name="light", cvd_mode="none", high_contrast=False):
        super().__init__(parent)
        self.setWindowTitle("Legend & Reference Guide")
        self.setMinimumSize(700, 500)
        self.resize(750, 550)

        self._theme_name = theme_name
        self._cvd_mode = cvd_mode
        self._high_contrast = high_contrast

        self._setup_ui()
        self.set_theme(theme_name, cvd_mode, high_contrast)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Heading
        heading = QLabel("<b>SQL Schedule Tracker — Legend & Reference Guide</b>")
        font = heading.font()
        font.setPointSize(12)
        font.setBold(True)
        heading.setFont(font)
        layout.addWidget(heading)

        # Tab Widget
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # 1. Visual Legend Tab
        self.legend_tab = self._create_legend_tab()
        self.tabs.addTab(self.legend_tab, "🎨 Visual Legend")

        # 2. Glossary Tab
        self.glossary_tab = self._create_glossary_tab()
        self.tabs.addTab(self.glossary_tab, "📖 Glossary & Terms")

        # 3. Keyboard Shortcuts Tab
        self.shortcuts_tab = self._create_shortcuts_tab()
        self.tabs.addTab(self.shortcuts_tab, "⌨ Keyboard Shortcuts")

        # Close Button
        btn_box = QDialogButtonBox(QDialogButtonBox.Close)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _create_legend_tab(self) -> QWidget:
        widget = QWidget()
        main_vbox = QVBoxLayout(widget)
        main_vbox.setContentsMargins(10, 10, 10, 10)
        main_vbox.setSpacing(12)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(12)

        # Statuses Group
        status_group = QGroupBox("Unit Status Indicators (Dots & Shapes)")
        status_layout = QVBoxLayout(status_group)
        status_layout.setContentsMargins(8, 12, 8, 8)
        
        self.status_table = QTableWidget(6, 3)
        self.status_table.setHorizontalHeaderLabels(["Symbol", "Status", "Definition & Logic"])
        self.status_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.status_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.status_table.horizontalHeader().setStretchLastSection(True)
        self.status_table.verticalHeader().setVisible(False)
        self.status_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.status_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.status_table.setAlternatingRowColors(True)
        status_layout.addWidget(self.status_table)
        scroll_layout.addWidget(status_group)

        # Alert Indicators Group
        alert_group = QGroupBox("Alerts View Indicators & Capacity Warnings")
        alert_layout = QVBoxLayout(alert_group)
        alert_layout.setContentsMargins(8, 12, 8, 8)

        self.alert_table = QTableWidget(3, 2)
        self.alert_table.setHorizontalHeaderLabels(["Indicator", "Description"])
        self.alert_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.alert_table.horizontalHeader().setStretchLastSection(True)
        self.alert_table.verticalHeader().setVisible(False)
        self.alert_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.alert_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.alert_table.setAlternatingRowColors(True)
        alert_layout.addWidget(self.alert_table)
        scroll_layout.addWidget(alert_group)

        # Timeline Panel Colors
        timeline_group = QGroupBox("Unit Timeline Milestone Colors")
        timeline_layout = QVBoxLayout(timeline_group)
        timeline_layout.setContentsMargins(8, 12, 8, 8)

        self.timeline_table = QTableWidget(6, 3)
        self.timeline_table.setHorizontalHeaderLabels(["Color Fill", "Status %", "Computed Status Range"])
        self.timeline_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.timeline_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.timeline_table.horizontalHeader().setStretchLastSection(True)
        self.timeline_table.verticalHeader().setVisible(False)
        self.timeline_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.timeline_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.timeline_table.setAlternatingRowColors(True)
        timeline_layout.addWidget(self.timeline_table)
        scroll_layout.addWidget(timeline_group)

        scroll.setWidget(scroll_content)
        main_vbox.addWidget(scroll)
        return widget

    def _create_glossary_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)

        self.glossary_table = QTableWidget(6, 2)
        self.glossary_table.setHorizontalHeaderLabels(["Term", "Definition & Purpose"])
        self.glossary_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.glossary_table.horizontalHeader().setStretchLastSection(True)
        self.glossary_table.verticalHeader().setVisible(False)
        self.glossary_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.glossary_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.glossary_table.setAlternatingRowColors(True)
        
        terms = [
            ("COM #", "Customer Order Number. The read-only primary unique identifier of a scheduling unit."),
            ("Detailer", "The detailing resource or employee currently assigned to model and detail the unit."),
            ("Checking", "A quality assurance process where a senior checker reviews completed detailing drawings. Statuses like 'Ready for Checking' (90%) and 'Checked & Returned' (95%) track this phase."),
            ("SSRS", "SQL Server Reporting Services. The external network system from which the tracker pulls master spreadsheet/schedule updates."),
            ("Stale Unit", "A scheduling unit that is past its due date by more than 30 days. Stale units are filtered out of the active Calendar and List views automatically to keep the UI clean."),
            ("Pre-save Validation", "Automatic validation rules run before changes are written to SQLite. These prevent saving invalid data, such as negative hours or incorrect date orders (e.g. Detailing Start must be before complete).")
        ]
        
        for idx, (term, definition) in enumerate(terms):
            self.glossary_table.setItem(idx, 0, QTableWidgetItem(term))
            self.glossary_table.setItem(idx, 1, QTableWidgetItem(definition))
            
        layout.addWidget(self.glossary_table)
        return widget

    def _create_shortcuts_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)

        self.shortcuts_table = QTableWidget(9, 2)
        self.shortcuts_table.setHorizontalHeaderLabels(["Shortcut Key", "Action & Description"])
        self.shortcuts_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.shortcuts_table.horizontalHeader().setStretchLastSection(True)
        self.shortcuts_table.verticalHeader().setVisible(False)
        self.shortcuts_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.shortcuts_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.shortcuts_table.setAlternatingRowColors(True)

        shortcuts = [
            ("Ctrl + S", "Save all modifications made to the active unit in the Edit Form."),
            ("Ctrl + T", "Toggle between Light Theme and Dark Theme immediately."),
            ("Ctrl + F", "Jump focus to the top global search bar and select all query text."),
            ("Escape", "Clear active search box query, or clear current unit selection."),
            ("F5", "Force reload and refresh all units immediately from the SQLite database."),
            ("Ctrl + 1", "Switch the active view to Calendar View."),
            ("Ctrl + 2", "Switch the active view to List View."),
            ("Ctrl + 3", "Switch the active view to Alerts View."),
            ("F1", "Open this Legend & Reference Guide dialog.")
        ]

        for idx, (key, description) in enumerate(shortcuts):
            self.shortcuts_table.setItem(idx, 0, QTableWidgetItem(key))
            self.shortcuts_table.setItem(idx, 1, QTableWidgetItem(description))

        layout.addWidget(self.shortcuts_table)
        return widget

    def set_theme(self, theme_name: str, cvd_mode: str = "none", high_contrast: bool = False) -> None:
        """Apply style tokens and status indicators dynamically based on the current theme/CVD mode."""
        self._theme_name = theme_name
        self._cvd_mode = cvd_mode
        self._high_contrast = high_contrast

        from gui.theme import apply_theme, THEMES, boost_contrast, status_style

        tokens = THEMES[theme_name]
        if high_contrast:
            tokens = boost_contrast(theme_name)

        # Style the dialog itself and key elements
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {tokens['bg_primary']};
            }}
            QTabWidget::pane {{
                border: 1px solid {tokens['border']};
                background: {tokens['bg_secondary']};
                border-radius: 6px;
            }}
            QTabBar::tab {{
                background: {tokens['bg_tertiary']};
                color: {tokens['text_secondary']};
                border: 1px solid {tokens['border']};
                border-bottom-color: transparent;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                padding: 6px 12px;
                margin-right: 2px;
            }}
            QTabBar::tab:selected {{
                background: {tokens['bg_secondary']};
                color: {tokens['text_primary']};
                border-bottom-color: transparent;
                font-weight: bold;
            }}
            QLabel {{
                color: {tokens['text_primary']};
            }}
            QGroupBox {{
                font-weight: bold;
                color: {tokens['text_primary']};
            }}
        """)

        # Call apply_theme to propagate styling to tables and buttons
        apply_theme(self, theme_name, cvd_mode=cvd_mode, high_contrast=high_contrast)

        # Update dynamic status values/colors in Visual Legend
        status_keys = ["green", "orange", "purple", "yellow", "gray", "red"]
        status_defs = {
            "green": "Unit is 100% complete. Displayed on calendar dates when all units due that day are completed.",
            "orange": "Unit is 95% - 99% complete, typically detailing is finished, awaiting final QA or returned.",
            "purple": "Unit is 90% - 94% complete, detailing is finished and drawings are ready for checking.",
            "yellow": "Unit is 1% - 89% complete, detailing work is currently in progress.",
            "gray": "Unit is 0% complete, detailing has not yet started or has no assigned hours.",
            "red": "Unit is incomplete and past its detailing due date, or remaining hours exceed available capacity."
        }

        # Clear tables content before populating
        self.status_table.setRowCount(0)
        self.status_table.setRowCount(len(status_keys))
        
        for idx, key in enumerate(status_keys):
            hex_color, shape, label = status_style(theme_name, key, cvd_mode)
            
            # Colored symbol item
            sym_item = QTableWidgetItem(shape)
            sym_item.setForeground(QColor(hex_color))
            sym_item.setTextAlignment(Qt.AlignCenter)
            font = sym_item.font()
            font.setPointSize(14)
            font.setBold(True)
            sym_item.setFont(font)
            self.status_table.setItem(idx, 0, sym_item)
            
            # Status label item
            label_item = QTableWidgetItem(label)
            label_font = label_item.font()
            label_font.setBold(True)
            label_item.setFont(label_font)
            self.status_table.setItem(idx, 1, label_item)
            
            # Description item
            self.status_table.setItem(idx, 2, QTableWidgetItem(status_defs[key]))

        # Clear and populate Alert Indicators
        self.alert_table.setRowCount(0)
        self.alert_table.setRowCount(3)

        alerts = [
            ("CHECK SURGE (Red Badge)", "Triggered in Alerts view when 3 or more units due on the same date are awaiting checking. Signals a bottleneck risk for checking resources."),
            ("⚠️ OVERLOADED Detailer Warning", "Displayed at the bottom of the Alerts view when a detailer's assigned units have more than 160 hours of remaining work (exceeds 4 weeks capacity)."),
            ("Stale Unit Warning", "Stale units are overdue by >30 days. They are hidden from views by default to maintain clean scheduling visibility, but can be toggled on/off in the List view.")
        ]
        for idx, (indicator, desc) in enumerate(alerts):
            ind_item = QTableWidgetItem(indicator)
            ind_font = ind_item.font()
            ind_font.setBold(True)
            ind_item.setFont(ind_font)
            if "SURGE" in indicator or "OVERLOADED" in indicator:
                ind_item.setForeground(QColor(status_style(theme_name, "red", cvd_mode)[0]))
            self.alert_table.setItem(idx, 0, ind_item)
            self.alert_table.setItem(idx, 1, QTableWidgetItem(desc))

        # Clear and populate Timeline Colors
        self.timeline_table.setRowCount(0)
        self.timeline_table.setRowCount(len(status_keys))

        timeline_defs = {
            "green": "100%",
            "orange": "95% - 99%",
            "purple": "90% - 94%",
            "yellow": "1% - 89%",
            "gray": "0%",
            "red": "Overdue / Behind Schedule"
        }
        for idx, key in enumerate(status_keys):
            hex_color, _, label = status_style(theme_name, key, cvd_mode)
            
            # Color name / swatch text
            color_item = QTableWidgetItem("█ Fill Color")
            color_item.setForeground(QColor(hex_color))
            color_font = color_item.font()
            color_font.setBold(True)
            color_item.setFont(color_font)
            self.timeline_table.setItem(idx, 0, color_item)
            
            # Status %
            pct_item = QTableWidgetItem(timeline_defs[key])
            pct_font = pct_item.font()
            pct_font.setBold(True)
            pct_item.setFont(pct_font)
            self.timeline_table.setItem(idx, 1, pct_item)
            
            # Description
            self.timeline_table.setItem(idx, 2, QTableWidgetItem(f"Timeline bar fill matches the {label} status color."))

        # Adjust header views for proper sizing
        for table in (self.status_table, self.alert_table, self.timeline_table, self.glossary_table, self.shortcuts_table):
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
            if table.columnCount() > 1:
                table.horizontalHeader().setStretchLastSection(True)
