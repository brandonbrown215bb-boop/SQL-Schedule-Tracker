"""MainWindow — thin orchestration layer.

Creates services, wires them to widgets, handles UI coordination.
All business logic is delegated to the services/ package.
"""

import contextlib
import logging
import os
import sys
import time

from PyQt5.QtCore import QFileSystemWatcher, Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QAction,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from data.models import Unit
from data.tag_parser import UnitTagRepository
from gui.alert_panel import AlertPanel
from gui.calendar_panel import CalendarPanel
from gui.conflict_dialog import ConflictDialog
from gui.due_date_changed_dialog import DueDateChangedDialog
from gui.edit_form import EditForm
from gui.list_panel import ListPanel
from gui.loading_overlay import LoadingOverlay
from gui.notification_panel import NotificationPanel
from gui.onboarding import should_show_onboarding, show_onboarding
from gui.reference_dialog import ReferenceDialog
from gui.sync_status import SyncStatusWidget
from gui.theme import apply_theme, init_labels, style_alerts_btn
from gui.timeline_panel import TimelinePanel
from services.config_service import ConfigService
from services.export_service import ExportService
from services.import_service import ImportService
from services.sync_service import SyncService
from services.unit_service import UnitService

logger = logging.getLogger(__name__)

SQLITE_HEADER = b"SQLite format 3\x00"


class LoadWorker(QThread):
    """Background worker for loading units from UnitService."""

    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, unit_service: UnitService):
        super().__init__()
        self._unit_service = unit_service

    def run(self):
        try:
            units = self._unit_service.load_all()
            self.finished.emit(units)
        except Exception as e:
            self.error.emit(str(e))


class SaveWorker(QThread):
    """Background worker for saving units via UnitService."""

    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, unit_service: UnitService, unit: Unit):
        super().__init__()
        self._unit_service = unit_service
        self.unit = unit

    def run(self):
        try:
            self._unit_service.save(self.unit)
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))


class PullSSRSWorker(QThread):
    """Background worker for fetching SSRS data."""

    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, import_service: ImportService, url: str, lookback_days: int, lookahead_days: int):
        super().__init__()
        self._import_service = import_service
        self.url = url
        self.lookback_days = lookback_days
        self.lookahead_days = lookahead_days

    def run(self):
        try:
            res = self._import_service.from_ssrs(
                url=self.url,
                lookback_days=self.lookback_days,
                lookahead_days=self.lookahead_days
            )
            self.finished.emit(res)
        except Exception as e:
            self.error.emit(str(e))


class CSVDiffWorker(QThread):
    """Background worker for computing CSV import diff."""

    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, import_service: ImportService, source_path: str):
        super().__init__()
        self._import_service = import_service
        self.source_path = source_path

    def run(self):
        try:
            diff = self._import_service.diff_before_import(self.source_path)
            self.finished.emit(diff)
        except Exception as e:
            self.error.emit(str(e))


class CSVImportWorker(QThread):
    """Background worker for importing CSV data."""

    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, import_service: ImportService, source_path: str):
        super().__init__()
        self._import_service = import_service
        self.source_path = source_path

    def run(self):
        try:
            res = self._import_service.from_csv(self.source_path)
            self.finished.emit(res)
        except Exception as e:
            self.error.emit(str(e))


class ExcelExportWorker(QThread):
    """Background worker for exporting to Excel."""

    finished = pyqtSignal(int)
    error = pyqtSignal(str)

    def __init__(self, export_service: ExportService, excel_path: str, db_path: str):
        super().__init__()
        self._export_service = export_service
        self.excel_path = excel_path
        self.db_path = db_path

    def run(self):
        try:
            row_count = self._export_service.to_excel(self.excel_path, self.db_path)
            self.finished.emit(row_count)
        except Exception as e:
            self.error.emit(str(e))


class ServiceRegistry:
    """Holds all service instances. Created by main(), injected into MainWindow."""

    def __init__(self, config: dict, config_path: str, db_path: str):
        self.config = config
        self.config_path = config_path
        self.db_path = db_path
        detailer_schedules = ConfigService.get_detailer_schedules(config)
        self.hook_registry = self._build_hook_registry()
        self.unit_service = UnitService(
            db_path,
            detailer_schedules=detailer_schedules,
            hook_registry=self.hook_registry,
        )
        self.import_service = ImportService(db_path)
        self.export_service = ExportService()
        self.sync_service = SyncService(db_path, config.get("multi_user", {}))
        self.config_service = ConfigService  # static methods only

    @staticmethod
    def _build_hook_registry():
        from services.pre_save_hooks import (
            PreSaveHookRegistry,
            date_order_hook,
            non_negative_hours_hook,
            non_primary_identical_hook,
            percent_complete_range_hook,
            target_hours_hook,
        )

        registry = PreSaveHookRegistry()
        registry.register("percent_complete_range", percent_complete_range_hook, priority=10)
        registry.register("non_negative_hours", non_negative_hours_hook, priority=20)
        registry.register("non_primary_identical", non_primary_identical_hook, priority=30)
        registry.register("target_hours", target_hours_hook, priority=40)
        registry.register("date_order", date_order_hook, priority=50)
        return registry


