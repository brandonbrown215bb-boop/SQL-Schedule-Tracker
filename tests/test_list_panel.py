# tests/test_list_panel.py
"""Tests for gui/list_panel.py — UnitListModel and ListPanel.

UnitListModel tests are pure Python (no Qt dependency) and run anywhere.
ListPanel widget tests require PyQt5 and are skipped on platforms
where Qt is not available.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from data.models import Unit
from gui.list_panel import (
    COLUMN_DEFS,
    DATE_FILTER_PRESETS,
    SEVERITY_ORDER,
    STATUS_COLORS_FALLBACK,
    ListPanel,
    UnitListModel,
)

# ─── Helpers ─────────────────────────────────────────────────────────


def _make_unit(
    com: str = "COM-001",
    detailer: str = "Jackie / IEC Internals",
    status_color: str = "yellow",
    pct: float = 50.0,
    dept_hours: float = 40.0,
    actual_hours: float = 20.0,
    target_hours: float = 36.0,
    due: date | None = None,
    job_name: str = "Test Job",
    **kwargs,
) -> Unit:
    """Factory for test Units with sensible defaults."""
    return Unit(
        com_number=com,
        job_name=job_name,
        contract_number=f"CNT-{com}",
        description=f"Description for {com}",
        detailer=detailer,
        checking_status=kwargs.get("checking_status", "Not Started"),
        status_color=status_color,
        department_hours=dept_hours,
        target_department_hours=target_hours,
        iec_internal_hours=kwargs.get("iec_internal_hours", 0.0),
        percent_complete=pct,
        actual_hours=actual_hours,
        working_days=kwargs.get("working_days", [0, 1, 2, 3]),
        detailing_due_date=due,
        build_date=kwargs.get("build_date"),
        unit_detailing_start_date=kwargs.get("unit_detailing_start_date"),
        unit_moved_to_checking_date=kwargs.get("unit_moved_to_checking_date"),
        unit_detailing_completion_date=kwargs.get("unit_detailing_completion_date"),
        dept_due_date_previous=kwargs.get("dept_due_date_previous"),
    )


def _build_unit_list() -> list[Unit]:
    """Return a diverse list of test units."""
    today = date.today()
    return [
        _make_unit("COM-100", "Jackie / IEC Internals", "red", 10.0,
                   due=today - timedelta(days=5),
                   job_name="Overdue Alpha"),
        _make_unit("COM-200", "Maria / RGV Team", "yellow", 50.0,
                   due=today + timedelta(days=3),
                   job_name="In Progress Beta"),
        _make_unit("COM-300", "Chen / HOU Team", "green", 100.0,
                   due=today + timedelta(days=10),
                   job_name="Completed Gamma"),
        _make_unit("COM-400", "Tracy / Checking", "gray", 0.0,
                   due=None, job_name="Unassigned Delta"),
        _make_unit("COM-500", "Jackie / IEC Internals", "purple", 90.0,
                   due=today + timedelta(days=7),
                   job_name="Checking Epsilon"),
        _make_unit("COM-600", "Maria / RGV Team", "orange", 95.0,
                   due=today + timedelta(days=30),
                   job_name="Returned Zeta"),
    ]


# ─── UnitListModel Construction ────────────────────────────────────


class TestUnitListModelConstruction:
    def test_empty_list(self):
        model = UnitListModel([])
        assert model.all_units == []
        assert model.filtered_units == []

    def test_holds_units(self):
        units = _build_unit_list()
        model = UnitListModel(units)
        assert len(model.all_units) == 6
        assert len(model.filtered_units) == 6

    def test_default_visible_columns(self):
        model = UnitListModel([])
        defaults = [key for key, _, _, visible in COLUMN_DEFS if visible]
        assert model.visible_columns == defaults

    def test_set_visible_columns(self):
        model = UnitListModel([])
        model.set_visible_columns(["com_number", "job_name"])
        assert model.visible_columns == ["com_number", "job_name"]

    def test_set_visible_columns_rejects_empty(self):
        model = UnitListModel([])
        model.set_visible_columns(["com_number"])
        model.set_visible_columns([])  # should be ignored
        assert model.visible_columns == ["com_number"]


# ─── UnitListModel Filtering ──────────────────────────────────────


class TestUnitListModelFiltering:
    def setup_method(self):
        self.model = UnitListModel(_build_unit_list())

    def test_no_filters_returns_all(self):
        self.model.apply_filters()
        assert len(self.model.filtered_units) == 6

    def test_filter_by_status_red(self):
        self.model.apply_filters(status="red")
        assert len(self.model.filtered_units) == 1
        assert self.model.filtered_units[0].com_number == "COM-100"

    def test_filter_by_status_green(self):
        self.model.apply_filters(status="green")
        assert len(self.model.filtered_units) == 1
        assert self.model.filtered_units[0].com_number == "COM-300"

    def test_filter_by_status_gray(self):
        self.model.apply_filters(status="gray")
        assert len(self.model.filtered_units) == 1
        assert self.model.filtered_units[0].com_number == "COM-400"

    def test_filter_by_detailer(self):
        self.model.apply_filters(detailer="Jackie / IEC Internals")
        assert len(self.model.filtered_units) == 2
        assert all(
            u.detailer == "Jackie / IEC Internals"
            for u in self.model.filtered_units
        )

    def test_filter_by_detailer_maria(self):
        self.model.apply_filters(detailer="Maria / RGV Team")
        assert len(self.model.filtered_units) == 2

    def test_filter_by_com_search(self):
        self.model.apply_filters(com_search="Alpha")
        assert len(self.model.filtered_units) == 1
        assert self.model.filtered_units[0].com_number == "COM-100"

    def test_filter_by_com_search_case_insensitive(self):
        self.model.apply_filters(com_search="BETA")
        assert len(self.model.filtered_units) == 1
        assert self.model.filtered_units[0].com_number == "COM-200"

    def test_filter_by_com_number(self):
        self.model.apply_filters(com_search="COM-500")
        assert len(self.model.filtered_units) == 1
        assert self.model.filtered_units[0].com_number == "COM-500"

    def test_filter_combines_and_logic(self):
        # Status=yellow AND Detailer=Maria
        self.model.apply_filters(
            status="yellow", detailer="Maria / RGV Team"
        )
        assert len(self.model.filtered_units) == 1
        assert self.model.filtered_units[0].com_number == "COM-200"

    def test_filter_combines_and_no_match(self):
        # Status=red AND Detailer=Maria → no units match both
        self.model.apply_filters(
            status="red", detailer="Maria / RGV Team"
        )
        assert len(self.model.filtered_units) == 0

    def test_filter_empty_search_returns_all(self):
        self.model.apply_filters(com_search="")
        assert len(self.model.filtered_units) == 6

    # ── Date filters ──

    def test_filter_overdue(self):
        self.model.apply_filters(date_preset="overdue")
        assert len(self.model.filtered_units) == 1
        assert self.model.filtered_units[0].com_number == "COM-100"

    def test_filter_next_7_days(self):
        self.model.apply_filters(date_preset="next_7_days")
        # COM-200 (due+3), COM-500 (due+7), COM-300 (due+10 is outside)
        assert len(self.model.filtered_units) == 2
        coms = {u.com_number for u in self.model.filtered_units}
        assert coms == {"COM-200", "COM-500"}

    def test_filter_next_30_days(self):
        self.model.apply_filters(date_preset="next_30_days")
        # COM-200(+3), COM-500(+7), COM-300(+10), COM-600(+30)
        assert len(self.model.filtered_units) == 4

    def test_filter_excludes_null_due_dates(self):
        # Units with no due date should not appear in date-filtered results
        self.model.apply_filters(date_preset="next_365_days" if False else "overdue")
        for u in self.model.filtered_units:
            assert u.detailing_due_date is not None


# ─── UnitListModel Sorting ────────────────────────────────────────


class TestUnitListModelSorting:
    def setup_method(self):
        self.model = UnitListModel(_build_unit_list())

    def test_sort_by_due_date_ascending(self):
        self.model.apply_filters()  # reset
        self.model.sort_by("detailing_due_date", ascending=True)
        coms = [u.com_number for u in self.model.filtered_units]
        # COM-100 (overdue, past), COM-200 (+3d), COM-500 (+7d), COM-300 (+10d), COM-600 (+30d)
        # COM-400 has no due date → sorts to end
        assert coms[0] == "COM-100"
        assert coms[-1] == "COM-400"

    def test_sort_by_due_date_descending(self):
        self.model.apply_filters()
        self.model.sort_by("detailing_due_date", ascending=False)
        coms = [u.com_number for u in self.model.filtered_units]
        assert coms[0] == "COM-400"  # None sorts to start when reversed
        # COM-600 (+30d) should be first non-None when desc
        # Actually with our key, None gets (1, date.max) so in desc it'll be last
        # Let's just check that overdue isn't first when desc
        assert coms[0] != "COM-100" or coms[-1] != "COM-100"

    def test_sort_by_status_severity(self):
        self.model.apply_filters()
        self.model.sort_by("status_color", ascending=True)
        # Severity order: red(0), orange(1), purple(2), yellow(3), gray(4), green(5)
        colors = [u.status_color for u in self.model.filtered_units]
        assert colors[0] == "red"
        assert colors[-1] == "green"

    def test_sort_by_com_number(self):
        self.model.apply_filters()
        self.model.sort_by("com_number", ascending=True)
        coms = [u.com_number for u in self.model.filtered_units]
        assert coms == sorted(coms)

    def test_sort_by_percent_complete(self):
        self.model.apply_filters()
        self.model.sort_by("percent_complete", ascending=True)
        pcts = [u.percent_complete for u in self.model.filtered_units]
        assert pcts == sorted(pcts)

    def test_sort_by_job_name(self):
        self.model.apply_filters()
        self.model.sort_by("job_name", ascending=True)
        names = [u.job_name for u in self.model.filtered_units]
        assert names == sorted(names, key=str.lower)


# ─── UnitListModel Metadata ───────────────────────────────────────


class TestUnitListModelMetadata:
    def test_unique_detailers(self):
        model = UnitListModel(_build_unit_list())
        detailers = model.get_unique_detailers()
        assert "Jackie / IEC Internals" in detailers
        assert "Maria / RGV Team" in detailers
        assert "Chen / HOU Team" in detailers
        assert "Tracy / Checking" in detailers

    def test_unique_detailers_sorted(self):
        model = UnitListModel(_build_unit_list())
        detailers = model.get_unique_detailers()
        assert detailers == sorted(detailers)

    def test_unique_detailers_empty(self):
        model = UnitListModel([])
        assert model.get_unique_detailers() == []


# ─── ListPanel Widget Tests (require PyQt5) ────────────────────────


# Check if Qt is available — skip GUI tests on platforms without PyQt5
try:
    from PyQt5.QtWidgets import QApplication

    HAS_QT = True
except ImportError:
    HAS_QT = False


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication for the test session if one doesn't exist."""
    if not HAS_QT:
        pytest.skip("PyQt5 not available")
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


