# Handoff Report — GUI and UX Audit Findings

This handoff report presents a comprehensive audit of the SQL-Schedule-Tracker graphical user interface and user experience layers (PyQt5). It lists all identified layout issues, style/theme glitches, event wiring bugs, accessibility/contrast problems, and dialog errors, along with precise locations, severities, and recommended fixes.

---

## Catalog of Identified GUI/UX Issues

### 1. Silent Thread Save Discard in Batch Edit (Concurrency/Functional Bug)
* **File Path**: `gui/main_window.py` (approx. lines 744–764) & `gui/batch_edit_dialog.py` (approx. lines 119–147)
* **Severity**: **High**
* **Description**:
  In `BatchEditDialog._apply()`, the dialog loops through all selected units and emits the `unit_saved` signal for each one. This signal is wired to `MainWindow.on_save_unit()`, which calls `_start_save_worker(unit)`. 
  Inside `_start_save_worker()`, the code checks if a save worker is already running:
  ```python
  if self._active_save_worker_running():
      logger.warning("Save already in progress — queuing")
      return
  ```
  Since the batch edit loop runs almost instantly on the GUI thread, the first worker is spawned, and all subsequent units in the loop immediately trigger the `isRunning()` condition. They log a warning saying "queuing" but **immediately return without queuing or saving**. Consequently, only the first selected unit in a batch edit is actually saved; the rest are silently ignored.
* **Recommendation**:
  Implement a proper FIFO queue for saves in `MainWindow`. Instead of immediately returning, add the unit to a list queue (e.g., `self._save_queue: list[Unit]`). When a save worker finishes, the `_on_save_finished` handler should check if there are pending units in the queue and trigger the next worker.

### 2. Invalid Field Stylesheet Override Clears Custom Theme (Theme/Style Glitch)
* **File Path**: `gui/edit_form.py` (line 27 & lines 343–346)
* **Severity**: **Medium**
* **Description**:
  When performing input validation, `EditForm._validate_fields()` resets styles by setting the stylesheet of input fields to `_VALID_STYLE = ""`. 
  ```python
  self.percent_spin.setStyleSheet(_VALID_STYLE)
  self.dept_hours_spin.setStyleSheet(_VALID_STYLE)
  ...
  ```
  Setting a widget's stylesheet to `""` clears any stylesheet applied to it. This erases the stylesheet applied by the global `apply_theme()` function (defined in `gui/theme.py`), causing the spin boxes and date inputs to revert to the default OS stylesheet/colors (e.g., light gray background even when the app is in Dark Theme).
* **Recommendation**:
  Instead of clearing the stylesheet completely with `""`, re-apply the standard input theme stylesheet for the active theme when a field becomes valid. Alternatively, use Qt property selectors in a single stylesheet (e.g., `QLineEdit[invalid="true"] { border: 2px solid red; }`) and call `widget.setProperty("invalid", True)` followed by `widget.style().unpolish(widget)` and `widget.style().polish(widget)`.

### 3. Contrast/Readability Violations for Invalid Fields in Dark Theme (Accessibility)
* **File Path**: `gui/edit_form.py` (line 26)
* **Severity**: **High**
* **Description**:
  The invalid field style is hardcoded to:
  ```python
  _INVALID_STYLE = "border: 2px solid red; background-color: #fff0f0;"
  ```
  This forces a light pink background (`#fff0f0`) on the input field. However, it does not set a foreground/text color. In Dark Theme, the text color is inherited as near-white (`#f1f5f9`). This results in almost white text on a light pink background, which has a very low contrast ratio and violates WCAG contrast guidelines, rendering the text completely unreadable.
* **Recommendation**:
  Update `_INVALID_STYLE` to explicitly specify a dark text color (e.g., `color: #1e293b;`) to ensure contrast against the light pink background, or make the invalid style theme-aware (e.g., a dark red background with light red text in Dark Theme).

