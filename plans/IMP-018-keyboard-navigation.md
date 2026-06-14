# IMP-018: Comprehensive Keyboard Navigation

**Status**: Draft  
**Priority**: High  
**Effort**: S (4 days)  
**Depends on**: None  

---

## Problem Statement

Current keyboard support is limited to a few hardcoded shortcuts: Ctrl+S, Ctrl+T, F5, Ctrl+F, and Escape. This is insufficient for power users who need fast, keyboard-driven navigation without reaching for the mouse. Specific gaps include:

- **No list navigation** — users must click to move between rows in list/alert views
- **No quick search** — Ctrl+F opens a dialog but doesn't support incremental filtering
- **No date field nudging** — date fields require mouse interaction or manual typing
- **No customization** — keybindings are hardcoded and cannot be remapped
- **No reference** — users cannot easily discover available shortcuts

---

## Proposed Solution

Implement a comprehensive keyboard navigation system with:

1. **Vim-style j/k navigation** in list and alert views
2. **/ for quick search** with instant filtering
3. **gg/G for top/bottom** navigation
4. **n/N for next/previous search result**
5. **Tab through form fields** in logical order
6. **Ctrl+Arrow for date field nudge** (+1/-1 day)
7. **Customizable keybindings** stored in `config.yaml`
8. **Keyboard shortcut reference dialog** (Ctrl+/)

### Keybinding Table

| Shortcut | Context | Action | Config Key |
|----------|---------|--------|------------|
| `j` | List/Alert views | Move cursor down one row | `nav.list.down` |
| `k` | List/Alert views | Move cursor up one row | `nav.list.up` |
| `/` | Global | Enter quick search mode | `nav.search.quick` |
| `gg` | List/Alert views | Jump to first item | `nav.list.top` |
| `G` | List/Alert views | Jump to last item | `nav.list.bottom` |
| `n` | After search | Jump to next match | `nav.search.next` |
| `N` | After search | Jump to previous match | `nav.search.prev` |
| `Tab` | Form/Any | Focus next field/control | `nav.form.next_field` |
| `Shift+Tab` | Form/Any | Focus previous field/control | `nav.form.prev_field` |
| `Ctrl+Right` | Date field | Nudge date +1 day | `nav.date.nudge_forward` |
| `Ctrl+Left` | Date field | Nudge date -1 day | `nav.date.nudge_backward` |
| `Ctrl+Up` | Date field | Nudge date +7 days (next week) | `nav.date.nudge_week_forward` |
| `Ctrl+Down` | Date field | Nudge date -7 days (prev week) | `nav.date.nudge_week_backward` |
| `Ctrl+S` | Global | Save current changes | `app.save` |
| `Ctrl+T` | Global | Toggle theme | `app.toggle_theme` |
| `F5` | Global | Refresh data | `app.refresh` |
| `Ctrl+F` | Global | Find/Search dialog | `app.find` |
| `Escape` | Any | Cancel/close dialog / exit search mode | `app.cancel` |
| `Ctrl+/` | Global | Show keyboard shortcuts reference | `app.shortcuts` |
| `Ctrl+Z` | Edit field | Undo last edit | `edit.undo` |
| `Ctrl+Y` | Edit field | Redo last edit | `edit.redo` |
| `?` | List/Alert views | Toggle help tooltip for selected item | `nav.list.help` |
| `r` | List/Alert views | Refresh/reload selected unit | `nav.list.refresh_unit` |
| `Enter` | List/Alert views | Open selected unit for editing | `nav.list.open` |
| `Delete` | List/Alert views | Delete selected unit (with confirmation) | `nav.list.delete` |
| `+` | List/Alert views | Expand/collapse detail row | `nav.list.toggle_detail` |
| `Home` | List/Alert views | Jump to first visible column | `nav.list.col_start` |
| `End` | List/Alert views | Jump to last visible column | `nav.list.col_end` |

---

## Architecture

### KeyboardManager

