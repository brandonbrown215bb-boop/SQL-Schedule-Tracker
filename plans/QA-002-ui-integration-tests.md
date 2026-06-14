# QA-002: UI Integration Tests with QtTest

**Status:** Draft  
**Created:** 2025-01-12  
**Author:** Quality Assurance Team  
**Priority:** High  
**Dependencies:** [ARCH-001](./ARCH-001-service-layer.md)  

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Current State & Problem Statement](#current-state--problem-statement)
3. [Objectives](#objectives)
4. [Technical Approach](#technical-approach)
5. [Implementation Plan](#implementation-plan)
6. [Test Architecture](#test-architecture)
7. [Screenshot Diffing](#screenshot-diffing)
8. [CI Integration](#ci-integration)
9. [Success Criteria](#success-criteria)
10. [Risk Assessment](#risk-assessment)

---

## Executive Summary

The Schedule Viewer application currently has **no automated UI testing**. All widget-level interaction testing is performed manually, leading to regressions in critical user flows (selection, filtering, import, theme toggling) with every release. This plan introduces a comprehensive UI integration test suite using **QTest** (Qt's native testing framework) combined with **pytest-qt** for Pythonic test orchestration.

Over **9 days** across **3 phases**, we will deliver a robust suite of widget-level integration tests covering all critical user workflows, with screenshot-based regression detection for visual regressions.

### Key Metrics

| Metric | Target |
|--------|--------|
| Test coverage (critical flows) | 100% |
| Test execution time | < 3 min |
| Screenshot diff false positives | < 2% |
| CI integration | Full pipeline |

---

## Current State & Problem Statement

### Current Pain Points

1. **Zero automated UI coverage** — All UI verification is manual
2. **Frequent regressions** — Theme changes, sorting logic, and dialog flows break silently
3. **Long manual QA cycles** — Full regression takes 4+ hours per release
4. **No visual regression detection** — Layout shifts and style changes go unnoticed until users report them

### Root Causes

- No existing test infrastructure for Qt widgets
- Widgets are tightly coupled to business logic (no service layer separation)
- No standardized approach to mocking database and external dependencies

---

## Objectives

1. **Establish UI testing infrastructure** with pytest-qt and QTest
2. **Achieve 100% coverage** of all critical user flows
3. **Implement screenshot diffing** for visual regression detection
4. **Integrate into CI pipeline** for PR-gated testing
5. **Reduce manual QA time** by 80% for regression cycles

---

## Technical Approach

### 1. Testing Framework Stack

- **pytest-qt** — Python test orchestration with QApplication fixture management
- **QTest** — Qt-native widget simulation (key clicks, mouse events, signal verification)
- **pytest-screenshot** — Automated screenshot capture and diff comparison
- **pytest-xdist** — Parallel test execution
- **pytest-benchmark** — Performance regression markers (optional)

### 2. Fixture Architecture

We define a layered fixture hierarchy in `tests/conftest.py`:

```python
import pytest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QTimer
from pytestqt.plugin import QtBot
from unittest.mock import MagicMock, patch
import tempfile
import shutil
import os

from gui.main_window import MainWindow
from gui.list_panel import ListPanel
from gui.calendar_widget import CalendarWidget
from gui.filter_dialog import FilterDialog
from gui.import_dialog import ImportDialog
from gui.conflict_dialog import ConflictDialog
from sync.database import DatabaseManager


# ---------------------------------------------------------------------------
# QApplication fixture (pytest-qt provides `qtbot` and `qapp` by default)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication instance for the entire test session.
    
    This avoids the overhead of creating/destroying QApplication per test.
    Uses QApplication with HighDpi scaling disabled for deterministic screenshots.
    """
    app = QApplication.instance()
    if app is None:
        os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
        app = QApplication([])
    yield app


# ---------------------------------------------------------------------------
# Database fixture (in-memory SQLite)
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db():
    """Create a fully mocked DatabaseManager with an in-memory SQLite backend.
    
    The fixture patches the database path so that all tests operate on 
    isolated, ephemeral data.
    """
    db = MagicMock(spec=DatabaseManager)
    
    # Seed basic return values
    db.get_all_units.return_value = [
        {
            "id": 1,
            "com_number": "COM-001",
            "contract_number": "CT-1001",
            "detailer": "Smith, John",
            "detailing_due_date": "2025-02-15",
            "status_color": "#FF0000",
            "description": "Test unit alpha",
            "tags": "critical,production"
        },
        {
            "id": 2,
            "com_number": "COM-002",
            "contract_number": "CT-1002",
            "detailer": "Doe, Jane",
            "detailing_due_date": "2025-03-01",
            "status_color": "#00FF00",
            "description": "Test unit beta",
            "tags": "maintenance"
        },
    ]
    db.get_filtered_units.return_value = db.get_all_units.return_value
    db.get_detailers.return_value = [
        "Smith, John",
        "Doe, Jane",
        "Brown, Robert",
    ]
    db.get_latest_due_date.return_value = "2025-06-01"
    return db


# ---------------------------------------------------------------------------
# MainWindow fixture with mocked dependencies
# ---------------------------------------------------------------------------

@pytest.fixture
def main_window(qapp, mock_db, qtbot):
    """Construct a fully instrumented MainWindow with all external dependencies mocked.
    
    This fixture:
      - Mocks DatabaseManager to avoid real DB calls
      - Mocks file system operations (import/export)
      - Mocks clipboard operations
      - Provides a 'qtbot' fixture for widget interaction
    """
    with patch("gui.main_window.DatabaseManager", return_value=mock_db):
        with patch("gui.main_window.QApplication.clipboard") as mock_clipboard:
            mock_clipboard.return_value = MagicMock()
            window = MainWindow()
            window.show()
            qtbot.addWidget(window)
            yield window


@pytest.fixture
def temp_data_dir():
    """Create a temporary directory with sample CSV/JSON files for import testing."""
    dirpath = tempfile.mkdtemp()
    # Write a sample CSV
    csv_content = "com_number,contract_number,detailer,detailing_due_date,status_color,description,tags\n"
    csv_content += "COM-003,CT-1003,Adams,2025-04-01,#0000FF,Import test unit,new\n"
    csv_content += "COM-004,CT-1004,Baker,2025-05-01,#FFFF00,Another import,test\n"
    with open(os.path.join(dirpath, "test_import.csv"), "w") as f:
        f.write(csv_content)
    yield dirpath
    shutil.rmtree(dirpath)
```

### 3. Widget Interaction Patterns

All UI tests follow a consistent pattern:

```python
def test_list_panel_select_first_row(main_window, qtbot):
    """Verify that clicking the first row populates the detail panel."""
    list_panel = main_window.list_panel
    
    # 1. Wait for the widget to be ready
    qtbot.waitExposed(list_panel)
    
    # 2. Simulate a click on the first row
    first_row = list_panel.table_widget.model().index(0, 0)
    list_panel.table_widget.setCurrentIndex(first_row)
    
    # 3. Use QTest to simulate mouse click
    qtbot.mouseClick(
        list_panel.table_widget.viewport(),
        Qt.MouseButton.LeftButton,
        pos=list_panel.table_widget.visualRect(first_row).center()
    )
    
    # 4. Assert that the detail panel updated with correct data
    expected_com = "COM-001"
    actual_com = main_window.detail_panel.com_label.text()
    assert actual_com == expected_com, (
        f"Expected detail panel to show {expected_com}, got {actual_com}"
    )
```

---

## Test Flows

### Flow 1: Application Initialization

```python
class TestInitialization:
    """Verify the application starts correctly with all panels visible."""

    def test_window_title(self, main_window):
        """The main window title should contain 'Schedule Viewer'."""
        assert "Schedule" in main_window.windowTitle()

    def test_panels_visible(self, main_window):
        """All three main panels should be visible at startup."""
        assert main_window.list_panel.isVisible()
        assert main_window.calendar_widget.isVisible()
        assert main_window.detail_panel.isVisible()

    def test_table_populated(self, main_window):
        """The list panel table should contain rows from the mock database."""
        model = main_window.list_panel.table_widget.model()
        assert model.rowCount() > 0, "Table should not be empty after init"

    def test_status_bar_ready(self, main_window):
        """Status bar should show a ready message with unit count."""
        status_text = main_window.statusBar().currentMessage()
        assert "ready" in status_text.lower() or "unit" in status_text.lower()
```

### Flow 2: Unit Selection

```python
class TestUnitSelection:
    """Verify that selecting a unit updates the detail panel and calendar."""

    def test_selection_updates_detail_panel(self, main_window, qtbot):
        """Clicking a row should populate all detail fields."""
        list_panel = main_window.list_panel
        first_row_idx = list_panel.table_widget.model().index(0, 0)
        list_panel.table_widget.setCurrentIndex(first_row_idx)
        qtbot.mouseClick(
            list_panel.table_widget.viewport(),
            Qt.MouseButton.LeftButton,
            pos=list_panel.table_widget.visualRect(first_row_idx).center(),
        )
        assert main_window.detail_panel.com_label.text() != ""

    def test_selection_highlights_calendar(self, main_window, qtbot):
        """Selecting a unit with a due date should highlight that date in the calendar."""
        due_date = main_window.list_panel.model().index(0, 0).data(
            Qt.ItemDataRole.UserRole
        )
        # ... click and verify calendar highlights the correct date

    def test_double_click_opens_detailed_view(self, main_window, qtbot):
        """Double-clicking should open a more detailed view or edit dialog."""
        row = main_window.list_panel.table_widget.model().index(0, 0)
        qtbot.mouseDClick(
            main_window.list_panel.table_widget.viewport(),
            Qt.MouseButton.LeftButton,
            pos=main_window.list_panel.table_widget.visualRect(row).center(),
        )
        # Verify the dialog opened
        assert main_window.detail_view_dialog.isVisible()
```

### Flow 3: Save Operation

```python
class TestSaveOperations:
    """Verify that saving data persists changes correctly."""

    def test_save_button_triggers_db_write(self, main_window, qtbot, mock_db):
        """Clicking save should call db.update_unit with the current data."""
        # Select a row first
        list_panel = main_window.list_panel
        row = list_panel.table_widget.model().index(0, 0)
        list_panel.table_widget.setCurrentIndex(row)

        # Modify a field in the detail panel
        main_window.detail_panel.description_input.setText("Updated description")

        # Click save
        qtbot.mouseClick(main_window.save_button, Qt.MouseButton.LeftButton)

        mock_db.update_unit.assert_called_once()
        args = mock_db.update_unit.call_args[1]
        assert args["description"] == "Updated description"

    def test_save_without_selection_shows_warning(self, main_window, qtbot):
        """Clicking save with no selection should show a dialog."""
        # Ensure no selection
        main_window.list_panel.table_widget.clearSelection()
        qtbot.mouseClick(main_window.save_button, Qt.MouseButton.LeftButton)
        # Check for warning message
        warning_dlg = main_window.findChild(type(main_window), "WarningDialog")
        assert warning_dlg is not None
```

### Flow 4: Filter Application

```python
class TestFilterOperations:
    """Verify filtering by detailer, date range, and status color works."""

    def test_filter_by_detailer(self, main_window, qtbot):
        """Filtering for a specific detailer should reduce visible rows."""
        initial_rows = main_window.list_panel.table_widget.model().rowCount()

        # Open filter dialog
        qtbot.mouseClick(main_window.filter_button, Qt.MouseButton.LeftButton)
        filter_dlg = main_window.findChild(FilterDialog)
        filter_dlg.detailer_combo.setCurrentText("Smith, John")
        qtbot.mouseClick(filter_dlg.apply_button, Qt.MouseButton.LeftButton)

        filtered_rows = main_window.list_panel.table_widget.model().rowCount()
        assert filtered_rows <= initial_rows

    def test_filter_by_date_range(self, main_window, qtbot):
        """Filtering by date range should only show units within that range."""
        # ... setup date range filter ...

    def test_filter_clear_restores_all(self, main_window, qtbot):
        """Clearing filters should restore the full unit list."""
        # Apply filter
        qtbot.mouseClick(main_window.filter_button, Qt.MouseButton.LeftButton)
        filter_dlg = main_window.findChild(FilterDialog)
        filter_dlg.detailer_combo.setCurrentText("Smith, John")
        qtbot.mouseClick(filter_dlg.apply_button, Qt.MouseButton.LeftButton)

        # Clear
        qtbot.mouseClick(main_window.filter_button, Qt.MouseButton.LeftButton)
        filter_dlg = main_window.findChild(FilterDialog)
        qtbot.mouseClick(filter_dlg.clear_button, Qt.MouseButton.LeftButton)

        total_rows = main_window.list_panel.table_widget.model().rowCount()
        assert total_rows == 2  # Mock data has 2 units
```

### Flow 5: Theme Toggle

```python
class TestThemeToggle:
    """Verify that toggling between light and dark themes works correctly."""

    def test_theme_toggle_changes_stylesheet(self, main_window, qtbot):
        """Toggling theme should update the application stylesheet."""
        original_style = main_window.styleSheet()

        qtbot.mouseClick(main_window.theme_toggle_button, Qt.MouseButton.LeftButton)

        new_style = main_window.styleSheet()
        assert new_style != original_style, "Stylesheet should change after theme toggle"

    def test_theme_persists_across_views(self, main_window, qtbot):
        """After toggling, all panels should use the new theme."""
        qtbot.mouseClick(main_window.theme_toggle_button, Qt.MouseButton.LeftButton)

        assert "dark" in main_window.list_panel.styleSheet().lower() or \
               "qdarkstyle" in main_window.styleSheet().lower()
```

### Flow 6: CSV Import

```python
class TestCSVImport:
    """Verify that importing CSV data works correctly."""

    def test_import_dialog_opens(self, main_window, qtbot):
        """Clicking import should show file chooser dialog."""
        qtbot.mouseClick(main_window.import_button, Qt.MouseButton.LeftButton)
        # With mocked QFileDialog, verify the dialog appeared
        # (actual dialog is patched in the fixture)

    def test_import_adds_rows_to_table(self, main_window, qtbot, mock_db, temp_data_dir):
        """After import, the table should contain new rows from the CSV."""
        # Recent mock to return updated data after import
        mock_db.get_all_units.return_value = mock_db.get_all_units.return_value + [
            {
                "id": 3,
                "com_number": "COM-003",
                "contract_number": "CT-1003",
                "detailer": "Adams",
                "detailing_due_date": "2025-04-01",
                "status_color": "#0000FF",
                "description": "Import test unit",
                "tags": "new",
            }
        ]

        with patch.object(main_window, "_get_import_path", return_value=os.path.join(temp_data_dir, "test_import.csv")):
            qtbot.mouseClick(main_window.import_button, Qt.MouseButton.LeftButton)

        model = main_window.list_panel.table_widget.model()
        assert model.rowCount() == 3
```

### Flow 7: Conflict Dialog

```python
class TestConflictResolution:
    """Verify that the conflict dialog handles duplicate/conflicting imports."""

    def test_conflict_dialog_appears_on_duplicate(self, main_window, qtbot, temp_data_dir):
        """When importing a CSV with COM numbers that already exist,
        a conflict resolution dialog should appear."""
        # Set up scenario where duplicate COM numbers exist
        import_path = os.path.join(temp_data_dir, "test_import.csv")
        with patch.object(main_window, "_get_import_path", return_value=import_path):
            with patch.object(main_window, "_check_for_duplicates", return_value=["COM-001"]):
                qtbot.mouseClick(main_window.import_button, Qt.MouseButton.LeftButton)

        conflict_dlg = main_window.findChild(ConflictDialog)
        assert conflict_dlg is not None
        assert conflict_dlg.isVisible()

    def test_conflict_resolve_skip(self, main_window, qtbot, temp_data_dir):
        """Choosing 'skip' for a conflict should ignore the duplicate row."""
        # ... setup and verify skip action ...

    def test_conflict_resolve_overwrite(self, main_window, qtbot, temp_data_dir, mock_db):
        """Choosing 'overwrite' should update existing row."""
        # ... setup and verify overwrite action calls db.update_unit ...
```

---

## Screenshot Diffing

### Approach

We use **pytest-screenshot** with a per-test snapshot directory:

```
tests/
  screenshots/
    baselines/        # Committed reference images
      test_init_window_title.png
      test_theme_dark_mode.png
      ...
    diffs/            # Generated diff images (not committed)
      test_theme_dark_mode_diff.png
    failures/         # Actual failure screenshots (not committed)
      test_theme_dark_mode_failure.png
```

### Implementation

```python
import pytest
from pathlib import Path
from PIL import Image, ImageChops

SCREENSHOT_DIR = Path(__file__).parent / "screenshots"
BASELINE_DIR = SCREENSHOT_DIR / "baselines"
DIFF_DIR = SCREENSHOT_DIR / "diffs"
FAILURE_DIR = SCREENSHOT_DIR / "failures"


@pytest.fixture
def screenshot(request, qtbot):
    """Fixture that captures a screenshot and compares it to a baseline."""
    baseline_path = BASELINE_DIR / f"{request.node.name}.png"
    diff_path = DIFF_DIR / f"{request.node.name}_diff.png"
    failure_path = FAILURE_DIR / f"{request.node.name}_failure.png"

    def _capture(widget, threshold=0.02):
        """Capture a screenshot of the given widget.

        Args:
            widget: The QWidget to capture.
            threshold: Maximum allowed pixel difference ratio (0.0-1.0).

        Returns:
            True if the screenshot matches the baseline within threshold.
        """
        # Capture widget as QPixmap then convert to PIL Image
        pixmap = widget.grab()
        temp_path = SCREENSHOT_DIR / f"{request.node.name}_actual.png"
        pixmap.save(str(temp_path))

        actual = Image.open(temp_path)
        baseline = Image.open(baseline_path) if baseline_path.exists() else None

        if baseline is None:
            # No baseline yet — save as new baseline
            actual.save(baseline_path)
            return True

        # Compare
        diff = ImageChops.difference(actual, baseline)
        diff_ratio = sum(
            1 for pixel in diff.getdata() if any(c != 0 for c in pixel)
        ) / (actual.width * actual.height)

        if diff_ratio > threshold:
            diff.save(diff_path)
            actual.save(failure_path)
            return False

        return True

    return _capture


def test_theme_dark_mode_screenshot(main_window, qtbot, screenshot):
    """Dark mode should render correctly with no visual regressions."""
    qtbot.mouseClick(main_window.theme_toggle_button, Qt.MouseButton.LeftButton)
    assert screenshot(main_window), "Dark mode screenshot differs from baseline"
```

### Diff Threshold Configuration

| Widget | Threshold | Rationale |
|--------|-----------|-----------|
| Main window (full) | 2% | Font rendering differences across platforms |
| Dialog widgets | 0.5% | Smaller widgets should be pixel-perfect |
| Calendar widget | 1% | Date rendering may shift by 1-2 pixels |
| Table widget | 1% | Cell borders may vary slightly |

### Baseline Management

1. Baselines are committed to the repository under `tests/screenshots/baselines/`
2. When intentional UI changes occur, run: `pytest --update-baselines`
3. CI will **fail** if screenshots differ from baselines beyond threshold
4. PRs with baseline changes must be reviewed by UI team

---

## Implementation Plan

### Phase 1: Infrastructure & Fixtures (Days 1–3)

| Day | Task | Deliverable |
|-----|------|-------------|
| 1 | Set up pytest-qt, install dependencies, configure `conftest.py` | Working test environment |
| 2 | Implement all fixtures: `qapp`, `mock_db`, `main_window`, `temp_data_dir` | Reusable fixture library |
| 3 | Create screenshot diffing infrastructure + baseline directory | Screenshot comparison pipeline |

**Total effort:** 3 days (1 engineer)

### Phase 2: Core Test Flows (Days 4–7)

| Day | Task | Deliverable |
|-----|------|-------------|
| 4 | Flow 1 (Init) + Flow 2 (Selection) | 8 test cases |
| 5 | Flow 3 (Save) + Flow 4 (Filter) | 10 test cases |
| 6 | Flow 5 (Theme) + Flow 6 (Import) | 8 test cases |
| 7 | Flow 7 (Conflict Dialog) + edge case coverage | 6 test cases + parameterization |

**Total effort:** 4 days (1 engineer)

### Phase 3: CI Integration & Hardening (Days 8–9)

| Day | Task | Deliverable |
|-----|------|-------------|
| 8 | CI pipeline configuration (GitHub Actions / Jenkins), parallel execution | CI integration PR |
| 9 | Flaky test detection, test retry logic, baseline maintenance script | Hardened test suite |

**Total effort:** 2 days (1 engineer)

---

## CI Integration

### GitHub Actions Configuration

```yaml
# .github/workflows/ui-tests.yml
name: UI Integration Tests

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  ui-tests:
    runs-on: ubuntu-latest

    services:
      xvfb:
        image: archlinux:latest
        options: --entrypoint /usr/bin/Xvfb
        args: :99 -ac -screen 0 1920x1080x24

    env:
      DISPLAY: :99
      QT_QPA_PLATFORM: offscreen

    steps:
    - uses: actions/checkout@v4

    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: "3.11"

    - name: Install system deps
      run: |
        sudo apt-get update
        sudo apt-get install -y \
          libxcb-xinerama0 \
          libxcb-icccm4 \
          libxcb-image0 \
          libxcb-keysyms1 \
          libxcb-randr0 \
          libxcb-render-util0 \
          libxcb-shape0 \
          libxcb-xfixes0 \
          libxcb-xkb1 \
          libxkbcommon-x11-0 \
          xvfb

    - name: Install Python deps
      run: |
        python -m pip install --upgrade pip
        pip install pytest pytest-qt pytest-screenshot pytest-xdist
        pip install -r requirements.txt

    - name: Run UI tests with Xvfb
      run: |
        Xvfb :99 -screen 0 1920x1080x24 &
        sleep 1
        pytest tests/ui/ \
          --verbose \
          --screenshot-dir=tests/screenshots \
          -n auto \
          --timeout=60

    - name: Upload screenshot diffs
      if: failure()
      uses: actions/upload-artifact@v4
      with:
        name: screenshot-diffs
        path: tests/screenshots/diffs/
```

### Headless Configuration

For CI environments without a display server, use the **offscreen** QPA platform:

```python
import os

# Must be set BEFORE importing any Qt modules
os.environ["QT_QPA_PLATFORM"] = "offscreen"

# Or via pytest CLI: QT_QPA_PLATFORM=offscreen pytest tests/ui/
```

---

## Success Criteria

| Criterion | Measurement | Pass/Fail |
|-----------|-------------|-----------|
| All critical flows tested | Coverage report shows 100% critical path coverage | |
| All tests pass in CI | CI pipeline green for 5 consecutive runs | |
| Screenshot baseline established | Baseline directory contains images for all tests | |
| Test execution < 3 minutes | CI timings < 180s | |
| Manual QA time reduced 80% | Time for regression cycle < 1 hour | |

---

## Risk Assessment

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Flaky tests due to timing | Medium | Medium | Use `qtbot.waitSignal`, `qtbot.waitExposed`, retry decorators |
| Screenshot diffs across platforms | Medium | High | Platform-specific baselines; tolerance threshold configuration |
| Qt version incompatibility | High | Low | Pin Qt version in CI; test against both PyQt6 and PySide6 |
| Slow test execution | Medium | Low | Parallel execution with pytest-xdist; fixture reuse |
| Mock mismatch with real behavior | Medium | Medium | Integration smoke tests against real DB daily |

---

## Appendix

### A. Dependencies

```txt
# requirements-test.txt
pytest>=8.0
pytest-qt>=4.2.0
pytest-screenshot>=1.0.0
pytest-xdist>=3.5.0
pytest-timeout>=2.2.0
pytest-benchmark>=4.0.0
Pillow>=10.0.0
```

### B. Related Documents

- [ARCH-001: Service Layer](./ARCH-001-service-layer.md) — Decouples business logic from UI, enabling mock injection
- [QA-001: Property-Based Testing](./QA-001-property-based-testing.md) — Complements UI tests with data invariants
- [QA-003: Fuzz Testing](./QA-003-fuzz-testing.md) — Additional fuzz coverage for import pipeline

---

*End of QA-002: UI Integration Tests with QtTest*
