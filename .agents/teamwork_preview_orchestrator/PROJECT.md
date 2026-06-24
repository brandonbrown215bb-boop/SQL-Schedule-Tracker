# Project: SQL-Schedule-Tracker Codebase Audit

## Architecture
- **UI Layer (`gui/`)**: PyQt5 widgets displaying schedule tables, calendars, edit forms, etc.
- **Service Layer (`services/`)**: Pure Python business logic wrapper around SQLite storage, import/export operations, conflict resolution, configuration parsing, validation rules.
- **Data & Model Layer (`data/`)**: Unit data class, raw SQL queries, data loader with identicals logic, data writer with optimistic concurrency checks.
- **Sync/Locking Layer (`sync/`)**: Lock manager, revision store, session registry, and shared cache.

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|---|---|---|---|
| 1 | Setup & Verification | Initial setup of plan.md, progress.md, and cron timer | None | DONE |
| 2 | Codebase Audit (Exploration) | Spawn 3 Explorer agents to inspect different layers (gui: d6afef10, services/data: 1eee6a7d, sync: a7265562) | M1 | DONE |
| 3 | Reproducing Tests | Write `tests/test_audit_findings.py` to reproduce identified bugs/pitfalls (Worker: 00428774) | M2 | DONE |
| 4 | Audit Report | Generate `AUDIT_REPORT_2026.md` summarizing findings (Worker: 00428774) | M2 | DONE |
| 5 | Review & Verification | Run Reviewers (eaa5c69a, 9687af7e), Challengers (87f69519, 647163aa), and Auditor 2 (a369a14d) | M3, M4 | DONE |
| 6 | Completion Handoff | Report findings back to the parent agent | M5 | DONE |

## Interface Contracts
- Tests in `tests/test_audit_findings.py` must run with `pytest tests/test_audit_findings.py` and fail when bugs are present.
- `AUDIT_REPORT_2026.md` must be placed at the project root.
- No modifications to files in `data/`, `gui/`, `services/`, `sync/`, `automation/`, and `main.py`.

## Code Layout
- `.agents/teamwork_preview_orchestrator/`: Agent metadata (plan.md, progress.md, BRIEFING.md, PROJECT.md)
- `tests/test_audit_findings.py`: Reproducing unit tests
- `AUDIT_REPORT_2026.md`: Detailed audit report