```python
# gui/keyboard_manager.py

from typing import Callable, Any
from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtGui import QKeySequence, QKeyEvent
import yaml
import os


class KeyboardManager(QObject):
    """Central keyboard shortcut manager with custom bindings support."""
    
    shortcut_triggered = pyqtSignal(str)  # config_key
    
    def __init__(self, config_path: str = 'config.yaml', parent=None):
        super().__init__(parent)
        self._config_path = config_path
        self._bindings: dict[str, 'KeyBinding'] = {}
        self._contexts: dict[str, list[str]] = {}  # context -> [config_keys]
        self._active_contexts: set[str] = set()
        self._search_mode: bool = False
        self._load_bindings()
    
    def _load_bindings(self):
        """Load keybindings from config.yaml with fallback to defaults."""
        self._bindings = self._default_bindings()
        
        if os.path.exists(self._config_path):
            with open(self._config_path, 'r') as f:
                config = yaml.safe_load(f)
            
            user_bindings = config.get('keybindings', {})
            for config_key, shortcut in user_bindings.items():
                if config_key in self._bindings:
                    self._bindings[config_key].shortcut = shortcut
                    self._bindings[config_key].is_custom = True
    
    def _default_bindings(self) -> dict[str, 'KeyBinding']:
        """Return default keybinding map."""
        from dataclasses import dataclass
        
        @dataclass
        class KeyBinding:
            config_key: str
            shortcut: str
            description: str
            context: str
            is_custom: bool = False
        
        return {
            'nav.list.down': KeyBinding('nav.list.down', 'j', 'Move down', 'list'),
            'nav.list.up': KeyBinding('nav.list.up', 'k', 'Move up', 'list'),
            'nav.search.quick': KeyBinding('nav.search.quick', '/', 'Quick search', 'global'),
            'nav.list.top': KeyBinding('nav.list.top', 'gg', 'Go to top', 'list'),
            'nav.list.bottom': KeyBinding('nav.list.bottom', 'G', 'Go to bottom', 'list'),
            'nav.search.next': KeyBinding('nav.search.next', 'n', 'Next match', 'search'),
            'nav.search.prev': KeyBinding('nav.search.prev', 'N', 'Previous match', 'search'),
            'nav.form.next_field': KeyBinding('nav.form.next_field', 'Tab', 'Next field', 'form'),
            'nav.form.prev_field': KeyBinding('nav.form.prev_field', 'Shift+Tab', 'Previous field', 'form'),
            'nav.date.nudge_forward': KeyBinding('nav.date.nudge_forward', 'Ctrl+Right', 'Nudge +1 day', 'date'),
            'nav.date.nudge_backward': KeyBinding('nav.date.nudge_backward', 'Ctrl+Left', 'Nudge -1 day', 'date'),
            'nav.date.nudge_week_forward': KeyBinding('nav.date.nudge_week_forward', 'Ctrl+Up', 'Nudge +7 days', 'date'),
            'nav.date.nudge_week_backward': KeyBinding('nav.date.nudge_week_backward', 'Ctrl+Down', 'Nudge -7 days', 'date'),
            'app.save': KeyBinding('app.save', 'Ctrl+S', 'Save', 'global'),
            'app.toggle_theme': KeyBinding('app.toggle_theme', 'Ctrl+T', 'Toggle theme', 'global'),
            'app.refresh': KeyBinding('app.refresh', 'F5', 'Refresh', 'global'),
            'app.find': KeyBinding('app.find', 'Ctrl+F', 'Find', 'global'),
            'app.cancel': KeyBinding('app.cancel', 'Escape', 'Cancel', 'global'),
            'app.shortcuts': KeyBinding('app.shortcuts', 'Ctrl+/', 'Shortcuts reference', 'global'),
            'edit.undo': KeyBinding('edit.undo', 'Ctrl+Z', 'Undo', 'edit'),
            'edit.redo': KeyBinding('edit.redo', 'Ctrl+Y', 'Redo', 'edit'),
            'nav.list.open': KeyBinding('nav.list.open', 'Enter', 'Open unit', 'list'),
            'nav.list.delete': KeyBinding('nav.list.delete', 'Delete', 'Delete unit', 'list'),
            'nav.list.toggle_detail': KeyBinding('nav.list.toggle_detail', '+', 'Toggle detail', 'list'),
        }
    
    def activate_context(self, context: str):
        """Activate a keyboard context (e.g., 'list', 'form', 'date')."""
        self._active_contexts.add(context)
    
    def deactivate_context(self, context: str):
        """Deactivate a keyboard context."""
        self._active_contexts.discard(context)
    
    def handle_key_event(self, event: QKeyEvent) -> bool:
        """Process a key event. Returns True if handled."""
        if self._search_mode:
            if event.key() == 16777216:  # Qt.Key_Escape
                self._search_mode = False
                self.shortcut_triggered.emit('app.cancel')
                return True
            # Pass through for search text input
            return False
        
        key_text = self._event_to_shortcut(event)
        
        # Try exact match first, then by context
        binding = self._find_binding(key_text)
        if binding:
            if self._is_context_valid(binding.context):
                self.shortcut_triggered.emit(binding.config_key)
                return True
        
        return False
    
    def _event_to_shortcut(self, event: QKeyEvent) -> str:
        """Convert a QKeyEvent to a shortcut string for matching."""
        parts = []
        if event.modifiers() & event.modifiers():
            if event.modifiers() & 67108864:  # Qt.ControlModifier
                parts.append('Ctrl')
            if event.modifiers() & 134217728:  # Qt.ShiftModifier
                parts.append('Shift')
            if event.modifiers() & 268435456:  # Qt.AltModifier
                parts.append('Alt')
        
        key = event.key()
        # Handle special keys
        key_map = {
            16777220: 'Enter', 16777221: 'Return',
            16777223: 'Tab', 16777216: 'Escape',
            16777234: 'Left', 16777235: 'Up',
            16777236: 'Right', 16777237: 'Down',
            16777249: 'Home', 16777250: 'End',
            16777251: 'Delete', 16777264: 'F5',
        }
        
        if key in key_map:
            key_name = key_map[key]
        elif 65 <= key <= 90:  # A-Z
            key_name = chr(key)
        elif 48 <= key <= 57:  # 0-9
            key_name = chr(key)
        else:
            key_name = chr(key) if 32 <= key <= 126 else ''
        
        if parts:
            return '+'.join(parts + [key_name])
        return key_name
    
    def _find_binding(self, key_text: str) -> Any:
        """Find a binding by shortcut text."""
        for binding in self._bindings.values():
            if binding.shortcut == key_text:
                return binding
        return None
    
    def _is_context_valid(self, context: str) -> bool:
        """Check if a context is active."""
        if context == 'global':
            return True
        return context in self._active_contexts
    
    def get_all_bindings(self) -> list[tuple[str, str, str]]:
        """Return all bindings as (shortcut, description, context) list."""
        return [(b.shortcut, b.description, b.context) for b in self._bindings.values()]
    
    def save_custom_bindings(self, custom_map: dict[str, str]):
        """Save custom keybindings to config.yaml."""
        config = {}
        if os.path.exists(self._config_path):
            with open(self._config_path, 'r') as f:
                config = yaml.safe_load(f) or {}
        
        config['keybindings'] = custom_map
        with open(self._config_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
        
        # Reload bindings
        self._load_bindings()
```

