# Execution Plan — SQL-Schedule-Tracker Codebase Audit

This plan outlines the steps to perform a codebase audit, generate the report, and write reproducing tests without modifying source files.

## Step-by-Step Implementation & Verification

### Step 1: Initial Setup and Planning
- Initialize orchestrator context, planning, and PROJECT.md documents.
- Verify existing tests can run in the environment.

### Step 2: Codebase Exploration
- Spawn `teamwork_preview_explorer` agents to perform a comprehensive audit of:
  - Logical and functional bugs in services, data loading, database schema/queries, tag parsing, etc.
  - Graphical UX errors in PySide/PyQt UI panels (`gui/*`).
  - Data integrity pitfalls (e.g., SQLite sync, optimistic locking, capacity checks).
- Identify specific file paths, line numbers, and potential fixes.

### Step 3: Reproducing Test Development
- Spawn a `teamwork_preview_worker` to write reproducing unit tests inside `tests/test_audit_findings.py`.
- The tests should demonstrate at least two identified bugs/pitfalls and fail *before* those issues are resolved. Since we are not allowed to fix the codebase, the tests must compile, run, and fail as expected.
- Verify `pytest tests/test_audit_findings.py` runs and correctly asserts the failures without other errors.

### Step 4: Audit Report Generation
- Spawn a `teamwork_preview_worker` to write `AUDIT_REPORT_2026.md` at the project root.
- The report will include:
  - Table of contents.
  - Categorization of issues: Logical/Functional, Graphical UX, Data Integrity.
  - For each issue: Severity (High/Medium/Low), File path & Line numbers, Description, Reproducibility/Evidence, Recommended fix.

### Step 5: Verification & Review
- Spawn `teamwork_preview_reviewer` and `teamwork_preview_challenger` to review `AUDIT_REPORT_2026.md` and `tests/test_audit_findings.py`.
- Run forensic auditor to verify that:
  - Source files in `data/`, `gui/`, `services/`, `sync/`, `automation/`, and `main.py` were NOT modified.
  - The tests run and verify genuine bugs.
- Verify that E2E or unit tests compile.

### Step 6: Finalization & Handoff
- Present the final report structure and test suite status to the user.
- Complete final orchestrator state documentation and reports.
