# Plan: Due Date Alert System

## Current State

- 2,765 units in `schedule.db`
- 2,718 units have `detailing_due_date` in the past — but the vast majority are historical data (2021-2023 era), not current misses
- Only **47 units** have due dates within the next 30 days (4 within 7d, 12 within 8-14d, 8 within 15-30d, 23 beyond 30d)
- `status_color` is uniformly `"gray"` across all 2,765 units — the computed color feature is non-functional
- Detailers carry massive overdue backlogs (Tanner D: 218 overdue / 12,296 hrs, Katie D: 199 / 8,117 hrs, etc.)

## Problem

There is no way to distinguish **real, current schedule risk** from **historical data noise**. A detailer opening the app sees 2,000+ "overdue" units and the signal is meaningless. The alert system needs to:

1. Filter out stale/historical data so only actionable items surface
2. Classify remaining units by urgency (overdue → urgent → approaching → on track → complete)
3. Show per-detailer workload vs. capacity for upcoming due dates
4. Integrate with the existing `status_color` system (currently broken — everything is gray)

## Design Decisions

| # | Question | Decision |
|---|----------|----------|
| 1 | Stale threshold | **30 days** — units with due dates >30 days past are hidden by default, toggle to show |
| 2 | 100% complete units | **Never overdue** — `percent_complete >= 1.0` suppresses all alert levels → COMPLETE |
| 3 | Weekly capacity | **40 hrs/week** uniform (four 10s). No per-detailer config. |
| 4 | Alert delivery | **In-app only** — the app runs as individual .exe copies from a shared work directory, so email/Discord push isn't feasible |
| 5 | Build dates | **Removed from alert logic** — build dates don't matter to detailing, only the due date drives alerts |

## Approach

### Phase 1: Data Freshness Filter

Add a `is_stale` property to `Unit`. Stale units are hidden by default but toggleable:

```python
STALE_THRESHOLD_DAYS = 30

@property
def is_stale(self) -> bool:
    """True if this unit's due date is more than 30 days in the past."""
    if self.detailing_due_date:
        return self.detailing_due_date < date.today() - timedelta(days=STALE_THRESHOLD_DAYS)
    return False
```

**UI:** Checkbox in list panel toolbar — "Show stale data" (unchecked by default). When unchecked, stale units are excluded from alerts, calendar, and list view. When checked, they render dimmed with strikethrough text.

This cuts the noise from 2,718 "overdue" to a manageable set of current actionable units.

### Phase 2: Alert Classification

Each non-stale unit gets an alert level based on due date proximity:

| Level | Condition | Color |
|-------|-----------|-------|
| `OVERDUE` | Past due date, < 100% complete | 🟠 Orange |
| `URGENT` | Due within 0–7 days, < 100% complete | 🟡 Yellow |
| `APPROACHING` | Due within 8–14 days, < 100% complete | 🔵 Blue |
| `ON_TRACK` | Due > 14 days out, < 100% complete | 🟢 Green |
| `COMPLETE` | `percent_complete >= 1.0` | ⚪ Gray |
| `UNSET` | No due date | ⚪ Gray |

This replaces the current `status_color` which is hardcoded to `"gray"` everywhere. The computed property feeds both the UI color and the list panel's conditional formatting.

```python
@property
def alert_level(self) -> str:
    if self.percent_complete >= 1.0:
        return "COMPLETE"
    if not self.detailing_due_date:
        return "UNSET"
    days_until = (self.detailing_due_date - date.today()).days
    if days_until < 0:
        return "OVERDUE"
    if days_until <= 7:
        return "URGENT"
    if days_until <= 14:
        return "APPROACHING"
    return "ON_TRACK"
```

### Phase 3: Status Color Sync

Replace the hardcoded `status_color="gray"` in `row_to_unit()` with the computed `alert_level`:

```python
# In row_to_unit():
unit.status_color = computed_alert_level  # from the property above
```

This makes the existing `status_color` field functional for the first time. The column persists on reload (fixing IMP-2 from the code review).

### Phase 4: Per-Detailer Alert Dashboard

A new panel showing alerts grouped by detailer:

```
┌─────────────────────────────────────────────────────┐
│  ALERTS — Katie D                                   │
├─────────────────────────────────────────────────────┤
│  🟠 OVERDUE                                         │
│     COM 14197 — due 05/28 (8d overdue), 60% done   │
│     COM 14196 — due 05/30 (6d overdue), 30% done   │
│                                                     │
│  🟡 URGENT (Due within 7 days)                      │
│     COM 14212 — due 06/07 (2d), 45% complete       │
│     COM 14213 — due 06/09 (4d), 12% complete       │
│                                                     │
│  🔵 APPROACHING (Due within 14 days)                │
│     COM 14215 — due 06/15 (10d), 0% complete       │
│                                                     │
│  ── Summary ──                                      │
│  Overdue: 2 units, 156 dept hrs remaining           │
│  Due within 7d: 2 units, 180 dept hrs              │
│  Capacity: 40 hrs/week                              │
│  Status: ⚠️ OVERLOADED (336 hrs / 40 per week)     │
└─────────────────────────────────────────────────────┘
```

Capacity calculation:
- `remaining_hours = SUM(department_hours * (1 - percent_complete))` for units due within window
- `weekly_capacity = 40` (uniform, no per-detailer config)
- `weeks_of_work = remaining_hours / 40`
- Status: UNDER (< 2 wks), BALANCED (2–4 wks), OVERLOADED (> 4 wks)

### Phase 5: Calendar Integration

Extend `calendar_panel.py`:
- Color-code due date dots by alert level (🟠 overdue, 🟡 urgent, 🔵 approaching, 🟢 on track)
- Click a date → filter list panel to units due that day
- "Show stale data" toggle controls whether stale dates appear

### Phase 6: List Panel Integration

- Alert level column (or color-coded row background) in the main unit list
- "Show stale data" checkbox in toolbar
- Alert filter dropdown: "All" / "Overdue" / "Urgent" / "Approaching" / "In Range"
- Overdue units sort to top when stale data is hidden

## Files Changed

| File | Change |
|------|--------|
| `data/models.py` | Add `is_stale`, `alert_level` properties |
| `data/db.py` | Persist `status_color` from computed `alert_level` in `row_to_unit()` |
| `gui/alert_panel.py` | New file — per-detailer alert dashboard widget |
| `gui/calendar_panel.py` | Color-code by alert level, click-to-filter |
| `gui/list_panel.py` | Add stale toggle, alert filter, alert column/colors |
| `gui/main_window.py` | Add alert panel as new tab, wire up navigation |
| `gui/edit_form.py` | Show alert badge/indicator on units with active alerts |

## Verification

1. Verify `is_stale` correctly identifies units >30 days past due
2. Confirm 100% complete units always show COMPLETE regardless of due date
3. Check alert classification against manual spot-checks (20+ units)
4. Test stale toggle — hidden units reappear when checked
5. Verify per-detailer dashboard capacity math against known workloads
6. Test calendar color-coding in both light and dark themes
7. Confirm `status_color` persists correctly after reload
8. Performance: alert panel loads < 1s with 2,765 units
