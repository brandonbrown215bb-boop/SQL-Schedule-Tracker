# IMP-019: Data Export Format Expansion

**Status**: Draft  
**Priority**: Medium  
**Effort**: S (4 days)  
**Depends on**: ARCH-004 (export plugins)  

---

## Problem Statement

Currently, only Excel export is available for data export functionality. This is insufficient for users who need:

- **PDF reports** — shareable, printable snapshots of list/alert views with proper formatting
- **CSV export** — simple, universally compatible data exchange with external tools
- **JSON export** — full field data export for programmatic consumption or backup
- **Configurable columns** — users can only export all columns, cannot select specific fields
- **Export templates** — saved column configurations for repeated exports
- **Batch export** — exporting to multiple formats in a single operation

---

## Proposed Solution

Implement a plugin-based export system (leveraging ARCH-004) that supports:

1. **PDF export** — list/alert views rendered as formatted PDF documents
2. **CSV export** — filtered, current-view data in comma-separated format
3. **JSON export** — selected units with full field data in structured JSON
4. **Configurable export columns** — user picks which fields to include
5. **Export templates** — saved column configurations stored in config
6. **Batch export** — export to multiple formats simultaneously

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                       Export Architecture                       │
└─────────────────────────────────────────────────────────────────┘

┌──────────────┐     ┌──────────────────┐     ┌────────────────┐
│  User clicks  │────►│ ExportController  │────►│ Format Plugin  │
│  Export menu  │     │ (manages flow)    │     │ (PDF/CSV/JSON) │
└──────────────┘     └──────────────────┘     └────────────────┘
                            │                           │
                            ▼                           ▼
                     ┌──────────────┐           ┌────────────────┐
                     │ Column Picker │           │ Output File    │
                     │ (configurable)│           │ (saved to disk)│
                     └──────────────┘           └────────────────┘
                            │
                            ▼
                     ┌──────────────┐
                     │ Export Template│
                     │ (saved config)│
                     └──────────────┘
```

### Export Plugin Interface

```python
# plugins/export/base.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ExportColumn:
    """Definition of a single export column."""
    key: str
    label: str
    visible: bool = True
    width: int = 100


@dataclass
class ExportConfig:
    """Configuration for a single export operation."""
    columns: list[ExportColumn]
    include_header: bool = True
    filter_active: bool = True
    sort_order: Optional[str] = None
    file_path: str = ''
    file_name: str = 'export'


@dataclass
class ExportTemplate:
    """A saved export configuration."""
    name: str
    description: str = ''
    columns: list[ExportColumn] = None
    format: str = 'csv'
    created_date: str = ''
    
    def to_dict(self) -> dict:
        return {
            'name': self.name,
            'description': self.description,
            'columns': [{'key': c.key, 'label': c.label, 
                         'visible': c.visible, 'width': c.width} 
                        for c in (self.columns or [])],
            'format': self.format,
            'created_date': self.created_date,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'ExportTemplate':
        columns = [ExportColumn(**c) for c in data.get('columns', [])]
        return cls(
            name=data['name'],
            description=data.get('description', ''),
            columns=columns,
            format=data.get('format', 'csv'),
            created_date=data.get('created_date', ''),
        )


class ExportPlugin(ABC):
    """Abstract base class for export format plugins."""
    
    @abstractmethod
    def format_name(self) -> str:
        """Return the display name of the format (e.g., 'PDF', 'CSV')."""
        pass
    
    @abstractmethod
    def file_extension(self) -> str:
        """Return the file extension (e.g., '.pdf', '.csv')."""
        pass
    
    @abstractmethod
    def export(self, data: list[dict], config: ExportConfig, 
               file_path: str) -> str:
        """Export data to the specified format.
        
        Args:
            data: List of row dictionaries (keys match column keys)
            config: Export configuration including column definitions
            file_path: Full output file path
            
        Returns:
            The path to the written file
        """
        pass
    
    def validate_data(self, data: list[dict], config: ExportConfig) -> bool:
        """Validate that data matches column definitions."""
        if not data or not config.columns:
            return False
        column_keys = {c.key for c in config.columns if c.visible}
        if not column_keys:
            return False
        for row in data:
            if not column_keys.issubset(row.keys()):
                return False
        return True
```

### PDF Export Plugin

```python
# plugins/export/pdf_export.py

import os
from datetime import datetime
from typing import Any

from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                 Paragraph, Spacer, PageBreak)
from reportlab.lib.units import inch