### 4. Contrast/Readability Violations in Conflict Dialog (Accessibility)
* **File Path**: `gui/conflict_dialog.py` (lines 119–120)
* **Severity**: **High**
* **Description**:
  When showing differences in the Conflict Dialog, cells that differ are highlighted with a light yellow background:
  ```python
  item_local.setBackground(QColor("#fef9c3"))
  item_remote.setBackground(QColor("#fef9c3"))
  ```
  In Dark Theme, the table text color is light (almost white). Since no foreground color is set on these highlighted cells, the user sees white text on a light yellow background.
* **Recommendation**:
  Calculate contrast dynamically or set a dark text color on highlighted cells:
  ```python
  item_local.setForeground(QBrush(QColor("#1e293b")))
  item_remote.setForeground(QBrush(QColor("#1e293b")))
  ```

### 5. Contrast/Readability Violations in Import Preview Dialog (Accessibility)
* **File Path**: `gui/import_preview_dialog.py` (lines 85, 95, 122)
* **Severity**: **High**
* **Description**:
  The dialog creates custom clickable rows for diff categories with hardcoded light background colors (new: `QColor(220, 255, 220)`, updated: `QColor(255, 255, 200)`, errors: `QColor(255, 220, 220)`). However, it never sets the text color of the labels (`com_label` and `status_label`) in these rows. In Dark Theme, they inherit white text, resulting in unreadable white text on light pastel backgrounds. Furthermore, this dialog does not call `apply_theme()` at all, bypassing the styling pipeline.
* **Recommendation**:
  Call `apply_theme(self, theme_name)` in the constructor and ensure text labels inside row widgets have their text colors set to dark (e.g., `#1e293b`) for maximum readability on light background swatches.

### 6. TimelineWidget Hardcoded Light Colors in Dark Theme (Theme/Accessibility)
* **File Path**: `gui/timeline_panel.py` (lines 152, 223, 227, 236–237, 243, 257, 279)
* **Severity**: **High**
* **Description**:
  The custom `paintEvent` of `TimelineWidget` hardcodes light background colors and dark text/line colors:
  * Line 152: `painter.fillRect(self.rect(), QBrush(QColor(252, 252, 255)))` (forces white background)
  * Line 223: `painter.fillRect(..., QColor(237, 240, 248))` (light alternating row background)
  * Lines 243, 257: Text colors are hardcoded to dark gray/black (`QColor(20, 20, 20)` and `QColor(80, 80, 100)`)
  In Dark Theme, this widget stands out as a jarring, high-glare white box with dark text, completely breaking the dark UI theme.
* **Recommendation**:
  Retrieve background and text colors dynamically from the active theme tokens:
  ```python
  tokens = THEMES[self._theme_name]
  bg_color = QColor(tokens["bg_secondary"])
  text_color = QColor(tokens["text_primary"])
  ```
  Replace all hardcoded drawing pens and brushes with these theme variables.

### 7. Lack of Visual Checked State for View Toggle Buttons (UX Issue)
* **File Path**: `gui/theme.py` (line 234) & `gui/main_window.py` (lines 411–426)
* **Severity**: **Medium**
* **Description**:
  The view toggle buttons (Calendar, List, Alerts) in `MainWindow` are checkable buttons (`setCheckable(True)`). They are styled using `_BTN_DEFAULT` stylesheet.
  However, the `_BTN_DEFAULT` stylesheet does not define a `QPushButton:checked` pseudoclass. When a view button is selected (checked), it has the exact same visual style as the unchecked buttons, offering no visual feedback on which panel is active.
* **Recommendation**:
  Add a `:checked` state to the `_BTN_DEFAULT` stylesheet template in `gui/theme.py` that styles checked buttons with the theme's active selection colors:
  ```css
  QPushButton:checked {
      background: {bg_selected};
      border-color: {accent};
      font-weight: bold;
  }
  ```

