# FEAT-12: Identical Unit Management

**Status**: NOT STARTED  
**Priority**: Low  
**Effort**: Medium  

## Objective

Provide UI for managing groups of identical units — viewing all members of a group, identifying the primary, and adjusting target hours.

## Background

The `_apply_identicals()` function in `loader.py` already identifies units that share the same `contract_number` (order number) and forces non-primary units to have `target_department_hours = 0.0`. The `is_non_primary_identical` flag is set on these units. BUG-3 was recently fixed so the edit form updates after reload when identicals are recalculated.

However, there's no UI to:
- See which units belong to the same identical group
- Identify which unit is the primary
- Manually override the identical grouping

## Schema

| Column | Purpose |
|--------|---------|
| `contract_number` | Order number — used to group identicals |
| `target_department_hours` | 0 for non-primary identicals |
| `is_non_primary_identical` | Flag set by `_apply_identicals` |
| `same_as` | Free-text "same as" field (exported to Excel column AD) |

## Proposed Capabilities

### 1. Identical group visualization

In the list panel, add a visual indicator for identical groups:
- Rows in the same group share a subtle background tint (alternating between 2-3 colors)
- Tooltip: "Identical group: order #12345 (3 units)"
- Group number shown as a new column

### 2. Identical group dialog

When clicking a unit that is in an identical group, show the group details:

```
┌─────────────────────────────────────────────┐
│ Identical Group — Order #12345              │
├──────────┬──────────┬───────┬───────────────┤
│ COM      │ Due Date │ Hours │ Role          │
├──────────┼──────────┼───────┼───────────────┤
│ 12345    │ 6/15     │ 40    │ ⭐ Primary    │
│ 12346    │ 6/20     │  0    │ Non-primary   │
│ 12347    │ 6/25     │  0    │ Non-primary   │
└─────────────────────────────────────────────┘
```

### 3. Primary reassignment

Allow the user to change which unit is the primary (the one with non-zero target hours). This updates `_apply_identicals()` in the in-memory list and persists on save.

### 4. Break identical relationship

Allow removing a unit from an identical group (sets `is_non_primary_identical = False` and restores normal target hour calculation).

## Data Layer

Add to `data/loader.py` or new `data/identical_manager.py`:

```python
def get_identical_group(contract_number: str, units: list[Unit]) -> list[Unit]:
    """Return all units sharing a contract number, sorted by due date."""
    return sorted(
        [u for u in units if u.contract_number == contract_number],
        key=lambda u: u.detailing_due_date or date.max
    )

def set_primary_unit(contract_number: str, new_primary_com: str, units: list[Unit]) -> None:
    """Reassign the primary within an identical group and reapply rules."""
    group = get_identical_group(contract_number, units)
    for u in group:
        u.is_non_primary_identical = u.com_number != new_primary_com
        u.target_department_hours = u.department_hours - u.iec_internal_hours if u.com_number == new_primary_com else 0.0
```

## Files to Create/Modify

1. `data/identical_manager.py` — New module
2. `gui/list_panel.py` — Group tinting and column
3. `gui/identical_group_dialog.py` — New dialog
4. `gui/edit_form.py` — "View group" button for identicals

## Testing

1. Three units sharing contract_number → all show as group in list panel
2. Primary unit has non-zero target hours, others have 0
3. Changing primary correctly redistributes target hours
4. Breaking relationship restores normal hour calculation

## Dependencies

- BUG-3 fix (already complete) ensures edit form reflects identicals changes after reload