# gui/list_panel.py
"""List Panel — sortable, filterable table view of all units.

Emits the same `unit_selected(Unit)` signal as CalendarPanel,
so the rest of the app (timeline, edit form) works unchanged.

Toggle between calendar and list views from MainWindow using a
QStackedWidget — both panels live side-by-side and receive the
same refresh() calls.

Usage:
    panel = ListPanel(units)
    panel.unit_selected.connect(main_window.on_unit_selected)
    panel.set_units(all_units)          # initial load
    panel.refresh(all_units)            # after data reload
"""

from __future__ import annotations

from datetime import date, timedelta

from PyQt5.QtCore import QItemSelection, QItemSelectionModel, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QBrush, QColor, QFont
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QAction,
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from data.models import Unit
from data.tag_parser import UnitTagRepository, parse_description
from gui.checklist_filter import ChecklistFilterButton, FilterOption
from gui.inline_edit_bar import InlineEditBar
from services.assignment import UNASSIGNED, UNASSIGNED_LABELS, assign_detailer, mark_cancelled


def get_week_of_month(friday_date: date) -> int:
    """Compute the Sunday-to-Saturday calendar week index of the month containing the Friday date."""
    first_day = date(friday_date.year, friday_date.month, 1)
    # Sunday is 0, Monday is 1, ..., Saturday is 6
    first_day_dow = (first_day.weekday() + 1) % 7
    return (friday_date.day - 1 + first_day_dow) // 7 + 1


# ─── Column Definitions ─────────────────────────────────────────────
# (key, header, width, default_visible)

COLUMN_DEFS: list[tuple[str, str, int, bool]] = [
    ("com_number", "COM", 70, True),
    ("unit_state", "Mfg State", 85, True),
    ("detailing_due_date", "Due Date", 80, True),
    ("dept_due_date_previous", "Prev Due", 80, True),
    ("job_name", "Job Name", 180, True),
    ("detailer", "Detailer", 100, True),
    ("status_color", "Status", 50, True),
    ("percent_complete", "% Complete", 70, True),
    ("description_tags", "Tags", 140, True),
    ("department_hours", "Dept Hours", 70, False),
    ("actual_hours", "Actual Hours", 70, False),
    ("target_department_hours", "Target Hrs", 70, False),
    ("checking_status", "Checking", 80, False),
    ("checker", "Checker", 90, False),
    ("dr_checks", "DR Check", 80, False),
    ("dvl_checks", "DVL Check", 80, False),
    ("contract_number", "Contract #", 90, False),
    ("build_date", "Build Date", 80, False),
    ("unit_detailing_start_date", "Start Date", 80, False),
    ("working_days_in_checking", "Check WD", 60, False),
    ("notes", "Notes", 200, False),
    ("alert_level", "Alert", 80, False),
]


# ─── Status Color Map ───────────────────────────────────────────────

STATUS_COLORS_FALLBACK: dict[str, QColor] = {
    "unassigned": QColor(148, 163, 184),
    "gray": QColor(148, 163, 184),
    "yellow": QColor(234, 179, 8),
    "purple": QColor(168, 85, 247),
    "orange": QColor(249, 115, 22),
    "green": QColor(34, 197, 94),
    "red": QColor(239, 68, 68),
}

UNIT_STATE_COLORS: dict[str, QColor] = {
    "Done": QColor(5, 150, 105),       # Emerald
    "Fab-Eng": QColor(124, 58, 237),   # Violet
    "Fab-Load": QColor(79, 70, 229),   # Indigo
    "Fab-Lock": QColor(217, 119, 6),   # Amber
    "Pre-Eng": QColor(2, 132, 199),    # Soft Blue
    "Pre-Load": QColor(100, 116, 139), # Slate
}

SEVERITY_ORDER: dict[str, int] = {
    "red": 0,
    "orange": 1,
    "purple": 2,
    "yellow": 3,
    "unassigned": 4,
    "gray": 5,
    "green": 6,
}


# ─── Filter Keys ────────────────────────────────────────────────────
# The List view filters on Year (with months), Detailer and Job Name.
# An empty selection means "no filter". Each dropdown only offers values
# present in the units matching the *other* dropdowns; a checked value
# that is no longer offered is dropped.

FILTER_DIMENSIONS: tuple[str, ...] = ("years", "detailers", "jobs")
UNASSIGNED_KEY = "(Unassigned)"
CANCELLED_KEY = "Cancelled"
BLANK_JOB_KEY = "(Blank)"
NO_DATE_KEY = "(No date)"

MONTH_NAMES = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)


def year_key(unit: Unit) -> str:
    due = unit.detailing_due_date
    return str(due.year) if due else NO_DATE_KEY


def month_key(unit: Unit) -> str | None:
    due = unit.detailing_due_date
    return f"{due.year}-{due.month:02d}" if due else None


def detailer_key(unit: Unit) -> str:
    if unit.is_cancelled:
        return CANCELLED_KEY
    if not unit.is_assigned:
        return UNASSIGNED_KEY
    return unit.detailer.strip()


def job_key(unit: Unit) -> str:
    return (unit.job_name or "").strip() or BLANK_JOB_KEY


def _unit_keys(unit: Unit, dimension: str) -> tuple[str, ...]:
    """Every filter key under which *unit* is offered for *dimension*."""
    if dimension == "years":
        month = month_key(unit)
        return (year_key(unit), month) if month else (year_key(unit),)
    if dimension == "detailers":
        return (detailer_key(unit),)
    return (job_key(unit),)


def _matches(unit: Unit, dimension: str, selected: set[str]) -> bool:
    if not selected:
        return True
    return any(k in selected for k in _unit_keys(unit, dimension))


# ─── UnitListModel ──────────────────────────────────────────────────


