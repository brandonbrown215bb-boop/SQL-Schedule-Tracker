"""
gui/a11y_dialog.py — Accessibility settings dialog.

Provides UI for colorblind_mode and high_contrast toggles that
previously had no user-facing controls.
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QCheckBox, QDialogButtonBox,
)


class A11yDialog(QDialog):
    """Modal dialog for accessibility preferences."""

    CVD_OPTIONS = [
        ("none",         "None"),
        ("deuteranopia", "Deuteranopia (red-green, most common)"),
        ("protanopia",   "Protanopia (red-green, darker)"),
        ("tritanopia",   "Tritanopia (blue-yellow, rare)"),
    ]

    def __init__(self, theme: str, cvd_mode: str,
                 high_contrast: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Accessibility Settings")
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)

        # CVD mode
        cvd_row = QHBoxLayout()
        cvd_row.addWidget(QLabel("Colorblind mode:"))
        self._cvd_combo = QComboBox()
        for key, label in self.CVD_OPTIONS:
            self._cvd_combo.addItem(label, key)
        idx = next((i for i, (k, _) in enumerate(self.CVD_OPTIONS)
                    if k == cvd_mode), 0)
        self._cvd_combo.setCurrentIndex(idx)
        cvd_row.addWidget(self._cvd_combo)
        layout.addLayout(cvd_row)

        # High contrast
        self._hc_check = QCheckBox("High contrast mode")
        self._hc_check.setChecked(high_contrast)
        layout.addWidget(self._hc_check)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def cvd_mode(self) -> str:
        return self._cvd_combo.currentData()

    @property
    def high_contrast(self) -> bool:
        return self._hc_check.isChecked()
