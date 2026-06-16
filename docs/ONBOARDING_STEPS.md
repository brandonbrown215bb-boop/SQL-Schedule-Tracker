# Onboarding Walkthrough — Step Reference

> **Last updated:** 2026-06-15
> **File:** `gui/onboarding.py`

The onboarding walkthrough is a first-launch (and replayable) step-by-step
overlay that highlights each major UI area and explains its purpose in one
short paragraph. It is skippable and replayable via *Help → Show Walkthrough*.

---

## Step overview (15 steps)

| # | Widget target | Title | What it captures |
|---|---|---|---|
| 1 | `calendar_panel` | Calendar & List & Alerts | Three views for browsing units: Calendar (dates with dots), List (sortable table with filters), and Alerts (per-detailer urgency dashboard). Switch via toggle buttons above. |
| 2 | `view_stack` | View Toggle Buttons | Toggle between Calendar, List, and Alerts views. Active view is saved between sessions. List view includes COM search, detailer/status/date filters, stale-unit toggle. |
| 3 | `calendar_view_btn` | Calendar View | Color-coded dots on dates with units due. Click a date to see its units below. Dots are color-coded by status (green/red/yellow/purple/orange). Stale units (>30 days past due) hidden by default. |
| 4 | `list_view_btn` | List View | Sortable table with multi-column filtering: status, detailer, date presets (overdue/today/next 7-30 days/month), custom date range, COM search, alert-level filter. Column widths resizable. Right-click context menus. Ctrl+F jumps to COM search. |
| 5 | `alerts_view_btn` | Alerts View | Per-detailer alert dashboard grouping units by urgency: Overdue (red), Urgent (≤7 days, orange), Approaching (≤14 days, yellow), On Track (blue/green). Checking-surge detection and capacity warnings. Tag-based novelty detection. |
| 6 | `timeline_panel` | Unit Timeline | Horizontal milestone bar chart. Shows Detailing Start, Moved to Checking, Detailing Complete, Dept Due (prev), Detailing Due. Bar fill reflects computed status: green=100%, orange=95-99%, purple=90-94%, yellow=1-89%, gray=0%, red=overdue/behind. Capacity-based logic (remaining hours vs. available working days). |
| 7 | `edit_form` | Edit Form | All 18 fields: COM (read-only), job name, contract, description, detailer, checking status, notes, dept/target/IEC hours, % complete, actual hours, 6 dates. Ctrl+S to save. Background saves, dirty tracking, auto-computed target hours, non-primary identical read-only. |
| 8 | `theme_btn` | Theme & Accessibility | Light/dark theme toggle (Ctrl+T). ♿ button for CVD modes (protanopia/deuteranopia/tritanopia) and high-contrast mode. Preference saved automatically. |
| 9 | `pull_csv_btn` | Import CSV | Import CSV from SSRS into SQLite. File picker, upsert by COM number, auto-refresh after import. |
| 10 | `pull_ssrs_btn` | Pull SSRS (Online Import) | Fetch from SSRS ReportServer endpoint (config.yaml). Configurable lookback/lookahead date ranges. Upsert into SQLite, auto-refresh. |
| 11 | `refresh_btn` | Refresh from SQLite | Reload all unit data from SQLite. 3-second cooldown. F5 shortcut. Auto-refresh on external file changes (file watcher). |
| 12 | `export_btn` | Export to Excel | Export SQLite contents to 'Current List' sheet of Excel workbook (.xlsm/.xlsx). Reconciles with shared team workbook. |
| 13 | `status_bar` | Status Bar | Loading progress, save confirmations, unit count, sync status. Auto-reloads on external DB changes. Multi-user presence indicator (click for session details). |
| 14 | `menuBar` | Reports & Help Menus | Reports menu → Scheduling Dashboard (segmented bar charts, PNG export, date-range filter). Help menu → replay walkthrough, About dialog. |
| 15 | `left_panel` | Keyboard Shortcuts | Ctrl+S = Save, Ctrl+T = Theme, F5 = Refresh, Ctrl+F = COM search, Escape = Clear selection. Arrow-key navigation and context menus in list view. |

---

## Feature coverage matrix

The walkthrough now covers every major user-facing feature in the application:

### Viewing & browsing
- [x] Calendar view with color-coded status dots and date-click event listing
- [x] List view with sortable columns, multi-filter bar, COM search, context menus
- [x] Alerts view with per-detailer urgency grouping and capacity warnings
- [x] View toggle and preference persistence
- [x] Stale-unit filtering (past-due >30 days)

### Editing & saving
- [x] Edit form with all 18 fields
- [x] Dirty tracking and unsaved-changes confirmation
- [x] Ctrl+S keyboard shortcut
- [x] Background save with status-bar feedback
- [x] Auto-computed target hours for identical units
- [x] Non-primary identical read-only logic

### Status & timeline
- [x] Timeline panel with 5 milestones and status-colored bar
- [x] Capacity-based status logic (remaining hours vs. working days)
- [x] Six status colors: gray, yellow, purple, orange, green, red

### Data import & export
- [x] CSV file import with file picker
- [x] SSRS online import (ReportServer endpoint)
- [x] Excel workbook export
- [x] SQLite refresh with cooldown

### Multi-user sync
- [x] Presence indicator in status bar
- [x] Session details popup
- [x] Optimistic locking with conflict dialog (overwrite/reload/cancel)
- [x] Due date change detection and notification dialog

### Accessibility & theming
- [x] Dark/light theme toggle
- [x] Color-vision-deficiency modes (protanopia, deuteranopia, tritanopia)
- [x] High-contrast mode
- [x] WCAG AA-compliant status colors

### Automation & background processes
- [x] File-system watcher with auto-reload on external DB changes
- [x] Auto-refresh timer (configurable interval)
- [x] Background load/save workers (QThread)
- [x] Error dialog throttling
- [x] Loading overlay during data loads
- [x] Close-with-sync progress dialog

### Menus & navigation
- [x] Reports menu → Scheduling Dashboard (charts, PNG export)
- [x] Help menu → Show Walkthrough, About
- [x] Keyboard shortcuts: Ctrl+S, Ctrl+T, F5, Ctrl+F, Escape

### Configuration
- [x] Config persistence (debounced YAML write)
- [x] Splitter size persistence
- [x] Last-view preference persistence
- [x] Theme, CVD, high-contrast persistence

---

## Technical details

### Widget lookup mechanism

Each step references a widget by its `objectName` property. The overlay uses
`QWidget.findChild(QWidget, widget_name)` to locate the target. If the widget
is not found or not visible, the callout is centered on screen.

### All required objectNames

The following widgets must have `setObjectName()` called for the onboarding
to find and highlight them:

| objectName | Widget | Set in |
|---|---|---|
| `calendar_panel` | CalendarPanel | `gui/calendar_panel.py` |
| `view_stack` | QStackedWidget | `gui/main_window.py` |
| `calendar_view_btn` | QPushButton | `gui/main_window.py` |
| `list_view_btn` | QPushButton | `gui/main_window.py` |
| `alerts_view_btn` | QPushButton | `gui/main_window.py` |
| `timeline_panel` | TimelinePanel | `gui/timeline_panel.py` |
| `edit_form` | EditForm | `gui/edit_form.py` |
| `theme_btn` | QPushButton | `gui/main_window.py` |
| `pull_csv_btn` | QPushButton | `gui/main_window.py` |
| `pull_ssrs_btn` | QPushButton | `gui/main_window.py` |
| `refresh_btn` | QPushButton | `gui/main_window.py` |
| `export_btn` | QPushButton | `gui/main_window.py` |
| `status_bar` | QStatusBar | `gui/main_window.py` |
| `menuBar` | QMenuBar | `gui/main_window.py` |
| `left_panel` | QWidget | `gui/main_window.py` |

### Callout positioning

Each step specifies a `position` (top, bottom, left, right) indicating where
the callout appears relative to the highlighted widget. If the widget is not
visible (e.g., alerts view is not the active stacked-widget page), the callout
is centered as a fallback.

### Persistence

On completion, `config["ui"]["onboarding_completed"] = True` is set and the
config is debounced-written to `config.yaml`. `should_show_onboarding()`
checks this flag and returns `False` on subsequent launches.

### Replay

Replayable via *Help → Show Walkthrough* in the menu bar, which calls
`show_onboarding(self, self.config)` unconditionally (the completion flag is
only written on completion, not checked before showing from the menu).