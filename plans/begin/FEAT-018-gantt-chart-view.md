# FEAT-018: Interactive Gantt Chart View

**Status**: Draft  
**Priority**: Medium  
**Effort**: XL (15 days)  
**Depends on**: ARCH-001, ARCH-002  
**Replaces**: `gui/calendar_panel.py` (opt-in)  

---

## Problem Statement

The current calendar view (`EventCalendarWidget`) shows units as colored dots on due dates. This has limited utility for capacity planning:

- **No duration visibility** — cannot see how long a unit spans across dates
- **No overlap detection** — cannot see when multiple units overlap for the same detailer
- **No drag interaction** — cannot visually reschedule due dates
- **No detailer filter** — calendar shows all units, clutter from unrelated detailers
- **No dependency lines** — cannot see relationships between units (identical groups, checking pipeline)

---

## Proposed Solution

A full-featured Gantt chart widget that replaces or augments the calendar panel, with:

1. **Horizontal bar chart** — one row per unit, bars spanning from start to due date
2. **Detailer grouping** — rows grouped by assigned detailer with collapsible sections
3. **Status color coding** — bar fill color reflects `calculated_status_color`
4. **Drag-to-reschedule** — drag bar endpoints to change dates (with confirmation)
5. **Dependency lines** — arrows showing identical unit relationships
6. **Zoom levels** — day/week/month/quarter views
7. **Inline percent complete** — bar fill percentage as a secondary visualization
8. **Today line** — vertical red line at current date
9. **Export to PNG/PDF** — save chart as image

### ASCII Mockup

```
┌─────────────────────────────────────────────────────────────────┐
│ [Detailer: All ▼] [Zoom: Week ▼] [🔍 Search...] [📷 Export]   │
├─────────────────────────────────────────────────────────────────┤
│ Detailer: Brandon B                              ┌──────────┐ │
│   ├─ COM 252994 ──▓▓▓▓▓▓▓▓░░░░░░░░░░░░░░░░░░░░  │ Mar 3-28 │ │
│   ├─ COM 14212 ──▓▓▓▓▓▓░░░░░░░░░░░░░░░░░░       │ Mar 5-25 │ │
│   └─ COM 14181 ──▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░░░░░     │ Mar 1-30 │ │
│                                                    │          │ │
│ Detailer: Jackie H                                └──────────┘ │
│   ├─ COM 14230 ──▓▓▓▓▓▓▓▓░░░░░░░░░░░░            │ Mar 8-22 │ │
│   ├─ COM 14247 ──▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░   │ Feb 28-  │ │
│   └─ COM 14201 ──▓▓▓▓▓▓▓▓░░░░░░░░░░░░░░░░       │ Mar 5-25 │ │
│                                                    │          │ │
│ ── TODAY ───────────────────────────────────────► │          │ │
│                                                    │          │ │
│ Legend: ● Unassigned ◆ In Progress ▲ Ready        │          │ │
│         ■ Checked   ✓ Released    ✕ Overdue       │          │ │
└─────────────────────────────────────────────────────────────────┘
```

### Architecture

