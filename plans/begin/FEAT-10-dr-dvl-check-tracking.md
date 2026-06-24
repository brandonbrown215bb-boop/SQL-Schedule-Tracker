# FEAT-10: DR/DVL Check Tracking

**Status**: IMPLEMENTED
**Priority**: Medium
**Effort**: Small

## Objective

Track whether Design Review (DR) and Design Verification Letter (DVL) checks have been completed for each unit, providing visibility into procedural compliance.

## Implementation

### Status Enum

Three states per field, stored as integers in the DB:
- `0` = Pending (amber/yellow badge)
- `1` = Done (green badge)
- `2` = N/A (gray badge)

Default: `0` (Pending)

### Schema

Two new columns added via ALTER TABLE migration in `data/db.py`:
- `dr_check_status INTEGER DEFAULT 0`
- `dvl_check_status INTEGER DEFAULT 0`

### Files Modified

1. **`data/models.py`** — Added `dr_check_status: int = 0` and `dvl_check_status: int = 0` to Unit dataclass
2. **`data/db.py`** — ALTER TABLE migration + read in `row_to_unit()`
3. **`data/writer.py`** — Added both fields to UPDATE statement in `save_unit()`
4. **`gui/edit_form.py`** — New "Checksheet" section with two QComboBox fields (Pending/Done/N/A), wired to dirty tracking and save
5. **`gui/list_panel.py`** — Two new column definitions (default hidden), badge rendering with theme-aware colors, sortable

### UI

- **Edit Form**: "Checksheet" section between Identity and Numeric fields, with DR Check and DVL Check dropdowns
- **List Panel**: "DR Check" and "DVL Check" columns (default hidden), rendered as colored badges (amber/green/gray)

## Testing

All 376 existing tests pass. Manual verification:
- DR/DVL values load and display correctly in edit form and list panel
- Editing and saving persists changes to database
- List panel columns sort correctly
- Badge colors render correctly in both light and dark themes
