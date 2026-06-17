# IMP-020: Customizable Dashboard

**Status**: Draft  
**Priority**: Medium  
**Effort**: M (8 days)  
**Depends on**: ARCH-002 (state management for layout persistence)  

---

## Problem Statement

Current views are fixed: calendar, list, alerts, and Gantt. Users cannot rearrange or customize their workspace to match their workflow. This results in:

- **Rigid layout** — all users see the same views in the same order regardless of role
- **No widget flexibility** — users cannot add, remove, or reposition individual information panels
- **No role-based presets** — managers, detailers, and viewers have different needs but the same layout
- **No layout persistence** — any customization would be lost on restart

---

## Proposed Solution

Implement a user-configurable dashboard with:

1. **Drag-drop widget layout** — rearrange widgets by dragging them to desired positions
2. **Widget library** — a collection of reusable dashboard widgets
3. **Layout persistence** — widget positions and settings saved to `config.yaml`
4. **Multiple dashboard presets** — "Default", "Manager View", "Detailer View"
5. **Settings dialog** — add/remove widgets and configure their properties

### Widget Library

| Widget | Description | Data Source | Refresh Rate |
|--------|-------------|-------------|-------------|
| Alert Summary | Count of active alerts by severity | AlertService | On alert change |
| Workload Gauge | Current detailer workload as a gauge widget | AnalyticsEngine | 30 seconds |
| Due-Date Calendar Mini | Compact calendar showing upcoming due dates | UnitService | On data change |
| Recent Changes Feed | List of recent edits to units | AuditService | Real-time |
| Detailer Workload Bars | Horizontal bars showing units per detailer | AnalyticsEngine | 30 seconds |
| Risk Scores | Risk score summary for active units | AnalyticsEngine | 60 seconds |
| Quick Stats | Unit counts by status (active, completed, overdue) | UnitService | On data change |

### Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Customizable Dashboard Architecture              │
└─────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│                       DashboardContainer                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐               │
│  │  Widget 1    │  │  Widget 2    │  │  Widget 3    │               │
│  │  (Alert Sum) │  │(Workload G.)│  │(Mini Cal.)  │               │
│  └─────────────┘  └─────────────┘  └─────────────┘               │
│  ┌─────────────┐  ┌─────────────┐                                │
│  │  Widget 4    │  │  Widget 5    │                                │
│  │ (Changes)    │  │(Workload B.)│                                │
│  └─────────────┘  └─────────────┘                                │
└──────────────────────────────────────────────────────────────────────┘
         │                       │
         ▼                       ▼
┌──────────────────┐   ┌──────────────────┐
│   WidgetLibrary   │   │ DashboardConfig  │
│ (available       │   │ (layout +        │
│  widgets)        │   │  settings)       │
└──────────────────┘   └──────────────────┘
                               │
                               ▼
                        ┌──────────────────┐
                        │   config.yaml     │
                        │ (persisted layout)│
                        └──────────────────┘
```

### Data Models

```python
# gui/dashboard/models.py

from dataclasses import dataclass, field
from typing import Any, Optional
from enum import Enum, auto
from datetime import datetime


class WidgetType(Enum):
    ALERT_SUMMARY = auto()
    WORKLOAD_GAUGE = auto()
    DUE_DATE_CALENDAR_MINI = auto()
    RECENT_CHANGES_FEED = auto()
    DETAILER_WORKLOAD_BARS = auto()
    RISK_SCORES = auto()
    QUICK_STATS = auto()


WIDGET_METADATA = {
    WidgetType.ALERT_SUMMARY: {
        'name': 'Alert Summary',
        'description': 'Count of active alerts by severity',
        'default_width': 2,
        'default_height': 2,
        'icon': '⚠️',
    },
    WidgetType.WORKLOAD_GAUGE: {
        'name': 'Workload Gauge',
        'description': 'Current detailer workload as a gauge',
        'default_width': 1,
        'default_height': 1,
        'icon': '📊',
    },
    WidgetType.DUE_DATE_CALENDAR_MINI: {
        'name': 'Mini Calendar',
        'description': 'Compact calendar showing upcoming due dates',
        'default_width': 2,
        'default_height': 2,
        'icon': '📅',
    },
    WidgetType.RECENT_CHANGES_FEED: {
        'name': 'Recent Changes',
        'description': 'List of recent edits to units',
        'default_width': 2,
        'default_height': 2,
        'icon': '📝',
    },
    WidgetType.DETAILER_WORKLOAD_BARS: {
        'name': 'Detailer Workload',
        'description': 'Horizontal bars showing units per detailer',
        'default_width': 2,
        'default_height': 1,
        'icon': '👥',
    },
    WidgetType.RISK_SCORES: {
        'name': 'Risk Scores',
        'description': 'Risk score summary for active units',
        'default_width': 2,
        'default_height': 2,
        'icon': '🔮',
    },
    WidgetType.QUICK_STATS: {
        'name': 'Quick Stats',
        'description': 'Unit counts by status',
        'default_width': 1,
        'default_height': 1,
        'icon': '📋',
    },
}


