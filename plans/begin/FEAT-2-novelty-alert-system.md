# FEAT-2: Novelty Alert System

**Status**: NOT STARTED  
**Priority**: Medium  
**Effort**: Medium  

## Objective

When a unit is assigned to a detailer, flag if the unit's type or feature combination is new to that detailer — enabling early identification of training needs or unfamiliar work.

## Background

The `UnitTagRepository` and `DetailerExperience` classes already have the infrastructure:
- `DetailerExperience.has_done_unit_type(unit_type)` — checks if detailer has done this type before
- `DetailerExperience.has_done_features(features)` — checks if all features have been used
- `UnitTagRepository.is_novel_for_detailer(unit)` — returns `(is_novel, reasons)`
- The description tags column already shows a ✦ indicator for novel units

The novelty detection works for the currently selected unit via `_compute_tags_display()` in `list_panel.py`. But there's no dedicated UI for surfacing novelty across all units.

## Proposed Implementation

### Phase 1 — Novelty badge in list panel

The ✦ indicator already exists in the tags column. Enhance it:
- Make the ✦ symbol colored (gold for unit type novelty, blue for feature novelty)
- Add a tooltip showing what's novel: "New unit type: O)3" or "New feature(s): VFD"
- Add a column filter: "Show only novel units" checkbox

### Phase 2 — Novelty summary dialog

Create `gui/novelty_dialog.py` showing all novel assignments across all detailers:

```
┌─────────────────────────────────────────────┐
│ Novelty Alerts                              │
├─────────────────────────────────────────────┤
│ Brandon B — New feature: VFD on COM 12345  │
│ Jane Smith — New unit type: RTF on COM 9876│
│ John Doe — New combo: CAMFIL+LAU on COM 5432
└─────────────────────────────────────────────┘
```

### Phase 3 — Notification on assignment

When a detailer is changed in the edit form and the new assignment includes novel features, show a popup:

```
⚠ New for Jane Smith: This unit type (RTF) has not been done by Jane before.
```

This uses `UnitTagRepository.is_novel_for_detailer()` with the new detailer name.

## Data Layer

`UnitTagRepository.is_novel_for_detailer(unit, detailer)` already returns `(bool, list[str])`. No new infrastructure needed.

## UI Changes

1. `gui/list_panel.py` — Enhanced novelty indicator (colored, tooltip)
2. `gui/list_panel.py` — "Show novel only" filter checkbox
3. `gui/novelty_dialog.py` — New file, novelty summary dialog
4. `gui/edit_form.py` — Confirmation popup when detailer is changed to a novel assignment
5. `gui/main_window.py` — Menu item to open novelty dialog

## Edge Cases

- **Detailer has no history**: Show "No prior work found for this detailer" (already handled)
- **Unit has no features**: Novelty is based solely on unit type
- **Frequent novelty false positives**: If every unit is "novel" (new detailer with no history), the feature may be noisy — consider showing only after N units assigned

## Testing

1. Assign a unit with VFD to a detailer who has never done VFD → Novelty indicator shows
2. Change detailer to one who has done VFD → Indicator disappears
3. Novelty dialog lists all novel assignments sorted by detailer
4. Assignment confirmation popup appears on detailer change in edit form