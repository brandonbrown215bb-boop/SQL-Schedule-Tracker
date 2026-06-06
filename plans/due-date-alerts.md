# Plan: Due Date Alert System

## Current State

- 2,765 units in `schedule.db`
- 2,718 units have `detailing_due_date` in the past — but the vast majority are historical data (2021-2023 era), not current misses
- Only **47 units** have due dates within the next 30 days (4 within 7d, 12 within 8-14d, 8 within 15-30d, 23 beyond 30d)
- `build_date` exists for 2,762 units — 54 have build dates BEFORE the detailing due date (schedule conflict)
- `status_color` is uniformly `"gray"` across all 2,765 units — the computed color feature is non-functional
- Detailers carry massive overdue backlogs (Tanner D: 218 overdue / 12,296 hrs, Katie D: 199 / 8,117 hrs, etc.)

## Problem

There is no way to distinguish **real, current schedule risk** from **historical data noise**. A detailer opening the app sees 2,000+ "overdue" units and the signal is meaningless. The alert system needs to:

1. Filter out stale/historical data so only actionable items surface
2. Flag genuine schedule conflicts (build date vs. detailing due date)
3. Show per-detailer workload vs. capacity for upcoming due dates
4. Integrate with the existing `status_color` system (currently broken — everything is gray)

## Approach

### Phase 1: Data Freshness Filter

Add a `is_active` computed property to `Unit` that filters out historical/stale units:

```python
@property
def is_active(self) -> bool:
    """True if this unit represents current, actionable work."""
    # Units with due dates more than 90 days in the past are historical
    if self.detailing_due_date and self.detailing_due_date < date.today() - timedelta(days=90):
        return False
    # Units that are fully complete (100% + completion date) are done
    if self.percent_complete >= 1.0 and self.unit_detailing_completion_date:
        return False
    return True
```

This cuts the noise from 2,718 "overdue" to only units that are genuinely at risk in the current window.

### Phase 2: Alert Classification

Each active unit gets an alert level based on due date proximity and build date conflict:

| Level | Condition | Color |
|-------|-----------|-------|
| `CRITICAL` | Build date ≤ detailing due date (impossible schedule) | 🔴 Red |
| `OVERDUE` | Past due date, not complete | 🟠 Orange |
| `URGENT` | Due within 7 days | 🟡 Yellow |
| `APPROACHING` | Due within 14 days | 🔵 Blue |
| `ON_TRACK` | Due > 14 days out, no conflicts | 🟢 Green |
| `COMPLETE` | 100% done or past completion date | ⚪ Gray |

This replaces the current `status_color` system which is hardcoded to `"gray"`.

### Phase 3: Build Date Conflict Detection

For units where `build_date` exists:

```python
@property
def build_date_gap(self) -> int | None:
    """Days between detailing due date and build date.
    Negative = build ships before detailing finishes (conflict)."""
    if self.build_date and self.detailing_due_date:
        return (self.build_date - self.detailing_due_date).days
    return None

@property
def has_build_conflict(self) -> bool:
    gap = self.build_date_gap
    return gap is not None and gap <= 3  # 0-3 days is tight/impossible
```

54 units currently have negative gaps (build before due). 14 more have 0-3 day gaps. These 68 units are your fire drills.

### Phase 4: Per-Detailer Alert Dashboard

A new panel (or tab) showing:

```
┌─────────────────────────────────────────────────────┐
│  ALERTS — Katie D                                   │
├─────────────────────────────────────────────────────┤
│  🔴 CRITICAL (Build Conflict)                       │
│     COM 14201 — due 06/08, build 06/09 (1d gap)    │
│     COM 14202 — due 06/10, build 06/10 (0d gap)   │
│                                                     │
│  🟠 OVERDUE                                         │
│     COM 14197 — due 05/28 (8d overdue)             │
│     COM 14196 — due 05/30 (6d overdue)             │
│                                                     │
│  🟡 URGENT (Due within 7 days)                      │
│     COM 14212 — due 06/07 (2d), 45% complete       │
│     COM 14213 — due 06/09 (4d), 12% complete       │
│                                                     │
│  Workload: 331 dept hrs due within 14d              │
│  Capacity: ~40 hrs/week → ⚠️ OVERLOADED            │
└─────────────────────────────────────────────────────┘
```

### Phase 5: Calendar Integration

The existing calendar (`calendar_panel.py`) only shows `detailing_due_date`. Extend to:
- Color-code dates by alert level (red dot = conflict, orange = overdue, yellow = urgent)
- Show build dates as a separate layer (toggle on/off)
- Click a date → filter list panel to units due that day

## Files Changed

| File | Change |
|------|--------|
| `data/models.py` | Add `is_active`, `alert_level`, `build_date_gap`, `has_build_conflict` properties |
| `gui/alert_panel.py` | New file — per-detailer alert dashboard widget |
| `gui/calendar_panel.py` | Color-code by alert level, add build date layer |
| `gui/main_window.py` | Add alert panel as new tab, wire up navigation |
| `gui/edit_form.py` | Show alert badge on units with conflicts |
| `data/db.py` | Add `status_color` column migration (persist computed colors) |

## Verification

1. Run `is_active` filter — confirm historical units are excluded from alerts
2. Verify alert classification: manually check 20 units against their due/build dates
3. Confirm build date conflict detection catches all 68 tight-gap units
4. Test calendar color-coding renders correctly in both light and dark themes
5. Verify per-detailer dashboard loads in < 1s with 2,765 units

## Open Questions

1. **What's the right "stale" threshold?** 90 days past due? 180? Should it be configurable?
2. **Should completed units (100%) ever show as overdue?** Currently they'd still flag — maybe suppress alerts for ≥100% complete?
3. **Capacity modeling** — what's a detailer's weekly hour capacity? Is it uniform (40 hrs) or per-detailer? This affects the overload calculation.
4. **Alert delivery** — in-app only, or also Discord/email notifications for critical conflicts?
5. **Build date confidence** — are build dates reliable? 54 negative-gap units could be data errors, not real conflicts.