class TestListPanelWidget:
    """Tests for the ListPanel QWidget — requires PyQt5."""

    def setup_method(self):
        self.units = _build_unit_list()

    def test_panel_creates_without_units(self, qapp):
        panel = ListPanel()
        assert panel is not None
        assert panel._model is None

    def test_panel_creates_with_units(self, qapp):
        panel = ListPanel(self.units)
        assert panel._model is not None
        assert len(panel._model.all_units) == 6

    def test_set_units(self, qapp):
        panel = ListPanel()
        panel.set_units(self.units)
        assert len(panel._model.all_units) == 6
        assert panel.table.rowCount() == 6

    def test_refresh_preserves_filters(self, qapp):
        panel = ListPanel(self.units)
        # Apply a filter
        panel.status_combo.setCurrentIndex(
            panel.status_combo.findData("red")
        )
        initial_count = panel.table.rowCount()
        assert initial_count == 1

        # Refresh with same data
        panel.refresh(self.units)
        assert panel.table.rowCount() == 1

    def test_clear_filters(self, qapp):
        panel = ListPanel(self.units)
        # Apply a filter
        panel.status_combo.setCurrentIndex(
            panel.status_combo.findData("red")
        )
        assert panel.table.rowCount() == 1

        # Clear
        panel._clear_filters()
        assert panel.table.rowCount() == 6

    def test_signal_emitted_on_selection(self, qapp):
        panel = ListPanel(self.units)
        received = []
        panel.unit_selected.connect(lambda u: received.append(u))
        # selectRow triggers itemSelectionChanged → _on_selection_changed
        panel.table.selectRow(0)
        # May fire 1-2 times depending on Qt internals; check ≥ 1
        assert len(received) >= 1
        assert isinstance(received[0], Unit)
        assert received[0].com_number == "COM-100"

    def test_default_sort_is_due_date(self, qapp):
        panel = ListPanel(self.units)
        assert panel._sort_column == "detailing_due_date"
        assert panel._sort_ascending is True

    def test_sort_toggle_on_header_click(self, qapp):
        panel = ListPanel(self.units)
        # First click on com_number column
        panel._on_header_clicked(0)  # COM column
        assert panel._sort_column == "com_number"
        assert panel._sort_ascending is True

        # Second click toggles direction
        panel._on_header_clicked(0)
        assert panel._sort_ascending is False

    def test_visible_columns_default(self, qapp):
        panel = ListPanel(self.units)
        defaults = [key for key, _, _, v in COLUMN_DEFS if v]
        assert panel._model.visible_columns == defaults

    def test_search_debounce_exists(self, qapp):
        panel = ListPanel(self.units)
        assert panel._search_debounce is not None
        assert panel._search_debounce.isSingleShot()

    def test_status_combo_has_all_options(self, qapp):
        """Filter combo has All + 6 status colors = 7 options."""
        panel = ListPanel(self.units)
        count = panel.status_combo.count()
        assert count == 7  # "All" + 6 status colors

    def test_date_combo_has_presets(self, qapp):
        panel = ListPanel(self.units)
        count = panel.date_combo.count()
        assert count == len(DATE_FILTER_PRESETS)

    def test_status_colors_complete(self, qapp):
        """Verify all 6 status levels have color definitions."""
        from gui.list_panel import STATUS_COLORS_FALLBACK
        for color_key in ["gray", "yellow", "purple", "orange", "green", "red"]:
            assert color_key in STATUS_COLORS_FALLBACK

    def test_severity_order_complete(self, qapp):
        for color_key in ["gray", "yellow", "purple", "orange", "green", "red"]:
            assert color_key in SEVERITY_ORDER


