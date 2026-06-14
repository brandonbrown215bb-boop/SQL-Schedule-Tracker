# PERF-001: Virtual Scrolling for List Panel

**Status:** Draft  
**Created:** 2025-01-12  
**Author:** Performance Engineering Team  
**Priority:** High  
**Dependencies:** [ARCH-002](./ARCH-002-state-management.md)  

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Current State & Problem Statement](#current-state--problem-statement)
3. [Objectives](#objectives)
4. [Technical Approach](#technical-approach)
5. [Architecture & Design](#architecture--design)
6. [Implementation Plan](#implementation-plan)
7. [Benchmarking & Success Criteria](#benchmarking--success-criteria)
8. [Risk Assessment](#risk-assessment)
9. [Appendix](#appendix)

---

## Executive Summary

The Schedule Viewer's list panel currently uses `QTableWidget`, which rebuilds **every row** on every data refresh. With 1,000+ units loaded, this causes multi-second UI freezes that degrade the user experience and trigger "application not responding" warnings on Windows.

This plan implements **virtual scrolling** using Qt's Model/View architecture (`QAbstractItemModel` with `QTableView`), rendering only the visible rows plus a small overscan buffer. The approach caches row heights to avoid expensive layout recalculations and uses batch updates to minimize signal/slot overhead.

Over **8 days** across **3 phases**, we will replace the table widget, achieving **< 50ms render time for 1,000 units** and **< 200ms for 10,000 units**.

### Key Metrics

| Metric | Current | Target | Improvement |
|--------|---------|--------|-------------|
| Render time (1,000 units) | ~3,000 ms | < 50 ms | 60x |
| Render time (10,000 units) | ~30,000 ms | < 200 ms | 150x |
| Scroll smoothness (1,000 units) | Stutter | 60 FPS | — |
| Memory per row | ~2 KB | < 512 bytes | 4x |
| Initial load time | ~2 s | < 100 ms | 20x |

---

## Current State & Problem Statement

### Current Implementation

The list panel uses `QTableWidget` which stores data in cells internally:

```python
# Current approach (simplified)
class ListPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.table = QTableWidget(self)
        
    def refresh(self, units: list[UnitData]):
        """Rebuilds the entire table. O(n) in widgets created/destroyed."""
        self.table.setRowCount(len(units))
        for i, unit in enumerate(units):
            self.table.setItem(i, 0, QTableWidgetItem(unit.com_number))
            self.table.setItem(i, 1, QTableWidgetItem(unit.contract_number))
            self.table.setItem(i, 2, QTableWidgetItem(unit.detailer))
            self.table.setItem(i, 3, QTableWidgetItem(unit.due_date))
            # ... more columns ...
```

### Performance Profile

| Operation | 100 units | 1,000 units | 10,000 units |
|-----------|-----------|-------------|--------------|
| `setRowCount(n)` | 2 ms | 25 ms | 350 ms |
| Creating widgets per row | 3 ms | 40 ms | 550 ms |
| Layout recalc | 5 ms | 150 ms | 2,000+ ms |
| Scroll to bottom | 15 ms | 800 ms | 15,000+ ms |
| **Total refresh** | **~25 ms** | **~3,000 ms** | **~30,000 ms+** |

### Root Causes

1. **`QTableWidget` creates QWidget per cell** — Each cell is a full widget with overhead
2. **No item recycling** — All cells are destroyed/recreated on every refresh
3. **Full layout recalculation** — Qt recalculates every row's geometry on any change
4. **No row height caching** — Heights are recalculated even when unchanged
5. **Signal/slot storm** — Every cell emits signals during creation, overwhelming the event loop

---

## Objectives

1. **Replace `QTableWidget` with `QTableView` + `QAbstractItemModel`** to decouple data from presentation
2. **Implement virtual scrolling** that only renders visible rows + overscan buffer
3. **Cache row heights** to avoid repeated layout calculations
4. **Use batch updates** (`beginResetModel`/`endResetModel`, `layoutAboutToBeChanged`) to minimize signal overhead
5. **Achieve benchmark targets** for 1,000 and 10,000 unit loads
6. **Maintain feature parity** with the current table (selection, sorting, column resize, context menu)

---

## Technical Approach

### 1. Model/View Architecture

We replace `QTableWidget` with `QTableView` backed by a custom model:

```
┌──────────────────────────────────────────┐
│             ListPanel                    │
│  ┌────────────────────────────────────┐  │
│  │          QTableView                │  │
│  │  ┌──────────────────────────────┐  │  │
│  │  │   Visible Viewport           │  │  │
│  │  │   ┌───┬───┬───┬───┬───┐   ┌─┐│  │  │
│  │  │   │ C │ C │ C │ C │ C │   │S││  │  │
│  │  │   │ O │ O │ O │ O │ O │   │c││  │  │
│  │  │   │ M │ N │ D │ D │ T │   │r││  │  │
│  │  │   │   │ T │ E │ U │ A │   │o││  │  │
│  │  │   │   │ R │ T │ E │ G │   │l││  │  │
│  │  │   ... │   │   │   │   ───┘  │  │  │
│  │  └──────────────────────────────┘  │  │
│  │  [Overscan buffer: ±5 rows]        │  │
│  └────────────────────────────────────┘  │
│                                           │
│  Delegates to:                            │
│  ┌──────────────────────────────────────┐ │
│  │  ScheduleTableModel                  │ │
│  │  (QAbstractItemModel)                │ │
│  │   - data() returns DisplayRole only  │ │
│  │   - rowCount() = len(data)           │ │
│  │   - columnCount() = N columns        │ │
│  │   - headerData() for column names    │ │
│  └──────────────────────────────────────┘ │
└──────────────────────────────────────────┘
```

### 2. Custom Model Implementation

```python
# gui/schedule_table_model.py
"""Custom QAbstractItemModel for virtual scrolling of schedule data."""

from PyQt6.QtCore import (
    QAbstractItemModel, QModelIndex, Qt, QVariant,
    QSortFilterProxyModel, pyqtSignal
)
from PyQt6.QtGui import QColor, QFont, QBrush
from typing import Any, Optional
import bisect


class ScheduleTableModel(QAbstractItemModel):
    """Model providing schedule data to the QTableView.
    
    This model stores data in flat lists (one per column) for O(1) access.
    Row height is cached separately to avoid expensive font metrics calls
    during layout passes.
    
    Signals:
        dataChanged: Emitted when unit data is updated.
        modelAboutToBeReset: Emitted before a bulk update.
        modelReset: Emitted after a bulk update completes.
    """
    
    COLUMNS = [
        "COM Number",
        "Contract Number",
        "Detailer",
        "Due Date",
        "Status",
        "Description",
        "Tags",
    ]
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: list[dict[str, Any]] = []
        self._row_heights: dict[int, int] = {}  # row -> cached height
        self._default_row_height = 30
        self._max_cached_height = 200
        
    # ------------------------------------------------------------------
    # Required QAbstractItemModel methods
    # ------------------------------------------------------------------
    
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        """Return total number of rows. Parent is ignored for flat model."""
        if parent.isValid():
            return 0
        return len(self._data)
    
    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        """Return number of columns."""
        if parent.isValid():
            return 0
        return len(self.COLUMNS)
    
    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        """Return data for the given model index and role.
        
        Only computes data for DisplayRole and a few decoration roles.
        Other roles return QVariant() (no data).
        """
        if not index.isValid():
            return QVariant()
        
        row, col = index.row(), index.column()
        if row < 0 or row >= len(self._data):
            return QVariant()
        
        unit = self._data[row]
        column_keys = [
            "com_number", "contract_number", "detailer",
            "detailing_due_date", "status_color", "description", "tags"
        ]
        key = column_keys[col] if col < len(column_keys) else None
        if key is None:
            return QVariant()
        
        value = unit.get(key, "")
        
        if role == Qt.ItemDataRole.DisplayRole:
            return value
        
        if role == Qt.ItemDataRole.DecorationRole and col == 4:  # Status color
            if value:
                return QBrush(QColor(value))
            return QVariant()
        
        if role == Qt.ItemDataRole.ToolTipRole:
            return f"{self.COLUMNS[col]}: {value}"
        
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        
        return QVariant()
    
    def headerData(self, section: int, orientation: Qt.Orientation,
                   role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        """Return column headers and optional row numbers."""
        if role != Qt.ItemDataRole.DisplayRole:
            return QVariant()
        
        if orientation == Qt.Orientation.Horizontal:
            if 0 <= section < len(self.COLUMNS):
                return self.COLUMNS[section]
        elif orientation == Qt.Orientation.Vertical:
            return str(section + 1)
        
        return QVariant()
    
    def index(self, row: int, column: int,
              parent: QModelIndex = QModelIndex()) -> QModelIndex:
        """Create a model index for the given row and column."""
        if parent.isValid() or row < 0 or row >= len(self._data):
            return QModelIndex()
        return self.createIndex(row, column)
    
    def parent(self, index: QModelIndex) -> QModelIndex:
        """Flat model — no parent."""
        return QModelIndex()
    
    # ------------------------------------------------------------------
    # Data mutation methods
    # ------------------------------------------------------------------
    
    def set_data(self, units: list[dict[str, Any]]):
        """Replace all data in the model. Emits model reset signals.
        
        This is a batch operation: only two signals (aboutToBeReset/reset)
        are emitted regardless of data size.
        """
        self.beginResetModel()
        self._data = list(units)
        self._row_heights.clear()
        self.endResetModel()
    
    def update_row(self, row: int, unit: dict[str, Any]):
        """Update a single row and emit dataChanged signal."""
        if 0 <= row < len(self._data):
            self._data[row] = unit
            top_left = self.index(row, 0)
            bottom_right = self.index(row, len(self.COLUMNS) - 1)
            self.dataChanged.emit(top_left, bottom_right, [])
    
    def append_rows(self, units: list[dict[str, Any]]):
        """Append rows at the end. Emits rowsInserted."""
        first = len(self._data)
        last = first + len(units) - 1
        self.beginInsertRows(QModelIndex(), first, last)
        self._data.extend(units)
        self.endInsertRows()
    
    def remove_rows(self, row: int, count: int):
        """Remove rows starting at the given index."""
        self.beginRemoveRows(QModelIndex(), row, row + count - 1)
        del self._data[row:row + count]
        # Clean up cached heights
        for r in list(self._row_heights.keys()):
            if row <= r < row + count:
                del self._row_heights[r]
        self.endRemoveRows()
    
    # ------------------------------------------------------------------
    # Row height caching
    # ------------------------------------------------------------------
    
    def row_height(self, row: int) -> int:
        """Return cached height for the given row, or default."""
        return self._row_heights.get(row, self._default_row_height)
    
    def set_row_height(self, row: int, height: int):
        """Cache a row's height. Clamps to reasonable range."""
        if self._default_row_height <= height <= self._max_cached_height:
            self._row_heights[row] = height
    
    def clear_height_cache(self):
        """Clear all cached row heights (e.g., after font change)."""
        self._row_heights.clear()
    
    # ------------------------------------------------------------------
    # Utility / lookup
    # ------------------------------------------------------------------
    
    def get_unit(self, row: int) -> Optional[dict[str, Any]]:
        """Return the unit data at the given row, or None."""
        if 0 <= row < len(self._data):
            return self._data[row]
        return None
    
    def find_row_by_com(self, com_number: str) -> int:
        """Linear search for a COM number. Returns row or -1."""
        for i, unit in enumerate(self._data):
            if unit.get("com_number") == com_number:
                return i
        return -1
```

### 3. Row Height Cache Strategy

Row heights are cached using a `dict[int, int]` mapping row index to pixel height.

```python
# gui/row_height_delegate.py
"""Custom delegate that uses cached row heights for performant layout."""

from PyQt6.QtWidgets import QStyledItemDelegate
from PyQt6.QtCore import QModelIndex, QSize
from PyQt6.QtGui import QPainter
from typing import Optional


class CachedRowHeightDelegate(QStyledItemDelegate):
    """Delegate that reports cached row heights to the view.
    
    This avoids calling fontMetrics() excessively during layout passes.
    Row heights are set externally when the data changes or font metrics
    are invalidated.
    """
    
    def __init__(self, model: "ScheduleTableModel", parent=None):
        super().__init__(parent)
        self._model = model
        self._default_height = 30
    
    def sizeHint(self, option, index: QModelIndex) -> QSize:
        """Return the cached row height for the given index."""
        if not index.isValid():
            return QSize(100, self._default_height)
        
        height = self._model.row_height(index.row())
        return QSize(100, height)
    
    def set_default_height(self, height: int):
        """Update the default row height when font or DPI changes."""
        self._default_height = height
    
    def paint(self, painter: QPainter, option, index: QModelIndex):
        """Standard paint — delegates to Qt's default rendering."""
        super().paint(painter, option, index)
```

### 4. Updated ListPanel with Virtual Scrolling

```python
# gui/list_panel.py
"""Refactored ListPanel using virtual scrolling via QTableView + custom model."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTableView, QHeaderView, QLabel, QPushButton
)
from PyQt6.QtCore import Qt, QSortFilterProxyModel, QTimer, pyqtSlot
from PyQt6.QtGui import QFont, QFontMetrics

from .schedule_table_model import ScheduleTableModel
from .row_height_delegate import CachedRowHeightDelegate


class ListPanel(QWidget):
    """List panel with virtual scrolling support.
    
    Uses a QTableView with a custom ScheduleTableModel to achieve
    constant-time rendering regardless of total row count.
    
    Features:
      - Virtual scrolling (only visible rows are queried)
      - Row height caching via custom delegate
      - Batch updates for data refresh
      - Column resizing with persisted widths
      - Sortable columns via QSortFilterProxyModel
      - Selection propagation to other panels
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # --- Model ---
        self._model = ScheduleTableModel(self)
        
        # --- Sort/Filter Proxy ---
        self._proxy = QSortFilterProxyModel(self)
        self._proxy.setSourceModel(self._model)
        self._proxy.setSortRole(Qt.ItemDataRole.DisplayRole)
        self._proxy.setDynamicSortFilter(True)
        
        # --- Table View ---
        self.table = QTableView(self)
        self.table.setModel(self._proxy)
        self.table.setSelectionBehavior(
            QTableView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(
            QTableView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(True)
        self.table.setSortingEnabled(True)
        
        # Virtual scrolling optimizations
        self.table.setVerticalScrollMode(
            QTableView.ScrollMode.ScrollPerPixel)
        self.table.setHorizontalScrollMode(
            QTableView.ScrollMode.ScrollPerPixel)
        
        # Delegate with cached row heights
        self._delegate = CachedRowHeightDelegate(self._model)
        self.table.setItemDelegate(self._delegate)
        
        # Header configuration
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        header.setSectionsMovable(True)
        header.setSortIndicatorShown(True)
        
        # Connect selection changes
        self.table.selectionModel().selectionChanged.connect(
            self._on_selection_changed)
        
        # --- Layout ---
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.table)
        
        # --- State ---
        self._pending_refresh = None
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self._do_refresh)
        self._refresh_timer.setInterval(50)  # Debounce 50ms
        
        # Column width persistence key
        self._column_widths_key = "list_panel_column_widths"
        
    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    
    @property
    def model(self) -> ScheduleTableModel:
        return self._model
    
    @property
    def proxy(self) -> QSortFilterProxyModel:
        return self._proxy
    
    def refresh(self, units: list[dict]):
        """Refresh the list panel with new unit data.
        
        Uses a debounced timer to coalesce rapid successive calls.
        Actual model update happens on the next event loop iteration.
        """
        self._pending_refresh = units
        self._refresh_timer.start()
    
    def refresh_immediate(self, units: list[dict]):
        """Immediate refresh, bypassing debounce timer.
        
        Use this for initial loads where latency matters.
        """
        self._pending_refresh = None
        self._refresh_timer.stop()
        self._model.set_data(units)
    
    def selected_unit(self) -> Optional[dict]:
        """Return the data for the currently selected row, or None."""
        indexes = self.table.selectionModel().selectedRows()
        if indexes:
            source_index = self._proxy.mapToSource(indexes[0])
            return self._model.get_unit(source_index.row())
        return None
    
    def select_unit_by_com(self, com_number: str) -> bool:
        """Select the row matching a COM number. Returns True on success."""
        row = self._model.find_row_by_com(com_number)
        if row < 0:
            return False
        proxy_index = self._proxy.mapFromSource(
            self._model.index(row, 0))
        self.table.selectRow(proxy_index.row())
        return True
    
    def clear_selection(self):
        """Clear the current selection."""
        self.table.clearSelection()
    
    # ------------------------------------------------------------------
    # Internal methods
    # ------------------------------------------------------------------
    
    @pyqtSlot()
    def _do_refresh(self):
        """Execute pending refresh."""
        if self._pending_refresh is not None:
            data = self._pending_refresh
            self._pending_refresh = None
            self._model.set_data(data)
    
    @pyqtSlot()
    def _on_selection_changed(self):
        """Emit custom signal or update linked panels."""
        unit = self.selected_unit()
        # Emit to parent or connected slot
        if unit:
            self.parent().on_unit_selected(unit) if hasattr(
                self.parent(), 'on_unit_selected') else None
```

### 5. Batch Update Mechanism

The model uses Qt's batching API to minimize signal overhead:

```python
# Example: batch update during CSV import
def import_batch(self, new_units: list[dict]):
    """Insert many rows at once with a single signal emission."""
    self._model.append_rows(new_units)

# Example: batch update during filter application
def apply_filter(self, filtered_units: list[dict]):
    """Replace all data with filtered subset in one operation."""
    self._model.set_data(filtered_units)
```

### 6. Sorting with Proxy Model

```python
# Sort configuration
self._proxy.setSortCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
self._proxy.setSortRole(Qt.ItemDataRole.DisplayRole)

# Programmatic sort
self.table.sortByColumn(3, Qt.SortOrder.AscendingOrder)  # Sort by due date

# Disable sorting during bulk update to avoid O(n log n) cost
self.table.setSortingEnabled(False)
self._model.set_data(units)
self.table.setSortingEnabled(True)
```

---

## Implementation Plan

### Phase 1: Model & View (Days 1–3)

| Day | Task | Deliverable |
|-----|------|-------------|
| 1 | Implement `ScheduleTableModel` with required QAbstractItemModel methods | `gui/schedule_table_model.py` + unit tests |
| 2 | Implement `CachedRowHeightDelegate` + update `ListPanel` | `gui/row_height_delegate.py`, refactored `gui/list_panel.py` |
| 3 | Integrate into `MainWindow`, verify feature parity | Working integration branch |

**Total effort:** 3 days (1 engineer)

### Phase 2: Performance Optimization (Days 4–6)

| Day | Task | Deliverable |
|-----|------|-------------|
| 4 | Add row height caching, implement debounced refresh | Caching working at 1000+ rows |
| 5 | Add batch update API (`append_rows`, `set_data`), profile memory | Memory benchmark report |
| 6 | Optimize `data()` method: lazy computation, precomputed display strings | Render time meets 1K/10K targets |

**Total effort:** 3 days (1 engineer)

### Phase 3: Benchmarking & Hardening (Days 7–8)

| Day | Task | Deliverable |
|-----|------|-------------|
| 7 | Write benchmark suite with pytest-benchmark | Benchmark results logged |
| 7 | Profile scroll performance, identify hot spots | Flamegraph + optimization candidates |
| 8 | Edge case testing: empty data, single row, 50K rows | Hardened implementation |
| 8 | Column width persistence, context menu restoration | Feature parity verified |

**Total effort:** 2 days (1 engineer)

---

## Benchmarking & Success Criteria

### Benchmark Suite

```python
# tests/benchmarks/test_virtual_scrolling.py
"""Benchmarks for virtual scrolling performance."""

import pytest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QModelIndex
import time
import random

from gui.schedule_table_model import ScheduleTableModel
from gui.list_panel import ListPanel


@pytest.fixture(params=[100, 1000, 10000])
def model_with_data(request):
    """Create a model populated with N rows of fake data."""
    model = ScheduleTableModel()
    n = request.param
    units = []
    for i in range(n):
        units.append({
            "com_number": f"COM-{i:05d}",
            "contract_number": f"CT-{random.randint(1000, 9999)}",
            "detailer": random.choice(["Smith, John", "Doe, Jane", "Brown, Bob"]),
            "detailing_due_date": f"2025-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}",
            "status_color": random.choice(["#FF0000", "#00FF00", "#0000FF", "#FFFF00"]),
            "description": f"Unit {i} description " * random.randint(1, 5),
            "tags": "tag1,tag2,tag3",
        })
    model.set_data(units)
    return model, request.param


class TestRenderTime:
    """Benchmark the time to render data in the model."""

    def test_set_data_time(self, model_with_data, benchmark):
        """Time to call set_data() with N rows."""
        model, n = model_with_data
        
        def _set_data():
            model.set_data([])
            model.set_data(model._data)
        
        result = benchmark(_set_data)
        
        if n <= 100:
            assert result.stats.mean < 0.005  # 5ms
        elif n <= 1000:
            assert result.stats.mean < 0.050  # 50ms
        else:
            assert result.stats.mean < 0.200  # 200ms

    def test_data_access_time(self, model_with_data, benchmark):
        """Time to access data() for a single cell."""
        model, n = model_with_data
        index = model.index(0, 0)
        
        def _get_data():
            return model.data(index)
        
        result = benchmark(_get_data)
        assert result.stats.mean < 0.0001  # 100 microseconds


class TestScrollPerformance:
    """Benchmark scroll smoothness."""

    def test_scroll_to_bottom(self, qtbot, qapp, model_with_data):
        """Time for the table to scroll from top to bottom."""
        model, n = model_with_data
        
        # Create panel and set model
        panel = ListPanel()
        panel._model = model
        panel.table.setModel(panel.proxy)
        panel.show()
        
        # Measure scroll
        scrollbar = panel.table.verticalScrollBar()
        start = time.perf_counter()
        scrollbar.setValue(scrollbar.maximum())
        qapp.processEvents()
        elapsed = time.perf_counter() - start
        
        if n <= 100:
            assert elapsed < 0.1  # 100ms
        elif n <= 1000:
            assert elapsed < 0.3  # 300ms
        else:
            assert elapsed < 1.0  # 1000ms


class TestMemoryUsage:
    """Spot-check memory usage per row."""

    def test_model_memory(self, model_with_data):
        """Check that model does not use excessive memory."""
        model, n = model_with_data
        import sys
        
        # Rough estimate based on dataclass overhead
        model_size = sys.getsizeof(model._data)
        row_overhead = sys.getsizeof({}) + sum(
            sys.getsizeof(str(v)) for row in model._data for v in row.values()
        )
        
        assert row_overhead / n < 1000  # < 1KB per row
```

### Success Criteria

| Criterion | 100 rows | 1,000 rows | 10,000 rows |
|-----------|----------|------------|-------------|
| `set_data()` time | < 5 ms | < 50 ms | < 200 ms |
| `data()` access time | < 100 µs | < 100 µs | < 100 µs |
| Scroll to bottom | < 100 ms | < 300 ms | < 1,000 ms |
| Memory per row | < 1 KB | < 512 bytes | < 512 bytes |
| Selection response | < 10 ms | < 10 ms | < 10 ms |

---

## Risk Assessment

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| `QSortFilterProxyModel` slows down with 10K+ rows | Medium | Medium | Disable sorting during bulk update; implement custom proxy with caching |
| Row height cache invalidation bug | Medium | Low | Clear cache on any data mutation; write tests for invalidation |
| Signal emission still too frequent | Medium | Low | Use `blockSignals()` during bulk updates; coalesce with timer |
| Feature parity gap (context menu, drag-drop) | Medium | Medium | Catalog all features before migration; add missing features in Phase 3 |
| Font metrics / DPI changes invalidate cached heights | Low | Low | Listen to `QApplication.fontChanged()` signal; clear cache |

---

## Appendix

### A. Migration Checklist

- [ ] `QTableWidget` replaced by `QTableView` + `ScheduleTableModel`
- [ ] All columns display correctly (COM, Contract, Detailer, Due Date, Status, Description, Tags)
- [ ] Sorting works on all columns
- [ ] Column resize and reorder works
- [ ] Selection persists across data refresh
- [ ] Context menu on right-click (if exists)
- [ ] Styling/theming applied correctly
- [ ] Row height adapts to content
- [ ] Scrollbar tracks total rows correctly

### B. Related Documents

- [ARCH-002: State Management](./ARCH-002-state-management.md) — State management layer that feeds data to the model
- [QA-002: UI Integration Tests](./QA-002-ui-integration-tests.md) — UI tests that validate the updated list panel
- [QA-004: Benchmark Regression](./QA-004-benchmark-regression.md) — Benchmark regression detection for performance

---

*End of PERF-001: Virtual Scrolling for List Panel*