class UnitListModel:
    """In-memory model: holds all units, applies filters + sort."""

    def __init__(self, units: list[Unit]):
        self._all_units: list[Unit] = list(units)
        self._filtered_units: list[Unit] = [u for u in units if not u.is_cancelled]
        self._column_order: list[str] = [key for key, _, _, _ in COLUMN_DEFS]
        self._visible_columns_set: set[str] = {key for key, _, _, visible in COLUMN_DEFS if visible}
        self._filters: dict[str, set[str]] = {dim: set() for dim in FILTER_DIMENSIONS}
        self._com_search: str = ""

    @property
    def all_units(self) -> list[Unit]:
        return self._all_units

    @property
    def filtered_units(self) -> list[Unit]:
        return self._filtered_units

    @property
    def filters(self) -> dict[str, set[str]]:
        """Current selection per dimension, after unavailable values were dropped."""
        return {dim: set(keys) for dim, keys in self._filters.items()}

    @property
    def column_order(self) -> list[str]:
        return list(self._column_order)

    def set_column_order(self, order: list[str]) -> None:
        if not order:
            return
        all_keys = [key for key, _, _, _ in COLUMN_DEFS]
        clean = [k for k in order if k in all_keys]
        missing = [k for k in all_keys if k not in clean]
        self._column_order = clean + missing

    @property
    def visible_columns(self) -> list[str]:
        return [key for key in self._column_order if key in self._visible_columns_set]

    def set_visible_columns(self, keys: list[str]) -> None:
        if keys:
            all_keys = {key for key, _, _, _ in COLUMN_DEFS}
            self._visible_columns_set = {k for k in keys if k in all_keys}

    # ── Filtering ───────────────────────────────────────────────────

    def apply_filters(
        self,
        years=None,
        detailers=None,
        jobs=None,
        com_search: str = "",
    ) -> None:
        """Apply Year, Detailer, Job Name and search with AND logic.

        Cancelled units are left out unless "Cancelled" is checked under Detailer.
        """
        self._filters = {
            "years": set(years or ()),
            "detailers": set(detailers or ()),
            "jobs": set(jobs or ()),
        }
        self._com_search = com_search
        self._drop_unavailable()

        result = self._matching()
        if com_search:
            query = com_search.lower().strip()
            result = [
                u
                for u in result
                if query in u.com_number.lower()
                or query in u.job_name.lower()
                or query in u.contract_number.lower()
                or query in u.description.lower()
                or query in u.notes.lower()
            ]
        self._filtered_units = result

    def _matching(self, skip: str | None = None) -> list[Unit]:
        """Units passing every dropdown except *skip* (search is not applied)."""
        show_cancelled = skip == "detailers" or CANCELLED_KEY in self._filters["detailers"]
        result = []
        for u in self._all_units:
            if u.is_cancelled and not show_cancelled:
                continue
            if all(
                _matches(u, dim, self._filters[dim])
                for dim in FILTER_DIMENSIONS
                if dim != skip
            ):
                result.append(u)
        return result

    def _available_keys(self, dimension: str) -> set[str]:
        keys: set[str] = set()
        for u in self._matching(skip=dimension):
            keys.update(_unit_keys(u, dimension))
        return keys

    def _drop_unavailable(self) -> None:
        """Uncheck values the other dropdowns no longer offer (until stable)."""
        if not self._all_units:
            return
        for _ in range(len(FILTER_DIMENSIONS) + 1):
            changed = False
            for dim in FILTER_DIMENSIONS:
                if not self._filters[dim]:
                    continue
                kept = self._filters[dim] & self._available_keys(dim)
                if kept != self._filters[dim]:
                    self._filters[dim] = kept
                    changed = True
            if not changed:
                return

    def filter_options(self, dimension: str) -> list[tuple[str, str, list[tuple[str, str]]]]:
        """Values *dimension*'s dropdown offers: (key, label, [(child_key, child_label)])."""
        units = self._matching(skip=dimension)
        if dimension == "years":
            months: dict[str, set[int]] = {}
            for u in units:
                months.setdefault(year_key(u), set())
                if u.detailing_due_date:
                    months[year_key(u)].add(u.detailing_due_date.month)
            ordered = sorted(k for k in months if k != NO_DATE_KEY)
            if NO_DATE_KEY in months:
                ordered.append(NO_DATE_KEY)
            return [
                (y, y, [(f"{y}-{m:02d}", MONTH_NAMES[m - 1]) for m in sorted(months[y])])
                for y in ordered
            ]
        if dimension == "detailers":
            values = {detailer_key(u) for u in units}
            first, last = [UNASSIGNED_KEY], [CANCELLED_KEY]
        else:
            values = {job_key(u) for u in units}
            first, last = [BLANK_JOB_KEY], []
        ordered = [v for v in first if v in values]
        ordered += sorted((v for v in values if v not in first + last), key=str.lower)
        ordered += [v for v in last if v in values]
        return [(v, v, []) for v in ordered]

    # ── Sorting ─────────────────────────────────────────────────────

    def sort_by(self, column_key: str, ascending: bool = True) -> None:
        """Sort filtered units in-place by the given column key."""
        if column_key == "status_color":

            def key_func(unit: Unit) -> int:
                return SEVERITY_ORDER.get(unit.status_color_name, 99)
        elif column_key == "detailing_due_date":

            def key_func(unit: Unit):
                d = unit.detailing_due_date
                return (0, d) if d is not None else (1, date.max)
        elif column_key == "percent_complete":

            def key_func(unit: Unit) -> float:
                return unit.percent_complete
        elif column_key in (
            "department_hours",
            "actual_hours",
            "target_department_hours",
            "working_days_in_checking",
        ):

            def key_func(unit: Unit) -> float:
                return getattr(unit, column_key, 0.0)
        else:
            # String sort for text columns
            def key_func(unit: Unit):
                val = getattr(unit, column_key, None)
                return str(val).lower() if val is not None else ""

        self._filtered_units.sort(key=key_func, reverse=not ascending)

    # ── Metadata ─────────────────────────────────────────────────────

    def get_unique_detailers(self) -> list[str]:
        """Sorted unique detailer strings from all units."""
        detailers = set()
        for u in self._all_units:
            if u.detailer:
                detailers.add(u.detailer)
        return sorted(detailers)


class HighlightDelegate(QStyledItemDelegate):
    """Custom item delegate that renders custom item background colors even when a QTableWidget stylesheet is active, while preserving standard selection rendering."""

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        # If the item is selected, let the default style paint the selection background.
        # Otherwise, paint custom background manually and prevent the stylesheet from overriding it.
        if not (opt.state & QStyle.State_Selected):
            bg_brush = index.data(Qt.BackgroundRole)
            if bg_brush and bg_brush.style() != Qt.NoBrush:
                painter.save()
                painter.fillRect(opt.rect, bg_brush)
                painter.restore()
                # Set backgroundBrush to transparent so super().paint doesn't overwrite it
                opt.backgroundBrush = QBrush(Qt.transparent)

        super().paint(painter, opt, index)


# ─── Column Chooser Dialog ──────────────────────────────────────────


class ColumnChooserDialog(QDialog):
    """Dialog to toggle visible columns and reorder them with drag-and-drop or Move Up/Down buttons."""

    def __init__(self, column_order: list[str], visible_columns: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Choose & Reorder Columns")
        self.resize(380, 480)

        self._reset_requested: bool = False
        self._column_defs_map = {key: header for key, header, _, _ in COLUMN_DEFS}

        layout = QVBoxLayout(self)

        hint_label = QLabel("Drag items or use buttons to reorder columns.\nCheck boxes to show/hide columns.")
        hint_label.setWordWrap(True)
        hint_label.setStyleSheet("color: palette(placeholder-text); font-size: 11px;")
        layout.addWidget(hint_label)

        content_layout = QHBoxLayout()

        self.list_widget = QListWidget()
        self.list_widget.setDragDropMode(QAbstractItemView.InternalMove)
        self.list_widget.setSelectionMode(QAbstractItemView.SingleSelection)

        visible_set = set(visible_columns)
        for key in column_order:
            header = self._column_defs_map.get(key, key)
            item = QListWidgetItem(header)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsDragEnabled | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            item.setCheckState(Qt.Checked if key in visible_set else Qt.Unchecked)
            item.setData(Qt.UserRole, key)
            self.list_widget.addItem(item)

        content_layout.addWidget(self.list_widget, 1)

        btn_layout = QVBoxLayout()
        self.btn_up = QPushButton("Move Up")
        self.btn_up.clicked.connect(self._move_up)
        self.btn_down = QPushButton("Move Down")
        self.btn_down.clicked.connect(self._move_down)
        self.btn_reset = QPushButton("Reset Defaults")
        self.btn_reset.clicked.connect(self._reset_defaults)

        btn_layout.addWidget(self.btn_up)
        btn_layout.addWidget(self.btn_down)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_reset)

        content_layout.addLayout(btn_layout)
        layout.addLayout(content_layout)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _move_up(self) -> None:
        row = self.list_widget.currentRow()
        if row > 0:
            item = self.list_widget.takeItem(row)
            self.list_widget.insertItem(row - 1, item)
            self.list_widget.setCurrentRow(row - 1)

    def _move_down(self) -> None:
        row = self.list_widget.currentRow()
        if row >= 0 and row < self.list_widget.count() - 1:
            item = self.list_widget.takeItem(row)
            self.list_widget.insertItem(row + 1, item)
            self.list_widget.setCurrentRow(row + 1)

    def _reset_defaults(self) -> None:
        self._reset_requested = True
        self.list_widget.clear()
        for key, header, _, default_visible in COLUMN_DEFS:
            item = QListWidgetItem(header)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsDragEnabled | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            item.setCheckState(Qt.Checked if default_visible else Qt.Unchecked)
            item.setData(Qt.UserRole, key)
            self.list_widget.addItem(item)

    @property
    def is_reset_requested(self) -> bool:
        return self._reset_requested

    def get_result(self) -> tuple[list[str], list[str]]:
        """Return (column_order, visible_columns) from dialog list widget."""
        ordered_keys: list[str] = []
        visible_keys: list[str] = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            key = item.data(Qt.UserRole)
            ordered_keys.append(key)
            if item.checkState() == Qt.Checked:
                visible_keys.append(key)
        return ordered_keys, visible_keys