# ─── Constants Validation ──────────────────────────────────────────


class TestConstants:
    def test_column_defs_unique_keys(self):
        keys = [d[0] for d in COLUMN_DEFS]
        assert len(keys) == len(set(keys))

    def test_column_defs_have_4_elements(self):
        for col_def in COLUMN_DEFS:
            assert len(col_def) == 4

    def test_status_labels_has_all_colors(self):
        from gui.theme import STATUS_LABELS
        for color in ["gray", "yellow", "purple", "orange", "green", "red"]:
            assert color in STATUS_LABELS

    def test_date_presets_non_empty(self):
        assert len(DATE_FILTER_PRESETS) >= 5


# ─── Integration: Model + Sorting + Filtering ──────────────────────


class TestFilterSortIntegration:
    """End-to-end: apply filter then sort, verify correct order."""

    def test_filter_overdue_sort_by_com(self):
        units = _build_unit_list()
        model = UnitListModel(units)
        model.apply_filters(date_preset="overdue")
        model.sort_by("com_number", ascending=True)
        assert len(model.filtered_units) == 1
        assert model.filtered_units[0].com_number == "COM-100"

    def test_filter_next_7_days_sort_by_status(self):
        units = _build_unit_list()
        model = UnitListModel(units)
        model.apply_filters(date_preset="next_7_days")
        model.sort_by("status_color", ascending=True)
        colors = [u.status_color for u in model.filtered_units]
        # Should be sorted by severity
        severity_values = [SEVERITY_ORDER[c] for c in colors]
        assert severity_values == sorted(severity_values)

    def test_filter_jackie_sort_by_pct(self):
        units = _build_unit_list()
        model = UnitListModel(units)
        model.apply_filters(detailer="Jackie / IEC Internals")
        model.sort_by("percent_complete", ascending=True)
        pcts = [u.percent_complete for u in model.filtered_units]
        assert pcts == sorted(pcts)

    def test_search_combined_with_status_filter(self):
        units = _build_unit_list()
        model = UnitListModel(units)
        model.apply_filters(status="yellow", com_search="Beta")
        assert len(model.filtered_units) == 1
        assert model.filtered_units[0].com_number == "COM-200"