```python
# gui/gantt_panel.py

from dataclasses import dataclass
from datetime import date
from enum import Enum, auto


class ZoomLevel(Enum):
    DAY = auto()
    WEEK = auto()
    MONTH = auto()
    QUARTER = auto()


@dataclass
class GanttRow:
    unit: "Unit"
    detailer: str
    bar_start: date
    bar_end: date
    percent_complete: float
    status_color: str
    dependencies: list[str] = None  # com_numbers this unit depends on


class GanttModel:
    """Data model for the Gantt chart.
    
    Determines bar positions, row layout, and dependency routes.
    """
    
    def __init__(self, units: list[Unit], zoom: ZoomLevel = ZoomLevel.WEEK):
        self._units = units
        self._zoom = zoom
        self._detailer_filter: str | None = None
    
    def get_rows(self) -> list[GanttRow]:
        """Compute GanttRow entries for current filter + zoom."""
        rows = []
        for unit in self._filtered_units():
            # Bar spans from start to due date (or a sensible range)
            start = (unit.unit_detailing_start_date 
                     or unit.detailing_due_date - timedelta(days=14))
            end = unit.detailing_due_date or start + timedelta(days=14)
            rows.append(GanttRow(
                unit=unit,
                detailer=unit.detailer or "Unassigned",
                bar_start=start,
                bar_end=end,
                percent_complete=unit.percent_complete,
                status_color=unit.calculated_status_color,
            ))
        # Group by detailer
        rows.sort(key=lambda r: (r.detailer.lower(), r.bar_start))
        return rows
    
    def _filtered_units(self) -> list[Unit]:
        if self._detailer_filter:
            return [u for u in self._units if u.detailer == self._detailer_filter]
        return self._units


class GanttWidget(QWidget):
    """Custom-painted interactive Gantt chart."""
    
    unit_selected = pyqtSignal(Unit)
    date_changed = pyqtSignal(str, date, date)  # com_number, old_date, new_date
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._model: GanttModel | None = None
        self._drag_state: dict | None = None  # track drag interactions
        self._zoom = ZoomLevel.WEEK
        self._scroll_offset = 0
        self._setup_paint_metrics()
    
    def set_model(self, model: GanttModel) -> None:
        self._model = model
        self.update()
    
    def set_zoom(self, zoom: ZoomLevel) -> None:
        self._zoom = zoom
        self._invalidate_layout()
        self.update()
    
    def paintEvent(self, event) -> None:
        """Paint the Gantt chart using QPainter."""
        # 1. Draw header with date axis (top row)
        # 2. Draw detailer group headers
        # 3. Draw unit bars with status colors
        # 4. Draw progress fill within each bar
        # 5. Draw dependency arrows between bars
        # 6. Draw today line
        # 7. Draw legend
        ...
    
    def mousePressEvent(self, event) -> None:
        """Detect bar edge clicks for drag-to-reschedule."""
        # If click is near a bar's left or right edge, start drag
        ...
    
    def mouseMoveEvent(self, event) -> None:
        """Update drag state and show preview."""
        ...
    
    def mouseReleaseEvent(self, event) -> None:
        """Finalize drag and emit date_changed signal."""
        ...
    
    def _draw_header(self, painter: QPainter) -> None:
        """Draw date axis with day/week/month labels based on zoom."""
        ...
    
    def _draw_bar(self, painter: QPainter, row: GanttRow, rect: QRect) -> None:
        """Draw a single unit bar with progress fill and status color."""
        ...
    
    def _draw_dependency(self, painter: QPainter, from_rect: QRect, to_rect: QRect) -> None:
        """Draw an arrow from one bar to another showing dependency."""
        ...
    
    def _draw_today_line(self, painter: QPainter) -> None:
        """Draw a vertical red line at today's date position."""
        ...


class GanttPanel(QWidget):
    """Wrapper panel: toolbar + GanttWidget."""
    
    def __init__(self, units: list[Unit], parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        
        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("<b>Gantt Chart</b>"))
        toolbar.addStretch()
        
        self.detailer_combo = QComboBox()
        self.detailer_combo.addItem("All Detailers")
        toolbar.addWidget(self.detailer_combo)
        
        self.zoom_combo = QComboBox()
        for level in ZoomLevel:
            self.zoom_combo.addItem(level.name.capitalize(), level)
        toolbar.addWidget(self.zoom_combo)
        
        export_btn = QPushButton("📷 Export PNG")
        export_btn.clicked.connect(self._export_png)
        toolbar.addWidget(export_btn)
        
        layout.addLayout(toolbar)
        
        # Gantt widget
        self.gantt = GanttWidget()
        layout.addWidget(self.gantt)
        
        # Model
        self._model = GanttModel(units)
        self.gantt.set_model(self._model)
```

### Integration with MainWindow

```python
# In MainWindow._init_left_panel(), add Gantt as a fourth view in the stack:

self.gantt_panel = GanttPanel(self.units)
self.gantt_panel.gantt.unit_selected.connect(self.on_unit_selected)
self.view_stack.addWidget(self.gantt_panel)

# Add a toggle button:
self.gantt_view_btn = QPushButton("📊 Gantt")
self.gantt_view_btn.setCheckable(True)
self.gantt_view_btn.clicked.connect(lambda: self._switch_view("gantt"))
```

---

## Implementation Phases

### Phase 1: GanttModel + Basic Rendering (5 days)
1. Implement `GanttModel` with filtering, grouping, row computation
2. Implement basic `GanttWidget.paintEvent` — draw bars, status colors, progress fill
3. Implement date axis header at WEEK zoom level
4. **Tests**: Test model computation with 100+ units, verify correct bar positions

### Phase 2: Interaction (4 days)
1. Implement mouse tracking — hover tooltip with unit details
2. Implement drag-to-reschedule for bar start/end dates
3. Implement confirmation dialog on date change
4. **Tests**: Test drag logic, validate date range constraints

### Phase 3: Advanced Features (4 days)
1. Implement dependency lines between identical units
2. Implement today line overlay
3. Add MONTH and QUARTER zoom levels with appropriate date axis formatting
4. Add detailer grouping with collapsible sections

### Phase 4: Export + Integration (2 days)
1. Implement PNG export via `QPixmap.grab()`
2. Wire GanttPanel into MainWindow view stack
3. Add view toggle button
4. Remove or deprecate calendar panel

---

## Success Criteria

1. Gantt chart renders 1000+ units without noticeable lag
2. Drag-to-reschedule works and correctly updates dates via UnitService
3. Detailer grouping shows collapsible sections with correct counts
4. Dependency lines correctly connect identical units
5. PNG export produces readable output at all zoom levels
6. Migration path for current calendar panel users

---

## Risk Assessment

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Performance with 1000+ bars | Medium | Virtual scrolling for rows; only paint visible area |
| Drag interaction complexity | Medium | Prototype with simplified drag; iterate |
| Calendar users resist change | Low | Keep calendar as optional view; Gantt is additive |
| Dependency line routing overlap | Medium | Use simple horizontal + vertical routing (no diagonal) |

---

## Effort Estimate

| Phase | Days |
|-------|------|
| Phase 1: Model + Basic Rendering | 5 |
| Phase 2: Interaction | 4 |
| Phase 3: Advanced Features | 4 |
| Phase 4: Export + Integration | 2 |
| **Total** | **15** |