# ─── ListPanel Widget ───────────────────────────────────────────────


class ListPanel(QWidget):
    """Left-panel widget: sortable, filterable QTableWidget of units.

    Emits `unit_selected(Unit)` — same signal as CalendarPanel.
    """

    unit_selected = pyqtSignal(object)  # Unit
    unit_saved = pyqtSignal(object)  # Unit (from inline edit bar)
    units_saved = pyqtSignal(list)  # list[Unit] (right-click actions; saved as one batch)
    inline_dirty_changed = pyqtSignal(bool)
    filters_changed = pyqtSignal(dict)  # filter_state()
    column_order_changed = pyqtSignal(list)  # list of column keys in full order
    column_widths_changed = pyqtSignal(dict)  # {key: width}
    column_visibility_changed = pyqtSignal(list)  # list of visible column keys
    batch_mode_changed = pyqtSignal(int)  # count of selected units (0 = no batch)
    show_inline_edit_changed = pyqtSignal(bool)

    def __init__(
        self,
        units: list[Unit] | None = None,
        default_detailers: list[str] | None = None,
        db_path: str = "",
        show_inline_edit: bool = True,
        parent=None,
        checking_statuses: list[str] | None = None,
    ):
        super().__init__(parent)
        self._model: UnitListModel | None = None
        self._sort_column: str = "detailing_due_date"
        self._sort_ascending: bool = True
        self._search_debounce: QTimer | None = None
        self._theme_name: str = "light"
        self._cvd_mode: str = "none"
        self._tag_repo: UnitTagRepository | None = None
        self._saved_widths: dict[str, int] = {}
        self._saved_visible_columns: list[str] = []
        self._saved_column_order: list[str] = []
        self._emitting_widths: bool = False
        self._emitting_order: bool = False
        self._default_detailers: list[str] = default_detailers or []
        self._checking_statuses: list[str] | None = checking_statuses
        self._db_path: str = db_path
        self._show_inline_edit: bool = show_inline_edit
        self._last_filter_state: dict = {}
        # (com_number, due date) of the unit kept at the top of the table
        self._scroll_anchor: tuple[str, date | None] | None = None
        self._anchor_pending: bool = False
        self._restoring_scroll: bool = False
        self._last_emitted_com: str | None = None
        # Cache of pre-computed tag display strings, keyed by com_number.
        # Invalidated when the model (unit set) changes, preserved across
        # sort-only refreshes so we don't re-parse on every column click.
        self._tag_strings_cache: dict[str, str] = {}

        self._build_ui()

        if units:
            self.set_units(units)

    def set_tag_repo(self, repo: UnitTagRepository | None) -> None:
        """Set the tag repository for novelty detection."""
        self._tag_repo = repo
        self._tag_strings_cache.clear()
        if self._model is not None:
            self._refresh_table_full()

    def _compute_tags_display(self, unit: Unit) -> str:
        """Compute the tags display string for a unit.

        Shows unit type + key features, with novelty indicator.
        """
        if not unit.description:
            return ""

        if self._tag_repo is not None:
            tags = self._tag_repo.get_tags(unit.com_number)
            is_novel, _reasons = self._tag_repo.is_novel_for_detailer(unit)
        else:
            tags = parse_description(unit.description)
            is_novel = False

        parts = []
        if tags.unit_type:
            parts.append(tags.unit_type)
        # Show top 3 features
        key_features = tags.features[:3]
        parts.extend(key_features)

        result = " ".join(parts) if parts else ""

        # Add novelty indicator
        if is_novel:
            result = f"✦ {result}" if result else "✦"

        return result

    def set_theme(self, theme_name: str, cvd_mode: str = "none") -> None:
        self._theme_name = theme_name
        self._cvd_mode = cvd_mode
        if hasattr(self, "_inline_edit_bar") and self._inline_edit_bar is not None:
            self._inline_edit_bar.set_theme(theme_name, cvd_mode)
        self._refresh_table_full()

    # ── UI Construction ──────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # ── Filter bar (Excel-style checklists; empty selection = no filter) ──
        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)
        self.year_filter = ChecklistFilterButton("Year")
        self.detailer_filter = ChecklistFilterButton("Detailer")
        self.job_filter = ChecklistFilterButton("Job Name")
        self.job_filter.setMinimumWidth(170)
        for button in (self.year_filter, self.detailer_filter, self.job_filter):
            button.selection_changed.connect(self._on_filter_changed)
            filter_row.addWidget(button)

        filter_row.addWidget(QLabel("Search:"))
        self.com_search = QLineEdit()
        self.com_search.setPlaceholderText("COM #, job, contract #, description, notes...")
        self.com_search.setClearButtonEnabled(True)
        self._search_debounce = QTimer(self)
        self._search_debounce.setSingleShot(True)
        self._search_debounce.setInterval(200)
        self._search_debounce.timeout.connect(self._on_filter_changed)
        self.com_search.textChanged.connect(self._on_search_text_changed)
        self.com_search.returnPressed.connect(self._on_search_return_pressed)
        filter_row.addWidget(self.com_search, 1)

        self.clear_btn = QPushButton("Clear Filters")
        self.clear_btn.clicked.connect(self._clear_filters)
        filter_row.addWidget(self.clear_btn)
        layout.addLayout(filter_row)

        # ── Table ──
        self.table = QTableWidget()
        self.table.setColumnCount(0)
        self.table.setRowCount(0)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        # Narrow columns show "STAT…" rather than clipping the header mid-letter
        self.table.horizontalHeader().setTextElideMode(Qt.ElideRight)
        self.table.horizontalHeader().setSectionsClickable(True)
        self.table.horizontalHeader().setSectionsMovable(True)
        self.table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
        self.table.horizontalHeader().sectionResized.connect(self._on_section_resized)
        self.table.horizontalHeader().sectionMoved.connect(self._on_section_moved)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.cellClicked.connect(self._on_cell_clicked)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.doubleClicked.connect(self._on_double_clicked)
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.table.setItemDelegate(HighlightDelegate(self.table))
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_table_context_menu)
        self.table.verticalScrollBar().valueChanged.connect(self._on_table_scrolled)

        # ── Ctrl+A Select All ──
        select_all_action = QAction("Select All", self.table)
        select_all_action.setShortcut("Ctrl+A")
        select_all_action.triggered.connect(self.table.selectAll)
        self.table.addAction(select_all_action)

        layout.addWidget(self.table, stretch=1)

        # ── Inline Edit Bar ──
        self._inline_edit_bar = InlineEditBar(
            self._default_detailers, checking_statuses=self._checking_statuses
        )
        self._inline_edit_bar.unit_saved.connect(self._on_inline_save)
        self._inline_edit_bar.dirty_changed.connect(self.inline_dirty_changed)
        if not self._show_inline_edit:
            self._inline_edit_bar.setVisible(False)
        layout.addWidget(self._inline_edit_bar)

        # ── Multi-selection hint (themed; actions live in the right-click menu) ──
        self._selection_label = QLabel("")
        self._selection_label.setObjectName("list_selection_label")
        self._selection_label.setStyleSheet("font-weight: bold; padding-left: 4px;")
        self._selection_label.setVisible(False)
        layout.addWidget(self._selection_label)

        # ── Status row: unit count + view options ──
        status_row = QHBoxLayout()
        self.status_label = QLabel("No units loaded")
        self.status_label.setObjectName("list_status_label")
        status_row.addWidget(self.status_label, 1)

        self.columns_btn = QPushButton("Columns...")
        self.columns_btn.clicked.connect(self._show_column_chooser)
        status_row.addWidget(self.columns_btn)

        self.inline_edit_toggle = QCheckBox("Inline Edit Bar")
        self.inline_edit_toggle.setToolTip("Show/hide the inline editing bar at the bottom of the table")
        self.inline_edit_toggle.setChecked(self._show_inline_edit)
        self.inline_edit_toggle.toggled.connect(self._on_inline_toggle_clicked)
        status_row.addWidget(self.inline_edit_toggle)
        layout.addLayout(status_row)

        # ── Blame label ──
        self.blame_label = QLabel("")
        self.blame_label.setObjectName("blame_label")
        self.blame_label.setStyleSheet("font-size: 11px; padding-left: 4px;")
        layout.addWidget(self.blame_label)

    # ── Public API ───────────────────────────────────────────────────

    def load_column_widths(self, widths: dict[str, int]) -> None:
        """Load saved column widths from config (key → pixel width)."""
        self._saved_widths = dict(widths)

    def load_sort_config(self, column: str, ascending: bool) -> None:
        """Load saved sort column and direction from config."""
        self._sort_column = column
        self._sort_ascending = ascending

    def load_visible_columns(self, keys: list[str]) -> None:
        """Load saved visible columns from config (list of column keys).

        Stores the keys and applies them if the model already exists.
        """
        if not keys:
            return
        self._saved_visible_columns = list(keys)
        if self._model is not None:
            self._model.set_visible_columns(keys)

    def load_column_order(self, order: list[str]) -> None:
        """Load saved column order from config (list of column keys)."""
        if not order:
            return
        self._saved_column_order = list(order)
        if self._model is not None:
            self._model.set_column_order(order)

    def set_units(self, units: list[Unit]) -> None:
        """Load units into the model (initial load)."""
        old_visible = self._model.visible_columns if self._model else None
        old_order = self._model.column_order if self._model else None
        self._model = UnitListModel(units)
        if old_order:
            self._model.set_column_order(old_order)
        elif self._saved_column_order:
            self._model.set_column_order(self._saved_column_order)

        if old_visible:
            self._model.set_visible_columns(old_visible)
        elif self._saved_visible_columns:
            self._model.set_visible_columns(self._saved_visible_columns)
        self._tag_strings_cache.clear()
        self._apply_filters_and_refresh()

    def refresh(self, units: list[Unit]) -> None:
        """Reload data (called after save/external change).

        Preserves filters, sort, the top visible unit, and visible columns.
        """
        if self._model is None:
            self.set_units(units)
            return

        # The table rebuild preserves the selection and scroll anchor itself
        old_visible = self._model.visible_columns
        old_order = self._model.column_order

        self._model = UnitListModel(units)
        self._model.set_column_order(old_order)
        self._model.set_visible_columns(old_visible)
        self._tag_strings_cache.clear()

        # Always do a full refresh after save to ensure changes are visible.
        # The incremental diff path had edge cases where changed rows were
        # not re-rendered (fingerprint cache, sort order changes, etc.).
        self._apply_filters_and_refresh()

        # Update inline edit bar's unit reference after save
        # (prevents stale updated_at causing false conflict on next save).
        # A dirty bar keeps its original unit so unsaved edits survive and the
        # save still goes through the optimistic-lock check.
        if (
            self._inline_edit_bar.isVisible()
            and self._inline_edit_bar._unit is not None
            and not self._inline_edit_bar.is_dirty
        ):
            com = self._inline_edit_bar._unit.com_number
            for u in units:
                if u.com_number == com:
                    self._inline_edit_bar._unit = u
                    self._inline_edit_bar.set_unit(u)
                    break

    def _format_cell(self, key: str, value) -> str:
        """Format a Unit attribute for display."""
        if value is None:
            return ""

        if key in (
            "detailing_due_date",
            "build_date",
            "unit_detailing_start_date",
            "unit_moved_to_checking_date",
            "unit_detailing_completion_date",
            "dept_due_date_previous",
        ):
            if hasattr(value, "strftime"):
                date_str = value.strftime("%m/%d/%Y")
                if key == "detailing_due_date" and isinstance(value, date):
                    friday = value + timedelta(days=(4 - value.weekday()) % 7)
                    week_idx = get_week_of_month(friday)
                    return f"{date_str} (W{week_idx})"
                return date_str
            return str(value)

        if key == "percent_complete":
            pct = value * 100.0 if isinstance(value, float) and value <= 1.0 else float(value)
            return f"{pct:.0f}%"

        if key in ("department_hours", "actual_hours", "target_department_hours"):
            return f"{value:.2f}"

        if key == "detailer":
            if not value or value in ("— Unassigned —", "Unassigned"):
                return "⚠ — Unassigned —"
            return str(value)

        if key == "status_color":
            return ""  # Color block — no text

        if key == "description_tags":
            if not value:
                return ""
            if isinstance(value, str):
                return value
            return str(value)

        return str(value)

    # ── Filtering ───────────────────────────────────────────────────

    def _on_search_text_changed(self, text: str) -> None:
        """Debounce the search — don't re-filter on every keystroke."""
        self._search_debounce.start()

    def _on_search_return_pressed(self) -> None:
        """Handle Enter key in the search box: apply filter immediately and select first match."""
        if self._search_debounce and self._search_debounce.isActive():
            self._search_debounce.stop()
            self._on_filter_changed()

        if self._model and self._model.filtered_units:
            first_unit = self._model.filtered_units[0]
            self._select_com(first_unit.com_number)
            self.table.setFocus()

    def _on_filter_changed(self) -> None:
        """Called when any filter widget changes (or debounce fires)."""
        if self._model is None:
            self._emit_filters_if_changed()
            return
        self._apply_filters_and_refresh()

    def _filter_buttons(self) -> dict[str, ChecklistFilterButton]:
        return {
            "years": self.year_filter,
            "detailers": self.detailer_filter,
            "jobs": self.job_filter,
        }

    def _apply_filters_and_refresh(self) -> None:
        """Read filter widget state → apply to model → refresh table."""
        if self._model is None:
            return

        buttons = self._filter_buttons()
        self._model.apply_filters(
            years=buttons["years"].selected(),
            detailers=buttons["detailers"].selected(),
            jobs=buttons["jobs"].selected(),
            com_search=self.com_search.text(),
        )
        # Show what is actually applied: values no longer offered were dropped
        applied = self._model.filters
        for dim, button in buttons.items():
            button.set_options(
                [
                    FilterOption(key, label, [FilterOption(ck, cl) for ck, cl in children])
                    for key, label, children in self._model.filter_options(dim)
                ]
            )
            button.set_selected(applied[dim])
        self._emit_filters_if_changed()
        self._model.sort_by(self._sort_column, self._sort_ascending)
        self._refresh_table_full()

    def filter_state(self) -> dict:
        """Current filters as plain lists, for saving to config."""
        state: dict = {dim: sorted(b.selected()) for dim, b in self._filter_buttons().items()}
        state["search"] = self.com_search.text()
        return state

    def load_filter_state(self, state: dict | None) -> None:
        """Restore saved filters (dimension → list of keys, plus "search")."""
        state = state or {}
        for dim, button in self._filter_buttons().items():
            button.set_selected(state.get(dim) or [])
        self.com_search.blockSignals(True)
        self.com_search.setText(state.get("search") or "")
        self.com_search.blockSignals(False)
        self._last_filter_state = self.filter_state()
        self._apply_filters_and_refresh()

    def _emit_filters_if_changed(self) -> None:
        state = self.filter_state()
        if state != self._last_filter_state:
            self._last_filter_state = state
            self.filters_changed.emit(state)

    # ── Scroll anchor: keep the same unit at the top across rebuilds ──

    def top_visible_com(self) -> str | None:
        """COM of the unit at the top of the table (or the one waiting to be restored)."""
        return self._scroll_anchor[0] if self._scroll_anchor else None

    def load_scroll_anchor(self, com_number: str | None) -> None:
        """Scroll to *com_number* once the table is shown (saved from the last session)."""
        if not com_number:
            return
        self._scroll_anchor = (com_number, None)
        self._anchor_pending = True
        self._restore_scroll_anchor()

    def _on_table_scrolled(self, _value: int) -> None:
        if self._restoring_scroll or not self.table.isVisible() or self._model is None:
            return
        row = self.table.rowAt(0)
        units = self._model.filtered_units
        if 0 <= row < len(units):
            unit = units[row]
            self._scroll_anchor = (unit.com_number, unit.detailing_due_date)
            self._anchor_pending = False

    def _restore_scroll_anchor(self) -> None:
        """Put the anchor unit at the top; fall back to the nearest due date."""
        if self._scroll_anchor is None or self._model is None:
            return
        if not self.table.isVisible():
            # Hidden tables have no usable scroll range; retry in showEvent
            self._anchor_pending = True
            return
        com, due = self._scroll_anchor
        units = self._model.filtered_units
        if due is None:
            due = next(
                (u.detailing_due_date for u in self._model.all_units if u.com_number == com),
                None,
            )
            if due is not None:
                self._scroll_anchor = (com, due)
        row = next((i for i, u in enumerate(units) if u.com_number == com), -1)
        if row < 0 and due is not None:
            dated = [(abs((u.detailing_due_date - due).days), i)
                     for i, u in enumerate(units) if u.detailing_due_date]
            row = min(dated)[1] if dated else -1
        self._anchor_pending = False
        if row < 0:
            return
        self._restoring_scroll = True
        try:
            item = self.table.item(row, 0)
            if item is not None:
                self.table.scrollToItem(item, QAbstractItemView.PositionAtTop)
        finally:
            self._restoring_scroll = False

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._anchor_pending:
            # Wait for the layout to give the table its real height
            QTimer.singleShot(0, self._restore_scroll_anchor)

    def _refresh_table_full(self) -> None:
        """Rebuild the entire table from scratch (fallback for small tables or large diffs)."""
        if self._model is None:
            return

        self._emitting_order = True
        # Row changes during the rebuild move the scrollbar; keep the anchor
        self._restoring_scroll = True
        try:
            # Capture the selection before rebuilding: every selected COM (so a
            # multi-selection survives sorting/reloads) and the current one
            selected_com = self._get_selected_com()
            selected_coms = {u.com_number for u in self._get_selected_units()}

            # Rebuild silently: a live itemSelectionChanged here would clear the
            # inline edit bar (losing unsaved edits) and re-emit unit_selected.
            self.table.blockSignals(True)

            # Clear selection and current item before changing row count so Qt does not
            # retain stale row indices onto different units
            self.table.clearSelection()
            self.table.setCurrentItem(None)

            units = self._model.filtered_units
            visible = self._model.visible_columns

            # Pre-compute min/max department hours for visible units to use in conditional formatting.
            # Only consider units with department_hours > 0.0.
            visible_dept_hours = [
                u.department_hours
                for u in units
                if u.department_hours is not None and u.department_hours > 0.0
            ]
            min_dept_hours = min(visible_dept_hours) if visible_dept_hours else 0.0
            max_dept_hours = max(visible_dept_hours) if visible_dept_hours else 0.0

            # Pre-compute description_tags for all visible units.
            # Uses a persistent cache keyed by com_number — only re-parses
            # when the unit tag repo changes or a new com_number appears.
            show_tags = "description_tags" in visible
            tag_cache: list[str] = []
            if show_tags:
                cache = self._tag_strings_cache
                for _unit in units:
                    com = _unit.com_number
                    if com in cache:
                        tag_cache.append(cache[com])
                    else:
                        tag_str = self._compute_tags_display(_unit)
                        cache[com] = tag_str
                        tag_cache.append(tag_str)

            header_map = {d[0]: d[1] for d in COLUMN_DEFS}
            col_headers: list[str] = []
            col_keys: list[str] = []
            for key in visible:
                header = header_map.get(key, key)
                if key == self._sort_column:
                    arrow = " \u25b2" if self._sort_ascending else " \u25bc"
                    col_headers.append(header + arrow)
                else:
                    col_headers.append(header)
                col_keys.append(key)

            self.table.setColumnCount(len(col_headers))
            self.table.setHorizontalHeaderLabels(col_headers)
            self.table.setRowCount(len(units))

            # Reset QHeaderView visual-to-logical section mapping so
            # logical index == visual index after every rebuild.
            header = self.table.horizontalHeader()
            for i in range(len(col_headers)):
                vi = header.visualIndex(i)
                if vi != i:
                    header.moveSection(vi, i)

            width_map = {d[0]: d[2] for d in COLUMN_DEFS}
            self._emitting_widths = True
            for col_idx, key in enumerate(col_keys):
                w = self._saved_widths.get(key, width_map.get(key, 80))
                self.table.setColumnWidth(col_idx, w)
            self._emitting_widths = False

            # Pre-compute value-based group highlight colors for due date and contract number.
            main_win = self.window()
            high_contrast = getattr(main_win, "_current_hc", False) or getattr(self, "_current_hc", False)

            def _compute_value_colors(key_fn) -> list[QColor | None]:
                keys = [key_fn(u) for u in units]
                freq: dict = {}
                for k in keys:
                    freq[k] = freq.get(k, 0) + 1
                result: list = []
                for k in keys:
                    if k is None or k == "" or freq[k] < 2:
                        result.append(None)
                    else:
                        from gui.theme import get_week_highlight_color
                        week_idx = (hash(str(k)) % 5) + 1
                        color = get_week_highlight_color(
                            self._theme_name, week_idx, self._cvd_mode, high_contrast
                        )
                        result.append(color)
                return result

            com_colors = _compute_value_colors(
                lambda u: u.contract_number or None
            )

            bold_font = QFont()
            bold_font.setBold(True)

            for row_idx, unit in enumerate(units):
                for col_idx, key in enumerate(col_keys):
                    if key == "description_tags" and show_tags:
                        value = tag_cache[row_idx]
                    else:
                        value = getattr(unit, key, None)
                    display = self._format_cell(key, value)
                    item = QTableWidgetItem(display)

                    if key == "detailing_due_date" and value and isinstance(value, date):
                        friday = value + timedelta(days=(4 - value.weekday()) % 7)
                        week_idx = get_week_of_month(friday)

                        from gui.theme import get_week_highlight_color
                        color = get_week_highlight_color(
                            self._theme_name, week_idx, self._cvd_mode, high_contrast
                        )
                        item.setBackground(QBrush(color))

                        from gui.theme import THEMES, boost_contrast
                        tokens = THEMES[self._theme_name]
                        if high_contrast:
                            tokens = boost_contrast(self._theme_name)
                        item.setForeground(QBrush(QColor(tokens["text_primary"])))
                        item.setToolTip(f"Due in Week {week_idx} of the month")

                    if key == "com_number":
                        color = com_colors[row_idx]
                        if color is not None:
                            item.setBackground(QBrush(color))
                            from gui.theme import THEMES, boost_contrast
                            tokens = THEMES[self._theme_name]
                            if high_contrast:
                                tokens = boost_contrast(self._theme_name)
                            item.setForeground(QBrush(QColor(tokens["text_primary"])))
                            item.setToolTip(f"Shared top level number: {unit.contract_number}")

                    if key == "department_hours" and value is not None and value > 0 and max_dept_hours > min_dept_hours:
                        from gui.theme import get_dept_hours_color
                        bg_color, fg_color = get_dept_hours_color(
                            self._theme_name,
                            value,
                            min_dept_hours,
                            max_dept_hours,
                            self._cvd_mode,
                            high_contrast,
                        )
                        item.setBackground(QBrush(bg_color))
                        item.setForeground(QBrush(fg_color))

                    if key in (
                        "percent_complete",
                        "department_hours",
                        "actual_hours",
                        "target_department_hours",
                        "working_days_in_checking",
                    ):
                        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    elif key == "status_color":
                        item.setTextAlignment(Qt.AlignCenter)
                    else:
                        item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)

                    if key == "detailer" and not unit.is_assigned:
                        item.setFont(bold_font)
                        item.setForeground(QBrush(QColor("#dc2626")))

                    if key == "status_color":
                        from gui.theme import status_style as _theme_status_style

                        computed_status = unit.status_color_name
                        hex_color, icon, label = _theme_status_style(
                            self._theme_name, computed_status, self._cvd_mode
                        )
                        color = QColor(hex_color)
                        item.setBackground(QBrush(color))
                        brightness = (
                            color.red() * 299 + color.green() * 587 + color.blue() * 114
                        ) / 1000
                        text_color = QColor("white") if brightness < 160 else QColor("#1e293b")
                        item.setForeground(QBrush(text_color))
                        item.setFont(bold_font)
                        item.setText(icon)
                        item.setToolTip(f"{icon} {label}")

                    if key == "unit_state" and value:
                        state_str = str(value).strip()
                        color = UNIT_STATE_COLORS.get(state_str, QColor(100, 116, 139))
                        item.setBackground(QBrush(color))
                        item.setForeground(QBrush(QColor("white")))
                        item.setFont(bold_font)
                        item.setTextAlignment(Qt.AlignCenter)
                        item.setToolTip(f"Manufacturing Order State: {state_str}")

                    if (
                        key == "detailing_due_date"
                        and value
                        and isinstance(value, date)
                        and value < date.today()
                        and unit.percent_complete < 100.0
                        and not unit.is_cancelled
                    ):
                        # Red on the week colour is unreadable; overdue drops the week fill
                        item.setBackground(QBrush())
                        item.setForeground(QBrush(QColor("#dc2626")))
                        item.setFont(bold_font)

                    # Due date changed indicator
                    if key == "detailing_due_date" and unit.due_date_changed:
                        item.setText("⚠ " + item.text())
                        item.setBackground(QBrush(QColor(255, 200, 50, 80)))
                        prev = unit.previous_detailing_due_date
                        prev_str = prev.strftime("%m/%d/%Y") if prev else "—"
                        item.setToolTip(f"Due date changed from {prev_str}")

                    if key == "dept_due_date_previous" and value:
                        item.setFont(bold_font)

                    if unit.is_cancelled:
                        if key == "detailer":
                            item.setText("🚫 Cancelled")
                            item.setFont(bold_font)
                            item.setForeground(QBrush(QColor("#64748b")))
                        elif key != "status_color":
                            item.setForeground(QBrush(QColor("#64748b")))

                    item.setData(Qt.UserRole, unit)
                    self.table.setItem(row_idx, col_idx, item)

            total = len(self._model.all_units)
            showing = len(units)
            self.status_label.setText(
                f"Showing {showing} of {total} units"
                f" | sorted by {self._sort_column}"
                f" {'asc' if self._sort_ascending else 'desc'}"
            )

            # Restore the selection for the COMs still present in the filtered view
            row = self._restore_selection(selected_coms, selected_com)
            self.table.blockSignals(False)

            if row >= 0 and self._last_emitted_com == selected_com:
                self._refresh_inline_bar_unit()
            elif row < 0 and self._inline_edit_bar.is_dirty:
                # The unit being edited was filtered out; keep its unsaved edits.
                self._last_emitted_com = None
                self.blame_label.setText("")
                self._update_batch_bar()
            else:
                self._on_selection_changed()

            # Selection restore can auto-scroll; the anchor decides what is on top
            self._restore_scroll_anchor()
        finally:
            self.table.blockSignals(False)
            self._emitting_order = False
            self._restoring_scroll = False

    def _refresh_inline_bar_unit(self) -> None:
        """Point the inline bar at the reloaded copy of the selected unit.

        A dirty bar keeps the unit it started from, so its save still carries
        the original updated_at and hits the optimistic-lock check.
        """
        bar = self._inline_edit_bar
        unit = self._get_selected_unit()
        if (
            unit is None
            or not self._show_inline_edit
            or len(self._get_selected_units()) >= 2
            or bar.is_dirty
        ):
            return
        if bar._unit is None or bar._unit is not unit:
            bar.set_unit(unit)

    def _select_only_row(self, row: int) -> None:
        """Select exactly *row* and make it current.

        Unlike QTableWidget.selectRow(), this ignores held Ctrl/Shift keys, which
        would otherwise toggle the row or extend the selection.
        """
        index = self.table.model().index(row, 0)
        self.table.selectionModel().setCurrentIndex(
            index, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows
        )

    def _restore_selection(self, coms: set[str], current_com: str) -> int:
        """Select every row whose COM is in *coms* and make *current_com* current.

        Returns the row of *current_com*, or -1 if it is no longer shown.
        """
        if not coms:
            return -1
        model = self.table.model()
        selection = QItemSelection()
        current_row = -1
        for r in range(self.table.rowCount()):
            unit = self._get_unit_at_row(r)
            if unit is not None and unit.com_number in coms:
                index = model.index(r, 0)
                selection.select(index, index)
                if unit.com_number == current_com:
                    current_row = r
        sel_model = self.table.selectionModel()
        sel_model.select(selection, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)
        if current_row >= 0:
            sel_model.setCurrentIndex(model.index(current_row, 0), QItemSelectionModel.NoUpdate)
        return current_row

    def _row_for_com(self, com_number: str) -> int:
        """Return the table row showing *com_number*, or -1."""
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is None:
                continue
            unit = item.data(Qt.UserRole)
            if (unit and unit.com_number == com_number) or (not unit and item.text() == com_number):
                return row
        return -1

    def _clear_filters(self) -> None:
        """Reset every dropdown and the search box, then refilter once."""
        for button in self._filter_buttons().values():
            button.set_selected(set())
        self._search_debounce.stop()
        self.com_search.blockSignals(True)
        self.com_search.clear()
        self.com_search.blockSignals(False)
        self._on_filter_changed()

    # ── Column Width Persistence ──────────────────────────────────────

    def _on_section_resized(self, column_index: int, old_width: int, new_width: int) -> None:
        """Capture user-driven column resizes and emit for config save."""
        if self._emitting_widths or self._model is None:
            return
        visible = self._model.visible_columns
        if column_index >= len(visible):
            return
        key = visible[column_index]
        self._saved_widths[key] = new_width
        self.column_widths_changed.emit(dict(self._saved_widths))

    def _on_section_moved(self, logical_index: int, old_visual_index: int, new_visual_index: int) -> None:
        """Handle user dragging a column header section.

        QHeaderView emits sectionMoved with visual positions.  We read the
        *actual* visual-to-logical mapping from the header to build the new
        visible order, then derive the full column order from that.
        """
        if self._emitting_order or self._model is None:
            return

        header = self.table.horizontalHeader()
        col_count = header.count()
        visible = self._model.visible_columns
        if col_count != len(visible):
            return  # header and model out of sync — skip

        # Build the new visible order by reading the header's actual
        # visual-to-logical mapping (after the drag has been applied).
        new_visible: list[str] = []
        for vi in range(col_count):
            li = header.logicalIndex(vi)
            if 0 <= li < len(visible):
                new_visible.append(visible[li])

        # Full column order = new visible order + hidden keys in their
        # previous relative order.
        visible_set = set(new_visible)
        current_order = self._model.column_order
        remaining = [k for k in current_order if k not in visible_set]
        updated_order = new_visible + remaining

        self._model.set_column_order(updated_order)
        self._saved_column_order = list(updated_order)

        self._refresh_table_full()
        self.column_order_changed.emit(list(updated_order))

    # ── Sorting ─────────────────────────────────────────────────────

    def _on_header_clicked(self, column_index: int) -> None:
        """Toggle sort on the clicked column."""
        if self._model is None:
            return
        visible = self._model.visible_columns
        if column_index >= len(visible):
            return

        clicked_key = visible[column_index]

        if clicked_key == self._sort_column:
            self._sort_ascending = not self._sort_ascending
        else:
            self._sort_column = clicked_key
            self._sort_ascending = True

        self._model.sort_by(self._sort_column, self._sort_ascending)
        self._refresh_table_full()

    # ── Selection ───────────────────────────────────────────────────

    def set_show_inline_edit(self, show: bool) -> bool:
        """Enable or disable the inline edit bar.

        Returns True if updated, False if user cancelled discard of dirty state.
        """
        if self._show_inline_edit == show:
            return True

        if not show and self._inline_edit_bar.is_dirty:
            from PyQt5.QtWidgets import QMessageBox

            result = QMessageBox.question(
                self,
                "Unsaved Changes",
                "You have unsaved changes in the inline edit bar.\n"
                "Disabling the inline edit bar will discard them.\n\n"
                "Discard changes and disable?",
                QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            if result == QMessageBox.Cancel:
                self.inline_edit_toggle.blockSignals(True)
                self.inline_edit_toggle.setChecked(True)
                self.inline_edit_toggle.blockSignals(False)
                return False

        self._show_inline_edit = show
        self.inline_edit_toggle.blockSignals(True)
        self.inline_edit_toggle.setChecked(show)
        self.inline_edit_toggle.blockSignals(False)

        if not show:
            self._inline_edit_bar.set_unit(None)
            self._inline_edit_bar.setVisible(False)
        else:
            selected = self._get_selected_units()
            if len(selected) == 1:
                self._inline_edit_bar.set_unit(selected[0])
                self._inline_edit_bar.setVisible(True)

        self.show_inline_edit_changed.emit(show)
        return True

    def _on_inline_toggle_clicked(self, checked: bool) -> None:
        self.set_show_inline_edit(checked)

    def _on_selection_changed(self) -> None:
        """Emit unit_selected when the user clicks a row."""
        unit = self._get_selected_unit()
        if unit is not None:
            # If inline bar is dirty and user selected a different unit, warn
            if (
                self._show_inline_edit
                and self._inline_edit_bar.is_dirty
                and self._inline_edit_bar._unit is not None
                and unit.com_number != self._inline_edit_bar._unit.com_number
            ):
                from PyQt5.QtWidgets import QMessageBox

                result = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "You have unsaved changes in the inline edit bar.\n"
                    "Switching rows will discard them.\n\n"
                    "Discard changes?",
                    QMessageBox.Discard | QMessageBox.Cancel,
                    QMessageBox.Cancel,
                )
                if result == QMessageBox.Cancel:
                    # Revert selection back to the dirty unit
                    self._select_com(self._inline_edit_bar._unit.com_number)
                    return

            if self._show_inline_edit and len(self._get_selected_units()) < 2:
                self._inline_edit_bar.set_unit(unit)
            else:
                self._inline_edit_bar.set_unit(None)
                self._inline_edit_bar.setVisible(False)

            self.unit_selected.emit(unit)
            self._last_emitted_com = unit.com_number
            self._update_blame(unit)
        else:
            self._last_emitted_com = None
            self._inline_edit_bar.set_unit(None)
            self._inline_edit_bar.setVisible(False)
            self.blame_label.setText("")
        self._update_batch_bar()

    def _on_cell_clicked(self, row: int, column: int) -> None:
        """Handle cell click to ensure unit is selected even if row was already considered selected by Qt."""
        # Ctrl/Shift-clicks build a multi-selection; Qt has already applied them.
        # Re-selecting here would toggle the clicked row back off.
        if QApplication.keyboardModifiers() & (Qt.ControlModifier | Qt.ShiftModifier):
            return
        if len(self._get_selected_units()) >= 2:
            return
        unit = self._get_unit_at_row(row)
        if unit is None:
            return
        if self._get_selected_com() != unit.com_number:
            self._select_only_row(row)
        needs_sync = (
            self._last_emitted_com != unit.com_number
            or (self._show_inline_edit and (self._inline_edit_bar._unit is None or self._inline_edit_bar._unit.com_number != unit.com_number))
        )
        if needs_sync:
            self._on_selection_changed()

    def _update_blame(self, unit: Unit) -> None:
        """Show last-editor info for the selected unit."""
        try:
            from data.db import get_audit_trail

            entries = get_audit_trail(
                self._db_path,
                com_number=unit.com_number,
                limit=1,
            )
            if entries:
                entry = entries[0]
                saved_by = entry.get("saved_by", "unknown")
                saved_at = entry.get("saved_at", "")
                # Format: "Last edited by Brandon B, Jun 10"
                if saved_at:
                    try:
                        from datetime import datetime

                        dt = datetime.fromisoformat(saved_at.replace(" ", "T"))
                        date_str = dt.strftime("%b %d")
                    except (ValueError, AttributeError):
                        date_str = saved_at[:10]
                    self.blame_label.setText(f"Last edited by {saved_by}, {date_str}")
                else:
                    self.blame_label.setText(f"Last edited by {saved_by}")
            else:
                self.blame_label.setText("")
        except Exception:
            self.blame_label.setText("")

    def _on_inline_save(self, unit: Unit) -> None:
        """Handle save from inline edit bar — emit unit_saved for MainWindow."""
        self.unit_saved.emit(unit)

    # ── Multi-selection ───────────────────────────────────────────────

    def _update_batch_bar(self) -> None:
        """Show the multi-selection hint / inline bar based on selection count."""
        selected = self._get_selected_units()
        count = len(selected)
        if count >= 2:
            self._selection_label.setText(
                f"{count} units selected — right-click to assign or cancel them"
            )
            self._selection_label.setVisible(True)
            self._inline_edit_bar.setVisible(False)
        else:
            self._selection_label.setVisible(False)
            if self._show_inline_edit and count == 1:
                self._inline_edit_bar.set_unit(selected[0])
                self._inline_edit_bar.setVisible(True)
            else:
                self._inline_edit_bar.setVisible(False)
        self.batch_mode_changed.emit(count)

    def _get_selected_units(self) -> list[Unit]:
        """Return list of currently selected Unit objects (deduped, row-based)."""
        seen_rows: set[int] = set()
        units: list[Unit] = []
        for index in self.table.selectedIndexes():
            row = index.row()
            if row in seen_rows:
                continue
            seen_rows.add(row)
            item = self.table.item(row, 0)
            if item is not None:
                unit = item.data(Qt.UserRole)
                if unit:
                    units.append(unit)
        return units

    def _on_table_context_menu(self, pos) -> None:
        """Show context menu for selected table rows."""
        selected = self._get_selected_units()
        if not selected:
            return

        from PyQt5.QtWidgets import QMenu

        menu = QMenu(self.table)
        noun = f"{len(selected)} units" if len(selected) > 1 else f"COM {selected[0].com_number}"
        assign_menu = menu.addMenu(f"👤 Assign {noun} to")
        assign_actions = {}
        for name in self._default_detailers:
            if name == "Cancelled" or name.strip() in UNASSIGNED_LABELS:
                continue
            assign_actions[assign_menu.addAction(name)] = name
        assign_menu.addSeparator()
        assign_actions[assign_menu.addAction("— Unassign —")] = UNASSIGNED

        # Kept apart from Assign so a misclick is less likely; it also asks first
        menu.addSeparator()
        cancel_action = menu.addAction("🚫 Mark as Cancelled…")

        action = menu.exec_(self.table.viewport().mapToGlobal(pos))
        if action in assign_actions:
            self._assign_units(selected, assign_actions[action])
        elif action == cancel_action:
            self._cancel_units(selected)

    def _assign_units(self, units: list[Unit], detailer: str) -> None:
        """Assign (or unassign) detailer on copies of *units* and save them as one batch."""
        updated = [u2 for u in units if (u2 := assign_detailer(u, detailer)) is not None]
        if updated:
            self.units_saved.emit(updated)

    def _cancel_units(self, units: list[Unit]) -> None:
        """Confirm, then mark *units* as Cancelled (target hours 0)."""
        from PyQt5.QtWidgets import QMessageBox

        to_cancel = [u for u in units if u.detailer != "Cancelled"]
        if not to_cancel:
            return
        coms = ", ".join(u.com_number for u in to_cancel[:10])
        if len(to_cancel) > 10:
            coms += f", … (+{len(to_cancel) - 10} more)"
        noun = "this unit" if len(to_cancel) == 1 else f"these {len(to_cancel)} units"
        answer = QMessageBox.question(
            self,
            "Mark as Cancelled",
            f"Mark {noun} as Cancelled?\n\n{coms}\n\n"
            "The detailer is set to Cancelled and target hours to 0.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        updated = [u2 for u in to_cancel if (u2 := mark_cancelled(u)) is not None]
        if updated:
            self.units_saved.emit(updated)

    def _on_double_clicked(self, index) -> None:
        """Double-click also selects (redundant with single-click but clear)."""
        unit = self._get_selected_unit()
        if unit is not None:
            self.unit_selected.emit(unit)

    def _get_unit_at_row(self, row: int) -> Unit | None:
        """Return the Unit stored in UserRole for the given row, or None."""
        if 0 <= row < self.table.rowCount():
            item = self.table.item(row, 0)
            if item is not None:
                return item.data(Qt.UserRole)
        return None

    def _get_selected_unit(self) -> Unit | None:
        """Return the Unit for the current (last clicked) selected row, or None.

        With several rows selected this is the row the user clicked last, not
        whichever selected item Qt happens to list first.
        """
        current = self.table.currentRow()
        if current >= 0:
            item = self.table.item(current, 0)
            if item is not None and item.isSelected():
                return item.data(Qt.UserRole)
        items = self.table.selectedItems()
        if not items:
            return None
        return items[0].data(Qt.UserRole)

    def _get_selected_com(self) -> str:
        """Return the COM number of the currently selected unit."""
        unit = self._get_selected_unit()
        return unit.com_number if unit else ""

    def _select_com(self, com_number: str) -> bool:
        """Select the row with the given COM number. Returns True if found."""
        row = self._row_for_com(com_number)
        if row < 0:
            return False
        self._select_only_row(row)
        if self._last_emitted_com != com_number:
            self._on_selection_changed()
        return True

    # ── Column Chooser ───────────────────────────────────────────────

    def _show_column_chooser(self) -> None:
        """Dialog to toggle visible columns and reorder them."""
        if self._model is None:
            return

        dialog = ColumnChooserDialog(
            column_order=self._model.column_order,
            visible_columns=self._model.visible_columns,
            parent=self,
        )

        if dialog.exec_() == QDialog.Accepted:
            new_order, new_visible = dialog.get_result()
            if not new_visible:
                new_visible = ["com_number"]

            if dialog.is_reset_requested:
                width_map = {d[0]: d[2] for d in COLUMN_DEFS}
                self._saved_widths = dict(width_map)
                self.column_widths_changed.emit(dict(self._saved_widths))

            self._model.set_column_order(new_order)
            self._model.set_visible_columns(new_visible)
            self._saved_column_order = list(new_order)
            self._saved_visible_columns = list(new_visible)

            self._refresh_table_full()
            self.column_order_changed.emit(list(new_order))
            self.column_visibility_changed.emit(list(new_visible))


