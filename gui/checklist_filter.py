# gui/checklist_filter.py
"""ChecklistFilterButton — Excel-style filter dropdown.

A button that opens a popup with a search box, Select All / Clear, and a
checkable list. Options may have children (e.g. a year with its months);
a parent shows partly checked when only some of its children are.

Selection semantics: an empty selection means "no filter". A parent key
in the selection means the whole parent; child keys mean only those
children. Checking every option is stored as an empty selection.

Usage:
    btn = ChecklistFilterButton("Detailer")
    btn.set_options([FilterOption("Jane", "Jane"), FilterOption("Tom", "Tom")])
    btn.selection_changed.connect(on_change)
    btn.selected()  # → {"Jane"}
"""

from __future__ import annotations

from dataclasses import dataclass, field

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QTreeWidgetItemIterator,
    QVBoxLayout,
)


@dataclass
class FilterOption:
    """One checkable entry; *children* makes it an expandable parent."""

    key: str
    label: str
    children: list[FilterOption] = field(default_factory=list)


class ChecklistPopup(QFrame):
    """The dropdown body. Applies its checks only when OK (or Enter) is pressed."""

    def __init__(self, options: list[FilterOption], selected: set[str], on_accept, parent=None):
        super().__init__(parent, Qt.Popup)
        self.setFrameShape(QFrame.StyledPanel)
        self._on_accept = on_accept

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._apply_search)
        self.search_edit.returnPressed.connect(self.accept)
        layout.addWidget(self.search_edit)

        bulk_row = QHBoxLayout()
        self.select_all_btn = QPushButton("Select All")
        self.select_all_btn.clicked.connect(lambda: self._set_visible_checks(Qt.Checked))
        bulk_row.addWidget(self.select_all_btn)
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(lambda: self._set_visible_checks(Qt.Unchecked))
        bulk_row.addWidget(self.clear_btn)
        layout.addLayout(bulk_row)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(any(o.children for o in options))
        self.tree.setMinimumHeight(260)
        layout.addWidget(self.tree, stretch=1)
        self._populate(options, selected)

        button_row = QHBoxLayout()
        button_row.addStretch()
        self.ok_btn = QPushButton("OK")
        self.ok_btn.setDefault(True)
        self.ok_btn.clicked.connect(self.accept)
        button_row.addWidget(self.ok_btn)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.close)
        button_row.addWidget(cancel_btn)
        layout.addLayout(button_row)

        self.search_edit.setFocus()

    def _populate(self, options: list[FilterOption], selected: set[str]) -> None:
        for option in options:
            item = QTreeWidgetItem([option.label])
            item.setData(0, Qt.UserRole, option.key)
            if option.children:
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsAutoTristate)
                whole = option.key in selected
                for child in option.children:
                    child_item = QTreeWidgetItem([child.label])
                    child_item.setData(0, Qt.UserRole, child.key)
                    child_item.setFlags(child_item.flags() | Qt.ItemIsUserCheckable)
                    checked = whole or child.key in selected
                    child_item.setCheckState(0, Qt.Checked if checked else Qt.Unchecked)
                    item.addChild(child_item)
            else:
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(0, Qt.Checked if option.key in selected else Qt.Unchecked)
            self.tree.addTopLevelItem(item)

    def _apply_search(self, text: str) -> None:
        query = text.strip().lower()
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            parent_match = not query or query in item.text(0).lower()
            any_child = False
            for j in range(item.childCount()):
                child = item.child(j)
                show = parent_match or query in child.text(0).lower()
                child.setHidden(not show)
                any_child = any_child or show
            item.setHidden(not (parent_match or any_child))
            if query and any_child and not parent_match:
                item.setExpanded(True)

    def _set_visible_checks(self, state: Qt.CheckState) -> None:
        iterator = QTreeWidgetItemIterator(self.tree)
        while iterator.value():
            item = iterator.value()
            if not item.isHidden() and item.childCount() == 0:
                item.setCheckState(0, state)
            iterator += 1

    def checked_keys(self) -> set[str]:
        """Selection as stored by the button (empty when everything is checked)."""
        keys: set[str] = set()
        all_checked = True
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            state = item.checkState(0)
            if state == Qt.Checked:
                keys.add(item.data(0, Qt.UserRole))
                continue
            all_checked = False
            if state == Qt.PartiallyChecked:
                for j in range(item.childCount()):
                    child = item.child(j)
                    if child.checkState(0) == Qt.Checked:
                        keys.add(child.data(0, Qt.UserRole))
        return set() if all_checked else keys

    def accept(self) -> None:
        self._on_accept(self.checked_keys())
        self.close()


class ChecklistFilterButton(QToolButton):
    """Dropdown button showing the current selection; emits selection_changed on OK."""

    selection_changed = pyqtSignal()

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self._title = title
        self._options: list[FilterOption] = []
        self._labels: dict[str, str] = {}
        self._selected: set[str] = set()
        self.popup: ChecklistPopup | None = None
        self.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.setArrowType(Qt.NoArrow)
        self.setMinimumWidth(130)
        self.clicked.connect(self.open_popup)
        self._update_text()

    # ── Public API ───────────────────────────────────────────────────

    def set_options(self, options: list[FilterOption]) -> None:
        self._options = list(options)
        self._labels = {}
        for option in options:
            self._labels[option.key] = option.label
            for child in option.children:
                self._labels[child.key] = f"{child.label} {option.label}"
        self._update_text()

    def options(self) -> list[FilterOption]:
        return list(self._options)

    def selected(self) -> set[str]:
        return set(self._selected)

    def set_selected(self, keys, emit: bool = False) -> None:
        new = set(keys or ())
        changed = new != self._selected
        self._selected = new
        self._update_text()
        if changed and emit:
            self.selection_changed.emit()

    def is_active(self) -> bool:
        return bool(self._selected)

    def open_popup(self) -> None:
        self.popup = ChecklistPopup(self._options, self._selected, self._on_popup_accepted, self)
        self.popup.setMinimumWidth(max(self.width(), 260))
        self.popup.move(self.mapToGlobal(self.rect().bottomLeft()))
        self.popup.show()

    # ── Internal ─────────────────────────────────────────────────────

    def _on_popup_accepted(self, keys: set[str]) -> None:
        self.set_selected(keys, emit=True)

    def _update_text(self) -> None:
        if not self._selected:
            summary = "All"
        elif len(self._selected) == 1:
            key = next(iter(self._selected))
            summary = self._labels.get(key, key)
        else:
            summary = f"{len(self._selected)} selected"
        self.setText(f"{self._title}: {summary}  ▾")
        font = QFont(self.font())
        font.setBold(bool(self._selected))
        self.setFont(font)
        if self._selected:
            labels = sorted(self._labels.get(k, k) for k in self._selected)
            self.setToolTip(f"{self._title} filter:\n" + "\n".join(labels))
        else:
            self.setToolTip(f"Filter by {self._title.lower()}")
