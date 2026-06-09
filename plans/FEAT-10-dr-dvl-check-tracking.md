# FEAT-10: DR/DVL Check Tracking

**Status**: NOT STARTED  
**Priority**: Low  
**Effort**: Small  

## Objective

Track whether Design Review (DR) and Design Verification Letter (DVL) checks have been completed for each unit, providing visibility into procedural compliance.

## Background

The `dr_checks` and `dvl_checks` columns already exist in the DB schema and are exported to Excel (columns AE and AF). They store free-text status strings (e.g., "Done", "Pending", "N/A"). However, they're not displayed in the UI.

## Schema

| Column | Type | Purpose |
|--------|------|---------|
| `dr_checks` | TEXT | Design Review check status |
| `dvl_checks` | TEXT | Design Verification Letter check status |

## Proposed Implementation

### 1. Add fields to Unit dataclass

```python
dr_checks: str = ""
dvl_checks: str = ""
```

### 2. Load from DB

In `row_to_unit()`:

```python
dr_checks=row["dr_checks"] or "",
dvl_checks=row["dvl_checks"] or "",
```

### 3. Persist on save

In `save_unit()`, add both fields to the UPDATE statement.

### 4. Add to edit form

Add two `QLineEdit` fields in the "Identity Fields" section (or a new "Checksheet" section).

### 5. Add to list panel

Add columns (default hidden):

```python
("dr_checks", "DR Check", 60, False),
("dvl_checks", "DVL Check", 60, False),
```

## Files to Modify

1. `data/models.py` — Add `dr_checks`, `dvl_checks`
2. `data/db.py` — Load in `row_to_unit()`
3. `data/writer.py` — Persist in `save_unit()`
4. `gui/edit_form.py` — Add form fields
5. `gui/list_panel.py` — Add column definitions

## Testing

1. DR/DVL values load and display correctly
2. Editing and saving persists changes
3. List panel columns sort and filter correctly