@dataclass
class WidgetConfig:
    """Configuration for a single dashboard widget instance."""
    widget_type: WidgetType
    x: int = 0
    y: int = 0
    width: int = 1
    height: int = 1
    title: str = ''
    settings: dict[str, Any] = field(default_factory=dict)
    
    @property
    def metadata(self) -> dict:
        return WIDGET_METADATA[self.widget_type]
    
    def to_dict(self) -> dict:
        return {
            'type': self.widget_type.name,
            'x': self.x,
            'y': self.y,
            'width': self.width,
            'height': self.height,
            'title': self.title,
            'settings': self.settings,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'WidgetConfig':
        return cls(
            widget_type=WidgetType[data['type']],
            x=data.get('x', 0),
            y=data.get('y', 0),
            width=data.get('width', 1),
            height=data.get('height', 1),
            title=data.get('title', ''),
            settings=data.get('settings', {}),
        )


@dataclass
class DashboardPreset:
    """A named dashboard layout preset."""
    name: str
    description: str = ''
    widgets: list[WidgetConfig] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            'name': self.name,
            'description': self.description,
            'widgets': [w.to_dict() for w in self.widgets],
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'DashboardPreset':
        return cls(
            name=data['name'],
            description=data.get('description', ''),
            widgets=[WidgetConfig.from_dict(w) for w in data.get('widgets', [])],
        )


# Default presets
def get_default_preset() -> DashboardPreset:
    return DashboardPreset(
        name='Default',
        description='Standard dashboard layout',
        widgets=[
            WidgetConfig(WidgetType.QUICK_STATS, 0, 0, 1, 1, 'Quick Stats'),
            WidgetConfig(WidgetType.WORKLOAD_GAUGE, 1, 0, 1, 1, 'Workload'),
            WidgetConfig(WidgetType.ALERT_SUMMARY, 0, 1, 2, 2, 'Alerts'),
            WidgetConfig(WidgetType.DUE_DATE_CALENDAR_MINI, 2, 0, 2, 2, 'Upcoming Dates'),
            WidgetConfig(WidgetType.RECENT_CHANGES_FEED, 2, 2, 2, 2, 'Recent Changes'),
        ]
    )

def get_manager_preset() -> DashboardPreset:
    return DashboardPreset(
        name='Manager View',
        description='Dashboard for managers focusing on team metrics',
        widgets=[
            WidgetConfig(WidgetType.RISK_SCORES, 0, 0, 2, 2, 'Risk Overview'),
            WidgetConfig(WidgetType.WORKLOAD_GAUGE, 2, 0, 1, 1, 'Team Workload'),
            WidgetConfig(WidgetType.QUICK_STATS, 2, 1, 1, 1, 'Unit Stats'),
            WidgetConfig(WidgetType.DETAILER_WORKLOAD_BARS, 0, 2, 3, 2, 'Detailer Workload'),
            WidgetConfig(WidgetType.ALERT_SUMMARY, 3, 0, 2, 2, 'Active Alerts'),
            WidgetConfig(WidgetType.RECENT_CHANGES_FEED, 3, 2, 2, 2, 'Activity Feed'),
        ]
    )

def get_detailer_preset() -> DashboardPreset:
    return DashboardPreset(
        name='Detailer View',
        description='Dashboard for detailers focusing on personal workload',
        widgets=[
            WidgetConfig(WidgetType.DUE_DATE_CALENDAR_MINI, 0, 0, 2, 2, 'My Due Dates'),
            WidgetConfig(WidgetType.QUICK_STATS, 2, 0, 1, 1, 'My Stats'),
            WidgetConfig(WidgetType.WORKLOAD_GAUGE, 2, 1, 1, 1, 'My Workload'),
            WidgetConfig(WidgetType.ALERT_SUMMARY, 0, 2, 2, 2, 'My Alerts'),
            WidgetConfig(WidgetType.RECENT_CHANGES_FEED, 2, 2, 2, 2, 'Recent Changes'),
        ]
    )
```

### Dashboard Grid Layout

```python
# gui/dashboard/grid_layout.py

from PyQt5.QtWidgets import QWidget, QGridLayout, QFrame
from PyQt5.QtCore import Qt, QRect, QPoint, pyqtSignal
from PyQt5.QtGui import QDragEnterEvent, QDropEvent, QPainter, QColor

from .models import WidgetConfig, DashboardPreset


class DashboardDropZone(QFrame):
    """A single cell in the dashboard grid where widgets are placed."""
    
    def __init__(self, x: int, y: int, parent=None):
        super().__init__(parent)
        self.grid_x = x
        self.grid_y = y
        self._widget_content: QWidget | None = None
        self.setAcceptDrops(True)
        self.setFrameStyle(QFrame.StyledPanel | QFrame.Sunken)
        self.setStyleSheet("""
            DashboardDropZone {
                border: 1px dashed #ccc;
                background-color: palette(window);
                min-width: 100px;
                min-height: 100px;
            }
            DashboardDropZone:hover {
                border: 1px dashed #4a90d9;
                background-color: #f0f6ff;
            }
        """)
    
    def set_widget(self, widget: QWidget):
        """Place a widget into this drop zone."""
        if self._widget_content:
            # Remove existing widget
            self._widget_content.setParent(None)
        self._widget_content = widget
        # Layout management handled by parent DashboardContainer
    
    def clear_widget(self):
        """Remove the widget from this drop zone."""
        if self._widget_content:
            self._widget_content.setParent(None)
            self._widget_content = None
    
    @property
    def has_widget(self) -> bool:
        return self._widget_content is not None


class DashboardContainer(QWidget):
    """Main dashboard container with drag-drop grid layout."""
    
    layout_changed = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._grid = QGridLayout(self)
        self._grid.setSpacing(8)
        self._grid.setContentsMargins(12, 12, 12, 12)
        self._zones: dict[tuple[int, int], DashboardDropZone] = {}
        self._widget_map: dict[WidgetConfig, QWidget] = {}
        self._current_preset: DashboardPreset | None = None
        self._grid_cols = 4
        self._grid_rows = 4
        self._setup_grid()
    
    def _setup_grid(self):
        """Initialize the grid with empty drop zones."""
        for row in range(self._grid_rows):
            for col in range(self._grid_cols):
                zone = DashboardDropZone(col, row)
                self._zones[(col, row)] = zone
                self._grid.addWidget(zone, row, col)
    
    def load_preset(self, preset: DashboardPreset):
        """Load a dashboard preset layout."""
        self._current_preset = preset
        self._clear_all()
        
        for wc in preset.widgets:
            self._place_widget(wc)
        
        self.layout_changed.emit()
    
    def _place_widget(self, config: WidgetConfig):
        """Place a widget according to its grid configuration."""
        zone = self._zones.get((config.x, config.y))
        if not zone:
            return
        
        # Create the actual widget content
        widget = self._create_widget_for_type(config)
        if not widget:
            return
        
        # Span configuration
        if config.width > 1 or config.height > 1:
            self._grid.addWidget(widget, config.y, config.x, 
                                 config.height, config.width)
        else:
            zone.set_widget(widget)
        
        self._widget_map[config] = widget
    
    def _create_widget_for_type(self, config: WidgetConfig) -> QWidget | None:
        """Factory method to create a widget from its config."""
        from .widgets import (AlertSummaryWidget, WorkloadGaugeWidget,
                              MiniCalendarWidget, RecentChangesWidget,
                              DetailerWorkloadBarsWidget, RiskScoresWidget,
                              QuickStatsWidget)
        
        widget_map = {
            WidgetType.ALERT_SUMMARY: AlertSummaryWidget,
            WidgetType.WORKLOAD_GAUGE: WorkloadGaugeWidget,
            WidgetType.DUE_DATE_CALENDAR_MINI: MiniCalendarWidget,
            WidgetType.RECENT_CHANGES_FEED: RecentChangesWidget,
            WidgetType.DETAILER_WORKLOAD_BARS: DetailerWorkloadBarsWidget,
            WidgetType.RISK_SCORES: RiskScoresWidget,
            WidgetType.QUICK_STATS: QuickStatsWidget,
        }
        
        WidgetClass = widget_map.get(config.widget_type)
        if WidgetClass:
            return WidgetClass(config, self)
        return None
    
    def _clear_all(self):
        """Remove all widgets from the dashboard."""
        for config, widget in list(self._widget_map.items()):
            widget.setParent(None)
            widget.deleteLater()
        self._widget_map.clear()
        
        # Reset all zones
        for zone in self._zones.values():
            zone.clear_widget()
    
    def get_current_config(self) -> DashboardPreset:
        """Get the current widget configuration as a preset."""
        widgets = []
        for config, widget in self._widget_map.items():
            # Get current position from layout
            idx = self._grid.indexOf(widget)
            if idx >= 0:
                pos = self._grid.getItemPosition(idx)
                config.x = pos[1]  # column
                config.y = pos[0]  # row
                config.width = pos[3] if len(pos) > 3 else config.width
                config.height = pos[2] if len(pos) > 2 else config.height
            widgets.append(config)
        
        return DashboardPreset(
            name=self._current_preset.name if self._current_preset else 'Custom',
            description='Current dashboard layout',
            widgets=widgets,
        )
```

### Widget Base Class and Implementations

```python
# gui/dashboard/widgets.py

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                              QLabel, QFrame, QPushButton)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QPainter, QColor, QPen, QFont

