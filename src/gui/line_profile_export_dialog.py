"""
Export dialog for line profile plots with customization options.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QCheckBox, QComboBox,
    QSpinBox, QDoubleSpinBox, QGroupBox, QDialogButtonBox,
    QFileDialog, QColorDialog
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPalette
import pyqtgraph as pg
import numpy as np
from typing import Optional, Dict, Any
from src.gui.line_profile_preview_dialog import LineProfilePreviewDialog


class LineProfileExportDialog(QDialog):
    """Dialog for customizing and exporting line profile plots."""

    def __init__(self, plot_data: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.plot_data = plot_data
        self.setWindowTitle("Export Line Profile Plot")
        self.setModal(True)
        self.resize(600, 700)

        # Store export settings
        self.export_settings = {
            'file_path': '',
            'width': 800,
            'height': 600,
            'dpi': 100,
            'theme': 'current',  # 'current', 'light', 'dark'
            'show_grid': True,
            'grid_alpha': 0.3,
            'title': 'Line Profile',
            'x_label': 'Distance',
            'y_label': 'Intensity',
            'x_unit': 'auto',  # Will be set from plot_data
            'x_range': None,  # None for auto, or (min, max)
            'y_range': None,  # None for auto, or (min, max)
            'line_color': '#FFD700',  # Default yellow
            'line_width': 2,
            'background_color': None,  # Will be set based on theme
            'show_statistics': True,
        }

        self._setup_ui()
        self._update_from_plot_data()

    def _setup_ui(self):
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)

        # File selection group
        file_group = QGroupBox("Export Settings")
        file_layout = QGridLayout(file_group)

        # File path
        file_layout.addWidget(QLabel("File:"), 0, 0)
        self.file_path_edit = QLineEdit()
        self.file_path_edit.setPlaceholderText("Choose export location...")
        file_layout.addWidget(self.file_path_edit, 0, 1)

        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.clicked.connect(self._on_browse)
        file_layout.addWidget(self.browse_btn, 0, 2)

        # Image dimensions
        file_layout.addWidget(QLabel("Width:"), 1, 0)
        self.width_spin = QSpinBox()
        self.width_spin.setRange(400, 3000)
        self.width_spin.setValue(800)
        self.width_spin.setSuffix(" px")
        file_layout.addWidget(self.width_spin, 1, 1)

        file_layout.addWidget(QLabel("Height:"), 2, 0)
        self.height_spin = QSpinBox()
        self.height_spin.setRange(300, 2000)
        self.height_spin.setValue(600)
        self.height_spin.setSuffix(" px")
        file_layout.addWidget(self.height_spin, 2, 1)

        layout.addWidget(file_group)

        # Appearance group
        appearance_group = QGroupBox("Appearance")
        appearance_layout = QGridLayout(appearance_group)

        # Theme
        appearance_layout.addWidget(QLabel("Theme:"), 0, 0)
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Current", "Light", "Dark"])
        self.theme_combo.currentTextChanged.connect(self._on_theme_changed)
        appearance_layout.addWidget(self.theme_combo, 0, 1)

        # Grid
        self.grid_check = QCheckBox("Show Grid")
        self.grid_check.setChecked(True)
        appearance_layout.addWidget(self.grid_check, 1, 0)

        appearance_layout.addWidget(QLabel("Grid Opacity:"), 1, 1)
        self.grid_alpha_spin = QDoubleSpinBox()
        self.grid_alpha_spin.setRange(0.1, 1.0)
        self.grid_alpha_spin.setValue(0.3)
        self.grid_alpha_spin.setSingleStep(0.1)
        appearance_layout.addWidget(self.grid_alpha_spin, 1, 2)

        # Line style
        appearance_layout.addWidget(QLabel("Line Color:"), 2, 0)
        self.line_color_btn = QPushButton()
        self.line_color_btn.setStyleSheet("background-color: #FFD700")
        self.line_color_btn.clicked.connect(self._on_choose_color)
        appearance_layout.addWidget(self.line_color_btn, 2, 1)

        appearance_layout.addWidget(QLabel("Line Width:"), 3, 0)
        self.line_width_spin = QSpinBox()
        self.line_width_spin.setRange(1, 10)
        self.line_width_spin.setValue(2)
        self.line_width_spin.setSuffix(" px")
        appearance_layout.addWidget(self.line_width_spin, 3, 1)

        # Show statistics
        self.stats_check = QCheckBox("Include Statistics")
        self.stats_check.setChecked(True)
        appearance_layout.addWidget(self.stats_check, 4, 0, 1, 2)

        layout.addWidget(appearance_group)

        # Labels group
        labels_group = QGroupBox("Labels and Titles")
        labels_layout = QGridLayout(labels_group)

        labels_layout.addWidget(QLabel("Title:"), 0, 0)
        self.title_edit = QLineEdit("Line Profile")
        labels_layout.addWidget(self.title_edit, 0, 1)

        labels_layout.addWidget(QLabel("X-Axis Label:"), 1, 0)
        self.x_label_edit = QLineEdit("Distance")
        labels_layout.addWidget(self.x_label_edit, 1, 1)

        labels_layout.addWidget(QLabel("Y-Axis Label:"), 2, 0)
        self.y_label_edit = QLineEdit("Intensity")
        labels_layout.addWidget(self.y_label_edit, 2, 1)

        layout.addWidget(labels_group)

        # Axis Range group
        range_group = QGroupBox("Axis Ranges")
        range_layout = QGridLayout(range_group)

        # X-axis range
        self.x_auto_check = QCheckBox("Auto X-Range")
        self.x_auto_check.setChecked(True)
        self.x_auto_check.toggled.connect(self._on_x_auto_toggled)
        range_layout.addWidget(self.x_auto_check, 0, 0, 1, 2)

        range_layout.addWidget(QLabel("X Min:"), 1, 0)
        self.x_min_spin = QDoubleSpinBox()
        self.x_min_spin.setRange(-999999, 999999)
        self.x_min_spin.setEnabled(False)
        range_layout.addWidget(self.x_min_spin, 1, 1)

        range_layout.addWidget(QLabel("X Max:"), 1, 2)
        self.x_max_spin = QDoubleSpinBox()
        self.x_max_spin.setRange(-999999, 999999)
        self.x_max_spin.setEnabled(False)
        range_layout.addWidget(self.x_max_spin, 1, 3)

        # Y-axis range
        self.y_auto_check = QCheckBox("Auto Y-Range")
        self.y_auto_check.setChecked(True)
        self.y_auto_check.toggled.connect(self._on_y_auto_toggled)
        range_layout.addWidget(self.y_auto_check, 2, 0, 1, 2)

        range_layout.addWidget(QLabel("Y Min:"), 3, 0)
        self.y_min_spin = QDoubleSpinBox()
        self.y_min_spin.setRange(-999999, 999999)
        self.y_min_spin.setEnabled(False)
        range_layout.addWidget(self.y_min_spin, 3, 1)

        range_layout.addWidget(QLabel("Y Max:"), 3, 2)
        self.y_max_spin = QDoubleSpinBox()
        self.y_max_spin.setRange(-999999, 999999)
        self.y_max_spin.setEnabled(False)
        range_layout.addWidget(self.y_max_spin, 3, 3)

        layout.addWidget(range_group)

        # Preview button
        self.preview_btn = QPushButton("Preview")
        self.preview_btn.clicked.connect(self._on_preview)
        layout.addWidget(self.preview_btn)

        # Dialog buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            parent=self
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _update_from_plot_data(self):
        """Update dialog from plot data."""
        if not self.plot_data:
            return

        # Set default ranges from data
        if 'distances' in self.plot_data and 'values' in self.plot_data:
            distances = np.array(self.plot_data['distances'])
            values = np.array(self.plot_data['values'])

            # Apply unit conversion for display if needed
            if self.plot_data.get('unit') == 'nm' and 'calibration' in self.plot_data and self.plot_data['calibration']:
                distances = distances * self.plot_data['calibration']

            if len(distances) > 0:
                self.x_min_spin.setValue(float(np.min(distances)))
                self.x_max_spin.setValue(float(np.max(distances)))

            if len(values) > 0:
                self.y_min_spin.setValue(float(np.min(values)))
                self.y_max_spin.setValue(float(np.max(values)))

        # Set unit if available
        if 'unit' in self.plot_data:
            self.export_settings['x_unit'] = self.plot_data['unit']

        # Update default title with endpoints if available
        if 'start' in self.plot_data and 'end' in self.plot_data:
            start = self.plot_data['start']
            end = self.plot_data['end']
            self.title_edit.setText(f"Line Profile: ({start[0]:.1f}, {start[1]:.1f}) → ({end[0]:.1f}, {end[1]:.1f})")

        # Set default filename
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.file_path_edit.setPlaceholderText(f"line_profile_{timestamp}.png")

    def _on_browse(self):
        """Open file browser for export location."""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Line Profile Plot",
            "line_profile.png",
            "PNG Files (*.png);;JPEG Files (*.jpg *.jpeg)"
        )

        if file_path:
            self.file_path_edit.setText(file_path)
            self.export_settings['file_path'] = file_path

    def _on_theme_changed(self, theme_text):
        """Handle theme selection change."""
        self.export_settings['theme'] = theme_text.lower()

    def _on_choose_color(self):
        """Open color picker for line color."""
        current_color = QColor(self.export_settings['line_color'])
        color = QColorDialog.getColor(current_color, self, "Choose Line Color")

        if color.isValid():
            hex_color = color.name()
            self.export_settings['line_color'] = hex_color
            self.line_color_btn.setStyleSheet(f"background-color: {hex_color}")

    def _on_x_auto_toggled(self, checked):
        """Handle X-axis auto range toggle."""
        self.x_min_spin.setEnabled(not checked)
        self.x_max_spin.setEnabled(not checked)

    def _on_y_auto_toggled(self, checked):
        """Handle Y-axis auto range toggle."""
        self.y_min_spin.setEnabled(not checked)
        self.y_max_spin.setEnabled(not checked)

    def _on_preview(self):
        """Show preview of the plot with current settings."""
        self._update_settings()

        # Prepare plot data with current unit
        preview_data = self.plot_data.copy()

        # Show preview dialog
        preview_dialog = LineProfilePreviewDialog(
            preview_data,
            self.export_settings,
            self
        )
        preview_dialog.exec_()

    def _update_settings(self):
        """Update export settings from UI."""
        self.export_settings['width'] = self.width_spin.value()
        self.export_settings['height'] = self.height_spin.value()
        self.export_settings['show_grid'] = self.grid_check.isChecked()
        self.export_settings['grid_alpha'] = self.grid_alpha_spin.value()
        self.export_settings['title'] = self.title_edit.text()
        self.export_settings['x_label'] = self.x_label_edit.text()
        self.export_settings['y_label'] = self.y_label_edit.text()
        self.export_settings['line_width'] = self.line_width_spin.value()
        self.export_settings['show_statistics'] = self.stats_check.isChecked()

        # Axis ranges
        if not self.x_auto_check.isChecked():
            self.export_settings['x_range'] = (
                self.x_min_spin.value(),
                self.x_max_spin.value()
            )
        else:
            self.export_settings['x_range'] = None

        if not self.y_auto_check.isChecked():
            self.export_settings['y_range'] = (
                self.y_min_spin.value(),
                self.y_max_spin.value()
            )
        else:
            self.export_settings['y_range'] = None

    def _on_accept(self):
        """Handle dialog acceptance."""
        if not self.file_path_edit.text():
            # Prompt for file if not selected
            self._on_browse()
            if not self.file_path_edit.text():
                return

        self._update_settings()
        self.accept()

    def get_export_settings(self) -> Dict[str, Any]:
        """Get the export settings."""
        return self.export_settings