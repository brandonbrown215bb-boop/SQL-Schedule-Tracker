# MOC-C: Change Review & Approval Workflow

**Status**: PROPOSED
**Priority**: Medium
**Effort**: Large
**MOC Principle**: Significant changes require review before they take effect

## Problem

Currently, any user can make any change and it goes straight to the database. There is no review step for high-impact changes. The ConflictDialog only handles concurrent edits, not sequential review.

## Proposed Implementation

### Phase 1 - Change Classification

Define change severity levels based on what field changed and magnitude:

| Field Changed | Low | Medium | High | Critical |
|---|---|---|---|---|
| Notes | Always | - | - | - |
| Percent complete | < 10% delta | 10-25% | > 25% | - |
| Due date shift | < 3 days | 3-7 days | >= 7 days | - |
| Detailer | - | Any single | - | Batch |
| Department hours | - | +/-10h | > +/-10h | - |
| Status color override | - | - | Any | - |
| Batch operations | - | - | - | Always |

### Phase 2 - Review Queue

HIGH and CRITICAL changes go to a change_reviews table instead of directly to units. The unit shows a pending change indicator. Reviewers get notified.

### Phase 3 - Review UI

Change Reviews panel: list pending changes with approve/reject/diff/view-impact. Approved changes flow to units + change_log. Rejected changes discarded.

### Phase 4 - Roles

detailer (propose LOW/MEDIUM), lead (propose HIGH, approve LOW/MEDIUM), admin (all). Configurable in config.yaml.

### Phase 5 - Agentic Review Assistant (Stretch)

Automated briefing per pending change: impact summary, pattern detection, business rule checks. Not auto-approve - a briefing for the human reviewer.

## Pros

- Second pair of eyes on high-impact changes
- Accountability via reviewer attribution
- Gradual rollout: classify first, block later
- Agentic augmentation makes review faster
- Integrates with MOC-A and MOC-B

## Cons

- Workflow friction - threshold gaming (7 x 1-day shifts to avoid 7-day review)
- Requires multiple users to be effective
- Threshold calibration is arbitrary, needs tuning
- UI complexity: new panel, dialog, indicators, banners
- May not fit small-shop culture - MOC-A and MOC-B may be sufficient

## Recommendation

Start with Phase 1 (classification + logging, no blocking). Collect 2 weeks of data, tune thresholds, then enable the blocking queue for HIGH/CRITICAL only.
