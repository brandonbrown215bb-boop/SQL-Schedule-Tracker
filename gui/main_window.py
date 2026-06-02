# gui/main_window.py
import logging
import os
import time

from PyQt5.QtCore import QFileSystemWatcher, Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from data.loader import load_units
from data.writer import save_unit
from data.models import Unit
from gui.calendar_panel import CalendarPanel
from gui.conflict_dialog import ConflictDialog
from gui.edit_form import EditForm
from gui.list_panel import ListPanel
from gui.loading_overlay import LoadingOverlay
from gui.onboarding import should_show_onboarding, show_onboarding
from gui.sync_status import SyncStatusWidget
from gui.timeline_panel import TimelinePanel
from sync.revision_store import RevisionConflictError

logger = logging.getLogger(__name__)

# Lazy imports (inside methods):
#   automation.import_csv.import_csv  (in _pull_csv)
#   sync.lock_manager.LockManager      (in _setup_multi_user_sync)
#   sync.revision_store.RevisionStore  (in _setup_multi_user_sync)
#   sync.session_registry.SessionRegistry (in _setup_multi_user_sync)
#   sync.shared_cache.SharedCache      (in _setup_multi_user_sync)


SQLITE_HEADER = b"SQLite format 3\x00"


class LoadWorker(QThread):
    """Background worker for loading units from SQLite."""

    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(
        self, db_path: str, detailer_schedules: dict, force_reload: bool = False
    ):
        super().__init__()
        self.db_path = db_path
        self.detailer_schedules = detailer_schedules
        self.force_reload = force_reload

    def run(self):
        try:
            units = load_units(
                self.db_path,
                detailer_schedules=self.detailer_schedules,
                force_reload=self.force_reload,
            )
            self.finished.emit(units)
        except Exception as e:
            self.error.emit(str(e))


class SaveWorker(QThread):
    """Background worker for saving units to SQLite.

    Emits ``finished`` on success, ``error(str)`` on generic errors.
    """

    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, db_path: str, unit: Unit):
        super().__init__()
        self.db_path = db_path
        self.unit = unit

    def run(self):
        try:
            save_unit(self.db_path, self.unit)
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))