### Quick Search Widget

```python
# gui/quick_search.py

from PyQt5.QtWidgets import QLineEdit, QCompleter, QListView
from PyQt5.QtCore import Qt, pyqtSignal


class QuickSearchBar(QLineEdit):
    """Overlay search bar for instant filtering."""
    
    search_changed = pyqtSignal(str)  # current filter text
    search_next = pyqtSignal()
    search_prev = pyqtSignal()
    search_closed = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText("Search... (type to filter, Enter for next, Shift+Enter for prev)")
        self.setClearButtonEnabled(True)
        self.textChanged.connect(self.search_changed.emit)
        
        # Style as an overlay
        self.setStyleSheet("""
            QLineEdit {
                border: 2px solid #4a90d9;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 14px;
                background-color: palette(window);
            }
        """)
    
    def keyPressEvent(self, event):
        if event.key() == 16777220:  # Enter
            if event.modifiers() & 134217728:  # Shift
                self.search_prev.emit()
            else:
                self.search_next.emit()
            return
        elif event.key() == 16777216:  # Escape
            self.clear()
            self.search_closed.emit()
            return
        
        super().keyPressEvent(event)
    
    def showEvent(self, event):
        super().showEvent(event)
        self.setFocus()
        self.selectAll()
```

### Date Field Nudging

```python
# gui/date_nudge.py

from PyQt5.QtWidgets import QDateEdit
from PyQt5.QtCore import Qt, QDate


class NudgeableDateEdit(QDateEdit):
    """Date field that supports keyboard nudge (Ctrl+Arrow)."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCalendarPopup(True)
    
    def keyPressEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            if event.key() == Qt.Key_Right:
                self._nudge_days(1)
                return
            elif event.key() == Qt.Key_Left:
                self._nudge_days(-1)
                return
            elif event.key() == Qt.Key_Up:
                self._nudge_days(7)
                return
            elif event.key() == Qt.Key_Down:
                self._nudge_days(-7)
                return
        super().keyPressEvent(event)
    
    def _nudge_days(self, days: int):
        current = self.date()
        new_date = current.addDays(days)
        self.setDate(new_date)
```

### Shortcut Reference Dialog