from .base import ExportPlugin, ExportConfig


class PDFExportPlugin(ExportPlugin):
    """Export data as a formatted PDF document."""
    
    def format_name(self) -> str:
        return "PDF"
    
    def file_extension(self) -> str:
        return ".pdf"
    
    def export(self, data: list[dict], config: ExportConfig, 
               file_path: str) -> str:
        # Ensure extension
        if not file_path.endswith('.pdf'):
            file_path += '.pdf'
        
        visible_columns = [c for c in config.columns if c.visible]
        headers = [c.label for c in visible_columns]
        column_keys = [c.key for c in visible_columns]
        
        # Build rows
        rows = [headers]
        for row_data in data:
            rows.append([str(row_data.get(k, '')) for k in column_keys])
        
        # Create PDF
        doc = SimpleDocTemplate(
            file_path,
            pagesize=landscape(letter),
            title=f"Export - {datetime.now().strftime('%Y-%m-%d')}",
            author="Schedule Viewer",
        )
        
        styles = getSampleStyleSheet()
        title_style = styles['Title']
        
        elements = []
        
        # Title
        title = f"Schedule Data Export"
        elements.append(Paragraph(title, title_style))
        elements.append(Spacer(1, 12))
        
        # Date info
        date_style = ParagraphStyle('DateInfo', parent=styles['Normal'],
                                     fontSize=10, textColor=colors.grey)
        elements.append(Paragraph(
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} | "
            f"Rows: {len(data)} | Columns: {len(visible_columns)}",
            date_style
        ))
        elements.append(Spacer(1, 24))
        
        # Data table
        if rows:
            # Calculate column widths
            avail_width = landscape(letter)[0] - 72  # 1 inch margins
            col_width = avail_width / len(headers)
            
            table = Table(rows, colWidths=[col_width] * len(headers))
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4a90d9')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                ('TOPPADDING', (0, 0), (-1, 0), 8),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), 
                 [colors.white, colors.HexColor('#f5f5f5')]),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            elements.append(table)
        
        doc.build(elements)
        return file_path
```

### CSV Export Plugin

```python
# plugins/export/csv_export.py

import csv
import os
from datetime import datetime
from typing import Any

from .base import ExportPlugin, ExportConfig


class CSVExportPlugin(ExportPlugin):
    """Export data as CSV with configurable columns."""
    
    def format_name(self) -> str:
        return "CSV"
    
    def file_extension(self) -> str:
        return ".csv"
    
    def export(self, data: list[dict], config: ExportConfig,
               file_path: str) -> str:
        if not file_path.endswith('.csv'):
            file_path += '.csv'
        
        visible_columns = [c for c in config.columns if c.visible]
        headers = [c.label for c in visible_columns]
        column_keys = [c.key for c in visible_columns]
        
        with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            
            if config.include_header:
                writer.writerow(headers)
            
            for row_data in data:
                writer.writerow([str(row_data.get(k, '')) for k in column_keys])
        
        return file_path
```

### JSON Export Plugin

```python
# plugins/export/json_export.py

import json
import os
from datetime import datetime
from typing import Any

from .base import ExportPlugin, ExportConfig


class JSONExportPlugin(ExportPlugin):
    """Export data as JSON with full field data."""
    
    def format_name(self) -> str:
        return "JSON"
    
    def file_extension(self) -> str:
        return ".json"
    
    def export(self, data: list[dict], config: ExportConfig,
               file_path: str) -> str:
        if not file_path.endswith('.json'):
            file_path += '.json'
        
        visible_columns = [c for c in config.columns if c.visible]
        column_keys = [c.key for c in visible_columns]
        
        # Filter data to only selected columns
        filtered_data = []
        for row in data:
            filtered_row = {k: row.get(k, '') for k in column_keys}
            filtered_data.append(filtered_row)
        
        output = {
            'export_metadata': {
                'generated_at': datetime.now().isoformat(),
                'format_version': '1.0',
                'row_count': len(filtered_data),
                'column_count': len(visible_columns),
                'columns': [{'key': c.key, 'label': c.label} 
                           for c in visible_columns],
            },
            'data': filtered_data,
        }
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, default=str)
        
        return file_path
```

### Export Controller (Main Coordinator)

```python
# plugins/export/controller.py

