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
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QStatusBar,
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
from gui.onboarding import should_show_onboarding, show_onboarding
from gui.sync_status import SyncStatusWidget
from gui.theme import apply_theme, init_labels
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
        self._sync_status_widget: SyncStatusWidget | None = None
        self._sync_status_btn: QToolButton | None = None
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

    def _init_status_bar(self) -> None:
        self.setWindowTitle("Unit Tracker")
        self.setMinimumSize(1200, 700)
        self.status_bar = QStatusBar()
        self.status_bar.setObjectName("status_bar")
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Loading...")

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
        self.calendar_view_btn = QPushButton("📅 Calendar")
        self.list_view_btn = QPushButton("📋 List")
        self.alerts_view_btn = QPushButton("🔔 Alerts")
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

        self.theme_btn = QPushButton("☀" if self._current_theme_name == "dark" else "🌙")
        self.theme_btn.setObjectName("theme_btn")
        self.theme_btn.setToolTip("Toggle dark/light theme (Ctrl+T)")
        self.theme_btn.clicked.connect(self._toggle_theme)
        toggle_layout.addWidget(self.theme_btn)

        self.a11y_btn = QPushButton("♿")
        self.a11y_btn.setObjectName("a11y_btn")
        self.a11y_btn.setToolTip("Accessibility settings")
        self.a11y_btn.clicked.connect(self._open_a11y_dialog)
        toggle_layout.addWidget(self.a11y_btn)
        left_container.addLayout(toggle_layout)

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
        self.list_panel.stale_changed.connect(self._on_stale_changed)
        self.list_panel.column_widths_changed.connect(self._on_column_widths_changed)
        self.list_panel.column_visibility_changed.connect(self._on_column_visibility_changed)
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

        self.edit_form = EditForm(
            default_detailers=self._services.config.get("default_detailers", [])
        )
        self.edit_form.saved.connect(self.on_save_unit)
        self.edit_form.dirty_changed.connect(self._on_dirty_changed)
        right_panel.addWidget(self.edit_form, 1)

        auto_bar = self._build_automation_bar()
        right_panel.addLayout(auto_bar)
        self.main_splitter.addWidget(right_widget)

    def _init_splitter_sizes(self) -> None:
        saved_sizes = self._services.config.get("ui", {}).get("splitter_sizes")
        if saved_sizes:
            self.main_splitter.setSizes(saved_sizes)
        else:
            self.main_splitter.setSizes([self.width() // 3, 2 * self.width() // 3])

    def _init_loading_overlay(self) -> None:
        self.loading_overlay = LoadingOverlay(self.centralWidget())

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
        walkthrough_action = help_menu.addAction("&Show Walkthrough")
        walkthrough_action.setToolTip("Show the onboarding walkthrough")
        walkthrough_action.triggered.connect(lambda: show_onboarding(self, self._services.config))
        help_menu.addSeparator()
        about_action = help_menu.addAction("&About Unit Tracker")
        about_action.triggered.connect(self._show_about)

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

    def _on_stale_changed(self, show_stale: bool) -> None:
        self.calendar_panel.calendar.set_show_stale(show_stale)
        self.calendar_panel.refresh(self.units)

    def _on_dirty_changed(self, dirty: bool) -> None:
        self._form_dirty = dirty

    def _confirm_discard(self) -> bool:
        if not getattr(self, "_form_dirty", False):
            return True
        reply = QMessageBox.question(
            self,
            "Unsaved Changes",
            "You have unsaved changes. Discard them?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return reply == QMessageBox.Yes

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
            self.status_bar.showMessage(f"✓ Saved COM {unit.com_number}", 3000)

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
        self.status_bar.showMessage("Save failed — check network connection", 8000)

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
        self.status_bar.showMessage(f"Loaded {len(self.units)} units from SQLite")
        logger.info("MainWindow: Loaded %d units.", len(self.units))

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

    # ── Automation bar ─────────────────────────────────────────────────

    def _build_automation_bar(self):
        outer = QVBoxLayout()
        outer.setSpacing(4)
        row1 = QHBoxLayout()
        pull_csv_btn = QPushButton("📥 Import CSV")
        pull_csv_btn.setObjectName("pull_csv_btn")
        pull_csv_btn.setToolTip("Import SSRS CSV into SQLite database")
        pull_csv_btn.clicked.connect(self._pull_csv)
        row1.addWidget(pull_csv_btn)

        pull_ssrs_btn = QPushButton("🌐 Pull SSRS")
        pull_ssrs_btn.setObjectName("pull_ssrs_btn")
        pull_ssrs_btn.setToolTip("Fetch latest data from SSRS ReportServer and import into SQLite")
        pull_ssrs_btn.clicked.connect(self._pull_ssrs)
        row1.addWidget(pull_ssrs_btn)

        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.setObjectName("refresh_btn")
        refresh_btn.setToolTip("Reload data from SQLite database")
        refresh_btn.clicked.connect(self._refresh_data)
        row1.addWidget(refresh_btn)

        export_btn = QPushButton("💾 Export Excel")
        export_btn.setObjectName("export_btn")
        export_btn.setToolTip("Export SQLite data to Excel workbook (Current List sheet)")
        export_btn.clicked.connect(self._export_excel)
        row1.addWidget(export_btn)

        history_btn = QPushButton("📋 History")
        history_btn.setObjectName("history_btn")
        history_btn.setToolTip("View change history for the selected unit")
        history_btn.clicked.connect(self._open_audit)
        row1.addWidget(history_btn)

        outer.addLayout(row1)

        self._sync_status_widget = SyncStatusWidget()
        self._sync_status_widget.setObjectName("sync_status_widget")
        outer.addWidget(self._sync_status_widget)
        return outer

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
        source_dir = self._services.config.get(
            "unedited_reports_dir", "P:/Detailing Schedule 2019/Unedited Reports"
        )
        source_path, _ = QFileDialog.getOpenFileName(
            self, "Select CSV Report", source_dir, "CSV Files (*.csv);;All Files (*)"
        )
        if not source_path:
            return
        self.status_bar.showMessage("Computing import diff...")
        try:
            diff = self._services.import_service.diff_before_import(source_path)
        except Exception as e:
            QMessageBox.warning(
                self, "Import Preview Error", f"Could not compute import diff:\n{e}"
            )
            self.status_bar.showMessage("Import preview failed", 5000)
            return
        from gui.import_preview_dialog import ImportPreviewDialog

        dlg = ImportPreviewDialog(diff, parent=self)
        dlg.exec_()
        if not dlg.approved:
            self.status_bar.showMessage("Import cancelled", 3000)
            return
        self.status_bar.showMessage("Importing CSV...")
        try:
            result = self._services.import_service.from_csv(source_path)
            self.status_bar.showMessage(
                f"✓ Imported {result.total_affected} rows successfully", 8000
            )
            self._refresh_data()
        except Exception as e:
            QMessageBox.warning(self, "Import Error", f"Failed:\n{e}")
            self.status_bar.showMessage("Import failed", 5000)

    def _pull_ssrs(self):
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
        self.status_bar.showMessage("Fetching SSRS data...")
        try:
            result = self._services.import_service.from_ssrs(
                url=ssrs_url, lookback_days=lookback, lookahead_days=lookahead
            )
            self.status_bar.showMessage(
                f"✓ SSRS import complete — {result.inserted} inserted, "
                f"{result.updated} updated, {result.errors} errors",
                8000,
            )
            self._refresh_data()
        except Exception as e:
            logger.exception("SSRS pull failed")
            QMessageBox.warning(self, "SSRS Import Error", f"Failed:\n{e}")
            self.status_bar.showMessage("SSRS import failed", 5000)

    def _export_excel(self):
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
        self.status_bar.showMessage("Exporting to Excel...")
        try:
            row_count = self._services.export_service.to_excel(excel_path, self._services.db_path)
            self.status_bar.showMessage(f"✓ Exported {row_count} rows to Excel", 8000)
        except Exception as e:
            logger.exception("Excel export failed")
            QMessageBox.warning(self, "Export Error", f"Failed:\n{e}")
            self.status_bar.showMessage("Export failed", 5000)

    def _open_audit(self) -> None:
        """Open the audit trail dialog for the selected unit."""
        from gui.audit_dialog import AuditDialog

        com_number = None
        if hasattr(self, "current_unit") and self.current_unit is not None:
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
        if a0.key() == Qt.Key_F and a0.modifiers() & Qt.ControlModifier:
            if hasattr(self.list_panel, "com_search"):
                self.list_panel.com_search.setFocus()
                self.list_panel.com_search.selectAll()
            return
        if a0.key() == Qt.Key_Escape:
            self.on_unit_selected(None)
            return
        super().keyPressEvent(a0)

    # ── Theme ──────────────────────────────────────────────────────────

    def _toggle_theme(self) -> None:
        new_theme = "dark" if self._current_theme_name == "light" else "light"
        self._apply_theme_by_name(new_theme)

    def _apply_theme_by_name(self, theme_name: str) -> None:
        from gui.theme import apply_theme

        apply_theme(self, theme_name, cvd_mode=self._current_cvd, high_contrast=self._current_hc)
        self._current_theme_name = theme_name
        self.theme_btn.setText("☀" if theme_name == "dark" else "🌙")
        for panel in (self.calendar_panel, self.list_panel, self.timeline_panel, self.edit_form):
            if hasattr(panel, "set_theme"):
                panel.set_theme(theme_name, self._current_cvd)
        self._save_ui_config()
        self.status_bar.showMessage(f"Theme: {theme_name}", 2000)

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
        if self._active_save_worker_running():
            event.ignore()
            if not self._close_waiting:
                self._begin_close_with_sync()
            return
        self._cleanup_before_close()
        event.accept()
