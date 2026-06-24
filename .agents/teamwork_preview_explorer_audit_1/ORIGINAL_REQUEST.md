## 2026-06-24T13:57:43Z
Objective: Perform a comprehensive audit of the SQL-Schedule-Tracker codebase to identify logical and functional bugs.
Scope Focus: Services and Data/Models logic (e.g. services/unit_service.py, services/config_service.py, data/db.py, data/loader.py, data/models.py, services/validation.py, services/sanitizer.py, services/pre_save_hooks.py, data/tag_parser.py).
Scope Boundaries: Do NOT modify any files in active source directories. This is a read-only exploration task. Do not design graphical UI fixes or examine UI elements unless it relates to logical bugs in the underlying services.
Input Information:
- Global project layout and configuration details are in config.yaml and AGENTS.md.
- Source code resides in services/, data/, and other directories.
- Previous test cases reside in tests/.
Output Requirements:
- Generate a detailed handoff report as `handoff.md` in your working directory.
- In `handoff.md`, list logical/functional bugs you find, specifying the file path, approximate line numbers, severity (High/Medium/Low), description of the issue, and recommendations for a fix.
Completion Criteria:
- A thorough read-only analysis of the services and data layers is completed.
- A complete `handoff.md` is written to your working directory.
- Send a message to the parent orchestrator (conversation ID 5261a668-12ec-4cdd-9c1c-1d5fc79896ea) notifying them of completion and referencing the handoff.md path.
