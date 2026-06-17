# ARCH-002: Centralized State Management

**Status**: Draft  
**Priority**: High  
**Effort**: L (2-3 weeks)  
**Depends on**: ARCH-001  
**Required by**: IMP-016 (Undo/Redo), FEAT-021 (Audit Trail), IMP-020 (Customizable Dashboard)  

---

## Problem Statement

Application state is scattered across `MainWindow` as 30+ instance variables:

```python
# Current state (MainWindow.__init__)
self.units: list[Unit] = []           # All loaded units
self.current_unit: Unit | None = None  # Selected unit
self._form_dirty: bool = False         # Edit form dirty flag
self._pending_save_unit: Unit | None   # Save queue
self._sync_status_session_total: int = 0
self._sync_status_session_initial: int = 0
self._sync_unit_durations: list[float] = []
self._error_dialog_count = 0
self._error_dialog_window_start = 0.0
# ... and 20+ more
```

This leads to:
- **Implicit state dependencies** — changing one variable can break unrelated features
- **No change notification** — panels poll or re-render everything on every refresh
- **No transaction support** — partial updates leave UI in inconsistent state
- **No history** — undo/redo impossible without complete rewrite
- **No serialization** — can't save/restore app state between sessions

---

## Proposed Solution

Introduce a **centralized Application State Store** using the Observer pattern (pub/sub). All state mutations go through the store, which emits typed events that widgets subscribe to. This enables:

1. **Predictable state flow** — one source of truth
2. **Granular change notification** — only affected widgets re-render
3. **Undo/redo** — implemented as a command history stack on the store
4. **State persistence** — serialize/deserialize store for session restore
5. **Time-travel debugging** — log all state changes for development (like Redux DevTools)

### Architecture

```
┌──────────────────────────────────────────────┐
│              ApplicationStore                 │
│  ┌────────────────────────────────────────┐  │
│  │            State (dataclass)            │  │
│  │  ┌──────────┐ ┌──────────┐ ┌────────┐ │  │
│  │  │ Units    │ │ UI Prefs │ │ Sync   │ │  │
│  │  │          │ │ (theme,  │ │ (locks,│ │  │
│  │  │          │ │ filters, │ │ revs,  │ │  │
│  │  │          │ │ view)    │ │ sess.) │ │  │
│  │  └──────────┘ └──────────┘ └────────┘ │  │
│  └────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────┐  │
│  │           Command History              │  │
│  │  [cmd1, cmd2, ..., cmdN] (undo stack) │  │
│  │  [redo1, redo2, ..., redoN] (redo)    │  │
│  └────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────┐  │
│  │        Event Bus (Observer)            │  │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐  │  │
│  │  │UnitsChgd│ │UIConfig │ │SaveDone │  │  │
│  │  │  Event  │ │  Event  │ │  Event  │  │  │
│  │  └─────────┘ └─────────┘ └─────────┘  │  │
│  └────────────────────────────────────────┘  │
└──────────────────────────────────────────────┘
```

### Store Design

```python
# services/store.py
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable
from data.models import Unit


@dataclass
class UIState:
    theme: str = "light"
    cvd_mode: str = "none"
    high_contrast: bool = False
    last_view: str = "calendar"
    splitter_sizes: list[int] = field(default_factory=lambda: [1434, 1102])
    list_sort_column: str = "detailing_due_date"
    list_sort_ascending: bool = True
    list_visible_columns: list[str] = field(default_factory=lambda: [
        "com_number", "detailing_due_date", "job_name", "detailer", "status_color", "percent_complete"
    ])
    list_column_widths: dict[str, int] = field(default_factory=dict)
    onboarding_completed: bool = False


@dataclass
class SyncState:
    enabled: bool = False
    owner_id: str = ""
    active_sessions: list = field(default_factory=list)
    pending_saves: int = 0
    save_blocked: bool = False


@dataclass
class AppState:
    units: list[Unit] = field(default_factory=list)
    current_unit: Unit | None = None
    form_dirty: bool = False
    io_busy: bool = False
    last_error: str | None = None
    ui: UIState = field(default_factory=UIState)
    sync: SyncState = field(default_factory=SyncState)


class StateChange:
    """Immutable change record for event bus and undo log."""
    def __init__(self, path: str, old_value: Any, new_value: Any,
                 metadata: dict | None = None): ...


EventHandler = Callable[[StateChange], None]


class EventBus:
    """Typed pub/sub with async dispatch."""
    def on(self, event_type: str, handler: EventHandler) -> None: ...
    def off(self, event_type: str, handler: EventHandler) -> None: ...
    def emit(self, change: StateChange) -> None: ...


class Command:
    """Undoable action."""
    def execute(self, store: 'ApplicationStore') -> None: ...
    def undo(self, store: 'ApplicationStore') -> None: ...
    @property
    def description(self) -> str: ...


class ApplicationStore:
    """Central state store with event bus and undo/redo."""
    
    def __init__(self):
        self._state = AppState()
        self._bus = EventBus()
        self._undo_stack: list[Command] = []
        self._redo_stack: list[Command] = []
        self._history: list[StateChange] = []  # audit log
    
    @property
    def state(self) -> AppState:
        return self._state
    
    def dispatch(self, command: Command) -> None:
        """Execute a command and record it in undo stack."""
        command.execute(self)
        self._undo_stack.append(command)
        self._redo_stack.clear()  # new branch
    
    def undo(self) -> None:
        if self._undo_stack:
            cmd = self._undo_stack.pop()
            cmd.undo(self)
            self._redo_stack.append(cmd)
    
    def redo(self) -> None:
        if self._redo_stack:
            cmd = self._redo_stack.pop()
            cmd.execute(self)
            self._undo_stack.append(cmd)
    
    def set(self, path: str, value: Any, metadata: dict | None = None) -> None:
        """Direct state mutation (for non-undoable changes like view switching)."""
        old = self._get_path(path)
        self._set_path(path, value)
        change = StateChange(path, old, value, metadata)
        self._history.append(change)
        self._bus.emit(change)
    
    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        self._bus.on(event_type, handler)
```