class MainWindow(QMainWindow):
    def __init__(self, services: ServiceRegistry):
        super().__init__()
        self._services = services
        self._svc = services.unit_service
        self.units: list[Unit] = []
        self.current_unit: Unit | None = None
        self._alert_critical_count: int = 0
        self._load_worker: LoadWorker | None = None
        self._save_worker: SaveWorker | None = None
        self._pending_save_unit: Unit | None = None
        self._form_dirty: bool = False
        self._tag_repo: UnitTagRepository | None = None
        self._shared_cache = None
        self._session_registry = None
        self._presence_label: QLabel | None = None
        self._presence_poll_timer: QTimer | None = None
        self._retired_save_workers: list[SaveWorker] = []
        self._save_worker_errors: dict[SaveWorker, str] = {}
        self._file_poll_timer: QTimer | None = None
        self._auto_refresh_timer: QTimer | None = None
        self._config_debounce_timer: QTimer | None = None
        self._io_busy: bool = False

        # ── Sync-queue UI state ───────────────────────────────────────
        self._sync_status_session_total: int = 0
        self._sync_status_session_initial: int = 0
        self._sync_unit_durations: list[float] = []
        self._current_unit_save_started_at: float = 0.0
        self._close_progress = None
        self._close_poll_timer: QTimer | None = None
        self._closing: bool = False
        self._close_waiting: bool = False

        # ── Error dialog throttling ────────────────────────────────────
        self._error_dialog_count = 0
        self._error_dialog_window_start = 0.0
        self._error_dialog_threshold = 3
        self._error_dialog_window_seconds = 10.0

        self._current_theme_name: str = "light"
        self._current_cvd: str = "none"
        self._current_hc: bool = False

        self._init_status_bar()
        self._init_toolbar()
        self._init_central_layout()
        self._init_left_panel()
        self._init_right_panel()
        self._init_splitter_sizes()
        self._init_loading_overlay()
        self._setup_file_watcher()
        self._setup_multi_user_sync()
        self._setup_auto_refresh()
        self._build_help_menu()
        self._init_theme()
        self._check_onboarding()
        self._load_data_async()

    def _init_theme(self) -> None:
        """Initialize theme from config and apply to widget tree."""
        init_labels(self._services.config.get("status_labels", {}))
        ui_cfg = self._services.config.get("ui", {})
        self._current_theme_name = ui_cfg.get("theme", "light")
        self._current_cvd = ui_cfg.get("colorblind_mode", "none")
        self._current_hc = ui_cfg.get("high_contrast", False)
        apply_theme(
            self,
            self._current_theme_name,
            cvd_mode=self._current_cvd,
            high_contrast=self._current_hc,
        )
        if hasattr(self, "notification_panel") and self.notification_panel is not None:
            self.notification_panel.set_theme(self._current_theme_name, self._current_cvd)

    def _init_status_bar(self) -> None:
        self.setWindowTitle("Unit Tracker")
        self.setMinimumSize(1200, 700)
        self.status_bar = QStatusBar()
        self.status_bar.setObjectName("status_bar")
        self.setStatusBar(self.status_bar)

        # Permanent status bar widgets (right-aligned)
        self._status_unit_count = QLabel("")
        self.status_bar.addPermanentWidget(self._status_unit_count)

        self._sync_status_widget = SyncStatusWidget()
        self._sync_status_widget.setObjectName("sync_status_widget")
        self.status_bar.addPermanentWidget(self._sync_status_widget)

    def _init_toolbar(self) -> None:
        """Create the top-level QToolBar with global operations (P1)."""
        from PyQt5.QtCore import QSize

        toolbar = QToolBar("Global Operations")
        toolbar.setObjectName("global_toolbar")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(24, 24))
        self.addToolBar(toolbar)

        # ── Import CSV ──
        action_import = QAction("📥 Import CSV", self)
        action_import.setToolTip("Import SSRS CSV into SQLite database")
        action_import.triggered.connect(self._pull_csv)
        toolbar.addAction(action_import)

        # ── Pull SSRS ──
        action_ssrs = QAction("🌐 Pull SSRS", self)
        action_ssrs.setToolTip("Fetch latest data from SSRS ReportServer and import into SQLite")
        action_ssrs.triggered.connect(self._pull_ssrs)
        toolbar.addAction(action_ssrs)

        # ── Refresh ──
        action_refresh = QAction("🔄 Refresh", self)
        action_refresh.setToolTip("Reload data from SQLite database")
        action_refresh.triggered.connect(self._refresh_data)
        toolbar.addAction(action_refresh)

        # ── Export Excel ──
        action_export = QAction("💾 Export Excel", self)
        action_export.setToolTip("Export SQLite data to Excel workbook (Current List sheet)")
        action_export.triggered.connect(self._export_excel)
        toolbar.addAction(action_export)

        toolbar.addSeparator()

        # ── Global Search Bar (P4) ──
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Search COM #, job, or contract…")
        self._search_edit.setFixedWidth(250)
        self._search_edit.setClearButtonEnabled(True)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self._on_global_search)
        self._search_edit.textChanged.connect(self._on_search_text_changed)
        self._search_edit.returnPressed.connect(self._on_search_entered)
        toolbar.addWidget(self._search_edit)

        self._toolbar = toolbar

    # ── Global Search (P4) ──────────────────────────────────────────────

    def _on_search_text_changed(self, text: str) -> None:
        """Restart the debounce timer on each keystroke."""
        self._search_timer.start()

    def _on_global_search(self) -> None:
        """Execute the global search after debounce fires."""
        query = self._search_edit.text().strip().lower()
        if not query:
            return
        if not self.units:
            return

        matches = [
            u for u in self.units
            if query in u.com_number.lower()
            or query in u.job_name.lower()
            or query in u.contract_number.lower()
        ]

        if len(matches) == 1:
            # Single match — select it (but don't auto-navigate; wait for Enter)
            self._search_single_match = matches[0]
        elif len(matches) > 1:
            # Multi-match — switch to List view and apply filter
            self._switch_view("list")
            self.list_panel.com_search.setText(self._search_edit.text().strip())
            self.list_panel.com_search.setFocus()
            self._search_single_match = None
        else:
            self._search_single_match = None

    def _on_search_entered(self) -> None:
        """Handle Enter key in the search bar — auto-select single match."""
        if hasattr(self, "_search_single_match") and self._search_single_match is not None:
            self.on_unit_selected(self._search_single_match)
            self._search_single_match = None

    def _init_central_layout(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout = QHBoxLayout(central)
        main_layout.addWidget(self.main_splitter)

    def _init_left_panel(self) -> None:
        left_widget = QWidget()
        left_widget.setObjectName("left_panel")
        left_container = QVBoxLayout(left_widget)

        # View toggle buttons
        toggle_layout = QHBoxLayout()
        self.calendar_view_btn = QPushButton("📅 Calendar (Ctrl+1)")
        self.list_view_btn = QPushButton("📋 List (Ctrl+2)")
        self.alerts_view_btn = QPushButton("🔔 Alerts (Ctrl+3)")
        self.list_view_btn.setObjectName("list_view_btn")
        self.calendar_view_btn.setObjectName("calendar_view_btn")
        self.alerts_view_btn.setObjectName("alerts_view_btn")
        self.calendar_view_btn.setCheckable(True)
        self.list_view_btn.setCheckable(True)
        self.alerts_view_btn.setCheckable(True)
        self.calendar_view_btn.setChecked(True)
        self.calendar_view_btn.clicked.connect(lambda: self._switch_view("calendar"))
        self.list_view_btn.clicked.connect(lambda: self._switch_view("list"))
        self.alerts_view_btn.clicked.connect(lambda: self._switch_view("alerts"))
        toggle_layout.addWidget(self.calendar_view_btn)
        toggle_layout.addWidget(self.list_view_btn)
        toggle_layout.addWidget(self.alerts_view_btn)
        toggle_layout.addStretch()

        self.theme_btn = QPushButton()
        self.theme_btn.setObjectName("theme_btn")
        self.theme_btn.setToolTip("Toggle dark/light theme (Ctrl+T)")
        self.theme_btn.clicked.connect(self._toggle_theme)
        self._update_theme_button()
        toggle_layout.addWidget(self.theme_btn)

        self.a11y_btn = QPushButton("♿")
        self.a11y_btn.setObjectName("a11y_btn")
        self.a11y_btn.setToolTip("Accessibility settings")
        self.a11y_btn.clicked.connect(self._open_a11y_dialog)
        toggle_layout.addWidget(self.a11y_btn)
        left_container.addLayout(toggle_layout)

        # View title label (P16)
        self.view_title = QLabel()
        self.view_title.setObjectName("view_title")
        self.view_title.setStyleSheet("font-size: 11px; padding: 2px 0 4px 0; color: palette(mid);")
        left_container.addWidget(self.view_title)

        self.view_stack = QStackedWidget()
        self.view_stack.setObjectName("view_stack")
        self.calendar_panel = CalendarPanel(self.units)
        self.calendar_panel.unit_selected.connect(self.on_unit_selected)
        self.view_stack.addWidget(self.calendar_panel)
        self.list_panel = ListPanel(
            self.units,
            default_detailers=self._services.config.get("default_detailers", []),
            db_path=self._services.db_path,
        )
        self.list_panel.unit_selected.connect(self.on_unit_selected)
        self.list_panel.unit_saved.connect(self.on_save_unit)
        self.list_panel.inline_dirty_changed.connect(self._on_inline_dirty_changed)
        self.list_panel.stale_changed.connect(self._on_stale_changed)
        self.list_panel.column_widths_changed.connect(self._on_column_widths_changed)
        self.list_panel.column_visibility_changed.connect(self._on_column_visibility_changed)
        self.list_panel.batch_mode_changed.connect(self._on_batch_mode_changed)
        self.view_stack.addWidget(self.list_panel)
        self.alert_panel = AlertPanel(self.units)
        self.alert_panel.unit_selected.connect(self.on_unit_selected)
        self.view_stack.addWidget(self.alert_panel)
        left_container.addWidget(self.view_stack)
        self.main_splitter.addWidget(left_widget)

        saved_view = self._services.config.get("ui", {}).get("last_view", "calendar")
        if saved_view == "list":
            self._switch_view("list")
        saved_widths = self._services.config.get("ui", {}).get("list_column_widths", {})
        if saved_widths:
            self.list_panel.load_column_widths(saved_widths)
        saved_visible = self._services.config.get("ui", {}).get("list_visible_columns", [])
        if saved_visible:
            self.list_panel.load_visible_columns(saved_visible)
        saved_sort_col = self._services.config.get("ui", {}).get("list_sort_column", "detailing_due_date")
        saved_sort_asc = self._services.config.get("ui", {}).get("list_sort_ascending", True)
        self.list_panel.load_sort_config(saved_sort_col, saved_sort_asc)

    def _init_right_panel(self) -> None:
        right_widget = QWidget()
        right_widget.setObjectName("right_panel")
        right_panel = QVBoxLayout(right_widget)

        self.timeline_panel = TimelinePanel()
        right_panel.addWidget(self.timeline_panel)

        # ── Batch mode banner (P8) ──
        self._batch_banner = QLabel()
        self._batch_banner.setObjectName("batch_banner")
        self._batch_banner.setStyleSheet(
            "background: #fbbf24; color: #1e293b; font-weight: bold; "
            "padding: 6px 10px; border-radius: 4px;"
        )
        self._batch_banner.setVisible(False)
        right_panel.addWidget(self._batch_banner)

        self.edit_form = EditForm(
            default_detailers=self._services.config.get("default_detailers", [])
        )
        self.edit_form.saved.connect(self.on_save_unit)
        self.edit_form.dirty_changed.connect(self._on_dirty_changed)
        self.edit_form.history_requested.connect(self._open_audit)
        right_panel.addWidget(self.edit_form, 1)

        self.main_splitter.addWidget(right_widget)

        # ── Right panel collapse toggle (P19) ──
        self._right_collapsed = False
        self._right_panel_sizes = None
        self._collapse_btn = QPushButton("▶")
        self._collapse_btn.setObjectName("right_collapse_btn")
        self._collapse_btn.setFixedSize(24, 24)
        self._collapse_btn.setToolTip("Collapse right panel")
        self._collapse_btn.clicked.connect(self._on_toggle_right_panel)
        collapse_header = QHBoxLayout()
        collapse_header.addStretch()
        collapse_header.addWidget(self._collapse_btn)
        right_panel.insertLayout(0, collapse_header)

        # ── Timeline collapse persistence (P2) ──
        self.timeline_panel.collapse_changed.connect(self._on_timeline_collapse_changed)
        saved_timeline_collapsed = self._services.config.get("ui", {}).get("timeline_collapsed", False)
        if saved_timeline_collapsed:
            self.timeline_panel.set_collapsed(True)

        # ── Right panel collapse persistence (P19) ──
        saved_right_collapsed = self._services.config.get("ui", {}).get("right_panel_collapsed", False)
        if saved_right_collapsed:
            QTimer.singleShot(0, self._on_toggle_right_panel)

    def _init_splitter_sizes(self) -> None:
        saved_sizes = self._services.config.get("ui", {}).get("splitter_sizes")
        if saved_sizes:
            self.main_splitter.setSizes(saved_sizes)
        else:
            self.main_splitter.setSizes([self.width() // 2, self.width() // 2])
        # Set minimum panel widths
        left_widget = self.findChild(QWidget, "left_panel")
        right_widget = self.findChild(QWidget, "right_panel")
        if left_widget:
            left_widget.setMinimumWidth(300)
        if right_widget:
            right_widget.setMinimumWidth(350)

    def _init_loading_overlay(self) -> None:
        self.loading_overlay = LoadingOverlay(self.centralWidget())
        self.notification_panel = NotificationPanel(self)

    def _check_onboarding(self) -> None:
        if should_show_onboarding(self._services.config):
            QTimer.singleShot(500, lambda: show_onboarding(self, self._services.config))

    # ── Help menu ──────────────────────────────────────────────────────

    def _build_help_menu(self):
        menubar = self.menuBar()
        menubar.setObjectName("menuBar")
        reports_menu = menubar.addMenu("&Reports")
        dashboard_action = reports_menu.addAction("📊 Scheduling Dashboard")
        dashboard_action.setToolTip("Open the scheduling status chart (exportable as PNG)")
        dashboard_action.triggered.connect(self._open_dashboard)
        help_menu = menubar.addMenu("&Help")
        
        legend_action = help_menu.addAction("&Legend & Reference Guide")
        legend_action.setToolTip("Show visual legend, glossary, and shortcuts (F1)")
        legend_action.triggered.connect(self._show_legend)
        
        walkthrough_action = help_menu.addAction("&Show Walkthrough")
        walkthrough_action.setToolTip("Show the onboarding walkthrough")
        walkthrough_action.triggered.connect(lambda: show_onboarding(self, self._services.config))
        help_menu.addSeparator()
        about_action = help_menu.addAction("&About Unit Tracker")
        about_action.triggered.connect(self._show_about)

    def _show_legend(self) -> None:
        dlg = ReferenceDialog(
            parent=self,
            theme_name=self._current_theme_name,
            cvd_mode=self._current_cvd,
            high_contrast=self._current_hc,
        )
        dlg.exec_()

    def _show_about(self):
        QMessageBox.about(
            self,
            "About Unit Tracker",
            "<b>Unit Tracker</b><br><br>"
            f"A desktop viewer/editor for detailing schedules.<br>"
            f"Python {sys.version.split()[0]} | PyQt5 | SQLite<br><br>"
            "© 2026",
        )

    def _open_dashboard(self) -> None:
        if not self._services.db_path:
            QMessageBox.information(self, "Dashboard", "No database loaded.")
            return
        from gui.pivot_chart import PivotChartWidget

        dlg = PivotChartWidget(
            self._services.db_path,
            theme_name=self._current_theme_name,
            cvd_mode=self._current_cvd,
            parent=self,
        )
        dlg.exec_()

    # ── View switching ─────────────────────────────────────────────────

    def _switch_view(self, view_name: str) -> None:
        titles = {
            "calendar": "📅 Calendar View — Upcoming due dates at a glance",
            "list": "📋 List View — Filtered sortable table of all units",
            "alerts": "🔔 Alerts View — Per-detailer alert dashboard",
        }
        self.view_title.setText(titles.get(view_name, ""))

        if view_name == "calendar":
            self.view_stack.setCurrentIndex(0)
            self.calendar_view_btn.setChecked(True)
            self.list_view_btn.setChecked(False)
            self.alerts_view_btn.setChecked(False)
        elif view_name == "list":
            self.view_stack.setCurrentIndex(1)
            self.calendar_view_btn.setChecked(False)
            self.list_view_btn.setChecked(True)
            self.alerts_view_btn.setChecked(False)
            if self.units and self.list_panel._model is None:
                self.list_panel.set_units(self.units)
        elif view_name == "alerts":
            self.view_stack.setCurrentIndex(2)
            self.calendar_view_btn.setChecked(False)
            self.list_view_btn.setChecked(False)
            self.alerts_view_btn.setChecked(True)
            self.alert_panel.set_units(self.units)
            QTimer.singleShot(0, self.alert_panel.refresh)

        self._services.config.setdefault("ui", {})["last_view"] = view_name

    def _update_alert_badge(self) -> None:
        """Update alert badge count on the Alerts view button (P10)."""
        self._alert_critical_count = sum(
            1 for u in self.units if u.calculated_status_color == "red" and not u.is_stale
        )
        if self._alert_critical_count > 0:
            self.alerts_view_btn.setText(
                f"🔔 Alerts ({self._alert_critical_count}) (Ctrl+3)"
            )
        else:
            self.alerts_view_btn.setText("🔔 Alerts (Ctrl+3)")

        style_alerts_btn(
            self.alerts_view_btn,
            self._current_theme_name,
            has_alerts=(self._alert_critical_count > 0),
            high_contrast=self._current_hc,
        )

    def _on_batch_mode_changed(self, count: int) -> None:
        """Show/hide batch banner in right panel and dim edit form (P8)."""
        if count >= 2:
            self._batch_banner.setText(f"📦 Batch Mode — {count} units selected")
            self._batch_banner.setVisible(True)
            self.edit_form.setEnabled(False)
            self.timeline_panel.setEnabled(False)
        else:
            self._batch_banner.setVisible(False)
            self.edit_form.setEnabled(True)
            self.timeline_panel.setEnabled(True)

    def _on_stale_changed(self, show_stale: bool) -> None:
        self.calendar_panel.calendar.set_show_stale(show_stale)
        self.calendar_panel.refresh(self.units)

    def _update_dirty_title(self) -> None:
        is_dirty = self._form_dirty or getattr(self, "_inline_dirty", False)
        base_title = "Unit Tracker"
        self.setWindowTitle(f"* {base_title}" if is_dirty else base_title)

    def _notify(self, message: str, level: str = "info") -> None:
        """Show a temporary toast notification and log it."""
        if hasattr(self, "notification_panel") and self.notification_panel is not None:
            self.notification_panel.show_notification(message, level)
        logger.info("Notification (%s): %s", level, message)

    def _on_dirty_changed(self, dirty: bool) -> None:
        self._form_dirty = dirty
        self._update_dirty_title()

    def _on_inline_dirty_changed(self, dirty: bool) -> None:
        self._inline_dirty = dirty
        self._update_dirty_title()

    def _confirm_discard(self) -> bool:
        is_dirty = self._form_dirty or getattr(self, "_inline_dirty", False)
        if not is_dirty:
            return True
        reply = QMessageBox.question(
            self,
            "Unsaved Changes",
            "You have unsaved changes. Discard them?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._form_dirty = False
            self._inline_dirty = False
            self._update_dirty_title()
            if hasattr(self, "edit_form"):
                self.edit_form._dirty = False
            if hasattr(self, "list_panel") and hasattr(self.list_panel, "_inline_edit_bar"):
                self.list_panel._inline_edit_bar._dirty = False
            return True
        return False

    # ── Selection + Save ───────────────────────────────────────────────

    def on_unit_selected(self, unit: Unit | None):
        if not self._confirm_discard():
            return
        self.current_unit = unit
        self.timeline_panel.set_unit(unit)
        self.edit_form.set_unit(unit)
        if unit is not None:
            if unit.due_date_changed:
                unit.due_date_changed = False
                unit.previous_detailing_due_date = None
                self.calendar_panel.refresh(self.units)
                self.list_panel.refresh(self.units)
            self.status_bar.showMessage(f"Selected: COM {unit.com_number} — {unit.job_name}")
        else:
            self.status_bar.showMessage("No unit selected")

    def on_save_unit(self, unit: Unit):
        self._start_save_worker(unit)

    def _start_save_worker(self, unit: Unit) -> None:
        if self._services.sync_service.is_save_blocked():
            QMessageBox.warning(
                self,
                "Save Blocked",
                "Multi-user sync is unavailable. Saves are disabled until sync is available "
                "or multi_user.enabled is false.",
            )
            return
        if self._active_save_worker_running():
            logger.warning("Save already in progress — queuing")
            return
        self.status_bar.showMessage(f"Saving COM {unit.com_number}...")
        worker = SaveWorker(self._svc, unit)
        worker.finished.connect(self._on_save_finished)
        worker.error.connect(self._on_save_error)
        self._save_worker = worker
        self._pending_save_unit = unit
        self._save_worker_errors[worker] = ""
        worker.start()

    def _on_save_finished(self) -> None:
        worker = self.sender()
        unit = worker.unit if isinstance(worker, SaveWorker) else self._pending_save_unit
        if isinstance(worker, SaveWorker):
            self._retire_save_worker(worker)
        if unit:
            self._commit_unit_to_memory(unit)
            self.calendar_panel.refresh(self.units)
            self.list_panel.refresh(self.units)
            self.timeline_panel.set_unit(unit)
            self.edit_form.current_unit = unit
            self._pending_save_unit = None
            self._notify(f"Saved COM {unit.com_number}", "success")

    def _on_save_error(self, error_msg: str) -> None:
        worker = self.sender()
        failed_unit = worker.unit if isinstance(worker, SaveWorker) else self._pending_save_unit
        if isinstance(worker, SaveWorker):
            self._save_worker_errors[worker] = error_msg
            self._retire_save_worker(worker)
        logger.error("Save error: %s", error_msg)
        if "was modified by another user" in error_msg:
            self._show_conflict_dialog(error_msg, failed_unit)
            return
        QMessageBox.warning(
            self,
            "Save Failed",
            f"Could not save to database:\n{error_msg}\n\n"
            f"Your changes are still in the form. Check your network connection and try saving again.",
        )
        self._notify("Save failed — check network connection", "error")

    def _show_conflict_dialog(self, error_msg: str, local_unit: Unit | None = None) -> None:
        local_unit = local_unit or self.current_unit
        com_number = local_unit.com_number if local_unit else "?"
        remote_unit = None
        try:
            remote_unit = self._svc.get_by_com(com_number)
        except Exception as e:
            logger.warning("Could not reload unit for conflict dialog: %s", e)
        local_values = self._unit_to_dict(local_unit) if local_unit else {}
        remote_values = self._unit_to_dict(remote_unit) if remote_unit else {}
        modified_at = remote_unit.updated_at if remote_unit else "unknown"
        dlg = ConflictDialog(
            com_number=com_number,
            local_values=local_values,
            remote_values=remote_values,
            modified_by="another user",
            modified_at=modified_at,
            parent=self,
        )
        dlg.exec_()
        if dlg.overwrite:
            logger.info("User chose to overwrite conflict for COM %s", com_number)
            if local_unit:
                local_unit.updated_at = ""
                self._start_save_worker(local_unit)
        elif dlg.reload:
            logger.info("User chose to reload COM %s after conflict", com_number)
            if remote_unit:
                self._replace_unit_in_memory(remote_unit)
                self.edit_form.set_unit(remote_unit)
                self.timeline_panel.set_unit(remote_unit)
                self.calendar_panel.refresh(self.units)
                self.list_panel.refresh(self.units)
            self.status_bar.showMessage("Reloaded from database", 5000)
            self._pending_save_unit = None

    @staticmethod
    def _unit_to_dict(unit: Unit) -> dict:
        return {
            "job_name": unit.job_name,
            "contract_number": unit.contract_number,
            "description": unit.description,
            "detailer": unit.detailer,
            "checking_status": unit.checking_status,
            "department_hours": unit.department_hours,
            "actual_hours": unit.actual_hours,
            "target_department_hours": unit.target_department_hours,
            "iec_internal_hours": unit.iec_internal_hours,
            "percent_complete": unit.percent_complete,
            "unit_detailing_start_date": unit.unit_detailing_start_date,
            "unit_moved_to_checking_date": unit.unit_moved_to_checking_date,
            "unit_detailing_completion_date": unit.unit_detailing_completion_date,
            "dept_due_date_previous": unit.dept_due_date_previous,
            "detailing_due_date": unit.detailing_due_date,
            "build_date": unit.build_date,
        }

    def _replace_unit_in_memory(self, new_unit: Unit) -> None:
        for i, u in enumerate(self.units):
            if u.com_number == new_unit.com_number:
                self.units[i] = new_unit
                if self.current_unit and self.current_unit.com_number == new_unit.com_number:
                    self.current_unit = new_unit
                return

    def _active_save_worker_running(self) -> bool:
        worker = self._save_worker
        if worker is None:
            return False
        try:
            return worker.isRunning()
        except RuntimeError:
            return False

    def _retire_save_worker(self, worker: SaveWorker) -> None:
        if self._save_worker is worker:
            self._save_worker = None
        if worker not in self._retired_save_workers:
            self._retired_save_workers.append(worker)
            worker.deleteLater()

    def _commit_unit_to_memory(self, unit: Unit) -> None:
        unit.status_color = unit.calculated_status_color
        for i, existing in enumerate(self.units):
            if existing.com_number == unit.com_number:
                unit.excel_row = unit.excel_row or existing.excel_row
                unit.fingerprint = unit.fingerprint or existing.fingerprint
                unit.base_revision = unit.base_revision or existing.base_revision
                self.units[i] = unit
                break
        else:
            self.units.append(unit)
        self.current_unit = unit
        # Invalidate fingerprint cache so list refresh detects the change
        from data.loader import _fingerprint_cache
        _fingerprint_cache.pop(unit.com_number, None)

    # ── Data loading ───────────────────────────────────────────────────

    def _load_data_async(self):
        if getattr(self, "_io_busy", False):
            logger.info("MainWindow: Load requested but I/O already in progress — skipping")
            self.status_bar.showMessage("Please wait — operation in progress...", 2000)
            return
        self.status_bar.showMessage("Loading...")
        self._set_io_busy(True)
        self._load_worker = LoadWorker(self._svc)
        self._load_worker.finished.connect(self._on_load_finished)
        self._load_worker.error.connect(self._on_load_error)
        self._load_worker.start()

    def _on_load_finished(self, units: list[Unit]):
        self._set_io_busy(False)
        changed_units = self._svc.detect_changed_due_dates(self.units, units)
        self.units = units

        if self.current_unit is not None:
            for new_unit in self.units:
                if new_unit.com_number == self.current_unit.com_number:
                    self.current_unit = new_unit
                    self.edit_form.current_unit = new_unit
                    if not self._form_dirty:
                        self.edit_form.set_unit(new_unit)
                    break

        self._tag_repo = UnitTagRepository(self.units)
        self.list_panel.set_tag_repo(self._tag_repo)
        self.calendar_panel.refresh(self.units)
        self.list_panel.set_units(self.units)
        self.alert_panel.set_units(self.units)
        self._update_alert_badge()
        self._status_unit_count.setText(f"{len(self.units)} units loaded")
        self._notify(f"Loaded {len(self.units)} units from SQLite", "success")
        logger.info("MainWindow: Loaded %d units.", len(self.units))

        # Re-run global search after data refresh to prevent desync (P4)
        if self._search_edit.text().strip():
            QTimer.singleShot(0, self._on_global_search)

        if changed_units:
            dlg = DueDateChangedDialog(
                [(c.unit, c.previous_due_date) for c in changed_units], parent=self
            )
            dlg.exec_()

        if self._pending_reload_count > 0:
            self._pending_reload_count = 0
            logger.info("MainWindow: Pending file change detected — scheduling follow-up reload")
            QTimer.singleShot(1000, self._trigger_pending_reload)

    def _trigger_pending_reload(self):
        if getattr(self, "_io_busy", False):
            return
        if self._active_save_worker_running():
            return
        self._load_data_async()

    def _should_suppress_error_dialog(self) -> bool:
        now = time.monotonic()
        if now - self._error_dialog_window_start >= self._error_dialog_window_seconds:
            self._error_dialog_window_start = now
            self._error_dialog_count = 0
        self._error_dialog_count += 1
        return self._error_dialog_count > self._error_dialog_threshold

    def _on_load_error(self, error_msg: str):
        self.loading_overlay.hide()
        self._set_io_busy(False)
        self._notify("Failed to load database", "error")
        logger.error("MainWindow: Error loading database: %s", error_msg)
        if self._should_suppress_error_dialog():
            logger.info("MainWindow: Error dialog suppressed (throttled)")
            return
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Load Error")
        msg_box.setText(
            f"Failed to load database:\n{error_msg}\n\n"
            f"Check config.yaml — sqlite_path must point to a valid SQLite database."
        )
        msg_box.setIcon(QMessageBox.Critical)
        retry_button = msg_box.addButton("Retry", QMessageBox.ActionRole)
        msg_box.addButton(QMessageBox.Ok)
        msg_box.exec_()
        if msg_box.clickedButton() == retry_button:
            self._load_data_async()
        self.units = []

    # ── Refresh / Pull ────────────────────────────────────────────────

    def _refresh_data(self):
        self._apply_refresh_cooldown()
        self._load_data_async()

    # ── File watcher ───────────────────────────────────────────────────

    def _setup_file_watcher(self) -> None:
        self._file_watcher = QFileSystemWatcher()
        self._file_watcher.fileChanged.connect(self._on_file_changed)
        self._pending_reload_count = 0
        if self._services.db_path and os.path.exists(self._services.db_path):
            self._file_watcher.addPath(self._services.db_path)

    def _on_file_changed(self, path: str):
        logger.info("MainWindow: Detected change in %s", path)
        if getattr(self, "_io_busy", False):
            return
        if self._active_save_worker_running():
            return
        now = time.monotonic()
        if now - getattr(self, "_last_file_change", 0) < 5.0:
            self._pending_reload_count += 1
            return
        self._last_file_change = now
        self._pending_reload_count = 0
        self._file_change_path = path
        self._file_deadline = now + 8.0
        self._stop_file_poll_timer()
        self._file_poll_timer = QTimer(self)
        self._file_poll_timer.setSingleShot(False)
        self._file_poll_timer.setInterval(500)
        self._file_poll_timer.timeout.connect(self._check_file_ready)
        self._file_poll_timer.start()
        self.status_bar.showMessage("File changed — waiting...", 2000)

    def _check_file_ready(self):
        path = self._file_change_path
        deadline = self._file_deadline
        if time.monotonic() > deadline:
            logger.info("MainWindow: File not ready after timeout, skipping reload")
            self._stop_file_poll_timer()
            return
        try:
            if not os.path.exists(path):
                return
            size = os.path.getsize(path)
            if size < 100:
                return
            with open(path, "rb") as f:
                header = f.read(16)
            if header.startswith(SQLITE_HEADER):
                self._stop_file_poll_timer()
                self._load_data_async()
                return
            if header[:4] == b"PK\x03\x04":
                self._stop_file_poll_timer()
                self._load_data_async()
                return
            return
        except OSError:
            return

    def _stop_file_poll_timer(self):
        timer = self._file_poll_timer
        self._file_poll_timer = None
        if timer is None:
            return
        try:
            timer.stop()
            timer.deleteLater()
        except RuntimeError:
            pass

    def _set_io_busy(self, busy: bool):
        self._io_busy = busy

    # ── Auto-refresh timer ─────────────────────────────────────────────

    def _setup_auto_refresh(self) -> None:
        interval_min = self._services.config.get("ui", {}).get("auto_refresh_minutes", 0)
        if interval_min <= 0:
            return
        interval_ms = interval_min * 60 * 1000
        self._auto_refresh_timer = QTimer(self)
        self._auto_refresh_timer.setInterval(interval_ms)
        self._auto_refresh_timer.timeout.connect(self._on_auto_refresh)
        self._auto_refresh_timer.start()
        logger.info("MainWindow: Auto-refresh every %d minute(s)", interval_min)
        self.status_bar.showMessage(f"Auto-refresh: {interval_min}min", 3000)

    def _on_auto_refresh(self) -> None:
        if getattr(self, "_io_busy", False):
            return
        if self._active_save_worker_running():
            return
        self._load_data_async()

    # ── Refresh cooldown ───────────────────────────────────────────────

    def _apply_refresh_cooldown(self) -> None:
        COOLDOWN = 3
        buttons: list[QPushButton] = []
        for name in ("refresh_btn",):
            btn = self.findChild(QPushButton, name)
            if btn:
                buttons.append(btn)
        for btn in buttons:
            btn.setEnabled(False)
        remaining = [COOLDOWN]

        def tick():
            remaining[0] -= 1
            if remaining[0] > 0:
                for btn in buttons:
                    btn.setToolTip(f"Refresh ready in {remaining[0]}s...")
            else:
                timer.stop()
                for btn in buttons:
                    btn.setEnabled(True)
                    btn.setToolTip("Reload data from SQLite database")

        timer = QTimer(self)
        timer.setInterval(1000)
        timer.timeout.connect(tick)
        timer.start()
        tick()

    def _setup_multi_user_sync(self):
        sync = self._services.sync_service
        if not sync.is_enabled():
            return
        try:
            self._shared_cache = sync._shared_cache
            self._session_registry = sync._session_registry
            self.owner_id = sync.get_owner_id()
            sync.start_heartbeat()
            self._presence_label = QLabel()
            self._presence_label.setObjectName("presence_label")
            self._presence_label.setToolTip("Click to see who else is online")
            self._presence_label.setCursor(Qt.PointingHandCursor)
            self._presence_label.mousePressEvent = lambda _: self._show_presence_tooltip()
            self.status_bar.addPermanentWidget(self._presence_label)
            self._presence_poll_timer = QTimer(self)
            self._presence_poll_timer.setInterval(60_000)
            self._presence_poll_timer.timeout.connect(self._update_presence_display)
            self._presence_poll_timer.start()
            self._update_presence_display()
            logger.info("MainWindow: Multi-user sync enabled for %s", self.owner_id)
        except Exception as e:
            logger.error("MainWindow: Multi-user sync unavailable: %s", e)
            if sync.is_save_blocked():
                QMessageBox.warning(
                    self,
                    "Sync Unavailable",
                    "Multi-user sync could not be initialized. Saves are disabled.",
                )

    def _update_presence_display(self) -> None:
        if self._presence_label is None:
            return
        try:
            sessions = self._services.sync_service.get_active_sessions()
            others = [s for s in sessions if s.owner != self.owner_id]
            if not others:
                self._presence_label.setText("")
                self._presence_label.setToolTip("No other users online")
            else:
                names = ", ".join(s.owner for s in others)
                self._presence_label.setText(
                    f"👤 {len(others)} other{'s' if len(others) > 1 else ''} online"
                )
                self._presence_label.setToolTip(f"Online: {names}")
        except Exception:
            self._presence_label.setText("")

    def _show_presence_tooltip(self) -> None:
        try:
            sessions = self._services.sync_service.get_active_sessions()
            if not sessions:
                QMessageBox.information(self, "Sessions", "No other users online.")
                return
            lines = ["Active sessions:"]
            for s in sessions:
                age = s.age_seconds
                ago = f"{age}s ago" if age < 120 else f"{age // 60}m ago"
                lines.append(f"  • {s.owner} (started {ago})")
            QMessageBox.information(self, "Active Sessions", "\n".join(lines))
        except Exception as e:
            self.status_bar.showMessage(f"Could not read sessions: {e}", 3000)

    # ── Import / Export (delegated to services) ────────────────────────

    def _pull_csv(self):
        if getattr(self, "_io_busy", False):
            self._notify("Operation in progress. Please wait...", "warning")
            return

        source_dir = self._services.config.get(
            "unedited_reports_dir", "P:/Detailing Schedule 2019/Unedited Reports"
        )
        source_path, _ = QFileDialog.getOpenFileName(
            self, "Select CSV Report", source_dir, "CSV Files (*.csv);;All Files (*)"
        )
        if not source_path:
            return

        self._set_io_busy(True)
        self.loading_overlay.show_with_message("Computing import diff...")
        self._csv_diff_worker = CSVDiffWorker(self._services.import_service, source_path)
        self._csv_diff_worker.finished.connect(self._on_csv_diff_finished)
        self._csv_diff_worker.error.connect(self._on_csv_diff_error)
        self._csv_diff_worker.start()

    def _on_csv_diff_finished(self, diff):
        self.loading_overlay.hide()
        self.notification_panel.flush_queue()
        self._set_io_busy(False)

        from gui.import_preview_dialog import ImportPreviewDialog
        dlg = ImportPreviewDialog(diff, parent=self)
        dlg.exec_()
        if not dlg.approved:
            self._notify("Import cancelled", "info")
            return

        self._set_io_busy(True)
        self.loading_overlay.show_with_message("Importing CSV...")
        self._csv_import_worker = CSVImportWorker(
            self._services.import_service, self._csv_diff_worker.source_path
        )
        self._csv_import_worker.finished.connect(self._on_csv_import_finished)
        self._csv_import_worker.error.connect(self._on_csv_import_error)
        self._csv_import_worker.start()

    def _on_csv_diff_error(self, error_msg: str):
        self.loading_overlay.hide()
        self.notification_panel.flush_queue()
        self._set_io_busy(False)
        logger.error("CSV diff calculation failed: %s", error_msg)
        QMessageBox.warning(
            self, "Import Preview Error", f"Could not compute import diff:\n{error_msg}"
        )
        self._notify("Import preview failed", "error")

    def _on_csv_import_finished(self, result):
        self.loading_overlay.hide()
        self.notification_panel.flush_queue()
        self._set_io_busy(False)
        self._notify(f"Imported {result.total_affected} rows successfully", "success")
        self._refresh_data()

    def _on_csv_import_error(self, error_msg: str):
        self.loading_overlay.hide()
        self.notification_panel.flush_queue()
        self._set_io_busy(False)
        logger.error("CSV import failed: %s", error_msg)
        QMessageBox.warning(self, "Import Error", f"Failed:\n{error_msg}")
        self._notify("Import failed", "error")

    def _pull_ssrs(self):
        if getattr(self, "_io_busy", False):
            self._notify("Operation in progress. Please wait...", "warning")
            return

        ssrs_url = self._services.config.get("ssrs_url", "")
        if not ssrs_url:
            QMessageBox.warning(
                self,
                "SSRS URL Missing",
                "No ssrs_url configured in config.yaml.\n"
                "Add the SSRS ReportServer endpoint URL under the ssrs_url key.",
            )
            return
        lookback = self._services.config.get("ssrs_lookback_days", 30)
        lookahead = self._services.config.get("ssrs_lookahead_days", 365)
        reply = QMessageBox.question(
            self,
            "Confirm SSRS Pull",
            f"Fetch latest data from SSRS?\n\nURL: {ssrs_url}\n"
            f"Date range: {lookback} days back → {lookahead} days forward\n\n"
            f"This will upsert all report rows into the SQLite database.\nContinue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        self._set_io_busy(True)
        self.loading_overlay.show_with_message("Fetching SSRS data...")
        self._pull_ssrs_worker = PullSSRSWorker(
            self._services.import_service, ssrs_url, lookback, lookahead
        )
        self._pull_ssrs_worker.finished.connect(self._on_pull_ssrs_finished)
        self._pull_ssrs_worker.error.connect(self._on_pull_ssrs_error)
        self._pull_ssrs_worker.start()

    def _on_pull_ssrs_finished(self, result):
        self.loading_overlay.hide()
        self.notification_panel.flush_queue()
        self._set_io_busy(False)
        self._notify(
            f"SSRS import complete — {result.inserted} inserted, "
            f"{result.updated} updated, {result.errors} errors",
            "success"
        )
        self._refresh_data()

    def _on_pull_ssrs_error(self, error_msg: str):
        self.loading_overlay.hide()
        self.notification_panel.flush_queue()
        self._set_io_busy(False)
        logger.error("SSRS pull failed: %s", error_msg)
        QMessageBox.warning(self, "SSRS Import Error", f"Failed:\n{error_msg}")
        self._notify("SSRS import failed", "error")

    def _export_excel(self):
        if getattr(self, "_io_busy", False):
            self._notify("Operation in progress. Please wait...", "warning")
            return

        excel_path = self._services.config.get("excel_path", "")
        if not excel_path or not os.path.exists(excel_path):
            reports_dir = self._services.config.get("unedited_reports_dir", "")
            if reports_dir:
                excel_path = os.path.join(reports_dir, "SCHDetailingReport_all_plants_MASTER.xlsm")
        if not excel_path or not os.path.exists(excel_path):
            excel_path, _ = QFileDialog.getOpenFileName(
                self,
                "Select Excel Workbook",
                os.path.dirname(excel_path) if excel_path else "",
                "Excel Files (*.xlsm *.xlsx);;All Files (*)",
            )
            if not excel_path:
                return
        reply = QMessageBox.question(
            self,
            "Confirm Export",
            f"Export SQLite data to:\n{excel_path}\n\n"
            f"This will overwrite the 'Current List' sheet.\nContinue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        self._set_io_busy(True)
        self.loading_overlay.show_with_message("Exporting to Excel...")
        self._excel_export_worker = ExcelExportWorker(
            self._services.export_service, excel_path, self._services.db_path
        )
        self._excel_export_worker.finished.connect(self._on_excel_export_finished)
        self._excel_export_worker.error.connect(self._on_excel_export_error)
        self._excel_export_worker.start()

    def _on_excel_export_finished(self, row_count):
        self.loading_overlay.hide()
        self.notification_panel.flush_queue()
        self._set_io_busy(False)
        self._notify(f"Exported {row_count} rows to Excel", "success")

    def _on_excel_export_error(self, error_msg: str):
        self.loading_overlay.hide()
        self.notification_panel.flush_queue()
        self._set_io_busy(False)
        logger.error("Excel export failed: %s", error_msg)
        QMessageBox.warning(self, "Export Error", f"Failed:\n{error_msg}")
        self._notify("Export failed", "error")

    def _open_audit(self, unit: Unit | None = None) -> None:
        """Open the audit trail dialog for the given or currently selected unit."""
        from gui.audit_dialog import AuditDialog

        com_number = None
        if unit is not None:
            com_number = unit.com_number
        elif hasattr(self, "current_unit") and self.current_unit is not None:
            com_number = self.current_unit.com_number
        dlg = AuditDialog(
            self._services.db_path,
            com_number=com_number,
            parent=self,
        )
        dlg.exec_()

    # ── Keyboard shortcuts ─────────────────────────────────────────────

    def keyPressEvent(self, a0) -> None:
        if a0 is None:
            super().keyPressEvent(a0)
            return
        if a0.key() == Qt.Key_S and a0.modifiers() & Qt.ControlModifier:
            if self.edit_form.current_unit is not None:
                self.edit_form._on_save()
            return
        if a0.key() == Qt.Key_T and a0.modifiers() & Qt.ControlModifier:
            self._toggle_theme()
            return
        if a0.key() == Qt.Key_F5:
            self._refresh_data()
            return
        if a0.key() == Qt.Key_F1:
            self._show_legend()
            return
        if a0.key() == Qt.Key_F and a0.modifiers() & Qt.ControlModifier:
            self._search_edit.setFocus()
            self._search_edit.selectAll()
            return
        if a0.key() == Qt.Key_1 and a0.modifiers() & Qt.ControlModifier:
            self._switch_view("calendar")
            return
        if a0.key() == Qt.Key_2 and a0.modifiers() & Qt.ControlModifier:
            self._switch_view("list")
            return
        if a0.key() == Qt.Key_3 and a0.modifiers() & Qt.ControlModifier:
            self._switch_view("alerts")
            return
        if a0.key() == Qt.Key_Escape:
            if self._search_edit.hasFocus():
                self._search_edit.clear()
                return
            self.on_unit_selected(None)
            return
        super().keyPressEvent(a0)

    # ── Theme ──────────────────────────────────────────────────────────

    def _toggle_theme(self) -> None:
        new_theme = "dark" if self._current_theme_name == "light" else "light"
        self._apply_theme_by_name(new_theme)

    def _update_theme_button(self) -> None:
        """Update theme button icon based on current theme (P14)."""
        if self._current_theme_name == "dark":
            self.theme_btn.setText("\u2600")  # ☀ sun (Unicode, no emoji)
        else:
            self.theme_btn.setText("\u263E")  # ☾ moon (Unicode, no emoji)
        self.theme_btn.setToolTip(
            "Switch to light theme (Ctrl+T)" if self._current_theme_name == "dark"
            else "Switch to dark theme (Ctrl+T)"
        )

    def _apply_theme_by_name(self, theme_name: str) -> None:
        from gui.theme import apply_theme

        apply_theme(self, theme_name, cvd_mode=self._current_cvd, high_contrast=self._current_hc)
        self._current_theme_name = theme_name
        self._update_theme_button()
        for panel in (self.calendar_panel, self.list_panel, self.timeline_panel, self.edit_form):
            if hasattr(panel, "set_theme"):
                panel.set_theme(theme_name, self._current_cvd)
        if hasattr(self, "notification_panel") and self.notification_panel is not None:
            self.notification_panel.set_theme(theme_name, self._current_cvd)
        self._update_alert_badge()
        self._save_ui_config()
        self._notify(f"Theme: {theme_name}", "info")

    def _on_column_widths_changed(self, widths: dict) -> None:
        self._services.config.setdefault("ui", {})["list_column_widths"] = widths
        self._save_ui_config()

    def _on_column_visibility_changed(self, keys: list) -> None:
        self._services.config.setdefault("ui", {})["list_visible_columns"] = keys
        self._save_ui_config()

    def _save_ui_config(self) -> None:
        if self._config_debounce_timer is None:
            self._config_debounce_timer = QTimer(self)
            self._config_debounce_timer.setSingleShot(True)
            self._config_debounce_timer.setInterval(2000)
            self._config_debounce_timer.timeout.connect(self._flush_config_save)
        self._config_debounce_timer.start()

    def _on_timeline_collapse_changed(self, collapsed: bool) -> None:
        """Persist timeline collapse state to config (P2)."""
        self._services.config.setdefault("ui", {})["timeline_collapsed"] = collapsed
        self._save_ui_config()

    def _on_toggle_right_panel(self) -> None:
        """Toggle right panel collapse/expand (P19)."""
        if self._right_collapsed:
            # Restore
            if self._right_panel_sizes:
                self.main_splitter.setSizes(self._right_panel_sizes)
            else:
                self.main_splitter.setSizes([self.width() // 2, self.width() // 2])
            self._right_collapsed = False
            self._collapse_btn.setText("▶")
            self._collapse_btn.setToolTip("Collapse right panel")
        else:
            # Collapse — save current sizes first
            self._right_panel_sizes = self.main_splitter.sizes()
            self.main_splitter.setSizes([self._right_panel_sizes[0] + self._right_panel_sizes[1], 0])
            self._right_collapsed = True
            self._collapse_btn.setText("◀")
            self._collapse_btn.setToolTip("Expand right panel")
        # Persist
        self._services.config.setdefault("ui", {})["right_panel_collapsed"] = self._right_collapsed
        self._save_ui_config()

    def _stop_debounce_flush(self) -> None:
        if self._config_debounce_timer is not None:
            with contextlib.suppress(RuntimeError):
                self._config_debounce_timer.stop()

    def _flush_config_save(self) -> None:
        self._services.config.setdefault("ui", {}).update(
            {
                "theme": self._current_theme_name,
                "colorblind_mode": self._current_cvd,
                "high_contrast": self._current_hc,
                "splitter_sizes": self.main_splitter.sizes(),
            }
        )
        # Persist current list sort state
        ui = self._services.config.setdefault("ui", {})
        if hasattr(self, "list_panel") and self.list_panel._model is not None:
            ui["list_sort_column"] = self.list_panel._sort_column
            ui["list_sort_ascending"] = self.list_panel._sort_ascending
        config_path = self._services.config_path
        if config_path and os.path.exists(os.path.dirname(config_path)):
            try:
                self._services.config_service.save(config_path, self._services.config)
            except OSError as exc:
                self.status_bar.showMessage(f"Could not save config: {exc}", 4000)

    def _open_a11y_dialog(self) -> None:
        from gui.a11y_dialog import A11yDialog

        dlg = A11yDialog(
            theme=self._current_theme_name,
            cvd_mode=self._current_cvd,
            high_contrast=self._current_hc,
            parent=self,
        )
        if dlg.exec_():
            self._current_cvd = dlg.cvd_mode
            self._current_hc = dlg.high_contrast
            self._apply_theme_by_name(self._current_theme_name)

    # ── Close handling ─────────────────────────────────────────────────

    def _begin_close_with_sync(self):
        from gui.close_progress_dialog import CloseProgressDialog

        self._stop_debounce_flush()
        self._close_waiting = True
        self._close_progress = CloseProgressDialog(parent=self)
        self._close_progress.show()
        self._close_poll_timer = QTimer(self)
        self._close_poll_timer.setInterval(150)
        self._close_poll_timer.timeout.connect(self._tick_close_progress)
        self._close_poll_timer.start()
        self._tick_close_progress()

    def _avg_unit_seconds(self) -> float:
        if not self._sync_unit_durations:
            return 0.0
        return sum(self._sync_unit_durations) / len(self._sync_unit_durations)

    def _tick_close_progress(self):
        in_flight = 1 if self._active_save_worker_running() else 0
        remaining = in_flight
        total = max(
            getattr(self, "_sync_status_session_initial", 0),
            getattr(self, "_sync_status_session_total", 0) + remaining,
        )
        avg = self._avg_unit_seconds()
        if self._close_progress is not None:
            self._close_progress.set_state(remaining, total, avg)
        if remaining == 0:
            if self._close_poll_timer is not None:
                self._close_poll_timer.stop()
                self._close_poll_timer = None
            if self._close_progress is not None:
                self._close_progress.accept()
                self._close_progress = None
            self._close_waiting = False
            QTimer.singleShot(0, self._real_close)

    def _cleanup_before_close(self) -> None:
        self._services.sync_service.stop_heartbeat()
        if self._presence_poll_timer is not None:
            with contextlib.suppress(RuntimeError):
                self._presence_poll_timer.stop()
        self._stop_debounce_flush()
        if self._close_poll_timer is not None:
            with contextlib.suppress(RuntimeError):
                self._close_poll_timer.stop()
        self._flush_config_save()

    def _real_close(self) -> None:
        self._closing = True
        self.close()

    def closeEvent(self, event) -> None:
        if self._closing:
            self._cleanup_before_close()
            event.accept()
            return
        if not self._confirm_discard():
            event.ignore()
            return
        if self._active_save_worker_running():
            event.ignore()
            if not self._close_waiting:
                self._begin_close_with_sync()
            return
        self._cleanup_before_close()
        event.accept()