import os
import yaml
from datetime import datetime
from typing import Any
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout,
                              QPushButton, QListWidget, QFileDialog,
                              QCheckBox, QLabel, QLineEdit, QMessageBox,
                              QGroupBox, QWidget)

from .base import ExportConfig, ExportColumn, ExportTemplate


class ExportController:
    """Coordinates export operations across format plugins."""
    
    def __init__(self, templates_path: str = 'config/export_templates.yaml'):
        self._plugins: dict[str, 'ExportPlugin'] = {}
        self._templates: list[ExportTemplate] = []
        self._templates_path = templates_path
        self._load_templates()
    
    def register_plugin(self, plugin: 'ExportPlugin'):
        """Register an export format plugin."""
        self._plugins[plugin.format_name().lower()] = plugin
    
    def get_available_formats(self) -> list[str]:
        """Return list of registered format names."""
        return [p.format_name() for p in self._plugins.values()]
    
    def export(self, data: list[dict], config: ExportConfig,
               format_name: str) -> str:
        """Export data using the specified format plugin."""
        plugin = self._plugins.get(format_name.lower())
        if not plugin:
            raise ValueError(f"Unsupported format: {format_name}")
        return plugin.export(data, config, config.file_path)
    
    def batch_export(self, data: list[dict], config: ExportConfig,
                     formats: list[str]) -> list[str]:
        """Export data to multiple formats at once."""
        paths = []
        for fmt in formats:
            fmt_config = ExportConfig(
                columns=config.columns,
                include_header=config.include_header,
                filter_active=config.filter_active,
                file_path=config.file_path.replace('.', f'.{fmt.lower()}.'),
            )
            path = self.export(data, fmt_config, fmt)
            paths.append(path)
        return paths
    
    def save_template(self, template: ExportTemplate):
        """Save an export template to config."""
        # Update or add
        for i, t in enumerate(self._templates):
            if t.name == template.name:
                self._templates[i] = template
                break
        else:
            self._templates.append(template)
        self._persist_templates()
    
    def delete_template(self, name: str):
        """Delete an export template."""
        self._templates = [t for t in self._templates if t.name != name]
        self._persist_templates()
    
    def get_templates(self) -> list[ExportTemplate]:
        """Return all saved templates."""
        return self._templates
    
    def _load_templates(self):
        """Load templates from config file."""
        if os.path.exists(self._templates_path):
            with open(self._templates_path, 'r') as f:
                data = yaml.safe_load(f) or {}
            self._templates = [
                ExportTemplate.from_dict(t) for t in data.get('templates', [])
            ]
    
    def _persist_templates(self):
        """Save templates to config file."""
        os.makedirs(os.path.dirname(self._templates_path), exist_ok=True)
        data = {
            'templates': [t.to_dict() for t in self._templates]
        }
        with open(self._templates_path, 'w') as f:
            yaml.dump(data, f, default_flow_style=False)
```

### Export Dialog UI

```python
# plugins/export/dialog.py

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout,
                              QPushButton, QListWidget, QFileDialog,
                              QCheckBox, QLabel, QLineEdit, QMessageBox,
                              QGroupBox, QWidget, QListWidgetItem,
                              QComboBox, QTabWidget, QFormLayout)
from PyQt5.QtCore import Qt

from .base import ExportConfig, ExportColumn, ExportTemplate
from .controller import ExportController