from .models import WidgetConfig, WidgetType


class DashboardWidget(QFrame):
    """Base class for all dashboard widgets."""
    
    widget_clicked = pyqtSignal(WidgetType)
    widget_removed = pyqtSignal(WidgetConfig)
    
    def __init__(self, config: WidgetConfig, parent=None):
        super().__init__(parent)
        self._config = config
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        
        self.setFrameStyle(QFrame.StyledPanel | QFrame.Raised)
        self.setStyleSheet("""
            DashboardWidget {
                border: 1px solid #ddd;
                border-radius: 6px;
                background-color: palette(base);
            }
            DashboardWidget:hover {
                border: 1px solid #4a90d9;
            }
        """)
        
        self._setup_layout()
        
        # Start refresh timer if configured
        refresh_interval = config.settings.get('refresh_interval', 30)
        if refresh_interval > 0:
            self._timer.start(refresh_interval * 1000)
    
    def _setup_layout(self):
        """Set up the widget header and content area."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setSpacing(4)
        
        # Header
        header = QHBoxLayout()
        title = QLabel(f"<b>{self._config.title or self._config.metadata['name']}</b>")
        header.addWidget(title)
        header.addStretch()
        
        # Remove button
        remove_btn = QPushButton("×")
        remove_btn.setFixedSize(20, 20)
        remove_btn.setStyleSheet("""
            QPushButton {
                border: none;
                font-size: 14px;
                font-weight: bold;
                color: #999;
            }
            QPushButton:hover {
                color: #c00;
            }
        """)
        remove_btn.clicked.connect(lambda: self.widget_removed.emit(self._config))
        header.addWidget(remove_btn)
        
        layout.addLayout(header)
        
        # Content area
        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        layout.addWidget(self._content, 1)
    
    def _refresh(self):
        """Refresh widget data. Override in subclasses."""
        pass


class AlertSummaryWidget(DashboardWidget):
    """Shows count of active alerts by severity."""
    
    def __init__(self, config, parent=None):
        super().__init__(config, parent)
        self._update_alerts()
    
    def _update_alerts(self):
        # Clear previous content
        self._clear_content()
        
        # Mock data - in production, fetch from AlertService
        alerts = {
            'Critical': 3,
            'High': 7,
            'Medium': 12,
            'Low': 25,
        }
        
        colors = {
            'Critical': '#d32f2f',
            'High': '#f57c00',
            'Medium': '#fbc02d',
            'Low': '#388e3c',
        }
        
        for severity, count in alerts.items():
            row = QHBoxLayout()
            color_box = QLabel()
            color_box.setFixedSize(12, 12)
            color_box.setStyleSheet(f"background-color: {colors[severity]}; "
                                     f"border-radius: 6px;")
            row.addWidget(color_box)
            
            label = QLabel(f"{severity}: {count}")
            row.addWidget(label)
            row.addStretch()
            
            self._content_layout.addLayout(row)
    
    def _clear_content(self):
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            if item.layout():
                while item.layout().count():
                    child = item.layout().takeAt(0)
                    if child.widget():
                        child.widget().deleteLater()
            if item.widget():
                item.widget().deleteLater()


class WorkloadGaugeWidget(DashboardWidget):
    """Gauge showing current workload as a percentage."""
    
    def __init__(self, config, parent=None):
        super().__init__(config, parent)
        self._workload = 0.67  # Mock: 67%
        self._draw_gauge()
    
    def _draw_gauge(self):
        # Simple gauge visualization
        gauge_frame = QFrame()
        gauge_frame.setMinimumHeight(60)
        gauge_frame.setStyleSheet("""
            QFrame {
                background-color: #f0f0f0;
                border-radius: 4px;
            }
        """)
        
        # Fill bar
        fill = QFrame(gauge_frame)
        fill.setGeometry(2, 2, 
                         int(gauge_frame.width() * self._workload) - 4, 
                         gauge_frame.height() - 4)
        color = self._gauge_color(self._workload)
        fill.setStyleSheet(f"background-color: {color}; border-radius: 3px;")
        
        # Percentage label
        pct_label = QLabel(f"{int(self._workload * 100)}%")
        pct_label.setAlignment(Qt.AlignCenter)
        pct_label.setStyleSheet("font-size: 24px; font-weight: bold;")
        
        self._content_layout.addWidget(gauge_frame)
        self._content_layout.addWidget(pct_label)
    
    def _gauge_color(self, value: float) -> str:
        if value < 0.5:
            return '#4caf50'
        elif value < 0.75:
            return '#ff9800'
        elif value < 0.9:
            return '#f44336'
        return '#b71c1c'


class MiniCalendarWidget(DashboardWidget):
    """Compact calendar showing upcoming due dates."""
    
    def __init__(self, config, parent=None):
        super().__init__(config, parent)
        self._draw_calendar()
    
    def _draw_calendar(self):
        # Upcoming events list
        events = [
            ('COM-14230', 'Mar 28', 'High'),
            ('COM-14247', 'Mar 30', 'Critical'),
            ('COM-14201', 'Apr 2', 'Medium'),
            ('COM-14212', 'Apr 5', 'Low'),
            ('COM-14181', 'Apr 7', 'High'),
        ]
        
        for com, date, priority in events:
            row = QHBoxLayout()
            dot = QLabel("●")
            dot_colors = {'Critical': '#d32f2f', 'High': '#f57c00',
                          'Medium': '#fbc02d', 'Low': '#388e3c'}
            dot.setStyleSheet(f"color: {dot_colors[priority]}; font-size: 10px;")
            row.addWidget(dot)
            row.addWidget(QLabel(f"{com} — {date}"))
            row.addStretch()
            self._content_layout.addLayout(row)


class RecentChangesWidget(DashboardWidget):
    """Shows recent edits to units."""
    
    def __init__(self, config, parent=None):
        super().__init__(config, parent)
        self._draw_changes()
    
    def _draw_changes(self):
        changes = [
            ('Brandon B', 'COM-14230', 'Status → Checked', '2m ago'),
            ('Jackie H', 'COM-14247', 'Due date → Apr 1', '5m ago'),
            ('Carol S', 'COM-14181', 'Notes updated', '12m ago'),
            ('Brandon B', 'COM-14201', 'Detailer → Dave M', '18m ago'),
            ('System', 'COM-14212', 'Auto-assigned', '25m ago'),
        ]
        
        for user, unit, change, time in changes:
            row = QHBoxLayout()
            row.addWidget(QLabel(f"<b>{user}</b>"))
            row.addWidget(QLabel(f"{unit}:"))
            row.addWidget(QLabel(change))
            row.addStretch()
            row.addWidget(QLabel(f"<i>{time}</i>"))
            self._content_layout.addLayout(row)


class DetailerWorkloadBarsWidget(DashboardWidget):
    """Horizontal bars showing units per detailer."""
    
    def __init__(self, config, parent=None):
        super().__init__(config, parent)
        self._draw_bars()
    
    def _draw_bars(self):
        workloads = [
            ('Brandon B', 12, 18),
            ('Jackie H', 8, 15),
            ('Carol S', 15, 20),
            ('Dave M', 5, 10),
            ('Unassigned', 22, 30),
        ]
        
        for name, assigned, capacity in workloads:
            row = QHBoxLayout()
            name_label = QLabel(f"{name}:")
            name_label.setFixedWidth(100)
            row.addWidget(name_label)
            
            bar = QFrame()
            bar.setMinimumHeight(16)
            bar.setStyleSheet("background-color: #e0e0e0; border-radius: 3px;")
            
            fill = QFrame(bar)
            fill_ratio = assigned / max(capacity, 1)
            fill_width = int(150 * fill_ratio)
            fill.setGeometry(0, 0, fill_width, 16)
            color = '#4caf50' if fill_ratio < 0.6 else '#ff9800' if fill_ratio < 0.8 else '#f44336'
            fill.setStyleSheet(f"background-color: {color}; border-radius: 3px;")
            
            row.addWidget(bar, 1)
            row.addWidget(QLabel(f"{assigned}/{capacity}"))
            
            self._content_layout.addLayout(row)


class RiskScoresWidget(DashboardWidget):
    """Risk score summary for active units."""
    
    def __init__(self, config, parent=None):
        super().__init__(config, parent)
        self._draw_risks()
    
    def _draw_risks(self):
        risks = [
            ('COM-14230', 0.85, 'Critical'),
            ('COM-14247', 0.72, 'High'),
            ('COM-14201', 0.45, 'Elevated'),
            ('COM-14181', 0.22, 'Moderate'),
            ('COM-14212', 0.08, 'Low'),
        ]
        
        color_map = {
            'Critical': ('#b71c1c', '#ffebee'),
            'High': ('#e65100', '#fff3e0'),
            'Elevated': ('#f57f17', '#fff8e1'),
            'Moderate': ('#f9a825', '#fffde7'),
            'Low': ('#2e7d32', '#e8f5e9'),
        }
        
        for com, score, label in risks:
            row = QHBoxLayout()
            fg, bg = color_map[label]
            
            score_label = QLabel(f"{int(score * 100)}%")
            score_label.setFixedWidth(40)
            score_label.setAlignment(Qt.AlignCenter)
            score_label.setStyleSheet(f"background-color: {bg}; color: {fg}; "
                                       f"font-weight: bold; border-radius: 3px; "
                                       f"padding: 2px;")
            row.addWidget(score_label)
            
            row.addWidget(QLabel(f"{com} — {label}"))
            row.addStretch()
            
            self._content_layout.addLayout(row)


class QuickStatsWidget(DashboardWidget):
    """Quick unit counts by status."""
    
    def __init__(self, config, parent=None):
        super().__init__(config, parent)
        self._draw_stats()
    
    def _draw_stats(self):
        stats = [
            ('Active', 47, '#4a90d9'),
            ('Completed', 182, '#4caf50'),
            ('Overdue', 8, '#f44336'),
            ('Unassigned', 22, '#ff9800'),
        ]
        
        for label, count, color in stats:
            row = QHBoxLayout()
            dot = QLabel()
            dot.setFixedSize(8, 8)
            dot.setStyleSheet(f"background-color: {color}; border-radius: 4px;")
            row.addWidget(dot)
            row.addWidget(QLabel(f"{label}:"))
            row.addStretch()
            row.addWidget(QLabel(f"<b>{count}</b>"))
            self._content_layout.addLayout(row)
```

### Dashboard Settings Dialog

```python
# gui/dashboard/settings_dialog.py

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout,
                              QPushButton, QListWidget, QLabel,
                              QMessageBox, QGroupBox, QWidget,
                              QListWidgetItem, QComboBox, QTabWidget)
from PyQt5.QtCore import Qt

from .models import (WidgetType, WIDGET_METADATA, WidgetConfig,
                     DashboardPreset, get_default_preset, 
                     get_manager_preset, get_detailer_preset)
from .grid_layout import DashboardContainer


class DashboardSettingsDialog(QDialog):
    """Dialog for configuring dashboard layout and presets."""
    
    def __init__(self, dashboard: DashboardContainer, parent=None):
        super().__init__(parent)
        self._dashboard = dashboard
        self.setWindowTitle("Dashboard Settings")
        self.setMinimumSize(500, 400)
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        tabs = QTabWidget()
        
        # Tab 1: Presets
        preset_tab = QWidget()
        preset_layout = QVBoxLayout(preset_tab)
        
        preset_layout.addWidget(QLabel("<b>Dashboard Presets</b> — Select a preset layout"))
        
        self._preset_list = QListWidget()
        presets = [
            ('Default', get_default_preset()),
            ('Manager View', get_manager_preset()),
            ('Detailer View', get_detailer_preset()),
        ]
        for name, _ in presets:
            self._preset_list.addItem(name)
        preset_layout.addWidget(self._preset_list)
        
        load_btn = QPushButton("Apply Preset")
        load_btn.clicked.connect(lambda: self._apply_preset(presets))
        preset_layout.addWidget(load_btn)
        
        tabs.addTab(preset_tab, "Presets")
        
        # Tab 2: Add/Remove Widgets
        widgets_tab = QWidget()
        widgets_layout = QVBoxLayout(widgets_tab)
        
        widgets_layout.addWidget(QLabel("<b>Available Widgets</b> — Click to add"))
        
        self._widget_list = QListWidget()
        for wt in WidgetType:
            meta = WIDGET_METADATA[wt]
            item = QListWidgetItem(f"{meta['icon']}  {meta['name']}")
            item.setData(Qt.UserRole, wt.name)
            item.setToolTip(meta['description'])
            self._widget_list.addItem(item)
        widgets_layout.addWidget(self._widget_list)
        
        add_btn = QPushButton("Add Selected Widget")
        add_btn.clicked.connect(self._add_widget)
        widgets_layout.addWidget(add_btn)
        
        tabs.addTab(widgets_tab, "Widgets")
        
        layout.addWidget(tabs)
        
        # Close button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)
    
    def _apply_preset(self, presets: list):
        current = self._preset_list.currentItem()
        if current:
            for name, preset in presets:
                if current.text() == name:
                    self._dashboard.load_preset(preset)
                    QMessageBox.information(self, "Preset Applied",
                        f"Dashboard preset '{name}' loaded.")
                    break
    
    def _add_widget(self):
        current = self._widget_list.currentItem()
        if current:
            type_name = current.data(Qt.UserRole)
            widget_type = WidgetType[type_name]
            meta = WIDGET_METADATA[widget_type]
            
            config = WidgetConfig(
                widget_type=widget_type,
                x=0, y=0,
                width=meta['default_width'],
                height=meta['default_height'],
                title=meta['name'],
            )
            
            # Find first empty zone
            # For simplicity, add to current config and reload
            current_config = self._dashboard.get_current_config()
            current_config.widgets.append(config)
            self._dashboard.load_preset(current_config)
            
            QMessageBox.information(self, "Widget Added",
                f"'{meta['name']}' added to dashboard. Drag to reposition.")
```

### Config Persistence

```yaml
# config.yaml dashboard section
dashboard:
  active_preset: "Default"
  presets:
    - name: "Default"
      description: "Standard dashboard layout"
      widgets:
        - type: "QUICK_STATS"
          x: 0
          y: 0
          width: 1
          height: 1
          title: "Quick Stats"
          settings: {}
        - type: "WORKLOAD_GAUGE"
          x: 1
          y: 0
          width: 1
          height: 1
          title: "Workload"
          settings: {}
        - type: "ALERT_SUMMARY"
          x: 0
          y: 1
          width: 2
          height: 2
          title: "Alerts"
          settings: {}
        - type: "DUE_DATE_CALENDAR_MINI"
          x: 2
          y: 0
          width: 2
          height: 2
          title: "Upcoming Dates"
          settings: {}
        - type: "RECENT_CHANGES_FEED"
          x: 2
          y: 2
          width: 2
          height: 2
          title: "Recent Changes"
          settings: {}
```

### Integration with MainWindow

```python
# In MainWindow.__init__():

from gui.dashboard.grid_layout import DashboardContainer
from gui.dashboard.settings_dialog import DashboardSettingsDialog
from gui.dashboard.models import (get_default_preset, DashboardPreset,
                                   WidgetConfig)

# Create dashboard container
self.dashboard = DashboardContainer()
self.dashboard.layout_changed.connect(self._save_dashboard_layout)

# Add to main layout (as a tab or in place of old view stack)
self.view_stack.addWidget(self.dashboard)

# Load saved or default preset
saved_preset = self._load_dashboard_preset()
self.dashboard.load_preset(saved_preset)

# Dashboard menu
dashboard_menu = QMenu("Dashboard", self)
dashboard_menu.addAction("Settings...", self._show_dashboard_settings)
dashboard_menu.addAction("Reset to Default", self._reset_dashboard)
menu_bar.addMenu(dashboard_menu)

def _show_dashboard_settings(self):
    dialog = DashboardSettingsDialog(self.dashboard, self)
    dialog.exec_()

def _save_dashboard_layout(self):
    config = self.dashboard.get_current_config()
    self._persist_dashboard_preset(config)

def _load_dashboard_preset(self) -> DashboardPreset:
    # Load from config.yaml
    import yaml, os
    if os.path.exists('config.yaml'):
        with open('config.yaml', 'r') as f:
            data = yaml.safe_load(f) or {}
        preset_data = data.get('dashboard', {}).get('active_preset', {})
        if preset_data:
            return DashboardPreset.from_dict(preset_data)
    return get_default_preset()

def _persist_dashboard_preset(self, preset: DashboardPreset):
    import yaml, os
    config = {}
    if os.path.exists('config.yaml'):
        with open('config.yaml', 'r') as f:
            config = yaml.safe_load(f) or {}
    config['dashboard'] = {'active_preset': preset.to_dict()}
    with open('config.yaml', 'w') as f:
        yaml.dump(config, f, default_flow_style=False)

def _reset_dashboard(self):
    self.dashboard.load_preset(get_default_preset())
    self._save_dashboard_layout()
```

---

## Implementation Phases

### Phase 1: Core Dashboard Grid (3 days)
1. Implement `DashboardPreset`, `WidgetConfig`, and `WidgetType` data models
2. Implement `DashboardDropZone` grid cell widget
3. Implement `DashboardContainer` with grid layout and widget placement
4. Implement widget base class `DashboardWidget` with header, content area, and remove button
5. Implement `QuickStatsWidget` and `AlertSummaryWidget`
6. **Tests**: Test grid layout with widget placement, removal, and grid coordination

### Phase 2: Widget Library (3 days)
1. Implement `WorkloadGaugeWidget` with gauge visualization
2. Implement `MiniCalendarWidget` with upcoming events list
3. Implement `RecentChangesWidget` with activity feed display
4. Implement `DetailerWorkloadBarsWidget` with horizontal bar chart
5. Implement `RiskScoresWidget` with color-coded risk display
6. Implement preset system with Default, Manager View, and Detailer View presets
7. **Tests**: Test each widget renders correctly with mock data

### Phase 3: Settings & Persistence (2 days)
1. Implement `DashboardSettingsDialog` with preset selection and widget management tabs
2. Implement config.yaml persistence for dashboard layout
3. Implement drag-drop repositioning (MVP: button-based reposition)
4. Wire dashboard into MainWindow with menu integration
5. **Tests**: Test config save/load round-trip, preset switching

---

## Success Criteria

1. Dashboard displays widgets in a grid according to the active preset
2. Users can switch between Default, Manager View, and Detailer View presets
3. Each widget displays correct data from its data source
4. Widget removal works and persists across restarts
5. Dashboard layout is saved to config.yaml and restored on startup
6. All seven widget types are available in the widget library
7. Dashboard loads within 500ms for typical widget configurations

---

## Risk Assessment

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Widget data sources are slow | Medium | Async data loading with loading indicators; configurable refresh intervals |
| Complex drag-drop interactions | Medium | Simplify to button-based repositioning for MVP; full drag-drop in later iteration |
| Layout breaks on different screen sizes | Medium | Use relative grid positioning; test at multiple resolutions |
| Config corruption from partial writes | Low | Atomic writes with temp file + rename |

---

## Effort Estimate

| Phase | Days |
|-------|------|
| Phase 1: Core Dashboard Grid | 3 |
| Phase 2: Widget Library | 3 |
| Phase 3: Settings & Persistence | 2 |
| **Total** | **8** |