```python
# gui/shortcut_dialog.py

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QTableWidget,
                              QTableWidgetItem, QHeaderView, QLabel,
                              QPushButton, QHBoxLayout)
from PyQt5.QtCore import Qt


class ShortcutReferenceDialog(QDialog):
    """Keyboard shortcut reference dialog (Ctrl+/)."""
    
    def __init__(self, keyboard_manager, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Keyboard Shortcuts")
        self.setMinimumSize(500, 400)
        self.setModal(True)
        
        layout = QVBoxLayout(self)
        
        # Header
        header = QLabel("<b>Keyboard Shortcuts</b> — "
                        "Customize bindings in <code>config.yaml</code> under <code>keybindings:</code>")
        header.setWordWrap(True)
        layout.addWidget(header)
        
        # Table
        table = QTableWidget()
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(["Shortcut", "Action", "Context"])
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setAlternatingRowColors(True)
        
        bindings = keyboard_manager.get_all_bindings()
        # Sort by context then shortcut
        bindings.sort(key=lambda b: (b[2], b[0]))
        
        table.setRowCount(len(bindings))
        for i, (shortcut, desc, context) in enumerate(bindings):
            table.setItem(i, 0, QTableWidgetItem(shortcut))
            table.setItem(i, 1, QTableWidgetItem(desc))
            table.setItem(i, 2, QTableWidgetItem(context))
        
        layout.addWidget(table)
        
        # Close button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)
```

### Config.yaml Keybindings Section

```yaml
# config.yaml keybindings section
keybindings:
  # Override defaults with custom shortcuts
  nav.list.down: "j"
  nav.list.up: "k"
  nav.list.top: "gg"
  nav.list.bottom: "G"
  nav.search.quick: "/"
  nav.search.next: "n"
  nav.search.prev: "N"
  app.save: "Ctrl+S"
  app.toggle_theme: "Ctrl+T"
  app.refresh: "F5"
  app.find: "Ctrl+F"
  app.cancel: "Escape"
  app.shortcuts: "Ctrl+/"
  edit.undo: "Ctrl+Z"
  edit.redo: "Ctrl+Y"
  nav.date.nudge_forward: "Ctrl+Right"
  nav.date.nudge_backward: "Ctrl+Left"
  nav.date.nudge_week_forward: "Ctrl+Up"
  nav.date.nudge_week_backward: "Ctrl+Down"
  nav.list.open: "Enter"
  nav.list.delete: "Delete"
  nav.list.toggle_detail: "+"
```

---

## Integration with MainWindow

```python
# In MainWindow.__init__():

self.keyboard_manager = KeyboardManager(config_path='config.yaml')

# Connect signals
self.keyboard_manager.shortcut_triggered.connect(self._handle_shortcut)

# Install event filter on central widget
self.centralWidget().installEventFilter(self)

# Global shortcuts via QShortcut
QShortcut(QKeySequence("Ctrl+/"), self, self._show_shortcuts_dialog)
QShortcut(QKeySequence("/"), self, self._enter_quick_search)
```

---

## Search Mode Flow

```
User presses /
    │
    ▼
Show QuickSearchBar overlay (centered, top of list)
    │
    ▼
User types filter text
    │
    ▼
List/Alert view filters to matching items in real-time
    │
    ▼
User presses Enter → jump to next match
User presses Shift+Enter → jump to previous match
User presses Escape → close search, restore unfiltered view
```

---

## Implementation Phases

### Phase 1: Core Navigation (2 days)
1. Implement `KeyboardManager` with context system and config loading
2. Implement j/k navigation in list and alert views
3. Implement gg/G for top/bottom
4. Wire KeyboardManager into MainWindow event handling
5. **Tests**: Test all navigation movements with programmatic key events

### Phase 2: Advanced Features (2 days)
1. Implement QuickSearchBar overlay with `/` key binding
2. Implement n/N search result cycling
3. Implement NudgeableDateEdit with Ctrl+Arrow support
4. Implement ShortcutReferenceDialog with Ctrl+/
5. Implement Tab traversal in form fields with logical ordering
6. Implement config.yaml save/load for custom keybindings
7. **Tests**: Test search filtering, date nudging, and custom binding persistence

---

## Success Criteria

1. j/k navigation works in all list and alert views with smooth scrolling
2. `/` quick search filters 10,000+ items with <100ms latency
3. gg/G correctly jumps to first/last item regardless of scroll position
4. n/N cycles through search results with visual highlight
5. Ctrl+Arrow nudges date fields by correct increments
6. Tab order follows logical left-to-right, top-to-bottom field layout
7. Custom keybindings in config.yaml override defaults immediately
8. Ctrl+/ shows complete shortcut reference with all current bindings

---

## Risk Assessment

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Keybinding conflicts with OS or Qt built-in shortcuts | Medium | Reserve global shortcuts; document known conflicts; allow unbinding |
| Search performance with large datasets | Low | Debounce input (150ms); use incremental filter with cancellation |
| Vim-style gg conflicts with typing in form fields | Medium | Context system deactivates list navigation when form fields are focused |
| Users unaware of new shortcuts | Low | Show Ctrl+/ reference; add onboarding tooltip for first-time users |

---

## Effort Estimate

| Phase | Days |
|-------|------|
| Phase 1: Core Navigation | 2 |
| Phase 2: Advanced Features | 2 |
| **Total** | **4** |