class ExportDialog(QDialog):
    """Main export dialog with format selection, column picker, and templates."""
    
    def __init__(self, controller: ExportController, 
                 available_columns: list[ExportColumn],
                 parent=None):
        super().__init__(parent)
        self._controller = controller
        self._available_columns = available_columns
        self._selected_columns = list(available_columns)  # default: all visible
        
        self.setWindowTitle("Export Data")
        self.setMinimumSize(600, 500)
        
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Tabs: Quick Export | Column Selection | Templates
        tabs = QTabWidget()
        
        # Tab 1: Quick Export
        quick_tab = QWidget()
        quick_layout = QVBoxLayout(quick_tab)
        
        quick_layout.addWidget(QLabel("<b>Quick Export</b> — Export current view with default columns"))
        
        # Format selection
        format_group = QGroupBox("Export Format")
        format_layout = QHBoxLayout(format_group)
        self._format_combo = QComboBox()
        for fmt in self._controller.get_available_formats():
            self._format_combo.addItem(fmt)
        format_layout.addWidget(QLabel("Format:"))
        format_layout.addWidget(self._format_combo)
        format_layout.addStretch()
        quick_layout.addWidget(format_group)
        
        # Quick export button
        quick_btn = QPushButton("Quick Export")
        quick_btn.clicked.connect(self._quick_export)
        quick_layout.addWidget(quick_btn)
        quick_layout.addStretch()
        
        tabs.addTab(quick_tab, "Quick Export")
        
        # Tab 2: Custom Export
        custom_tab = QWidget()
        custom_layout = QVBoxLayout(custom_tab)
        
        # Column picker
        custom_layout.addWidget(QLabel("<b>Select Columns to Export</b>"))
        self._column_list = QListWidget()
        for col in self._available_columns:
            item = QListWidgetItem(col.label)
            item.setData(Qt.UserRole, col.key)
            item.setCheckState(Qt.Checked if col.visible else Qt.Unchecked)
            self._column_list.addItem(item)
        custom_layout.addWidget(self._column_list)
        
        # Select all / none buttons
        btn_row = QHBoxLayout()
        select_all = QPushButton("Select All")
        select_all.clicked.connect(lambda: self._toggle_all_columns(True))
        select_none = QPushButton("Select None")
        select_none.clicked.connect(lambda: self._toggle_all_columns(False))
        btn_row.addWidget(select_all)
        btn_row.addWidget(select_none)
        btn_row.addStretch()
        custom_layout.addLayout(btn_row)
        
        # Format selection
        custom_format_group = QGroupBox("Export Format")
        custom_format_layout = QHBoxLayout(custom_format_group)
        self._custom_format_combo = QComboBox()
        for fmt in self._controller.get_available_formats():
            self._custom_format_combo.addItem(fmt)
        custom_format_layout.addWidget(QLabel("Format:"))
        custom_format_layout.addWidget(self._custom_format_combo)
        custom_format_layout.addStretch()
        custom_layout.addWidget(custom_format_group)
        
        # Batch export checkboxes
        batch_group = QGroupBox("Batch Export (Multiple Formats)")
        batch_layout = QVBoxLayout(batch_group)
        self._batch_checks = {}
        for fmt in self._controller.get_available_formats():
            cb = QCheckBox(fmt)
            self._batch_checks[fmt.lower()] = cb
            batch_layout.addWidget(cb)
        custom_layout.addWidget(batch_group)
        
        # Export button
        export_btn = QPushButton("Export Selected Columns")
        export_btn.clicked.connect(self._custom_export)
        custom_layout.addWidget(export_btn)
        
        tabs.addTab(custom_tab, "Custom Export")
        
        # Tab 3: Templates
        template_tab = QWidget()
        template_layout = QVBoxLayout(template_tab)
        
        template_layout.addWidget(QLabel("<b>Saved Export Templates</b>"))
        
        self._template_list = QListWidget()
        for t in self._controller.get_templates():
            self._template_list.addItem(f"{t.name} ({t.format}) - {t.description}")
        template_layout.addWidget(self._template_list)
        
        template_buttons = QHBoxLayout()
        load_template = QPushButton("Load Template")
        load_template.clicked.connect(self._load_template)
        delete_template = QPushButton("Delete Template")
        delete_template.clicked.connect(self._delete_template)
        template_buttons.addWidget(load_template)
        template_buttons.addWidget(delete_template)
        template_buttons.addStretch()
        template_layout.addLayout(template_buttons)
        
        tabs.addTab(template_tab, "Templates")
        
        layout.addWidget(tabs)
        
        # Cancel button
        cancel_layout = QHBoxLayout()
        cancel_layout.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        cancel_layout.addWidget(cancel_btn)
        layout.addLayout(cancel_layout)
    
    def _toggle_all_columns(self, checked: bool):
        for i in range(self._column_list.count()):
            item = self._column_list.item(i)
            item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
    
    def _get_selected_columns(self) -> list[ExportColumn]:
        columns = []
        for i in range(self._column_list.count()):
            item = self._column_list.item(i)
            key = item.data(Qt.UserRole)
            visible = item.checkState() == Qt.Checked
            # Find the original column data
            for col in self._available_columns:
                if col.key == key:
                    columns.append(ExportColumn(
                        key=col.key, label=col.label, visible=visible,
                        width=col.width
                    ))
                    break
        return columns
    
    def _quick_export(self):
        fmt = self._format_combo.currentText()
        file_path, _ = QFileDialog.getSaveFileName(
            self, f"Export as {fmt}", f"export.{fmt.lower()}",
            f"{fmt} Files (*.{fmt.lower()})"
        )
        if not file_path:
            return
        
        config = ExportConfig(
            columns=self._available_columns,
            file_path=file_path,
        )
        
        try:
            # Collect data from the current view (simplified)
            result_path = self._controller.export([], config, fmt)
            QMessageBox.information(self, "Export Complete", 
                                    f"Data exported to:\n{result_path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", str(e))
    
    def _custom_export(self):
        columns = self._get_selected_columns()
        fmt = self._custom_format_combo.currentText()
        
        # Check batch
        batch_formats = [name for name, cb in self._batch_checks.items() if cb.isChecked()]
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, f"Export as {fmt}", f"export.{fmt.lower()}",
            f"{fmt} Files (*.{fmt.lower()})"
        )
        if not file_path:
            return
        
        config = ExportConfig(
            columns=columns,
            file_path=file_path,
        )
        
        try:
            if batch_formats:
                paths = self._controller.batch_export([], config, batch_formats)
                QMessageBox.information(self, "Export Complete",
                    f"Data exported to:\n" + "\n".join(paths))
            else:
                result_path = self._controller.export([], config, fmt)
                QMessageBox.information(self, "Export Complete",
                    f"Data exported to:\n{result_path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", str(e))
    
    def _load_template(self):
        current = self._template_list.currentItem()
        if current:
            template_name = current.text().split(" (")[0]
            QMessageBox.information(self, "Template Loaded",
                                    f"Template '{template_name}' loaded. "
                                    "Switch to Custom Export tab to modify.")
    
    def _delete_template(self):
        current = self._template_list.currentItem()
        if current:
            template_name = current.text().split(" (")[0]
            reply = QMessageBox.question(self, "Delete Template",
                f"Delete template '{template_name}'?",
                QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                self._controller.delete_template(template_name)
                self._template_list.takeItem(self._template_list.row(current))
```

### Integration with MainWindow

```python
# In MainWindow.__init__():

# Initialize export system
self.export_controller = ExportController()
self.export_controller.register_plugin(PDFExportPlugin())
self.export_controller.register_plugin(CSVExportPlugin())
self.export_controller.register_plugin(JSONExportPlugin())

# Export menu
export_menu = QMenu("Export", self)
export_menu.addAction("Quick Export...", self._show_quick_export)
export_menu.addAction("Custom Export...", self._show_custom_export)
export_menu.addSeparator()
export_menu.addAction("Manage Templates...", self._show_template_manager)
menu_bar.addMenu(export_menu)
```

---

## Implementation Phases

### Phase 1: Core Export System (2 days)
1. Implement `ExportPlugin` abstract base class
2. Implement `ExportConfig` and `ExportColumn` data classes
3. Implement `ExportController` with plugin registration and dispatch
4. Implement CSV export plugin
5. Implement JSON export plugin
6. **Tests**: Unit tests for CSV and JSON export with known data

### Phase 2: Advanced Features (2 days)
1. Implement PDF export plugin with reportlab
2. Implement export dialog with Quick Export and Custom Export tabs
3. Implement column picker with checkboxes for field selection
4. Implement batch export to multiple formats
5. Implement export template save/load with config.yaml persistence
6. Wire export system into MainWindow menu
7. **Tests**: Integration test for dialog, template save/load round-trip

---

## Success Criteria

1. PDF export produces a formatted, paginated document with header row styling
2. CSV export writes UTF-8-BOM encoded files readable by Excel
3. JSON export includes metadata section and preserves all field types
4. Column picker allows selecting/deselecting any subset of visible fields
5. Export templates persist across application restarts
6. Batch export generates all selected format files in a single operation
7. All exports complete within 5 seconds for 10,000 rows

---

## Risk Assessment

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| reportlab dependency for PDF | Low | Include in requirements.txt; provide fallback error if not installed |
| Large exports cause memory issues | Low | Implement streaming for CSV/JSON; paginate PDF output |
| Unicode encoding issues in CSV | Low | Use UTF-8-BOM for Excel compatibility |
| Template config corruption | Low | Validate on load; provide defaults on parse failure |

---

## Effort Estimate

| Phase | Days |
|-------|------|
| Phase 1: Core Export System | 2 |
| Phase 2: Advanced Features | 2 |
| **Total** | **4** |