class MainWindow(QMainWindow):
    def __init__(self, config: dict, config_path: str | None = None, db_path: str | None = None):
        super().__init__()
        self.config = config
        self.db_path = db_path
        self.units: list[Unit] = []
        self.current_unit: Unit | None = None
        self._load_worker: LoadWorker | None = None
        self._save_worker: SaveWorker | None = None
        self._form_dirty: bool = False
        self._shared_cache = None
        self._session_registry = None
        self._presence_label: QLabel | None = None
        self._presence_poll_timer: QTimer | None = None
        self._retired_save_workers: list[SaveWorker] = []
        self._save_worker_errors: dict[SaveWorker, str] = {}
        self._file_poll_timer: QTimer | None = None
        self._auto_refresh_timer: QTimer | None = None
        self._config_debounce_timer: QTimer | None = None

        # ── Sync-queue UI state ───────────────────────────────────
        self._sync_status_widget: SyncStatusWidget | None = None
        self._sync_status_btn: QToolButton | None = None
        self._sync_status_session_total: int = 0
        self._sync_status_session_initial: int = 0
        self._sync_unit_durations: list[float] = []
        self._current_unit_save_started_at: float = 0.0
        self._close_progress = None
        self._close_poll_timer: QTimer | None = None
        self._closing: bool = False

        # ── US-003: Error dialog throttling ──────────────────────────
        self._error_dialog_count = 0
        self._error_dialog_window_start = 0.0
        self._error_dialog_threshold = 3
        self._error_dialog_window_seconds = 10.0

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
        self._init_theme(config, config_path)
        self._check_onboarding()
        self._load_data_async(force_reload=False)

    def _init_theme(self, config: dict, config_path: str | None) -> None:
        """Initialize theme from config and apply to widget tree."""
        from gui.theme import init_labels, apply_theme
        init_labels(config.get("status_labels", {}))
        ui_cfg = config.get("ui", {})
        self._current_theme_name = ui_cfg.get("theme", "light")
        self._current_cvd: str = ui_cfg.get("colorblind_mode", "none")
        self._current_hc: bool = ui_cfg.get("high_contrast", False)
        apply_theme(self, self._current_theme_name,
                    cvd_mode=self._current_cvd,
                    high_contrast=self._current_hc)
        self._config_path = config_path

    def _init_status_bar(self) -> None:
        """Create and configure the status bar."""
        self.setWindowTitle("Unit Tracker")
        self.setMinimumSize(1200, 700)
        self.status_bar = QStatusBar()
        self.status_bar.setObjectName("status_bar")
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Loading...")

    def _init_central_layout(self) -> None:
        """Create central widget with QSplitter."""
        central = QWidget()
        self.setCentralWidget(central)
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout = QHBoxLayout(central)
        main_layout.addWidget(self.main_splitter)

    def _init_left_panel(self) -> None:
        """Build the left panel: view toggle + stacked calendar/list."""
        left_widget = QWidget()
        left_container = QVBoxLayout(left_widget)

        # View toggle buttons
        toggle_layout = QHBoxLayout()
        self.calendar_view_btn = QPushButton("📅 Calendar")
        self.list_view_btn = QPushButton("\U0001f4cb List")
        self.list_view_btn.setObjectName("list_view_btn")
        self.calendar_view_btn.setCheckable(True)
        self.list_view_btn.setCheckable(True)
        self.calendar_view_btn.setChecked(True)
        self.calendar_view_btn.clicked.connect(lambda: self._switch_view("calendar"))
        self.list_view_btn.clicked.connect(lambda: self._switch_view("list"))
        toggle_layout.addWidget(self.calendar_view_btn)
        toggle_layout.addWidget(self.list_view_btn)
        toggle_layout.addStretch()

        # Theme toggle button
        self.theme_btn = QPushButton("☀" if self._current_theme_name == "dark" else "🌙")
        self.theme_btn.setObjectName("theme_btn")
        self.theme_btn.setToolTip("Toggle dark/light theme (Ctrl+T)")
        self.theme_btn.clicked.connect(self._toggle_theme)
        toggle_layout.addWidget(self.theme_btn)

        # Accessibility settings button
        self.a11y_btn = QPushButton("♿")
        self.a11y_btn.setObjectName("a11y_btn")
        self.a11y_btn.setToolTip("Accessibility settings")
        self.a11y_btn.clicked.connect(self._open_a11y_dialog)
        toggle_layout.addWidget(self.a11y_btn)

        left_container.addLayout(toggle_layout)

        # Stacked widget
        self.view_stack = QStackedWidget()
        self.view_stack.setObjectName("view_stack")
        self.calendar_panel = CalendarPanel(self.units)
        self.calendar_panel.unit_selected.connect(self.on_unit_selected)
        self.view_stack.addWidget(self.calendar_panel)
        self.list_panel = ListPanel(self.units)
        self.list_panel.unit_selected.connect(self.on_unit_selected)
        self.view_stack.addWidget(self.list_panel)
        left_container.addWidget(self.view_stack)
        self.main_splitter.addWidget(left_widget)

        # Restore saved view preference
        saved_view = self.config.get("ui", {}).get("last_view", "calendar")
        if saved_view == "list":
            self._switch_view("list")

    def _init_right_panel(self) -> None:
        """Build the right panel: timeline + edit form + automation bar."""
        right_widget = QWidget()
        right_panel = QVBoxLayout(right_widget)

        self.timeline_panel = TimelinePanel()
        right_panel.addWidget(self.timeline_panel)

        self.edit_form = EditForm(default_detailers=self.config.get("default_detailers", []))
        self.edit_form.saved.connect(self.on_save_unit)
        self.edit_form.dirty_changed.connect(self._on_dirty_changed)
        right_panel.addWidget(self.edit_form, 1)

        auto_bar = self._build_automation_bar()
        right_panel.addLayout(auto_bar)
        self.main_splitter.addWidget(right_widget)

    def _init_splitter_sizes(self) -> None:
        """Restore saved splitter sizes or use defaults."""
        saved_sizes = self.config.get("ui", {}).get("splitter_sizes")
        if saved_sizes:
            self.main_splitter.setSizes(saved_sizes)
        else:
            self.main_splitter.setSizes([self.width() // 3, 2 * self.width() // 3])

    def _init_loading_overlay(self) -> None:
        """Create the loading overlay on top of the central widget."""
        self.loading_overlay = LoadingOverlay(self.centralWidget())

    def _check_onboarding(self) -> None:
        """Show onboarding walkthrough on first launch."""
        if should_show_onboarding(self.config):
            QTimer.singleShot(500, lambda: show_onboarding(self, self.config))

    # ── Help menu ──────────────────────────────────────────────────────

    def _build_help_menu(self):
        """Build the Help menu with walkthrough and about actions."""
        menubar = self.menuBar()

        # ── Reports menu ──
        reports_menu = menubar.addMenu("&Reports")

        dashboard_action = reports_menu.addAction("📊 Scheduling Dashboard")
        dashboard_action.setToolTip("Open the scheduling status chart (exportable as PNG)")
        dashboard_action.triggered.connect(self._open_dashboard)

        # ── Help menu ──
        help_menu = menubar.addMenu("&Help")

        # Show Walkthrough
        walkthrough_action = help_menu.addAction("&Show Walkthrough")
        walkthrough_action.setToolTip("Show the onboarding walkthrough")
        walkthrough_action.triggered.connect(
            lambda: show_onboarding(self, self.config)
        )

        help_menu.addSeparator()

        # About
        about_action = help_menu.addAction("&About Unit Tracker")
        about_action.triggered.connect(self._show_about)

    def _show_about(self):
        QMessageBox.about(
            self,
            "About Unit Tracker",
            "<b>Unit Tracker</b><br><br>"
            "A desktop viewer/editor for detailing schedules.<br>"
            f"Python {__import__('sys').version.split()[0]} | "
        f"PyQt5 | SQLite<br><br>"
            "© 2026",
        )

    def _open_dashboard(self) -> None:
        """Open the scheduling dashboard dialog."""
        if not self.db_path:
            QMessageBox.information(self, "Dashboard", "No database loaded.")
            return
        from gui.pivot_chart import PivotChartWidget as PivotChartDialog
        dlg = PivotChartDialog(
            self.db_path,
            theme_name=self._current_theme_name,
            cvd_mode=self._current_cvd,
            parent=self,
        )
        dlg.exec_()

    # ── View switching ─────────────────────────────────────────────────

    def _switch_view(self, view_name: str) -> None:
        """Swap between calendar and list views."""
        if view_name == "calendar":
            self.view_stack.setCurrentIndex(0)
            self.calendar_view_btn.setChecked(True)
            self.list_view_btn.setChecked(False)
        elif view_name == "list":
            self.view_stack.setCurrentIndex(1)
            self.calendar_view_btn.setChecked(False)
            self.list_view_btn.setChecked(True)
            # Populate list panel if it has no data yet
            if self.units and self.list_panel._model is None:
                self.list_panel.set_units(self.units)

        # Save preference
        self.config.setdefault("ui", {})["last_view"] = view_name
        logger.info("MainWindow: Switched to %s view.", view_name)

    def _on_dirty_changed(self, dirty: bool) -> None:
        self._form_dirty = dirty

    def _confirm_discard(self) -> bool:
        """Return True if it's safe to discard unsaved changes."""
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
            self.status_bar.showMessage(f"Selected: COM {unit.com_number} — {unit.job_name}")
        else:
            self.status_bar.showMessage("No unit selected")

    def on_save_unit(self, unit: Unit):
        """Save unit to SQLite asynchronously and refresh UI."""
        self._commit_unit_to_memory(unit)
        self._start_save_worker(unit)

    def _start_save_worker(self, unit: Unit) -> None:
        """Start a background SaveWorker for the given unit."""
        if self._active_save_worker_running():
            logger.warning("Save already in progress — queuing")
            return

        self.status_bar.showMessage(f"Saving COM {unit.com_number}...")
        worker = SaveWorker(self.db_path, unit)
        worker.finished.connect(self._on_save_finished)
        worker.error.connect(self._on_save_error)
        self._save_worker = worker
        self._save_worker_errors[worker] = ""
        worker.start()

    def _on_save_finished(self) -> None:
        """Handle successful save — refresh UI."""
        worker = self.sender()
        if worker:
            self._retire_save_worker(worker)

        unit = self.current_unit
        if unit:
            self.calendar_panel.refresh(self.units)
            self.list_panel.refresh(self.units)
            self.timeline_panel.set_unit(unit)
            self.edit_form.current_unit = unit
            self.status_bar.showMessage(f"✓ Saved COM {unit.com_number}", 3000)

    def _on_save_error(self, error_msg: str) -> None:
        """Handle save error."""
        worker = self.sender()
        if worker:
            self._save_worker_errors[worker] = error_msg
            self._retire_save_worker(worker)

        logger.error("Save error: %s", error_msg)
        QMessageBox.warning(self, "Save Error", f"Failed to save:\n{error_msg}")
        self.status_bar.showMessage("Save failed", 5000)

    def _active_save_worker_running(self) -> bool:
        """Return True while the active worker's thread is still alive."""
        worker = self._save_worker
        if worker is None:
            return False
        try:
            return worker.isRunning()
        except RuntimeError:
            return False

    def _retire_save_worker(self, worker: SaveWorker) -> None:
        """Keep a finished worker referenced until Qt safely deletes it."""
        if self._save_worker is worker:
            self._save_worker = None
        if worker not in self._retired_save_workers:
            self._retired_save_workers.append(worker)
            worker.deleteLater()

    def _release_save_worker(self, worker: SaveWorker) -> None:
        """Drop references after Qt destroys the QThread object."""
        if worker in self._retired_save_workers:
            self._retired_save_workers.remove(worker)
        self._save_worker_errors.pop(worker, None)

    def _commit_unit_to_memory(self, unit: Unit) -> None:
        """Replace the selected unit immediately so navigation shows current edits."""
        # Preserve manually-assigned status colors (purple/orange) — only
        # recalculate if the current color is one of the auto-computed ones.
        if unit.status_color in ("gray", "yellow", "green", "red"):
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

    # ── Data loading ───────────────────────────────────────────────────

    def _load_data_async(self, force_reload: bool = False):
        """Load data in background thread from SQLite."""
        if getattr(self, "_io_busy", False):
            logger.info("MainWindow: Load requested but I/O already in progress — skipping")
            self.status_bar.showMessage("Please wait — operation in progress...", 2000)
            return
        self.status_bar.showMessage("Loading..." if not force_reload else "Refreshing...")

        self._set_io_busy(True)
        self._load_worker = LoadWorker(
            self.db_path,
            self.config.get("detailer_schedules", {}),
            force_reload=force_reload,
        )
        self._load_worker.finished.connect(self._on_load_finished)
        self._load_worker.error.connect(self._on_load_error)
        self._load_worker.start()

    def _on_load_finished(self, units: list[Unit]):
        """Handle successful load."""
        self._set_io_busy(False)
        self.units = units
        self.calendar_panel.refresh(self.units)
        self.list_panel.set_units(self.units)
        self.status_bar.showMessage(f"Loaded {len(self.units)} units from SQLite")
        logger.info("MainWindow: Loaded %d units.", len(self.units))

        # US-007: If file changed during the reload, schedule one more reload
        # to capture the latest state (capped at 1 follow-up to prevent loops).
        if self._pending_reload_count > 0:
            self._pending_reload_count = 0
            logger.info("MainWindow: Pending file change detected — scheduling follow-up reload")
            QTimer.singleShot(1000, self._trigger_pending_reload)

    def _trigger_pending_reload(self):
        """Trigger a single follow-up reload after a load completed (US-007)."""
        if getattr(self, "_io_busy", False):
            return
        if self._active_save_worker_running():
            return
        self._load_data_async(force_reload=False)

    def _should_suppress_error_dialog(self) -> bool:
        """Return True if error dialogs should be throttled (US-003)."""
        now = time.monotonic()
        if now - self._error_dialog_window_start >= self._error_dialog_window_seconds:
            # Reset window
            self._error_dialog_window_start = now
            self._error_dialog_count = 0
        self._error_dialog_count += 1
        if self._error_dialog_count > self._error_dialog_threshold:
            return True
        return False

    def _on_load_error(self, error_msg: str):
        """Handle load error with retry and throttling (US-003)."""
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
            self._load_data_async(force_reload=True)

        self.units = []

    # ── Refresh / Pull ──────────────────────────────────────────────

    def _refresh_data(self):
        """Refresh data from SQLite (async)."""
        self._apply_refresh_cooldown()
        self._load_data_async(force_reload=False)

    # ── File watcher ───────────────────────────────────────────────────

    def _setup_file_watcher(self) -> None:
        """Setup file watcher to auto-refresh when SQLite database changes."""
        self._file_watcher = QFileSystemWatcher()
        self._file_watcher.fileChanged.connect(self._on_file_changed)
        self._pending_reload_count = 0
        # Watch the SQLite database file for external changes
        if self.db_path and os.path.exists(self.db_path):
            self._file_watcher.addPath(self.db_path)

    def _on_file_changed(self, path: str):
        """Handle file change notification from QFileSystemWatcher.

        When the SQLite database file changes externally, we wait for it to be
        fully written (via polling) and then reload. For SQLite files, we check
        the SQLite header magic bytes. For Excel files, we check the ZIP header.
        """
        logger.info("MainWindow: Detected change in %s", path)

        # Ignore if we're currently loading or saving (prevents save→load→save loops)
        if getattr(self, "_io_busy", False):
            logger.info("MainWindow: Ignoring file change — I/O in progress")
            return
        if self._active_save_worker_running():
            logger.info("MainWindow: Ignoring file change — Excel sync in progress")
            return

        # Coalesce: ignore duplicate events within 5 seconds
        now = time.monotonic()
        if now - getattr(self, "_last_file_change", 0) < 5.0:
            # A reload is already queued/scheduled — mark that another change arrived
            self._pending_reload_count += 1
            logger.info("MainWindow: File change during debounce window (pending=%d)", self._pending_reload_count)
            return
        self._last_file_change = now
        self._pending_reload_count = 0

        # Schedule non-blocking file readiness check via QTimer
        self._file_change_path = path
        self._file_deadline = now + 8.0
        self._stop_file_poll_timer()
        self._file_poll_timer = QTimer(self)
        self._file_poll_timer.setSingleShot(False)
        self._file_poll_timer.setInterval(500)  # check every 500ms
        self._file_poll_timer.timeout.connect(self._check_file_ready)
        self._file_poll_timer.start()
        self.status_bar.showMessage("File changed — waiting...", 2000)

    def _check_file_ready(self):
        """Non-blocking check if the changed file is ready to read.

        Works with both SQLite databases and Excel (.xlsx) files by checking
        the appropriate magic bytes.
        """
        path = self._file_change_path
        deadline = self._file_deadline

        if time.monotonic() > deadline:
            logger.info("MainWindow: File not ready after timeout, skipping reload")
            self._stop_file_poll_timer()
            return

        try:
            if not os.path.exists(path):
                return  # still not ready, wait for next tick
            size = os.path.getsize(path)
            if size < 100:
                return
            with open(path, "rb") as f:
                header = f.read(16)  # Read enough for both SQLite (16) and ZIP (4) headers
            # Check for SQLite header first
            if header.startswith(SQLITE_HEADER):
                # SQLite file is ready — stop polling and reload
                self._stop_file_poll_timer()
                self._load_data_async(force_reload=False)
                return
            # Check for ZIP/xlsx header
            if header[:4] == b"PK\x03\x04":
                # File is ready — stop polling
                self._stop_file_poll_timer()
                self._load_data_async(force_reload=False)
                return
            # Unknown file type — return and let polling continue until timeout
            return
        except OSError:
            return  # file still locked, wait for next tick

    def _stop_file_poll_timer(self):
        """Stop and clear the file poll timer even if Qt already deleted it."""
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
        """Mark I/O as in-progress (prevents watcher from re-triggering)."""
        self._io_busy = busy

    # ── A1: Auto-refresh timer ─────────────────────────────────────────

    def _setup_auto_refresh(self) -> None:
        """Start a periodic background refresh timer (configurable interval)."""
        interval_min = self.config.get("ui", {}).get("auto_refresh_minutes", 0)
        if interval_min <= 0:
            return  # disabled

        interval_ms = interval_min * 60 * 1000
        self._auto_refresh_timer = QTimer(self)
        self._auto_refresh_timer.setInterval(interval_ms)
        self._auto_refresh_timer.timeout.connect(self._on_auto_refresh)
        self._auto_refresh_timer.start()
        logger.info("MainWindow: Auto-refresh every %d minute(s)", interval_min)
        self.status_bar.showMessage(f"Auto-refresh: {interval_min}min", 3000)

    def _on_auto_refresh(self) -> None:
        """Called by auto-refresh timer. Skips if I/O is busy or a save is pending."""
        if getattr(self, "_io_busy", False):
            return
        if self._active_save_worker_running():
            return
        # Cache-first reload — don't force a full Excel parse
        self._load_data_async(force_reload=False)

    # ── A3: Refresh cooldown ───────────────────────────────────────────

    def _apply_refresh_cooldown(self) -> None:
        """Disable refresh buttons for COOLDOWN seconds, with countdown tooltip."""
        COOLDOWN = 3  # seconds

        buttons: list[QPushButton] = []
        for name in ("refresh_btn",):
            btn = self.findChild(QPushButton, name)
            if btn:
                buttons.append(btn)

        for btn in buttons:
            btn.setEnabled(False)

        # Countdown timer — update tooltip every second
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
                    if btn.objectName() == "refresh_btn":
                        btn.setToolTip("Reload data from SQLite database")
                    else:
                        btn.setToolTip("Force a full reload from the Excel workbook")

        timer = QTimer(self)
        timer.setInterval(1000)
        timer.timeout.connect(tick)
        timer.start()
        tick()  # immediate first update

    # ── Automation bar ─────────────────────────────────────────────────

    def _build_automation_bar(self):
        outer = QVBoxLayout()
        outer.setSpacing(4)

        # Row 1: Action buttons
        row1 = QHBoxLayout()
        pull_csv_btn = QPushButton("\U0001f4e5 Import CSV")
        pull_csv_btn.setObjectName("pull_csv_btn")
        pull_csv_btn.setToolTip("Import SSRS CSV into SQLite database")
        pull_csv_btn.clicked.connect(self._pull_csv)
        row1.addWidget(pull_csv_btn)

        refresh_btn = QPushButton("\U0001f504 Refresh")
        refresh_btn.setObjectName("refresh_btn")
        refresh_btn.setToolTip("Reload data from SQLite database")
        refresh_btn.clicked.connect(self._refresh_data)
        row1.addWidget(refresh_btn)

        outer.addLayout(row1)

        # Row 2: Sync queue status widget (hidden when idle)
        self._sync_status_widget = SyncStatusWidget()
        self._sync_status_widget.setObjectName("sync_status_widget")
        outer.addWidget(self._sync_status_widget)

        return outer
    def _setup_multi_user_sync(self):
        """Initialize optional cache-first multi-user sync helpers.

        Sets up:
          - LockManager (file-level locks)
          - RevisionStore (per-COM optimistic revisions)
          - SharedCache (per-COM remote field values for conflict diffs)
          - SessionRegistry (heartbeat + presence)
          - Presence label in status bar
        """
        settings = self.config.get("multi_user", {})
        if not settings.get("enabled", False):
            return
        try:
            import getpass
            import socket

            from sync.lock_manager import LockManager
            from sync.revision_store import RevisionStore
            from sync.shared_cache import SharedCache
            from sync.session_registry import SessionRegistry

            username = settings.get("username") or os.environ.get("USERNAME") or getpass.getuser()
            machine = settings.get("machine") or os.environ.get("COMPUTERNAME") or socket.gethostname()
            self.owner_id = f"{username}@{machine}"

            # Core sync infrastructure (uses db_path for lock files)
            self.lock_manager = LockManager(self.db_path, username, machine)
            self.revision_store = RevisionStore(self.db_path)
            self._shared_cache = SharedCache(self.db_path)

            # Wire shared cache into revision store so commits auto-update it
            self.revision_store.set_shared_cache(self._shared_cache)

            # Session heartbeat
            self._session_registry = SessionRegistry(self.db_path, self.owner_id)
            self._session_registry.start(parent=self)

            # Presence display (status bar label)
            self._presence_label = QLabel()
            self._presence_label.setObjectName("presence_label")
            self._presence_label.setToolTip("Click to see who else is online")
            self._presence_label.setCursor(Qt.PointingHandCursor)
            self._presence_label.mousePressEvent = lambda _: self._show_presence_tooltip()
            self.status_bar.addPermanentWidget(self._presence_label)

            # Presence polling timer (every 60 seconds)
            self._presence_poll_timer = QTimer(self)
            self._presence_poll_timer.setInterval(60_000)
            self._presence_poll_timer.timeout.connect(self._update_presence_display)
            self._presence_poll_timer.start()

            # Initial presence update
            self._update_presence_display()

            logger.info("MainWindow: Multi-user sync enabled for %s", self.owner_id)
        except Exception as e:
            mode = settings.get("fallback_mode", "block")
            logger.error("MainWindow: Multi-user sync unavailable: %s", e)
            if mode == "block":
                self._sync_save_blocked = True
                QMessageBox.warning(
                    self,
                    "Sync Unavailable",
                    "Multi-user sync could not be initialized. Saves are disabled until "
                    "sync is available or multi_user.enabled is false.",
                )

    def _update_presence_display(self) -> None:
        """Update the presence label in the status bar."""
        if self._presence_label is None:
            return
        try:
            from sync.session_registry import SessionRegistry
            sessions = SessionRegistry.list_active(self.db_path)
            # Filter out our own session
            others = [s for s in sessions if s.owner != self.owner_id]
            if not others:
                self._presence_label.setText("")
                self._presence_label.setToolTip("No other users online")
            else:
                names = ", ".join(s.owner for s in others)
                self._presence_label.setText(f"👤 {len(others)} other{'s' if len(others) > 1 else ''} online")
                self._presence_label.setToolTip(f"Online: {names}")
        except Exception:
            self._presence_label.setText("")

    def _show_presence_tooltip(self) -> None:
        """Show a detailed popup listing active sessions."""
        try:
            from sync.session_registry import SessionRegistry
            sessions = SessionRegistry.list_active(self.db_path)
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

    def _pull_csv(self):
        # Step 1: File dialog — user picks the CSV file
        import logging
        logger = logging.getLogger(__name__)
        source_dir = self.config.get(
            "unedited_reports_dir", "P:/Detailing Schedule 2019/Unedited Reports"
        )
        source_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select CSV Report",
            source_dir,
            "CSV Files (*.csv);;All Files (*)",
        )
        if not source_path:
            return  # user cancelled

        # Step 2: Confirm
        reply = QMessageBox.question(
            self,
            "Confirm Import",
            f"Import data from:\n{source_path}\n\n"
            f"Into SQLite database?\n\n"
            f"Continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        # Step 3: Run the import pipeline
        self.status_bar.showMessage("Importing CSV...")
        try:
            from automation.import_csv import import_csv
            row_count = import_csv(self.db_path, source_path)
            self.status_bar.showMessage(
                f"✓ Imported {row_count} rows successfully", 8000
            )
            # Reload data so the calendar reflects the update
            self._refresh_data()
        except Exception as e:
            QMessageBox.warning(self, "Import Error", f"Failed:\n{e}")
            self.status_bar.showMessage("Import failed", 5000)

    def keyPressEvent(self, a0) -> None:
        if a0 is None:
            super().keyPressEvent(a0)
            return
        # Ctrl+S — save
        if a0.key() == Qt.Key_S and a0.modifiers() & Qt.ControlModifier:
            if self.edit_form.current_unit is not None:
                self.edit_form._on_save()
            return
        # Ctrl+T — toggle theme
        if a0.key() == Qt.Key_T and a0.modifiers() & Qt.ControlModifier:
            self._toggle_theme()
            return
        # F5 — refresh
        if a0.key() == Qt.Key_F5:
            self._refresh_data()
            return
        # Ctrl+F — focus search
        if a0.key() == Qt.Key_F and a0.modifiers() & Qt.ControlModifier:
            if hasattr(self.list_panel, 'com_search'):
                self.list_panel.com_search.setFocus()
                self.list_panel.com_search.selectAll()
            return
        # Escape — clear selection
        if a0.key() == Qt.Key_Escape:
            self.on_unit_selected(None)
            return
        super().keyPressEvent(a0)

    # ── Theme ────────────────────────────────────────────────────────────

    def _toggle_theme(self) -> None:
        new_theme = "dark" if self._current_theme_name == "light" else "light"
        self._apply_theme_by_name(new_theme)

    def _apply_theme_by_name(self, theme_name: str) -> None:
        """Apply theme to entire widget tree, notify panels, persist."""
        from gui.theme import apply_theme
        apply_theme(self, theme_name,
                    cvd_mode=self._current_cvd,
                    high_contrast=self._current_hc)
        self._current_theme_name = theme_name
        self.theme_btn.setText("☀" if theme_name == "dark" else "🌙")
        # Propagate to panels — no parent-walking needed
        for panel in (self.calendar_panel, self.list_panel,
                      self.timeline_panel, self.edit_form):
            if hasattr(panel, "set_theme"):
                panel.set_theme(theme_name, self._current_cvd)
        self._save_ui_config()
        self.status_bar.showMessage(f"Theme: {theme_name}", 2000)

    def _save_ui_config(self) -> None:
        """Debounced write of ui config to config.yaml (US-005).

        Batches rapid setting changes into a single write after 2 seconds
        of inactivity.  Call :meth:`_flush_config_save` to write immediately
        (e.g. on application close).
        """
        if self._config_debounce_timer is None:
            self._config_debounce_timer = QTimer(self)
            self._config_debounce_timer.setSingleShot(True)
            self._config_debounce_timer.setInterval(2000)  # 2-second debounce
            self._config_debounce_timer.timeout.connect(self._flush_config_save)
        self._config_debounce_timer.start()

    def _stop_debounce_flush(self) -> None:
        """Stop the config debounce timer if running."""
        if self._config_debounce_timer is not None:
            try:
                self._config_debounce_timer.stop()
            except RuntimeError:
                pass

    def _flush_config_save(self) -> None:
        """Immediately write ui config to config.yaml (US-005)."""
        import yaml
        import os
        self.config.setdefault("ui", {}).update({
            "theme": self._current_theme_name,
            "colorblind_mode": self._current_cvd,
            "high_contrast": self._current_hc,
            "splitter_sizes": self.main_splitter.sizes(),
        })
        # Remove runtime-only keys that should not be persisted to YAML
        save_config = {k: v for k, v in self.config.items() if k != "config_path"}
        config_path = getattr(self, "_config_path", None)
        if config_path and os.path.exists(os.path.dirname(config_path)):
            try:
                with open(config_path, "w", encoding="utf-8") as fh:
                    yaml.safe_dump(save_config, fh, default_flow_style=False,
                                   allow_unicode=True)
            except OSError as exc:
                self.status_bar.showMessage(
                    f"Could not save theme preference: {exc}", 4000)

    def _open_a11y_dialog(self) -> None:
        """Open the accessibility settings dialog."""
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

    def _begin_close_with_sync(self) -> None:
        from gui.close_progress_dialog import CloseProgressDialog
        self._stop_debounce_flush()
        self._closing = True
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

    def _tick_close_progress(self) -> None:
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
            QTimer.singleShot(0, self._real_close)

    def _real_close(self) -> None:
        if self._session_registry is not None:
            try:
                self._session_registry.stop()
            except Exception:
                pass
        if self._presence_poll_timer is not None:
            try:
                self._presence_poll_timer.stop()
            except RuntimeError:
                pass
        self._stop_debounce_flush()
        if self._close_poll_timer is not None:
            try:
                self._close_poll_timer.stop()
            except RuntimeError:
                pass
        self._flush_config_save()
        super().close()