### 8. Sync Status Widget is Dead UI Code (Implementation Bug)
* **File Path**: `gui/main_window.py` (lines 303–305) & `gui/sync_status.py`
* **Severity**: **Medium**
* **Description**:
  `SyncStatusWidget` is instantiated and placed in the status bar of `MainWindow` during initialization. However, `set_progress()` is never called anywhere in the codebase. As a result, the progress bar is never updated, remains invisible (`setVisible(False)` is set in the widget's constructor), and serves no purpose.
* **Recommendation**:
  Connect the background worker saves to update this widget. In `MainWindow._start_save_worker`, set the progress, and in `_on_save_finished`, decrement and update. If no saves are running, hide the widget.

### 9. Broken Close ETA Tracking (UX Issue)
* **File Path**: `gui/main_window.py` (lines 242–244, 1541–1543)
* **Severity**: **Medium**
* **Description**:
  When closing the application while save workers are running, a modal `CloseProgressDialog` is shown. It queries `self._avg_unit_seconds()` to calculate the ETA.
  However, `self._sync_unit_durations` is initialized to `[]` and never populated. `self._sync_status_session_total` and `self._sync_status_session_initial` are also initialized to `0` and never updated. As a result, `_avg_unit_seconds()` always returns `0.0`, causing the close dialog to display a static `Estimated time remaining: …` (three dots) instead of a real estimate.
* **Recommendation**:
  Record the start time when a save worker begins (`self._current_unit_save_started_at = time.monotonic()`) and calculate the duration in `_on_save_finished()`, appending the elapsed seconds to `self._sync_unit_durations`. Also increment `_sync_status_session_total` and `_sync_status_session_initial` appropriately when saving.

### 10. Audit Dialog Populating & Sorting Race (Performance/UI Glitch)
* **File Path**: `gui/audit_dialog.py` (line 100 & lines 139–141)
* **Severity**: **Medium**
* **Description**:
  In `AuditDialog.__init__`, `self.table.setSortingEnabled(True)` is called. Immediately after, `self._load_data()` is executed, which loops through entries and calls `self._set_table_row()`.
  Calling `setSortingEnabled(True)` before populating a `QTableWidget` causes Qt to run its sorting algorithm every time `setItem()` is called. This degrades performance significantly (especially with up to 1000 history entries), freezing the UI. Furthermore, it can shuffle the row indices during insertion, leading to mismatched cell values.
* **Recommendation**:
  Disable sorting during population:
  ```python
  self.table.setSortingEnabled(False)
  for row, entry in enumerate(entries):
      self._set_table_row(row, entry)
  self.table.setSortingEnabled(True)
  ```

### 11. Stale Search Match Selection (State Bug)
* **File Path**: `gui/main_window.py` (lines 360–396)
* **Severity**: **Low**
* **Description**:
  Clearing the search input box via backspace/clear button calls `_on_global_search()`. Since the text query is empty, `_on_global_search()` returns early.
  However, it does not clear `self._search_single_match`. If the user hits "Enter" after clearing the search box, `_on_search_entered()` is triggered, which selects the stale matched unit and populates the form, even though the search field is blank.
* **Recommendation**:
  If the query is empty in `_on_global_search()`, set `self._search_single_match = None` before returning.

### 12. Misleading Target Save Warning on Local Validation Failure (UX Misdirection)
* **File Path**: `gui/main_window.py` (lines 789–795)
* **Severity**: **Low**
* **Description**:
  When a save fails due to a local pre-save validation hook error (e.g. date order validation or target hours constraints), `_on_save_error()` displays a message box:
  `"Could not save to database:\n{error_msg}\n\nYour changes are still in the form. Check your network connection and try saving again."`
  This advises the user to check their network connection, which is misleading and confusing since the error is a local data validation validation rule mismatch, not a network/connection issue.
* **Recommendation**:
  Inspect the `error_msg` or catch a specific subclass of validation errors to present a message indicating that fields do not match validation criteria, rather than suggesting a network failure.

### 13. Inline Edit Bar Save Button Styled Incorrectly (Style/Theme Glitch)
* **File Path**: `gui/inline_edit_bar.py` (lines 95–99)
* **Severity**: **Low**
* **Description**:
  The Save button in `InlineEditBar` is created as `self.save_btn = QPushButton("Save")` but is never given an `objectName`.
  In `theme.py`, `_style_button` styles buttons green (`_BTN_SUCCESS`) only if `"save" in widget.objectName().lower()`. Because the inline bar's button has no name, it is styled as a default gray button, violating the visual pattern that Save buttons are green.
* **Recommendation**:
  Set the object name in the constructor of `InlineEditBar`:
  ```python
  self.save_btn.setObjectName("inline_save_btn")
  ```

### 14. Missing Selection Synchronization in CalendarPanel (UX Issue)
* **File Path**: `gui/main_window.py` (lines 725–740) & `gui/calendar_panel.py` (lines 270–280)
* **Severity**: **Medium**
* **Description**:
  When a unit is selected (via the List view, or via global search), `MainWindow.on_unit_selected()` is called, but it does not notify `CalendarPanel`. 
  This means the calendar does not highlight the selected unit's due date, causing a visual desynchronization when navigating between views.
* **Recommendation**:
  In `MainWindow.on_unit_selected()`, call `self.calendar_panel.set_highlighted_unit(unit.com_number if unit else None)`.

### 15. Missing Selection Synchronization in AlertPanel (UX Issue)
* **File Path**: `gui/main_window.py` (lines 725–740) & `gui/alert_panel.py`
* **Severity**: **Medium**
* **Description**:
  Similar to the calendar, when a unit is selected via search or list view, the selection is not propagated to `AlertPanel`. If the user switches to the Alerts tab, no item is selected/highlighted in the alerts list widget.
* **Recommendation**:
  Implement a `set_selected_unit(self, unit)` method in `AlertPanel` and call it from `MainWindow.on_unit_selected()`.

### 16. Onboarding Walks Through Non-Existent Right-Click Menus (Documentation Drift)
* **File Path**: `gui/onboarding.py` (line 87)
* **Severity**: **Low**
* **Description**:
  The onboarding walkthrough for the List View tells the user that "Right-click context menus available". However, right-click menus are not implemented in `gui/list_panel.py`.
* **Recommendation**:
  Either remove the text from `onboarding.py` or implement the custom context menu context policies on the `QTableWidget` inside `ListPanel`.

---

## 5-Component Report

### 1. Observation
We observed the following code sections by inspection:
* **Batch edit thread saves**:
  `gui/main_window.py` lines 753–755:
  ```python
  if self._active_save_worker_running():
      logger.warning("Save already in progress — queuing")
      return
  ```
  And `gui/batch_edit_dialog.py` lines 142–143:
  ```python
  self._updated_units.append(unit)
  self.unit_saved.emit(unit)
  ```
* **Theme stylesheets reset**:
  `gui/edit_form.py` line 27:
  ```python
  _VALID_STYLE = ""  # Reset to default
  ```
  `gui/edit_form.py` lines 343–346:
  ```python
  self.percent_spin.setStyleSheet(_VALID_STYLE)
  self.dept_hours_spin.setStyleSheet(_VALID_STYLE)
  self.actual_hours_spin.setStyleSheet(_VALID_STYLE)
  self.due_date_edit.setStyleSheet(_VALID_STYLE)
  ```
* **Invalid color contrast styles**:
  `gui/edit_form.py` line 26:
  ```python
  _INVALID_STYLE = "border: 2px solid red; background-color: #fff0f0;"
  ```
  `gui/conflict_dialog.py` lines 119–120:
  ```python
  item_local.setBackground(QColor("#fef9c3"))
  item_remote.setBackground(QColor("#fef9c3"))
  ```
  `gui/import_preview_dialog.py` lines 85, 95, 122:
  Passing `QColor(220, 255, 220)`, `QColor(255, 255, 200)`, and `QColor(255, 220, 220)` for row backgrounds without setting foreground color, and the dialog doesn't call `apply_theme()`.
* **TimelineWidget Painting**:
  `gui/timeline_panel.py` lines 152, 223, 243, 257:
  ```python
  painter.fillRect(self.rect(), QBrush(QColor(252, 252, 255)))
  ```
  And other hardcoded colors like `QColor(237, 240, 248)` for backgrounds, and `QColor(20, 20, 20)` for text.
* **View toggle default button style**:
  `gui/theme.py` line 234:
  ```python
  _BTN_DEFAULT = """
      QPushButton {
          background: {bg_tertiary};
          color: {text_primary};
          border: 1px solid {border};
          border-radius: 6px;
          padding: 6px 14px;
          font-weight: 500;
      }
      QPushButton:hover { background: {border}; }
  """
  ```
* **Sync Status Widget wiring**:
  `gui/main_window.py` lines 303–305:
  ```python
  self._sync_status_widget = SyncStatusWidget()
  self._sync_status_widget.setObjectName("sync_status_widget")
  self.status_bar.addPermanentWidget(self._sync_status_widget)
  ```
  `set_progress` is never invoked in `main_window.py` or any service file.
* **Rolling ETA variables**:
  `gui/main_window.py` lines 242–244:
  ```python
  self._sync_status_session_total: int = 0
  self._sync_status_session_initial: int = 0
  self._sync_unit_durations: list[float] = []
  ```
  These are never modified during the runtime lifecycle.
* **Audit Dialog sorting**:
  `gui/audit_dialog.py` line 100:
  ```python
  self.table.setSortingEnabled(True)
  ```
  Immediately followed by `self._load_data()` loading database entries.
* **Onboarding context menu claim**:
  `gui/onboarding.py` line 87:
  ```python
  "Column widths are resizable. Right-click context menus available. "
  ```
* **Stale global search single match**:
  `gui/main_window.py` lines 366–368:
  ```python
  query = self._search_edit.text().strip().lower()
  if not query:
      return
  ```
  Leaving `self._search_single_match` set.

### 2. Logic Chain
1. *Batch Edit*: `BatchEditDialog` iterates and fires `unit_saved` signals. Since `SaveWorker` threads execute asynchronously, `_active_save_worker_running()` is True immediately after the first loop iteration. Because there is no queue list, all subsequent units are discarded. Thus, batch editing is broken.
2. *Valid Style Reset*: Standard theme stylesheets are applied dynamically to input fields. Calling `setStyleSheet("")` resets the stylesheet completely, discarding all rules from `gui/theme.py`, causing theme leakage.
3. *Contrast*: Standard text colors in Dark Theme are light/white (`#f1f5f9`). Setting light backgrounds (pink `#fff0f0`, yellow `#fef9c3`, or pastel colors in `ImportPreviewDialog`) without overriding the foreground text color to dark results in white text on light backgrounds, causing WCAG contrast violations.
4. *TimelineWidget*: The widget draws directly in a paint event using hardcoded RGB values of light colors (e.g., `#fcfcff`). Therefore, it cannot adapt when the user switches to Dark Theme, creating a bright block on the screen.
5. *Toggle checked state*: View buttons are checkable. Since no `:checked` style exists in their stylesheet, their visual state remains identical whether checked or unchecked.
6. *Dead UI / ETA*: `set_progress()` is never called, and `_sync_unit_durations` is never appended to. Thus, the sync status bar remains hidden and the Close progress dialog's rolling average is always `0.0`.
7. *Audit dialog performance*: Activating table sorting before row cell insertion causes Qt to sort on every item insertion, leading to slow rendering.

### 3. Caveats
* The audit was performed entirely by code inspection (read-only investigation) without running the application interactively or setting up database mock data.
* Minor UI layout issues might vary depending on system DPI scale and OS (Windows vs. Linux Qt styles).

### 4. Conclusion
The SQL-Schedule-Tracker application contains several key graphical UX/UI issues, particularly regarding **Dark Theme contrast readability** in modal dialogs (Conflict, Import Preview, Edit Form validation), **theme leakage** (style overrides), **view selection indicators**, and **broken async save queuing** during batch editing operations.

### 5. Verification Method
* **Batch edit save bug**: Run the application, select multiple units, click Batch Edit, modify a field and hit OK. Examine logs to see `Save already in progress — queuing` warnings, and verify in the database that only one unit was updated.
* **Contrast verification**: Switch the theme to Dark Theme (`Ctrl+T`), select an invalid value in the edit form, and observe readability of the text. Open `ImportPreviewDialog` or `ConflictDialog` in Dark Theme and inspect the pastel highlights.
* **Timeline panel theme**: Switch to Dark Theme and inspect if the Timeline panel background is white.
* **View button state**: Click view buttons and observe that their background/border styles do not change.
* **Audit table performance**: Insert 500 audit log entries and open the Change History dialog to see if it causes a brief UI freeze on load.
