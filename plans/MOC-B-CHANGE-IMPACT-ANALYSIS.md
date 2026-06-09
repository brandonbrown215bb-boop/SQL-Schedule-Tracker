# MOC-B: Change Impact Analysis

**Status**: PROPOSED
**Priority**: High
**Effort**: Medium-Large
**MOC Principle**: Before a change is finalized, show what else is affected

## Problem

When a user makes a change — reassigning a detailer, pushing a due date, updating hours — the app saves it instantly with no analysis of downstream consequences. The capacity warnings and surge detection exist but only show up passively in the alerts panel, after the fact.

Real scenarios where this causes pain:

1. **Due date push**: Jane has 10 units due next week. Her manager pushes all their due dates back 2 weeks. Now the capacity warnings disappear, but the checker still has 10 units landing on the same day. There's no "this will create a checking surge" warning at the point of change.

2. **Detailer reassignment**: John is over capacity (180h). His manager reassigns 5 units to Jane. Jane is now at 175h. The reassignment dialog doesn't show "Jane will be over capacity after this change."

3. **Cascade due date change**: Pushing a unit's due date might push it past another unit's due date in the same contract group. No warning is shown.

4. **Checking bottleneck**: Changing a unit from "not in checking" to "in checking" frees up the 4-day checking overhead reserve, which changes the capacity calculus for all units assigned to that detailer. No re-analysis is triggered.

The existing `calculated_status_color` capacity check is computed per-unit at read time. It's never used as a *pre-save validation* signal.

## Proposed Implementation

### Phase 1 — Pre-Save Impact Preview

Add an `ImpactAnalyzer` class that, before saving a unit change, computes:

```python
class ImpactAnalyzer:
    """Pre-save impact analysis for unit changes."""

    def analyze_detailer_change(
        self, unit: Unit, new_detailer: str, all_units: list[Unit]
    ) -> ImpactReport:
        """
        Returns:
            - Old detailer's new capacity (hours remaining after removing this unit)
            - New detailer's new capacity (hours remaining after adding this unit)
            - Whether new detailer crosses the 160h threshold
            - Whether any units change status_color due to recalculation
        """

    def analyze_due_date_change(
        self, unit: Unit, new_due_date: date, all_units: list[Unit]
    ) -> ImpactReport:
        """
        Returns:
            - Whether the unit's status_color changes (e.g., from red to green)
            - Whether this creates a checking surge (>=3 units due same day)
            - Whether this creates a contract cascade (other units in same
              contract_group now have earlier due dates than this one)
            - Capacity impact: how many working days changed
        """

    def analyze_hours_change(
        self, unit: Unit, new_hours: float, all_units: list[Unit]
    ) -> ImpactReport:
        """
        Returns:
            - Whether this pushes the detailer over capacity threshold
            - Whether the unit's status_color changes
        """
```

When the user clicks Save in the edit form, if the change touches detailer/due_date/hours, show a non-blocking notification banner *before* the save completes:

```
┌─────────────────────────────────────────────────────┐
│ ⚠ Impact: Moving COM 20091 to Jane Smith will push │
│ Jane to 178h (over 160h threshold).                │
│                                                     │
│ 3 other units assigned to Jane will change from     │
│ ON_TRACK to CRITICAL due to recalculation.          │
│                                                     │
│ [Save Anyway]  [Cancel]  [View Details]            │
└─────────────────────────────────────────────────────┘
```

This is a *warning*, not a block — the user can proceed. But they can't say they didn't know.

### Phase 2 — Batch Impact Preview

For IMP-13 (Batch Operations), show the aggregate impact before applying:

```
┌─────────────────────────────────────────────────────┐
│ Batch Impact — 12 units will be affected            │
├─────────────────────────────────────────────────────┤
│ • 2 detailers will cross capacity threshold         │
│ • 1 checking surge will be created (6/25: 5 units)  │
│ • 3 units will change status (2 yellow→red, 1 red→gray) │
│ • No contract cascade conflicts                     │
│                                                     │
│ [Apply Batch]  [Cancel]  [View Affected Units]     │
└─────────────────────────────────────────────────────┘
```

### Phase 3 — Post-Save Change Ripple

After saving, automatically refresh the alerts panel and highlight units whose status_color changed as a result. Add a transient notification:

```
Saved COM 20091. 3 other units' status changed due to capacity recalculation.
[View Changes]
```

## Files to Create/Modify

1. `data/impact_analyzer.py` — New module, `ImpactAnalyzer` class with pre-save analysis methods
2. `gui/edit_form.py` — Hook into save flow: call `ImpactAnalyzer` before `save_unit()`, show warning banner if impacts detected
3. `gui/batch_edit_dialog.py` (from IMP-13) — Add impact preview before applying batch
4. `gui/main_window.py` — Post-save ripple notification + refresh propagation
5. `gui/impact_report_dialog.py` — New file, detailed impact breakdown viewer

## Edge Cases

- **Minor changes**: If the impact is trivial (no thresholds crossed, no status changes), don't show any warning — just save silently. Avoid alert fatigue.
- **Chain reactions**: Changing one unit's due date changes its status, which changes the capacity calculation for other units (because checking overhead is reserved differently). The analysis should account for this two-hop effect.
- **Performance**: Impact analysis iterates over all units assigned to affected detailers. With 2,765 units and 15 detailers, this is ~184 units per detailer on average — fast enough for synchronous analysis.
- **False positives**: The capacity model is an approximation (10 hrs/day, 4-day checking overhead). Users will learn to treat warnings as guidance, not gospel.

## Pros

- **Prevents surprises** — users see consequences before committing changes
- **Capacity-aware reassignments** — no more accidentally overloading a detailer
- **Cascade detection** — catches contract-level due date conflicts early
- **Surge prevention** — warns before creating a checking bottleneck
- **Non-blocking** — warnings inform but don't prevent; experienced users can override
- **Batch safety** — batch operations get an aggregate impact view before committing
- **Leverages existing calculations** — uses `calculated_status_color` logic already in the codebase; no new algorithms needed

## Cons

- **Pre-save latency** — analysis runs synchronously before save; with 2,765 units, could add 50-200ms to save time (acceptable for single edits, noticeable for batches)
- **Model accuracy** — the capacity model is approximate; warnings may be wrong for edge cases (users on non-standard schedules, units with unusual hour distributions)
- **Alert fatigue threshold** — if too many changes trigger warnings, users will click through without reading. The "minor change" filter is critical.
- **UI complexity** — adds a new dialog/panel to the save flow. Must be well-designed to not feel like a speed bump.
- **Chain reaction visibility** — two-hop effects (unit A's change affects unit B's status which affects unit C's capacity) are computationally expensive to trace and may be missed by a simple analyzer
- **Not a substitute for review** — this is analysis, not approval. It tells you what *might* happen, not whether the change *should* happen.

## Dependencies

- IMP-13 (Batch Operations) for Phase 2 batch impact preview
- Existing `calculated_status_color` logic (no new algorithms)
- MOC-A (Change Audit Trail) — impact analysis complements the audit trail: one warns before, the other records after