### Event Types

```python
# Event type constants
EVENT_UNITS_LOADED = "units:loaded"
EVENT_UNIT_SELECTED = "unit:selected"
EVENT_UNIT_SAVED = "unit:saved"
EVENT_UNIT_CHANGED = "unit:changed"  # external modification detected
EVENT_UI_THEME_CHANGED = "ui:theme"
EVENT_UI_VIEW_CHANGED = "ui:view"
EVENT_UI_FILTER_CHANGED = "ui:filter"
EVENT_IO_BUSY = "io:busy"
EVENT_ERROR = "error"
EVENT_SYNC_PRESENCE = "sync:presence"
EVENT_SYNC_CONFLICT = "sync:conflict"
```

### Widget Integration

```python
# In each widget that subscribes to state:
store.subscribe(EVENT_UNITS_LOADED, self._on_units_loaded)
store.subscribe(EVENT_UNIT_SELECTED, self._on_unit_selected)
store.subscribe(EVENT_UI_THEME_CHANGED, self._on_theme_changed)

# Instead of direct method calls:
# OLD: self.calendar_panel.refresh(self.units)
# NEW:
store.dispatch(SelectUnitCommand(unit))
```

### Example Commands

```python
class SelectUnitCommand(Command):
    def __init__(self, unit: Unit | None):
        self.unit = unit
        self._previous: Unit | None = None
    
    def execute(self, store: ApplicationStore) -> None:
        self._previous = store.state.current_unit
        store.state.current_unit = self.unit
        store._bus.emit(StateChange("current_unit", self._previous, self.unit))
    
    def undo(self, store: ApplicationStore) -> None:
        store.state.current_unit = self._previous
        store._bus.emit(StateChange("current_unit", self.unit, self._previous))
    
    @property
    def description(self) -> str:
        return f"Select {self.unit.com_number if self.unit else 'none'}"


class SaveUnitCommand(Command):
    def __init__(self, service: UnitService, unit: Unit):
        self.service = service
        self.unit = unit
        self._saved_unit: Unit | None = None
    
    def execute(self, store: ApplicationStore) -> None:
        self._saved_unit = self.service.save(self.unit, self.unit.updated_at)
        store.state.units = [
            self._saved_unit if u.com_number == self.unit.com_number else u
            for u in store.state.units
        ]
        store._bus.emit(StateChange("units", None, store.state.units))
    
    def undo(self, store: ApplicationStore) -> None:
        # Revert to pre-save state (requires DB rollback or reverse write)
        raise NotImplementedError("Save undo requires DB reverse operation")
    
    @property
    def description(self) -> str:
        return f"Save COM {self.unit.com_number}"
```

---

## Implementation Phases

### Phase 1: Core Store + Event Bus (3 days)
1. Implement `ApplicationStore`, `EventBus`, `StateChange` classes
2. Implement `AppState`, `UIState`, `SyncState` dataclasses
3. Write unit tests for state mutation, event emission, subscription patterns

### Phase 2: Command Pattern + Undo/Redo (3 days)
1. Implement `Command` base class with `execute`/`undo`
2. Implement undo stack and redo stack in store
3. Implement `SelectUnitCommand`, `SetFieldCommand`, `BatchEditCommand`
4. **Tests**: verify undo/redo correctness, stack limits, memory bounds

### Phase 3: Widget Migration (5 days)
1. Create store singleton in `MainWindow` init
2. Migrate `CalendarPanel` to subscribe to store events
3. Migrate `ListPanel` to subscribe to store events
4. Migrate `EditForm` to subscribe to store events
5. Migrate `TimelinePanel` to subscribe to store events
6. Migrate `AlertPanel` to subscribe to store events

### Phase 4: State Persistence (2 days)
1. Add serialize/deserialize to `AppState` (JSON)
2. Save state on app close, restore on startup
3. **Tests**: round-trip serialization fidelity

---

## Success Criteria

1. All state mutations go through `ApplicationStore` — zero direct instance var writes
2. All panel refreshes are driven by store subscriptions — zero manual `refresh()` calls
3. Undo/redo works for selection, field edits, and view changes
4. State persists across app restarts (UI prefs, last view, column widths)
5. Store has > 90% test coverage

---

## Risk Assessment

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Event storms during bulk load | Medium | Debounce/throttle events; batch updates |
| Memory growth from undo stack | Low | Cap at 100 commands; serialize to temp on overflow |
| Widget migration regressions | Medium | Each migration phase followed by full regression test |
| Dev complexity of Command pattern | Low | Well-understood pattern; examples in architecture doc |

---

## Effort Estimate

| Phase | Days |
|-------|------|
| Phase 1: Core Store | 3 |
| Phase 2: Command Pattern | 3 |
| Phase 3: Widget Migration | 5 |
| Phase 4: State Persistence | 2 |
| **Total** | **13** |