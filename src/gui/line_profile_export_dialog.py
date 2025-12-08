"""
Export dialog for line profile plots with customization options.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QCheckBox, QComboBox,
    QSpinBox, QDoubleSpinBox, QGroupBox, QDialogButtonBox,
    QFileDialog, QColorDialog, QSplitter, QRadioButton,
    QButtonGroup, QMessageBox, QWidget
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPalette, QFont
import pyqtgraph as pg
import numpy as np
import csv
from typing import Optional, Dict, Any
from src.gui.line_profile_preview_dialog import LineProfilePreviewDialog


class LineProfileExportDialog(QDialog):
    """Dialog for customizing and exporting line profile plots."""

    def __init__(self, plot_data: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.plot_data = plot_data
        self.setWindowTitle("Export Line Profile")
        self.setModal(True)
        self.resize(1200, 700)  # Wider to accommodate preview

        # Store export settings
        self.export_settings = {
            'export_type': 'image',  # 'image' or 'csv'
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

        # Create preview plot widget
        self.preview_plot = pg.PlotWidget()

        self._setup_ui()
        self._update_from_plot_data()
        self._update_preview()  # Initial preview

    def _setup_ui(self):
        """Set up the dialog UI with side-by-side layout."""
        main_layout = QVBoxLayout(self)

        # Create splitter for side-by-side layout
        splitter = QSplitter(Qt.Horizontal)

        # Left panel - Controls
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)

        # Export Type selection
        type_group = QGroupBox("Export Type")
        type_layout = QVBoxLayout(type_group)

        self.export_type_group = QButtonGroup()
        self.image_radio = QRadioButton("Export as Image (PNG/JPEG)")
        self.image_radio.setChecked(True)
        self.csv_radio = QRadioButton("Export as CSV (Data)")

        self.export_type_group.addButton(self.image_radio)
        self.export_type_group.addButton(self.csv_radio)

        type_layout.addWidget(self.image_radio)
        type_layout.addWidget(self.csv_radio)

        self.image_radio.toggled.connect(self._on_export_type_changed)

        left_layout.addWidget(type_group)

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

        # Image dimensions (only for image export)
        self.dimension_widgets = []

        file_layout.addWidget(QLabel("Width:"), 1, 0)
        self.width_spin = QSpinBox()
        self.width_spin.setRange(400, 3000)
        self.width_spin.setValue(800)
        self.width_spin.setSuffix(" px")
        self.width_spin.valueChanged.connect(self._on_settings_changed)
        file_layout.addWidget(self.width_spin, 1, 1)
        self.dimension_widgets.append(self.width_spin)

        file_layout.addWidget(QLabel("Height:"), 2, 0)
        self.height_spin = QSpinBox()
        self.height_spin.setRange(300, 2000)
        self.height_spin.setValue(600)
        self.height_spin.setSuffix(" px")
        self.height_spin.valueChanged.connect(self._on_settings_changed)
        file_layout.addWidget(self.height_spin, 2, 1)
        self.dimension_widgets.append(self.height_spin)

        left_layout.addWidget(file_group)

        # Appearance group (only for image export)
        self.appearance_group = QGroupBox("Appearance")
        appearance_layout = QGridLayout(self.appearance_group)

        # Theme
        appearance_layout.addWidget(QLabel("Theme:"), 0, 0)
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Current", "Light", "Dark"])
        self.theme_combo.currentTextChanged.connect(self._on_theme_changed)
        appearance_layout.addWidget(self.theme_combo, 0, 1)

        # Grid
        self.grid_check = QCheckBox("Show Grid")
        self.grid_check.setChecked(True)
        self.grid_check.toggled.connect(self._on_settings_changed)
        appearance_layout.addWidget(self.grid_check, 1, 0)

        appearance_layout.addWidget(QLabel("Grid Opacity:"), 1, 1)
        self.grid_alpha_spin = QDoubleSpinBox()
        self.grid_alpha_spin.setRange(0.1, 1.0)
        self.grid_alpha_spin.setValue(0.3)
        self.grid_alpha_spin.setSingleStep(0.1)
        self.grid_alpha_spin.valueChanged.connect(self._on_settings_changed)
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
        self.line_width_spin.valueChanged.connect(self._on_settings_changed)
        appearance_layout.addWidget(self.line_width_spin, 3, 1)

        # Show statistics
        self.stats_check = QCheckBox("Include Statistics")
        self.stats_check.setChecked(True)
        self.stats_check.toggled.connect(self._on_settings_changed)
        appearance_layout.addWidget(self.stats_check, 4, 0, 1, 2)

        left_layout.addWidget(self.appearance_group)

        # Labels group (only for image export)
        self.labels_group = QGroupBox("Labels and Titles")
        labels_layout = QGridLayout(self.labels_group)

        labels_layout.addWidget(QLabel("Title:"), 0, 0)
        self.title_edit = QLineEdit("Line Profile")
        self.title_edit.textChanged.connect(self._on_settings_changed)
        labels_layout.addWidget(self.title_edit, 0, 1)

        labels_layout.addWidget(QLabel("X-Axis:"), 1, 0)
        self.x_label_edit = QLineEdit("Distance")
        self.x_label_edit.textChanged.connect(self._on_settings_changed)
        labels_layout.addWidget(self.x_label_edit, 1, 1)

        labels_layout.addWidget(QLabel("Y-Axis:"), 2, 0)
        self.y_label_edit = QLineEdit("Intensity")
        self.y_label_edit.textChanged.connect(self._on_settings_changed)
        labels_layout.addWidget(self.y_label_edit, 2, 1)

        left_layout.addWidget(self.labels_group)

        # For spacing
        left_layout.addStretch()

        # Add left widget to splitter
        splitter.addWidget(left_widget)

        # Right panel - Preview
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        preview_label = QLabel("Live Preview")
        preview_label.setStyleSheet("font-weight: bold; font-size: 14px")
        preview_label.setAlignment(Qt.AlignCenter)
        right_layout.addWidget(preview_label)

        # Add preview plot
        right_layout.addWidget(self.preview_plot)

        # Add right widget to splitter
        splitter.addWidget(right_widget)

        # Set initial splitter sizes (40% left, 60% right)
        splitter.setSizes([480, 720])

        main_layout.addWidget(splitter)

        # Dialog buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            parent=self
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        main_layout.addWidget(buttons)

    def _update_from_plot_data(self):
        """Update dialog from plot data."""
        if not self.plot_data:
            return

        # Store data ranges for reference (but don't set UI since we removed those spinboxes)
        if 'distances' in self.plot_data and 'values' in self.plot_data:
            distances = np.array(self.plot_data['distances'])
            values = np.array(self.plot_data['values'])

            # Apply unit conversion for display if needed
            if self.plot_data.get('unit') == 'nm' and 'calibration' in self.plot_data and self.plot_data['calibration']:
                distances = distances * self.plot_data['calibration']

            # Store ranges for auto-ranging
            if len(distances) > 0:
                self.export_settings['x_range'] = None  # Auto-range

            if len(values) > 0:
                self.export_settings['y_range'] = None  # Auto-range

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

    def _on_export_type_changed(self, checked):
        """Handle export type change."""
        is_image_export = self.image_radio.isChecked()

        # Show/hide relevant controls
        for widget in self.dimension_widgets:
            widget.setEnabled(is_image_export)

        self.appearance_group.setEnabled(is_image_export)
        self.labels_group.setEnabled(is_image_export)

        # Update preview visibility
        self.preview_plot.setVisible(is_image_export)

        # Update export type
        self.export_settings['export_type'] = 'image' if is_image_export else 'csv'

    def _on_settings_changed(self):
        """Handle any settings change - update preview."""
        self._update_preview()

    def _on_browse(self):
        """Open file browser for export location."""
        if self.image_radio.isChecked():
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Export Line Profile Plot",
                "line_profile.png",
                "PNG Files (*.png);;JPEG Files (*.jpg *.jpeg)"
            )
        else:
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Export Line Profile Data",
                "line_profile.csv",
                "CSV Files (*.csv);;All Files (*)"
            )

        if file_path:
            self.file_path_edit.setText(file_path)
            self.export_settings['file_path'] = file_path

    def _on_theme_changed(self, theme_text):
        """Handle theme selection change."""
        self.export_settings['theme'] = theme_text.lower()
        self._update_preview()

    def _on_choose_color(self):
        """Open color picker for line color."""
        current_color = QColor(self.export_settings['line_color'])
        color = QColorDialog.getColor(current_color, self, "Choose Line Color")

        if color.isValid():
            hex_color = color.name()
            self.export_settings['line_color'] = hex_color
            self.line_color_btn.setStyleSheet(f"background-color: {hex_color}")
            self._update_preview()

    def _update_preview(self):
        """Update the live preview plot."""
        if not self.plot_data or not self.image_radio.isChecked():
            return

        # Clear previous plot
        self.preview_plot.clear()

        # Update settings first
        self._update_settings()

        settings = self.export_settings

        # Apply theme
        if settings['theme'] == 'light':
            self.preview_plot.setBackground('w')
            text_color = 'k'
        elif settings['theme'] == 'dark':
            self.preview_plot.setBackground('#1e1e1e')
            text_color = 'w'
        else:
            # Current theme (dark by default for preview)
            self.preview_plot.setBackground('#1e1e1e')
            text_color = 'w'

        # Set title and labels
        self.preview_plot.setTitle(settings['title'], color=text_color, size='12pt')
        self.preview_plot.setLabel('left', settings['y_label'], color=text_color)

        # X-axis with unit
        x_unit = self.plot_data.get('unit', 'px')
        self.preview_plot.setLabel('bottom', settings['x_label'], units=x_unit, color=text_color)

        # Set grid
        if settings['show_grid']:
            self.preview_plot.showGrid(x=True, y=True, alpha=settings['grid_alpha'])

        # Plot data
        if 'values' in self.plot_data and 'distances' in self.plot_data:
            values = np.array(self.plot_data['values'])
            distances = np.array(self.plot_data['distances'])

            # Apply unit conversion if needed
            if x_unit == 'nm' and 'calibration' in self.plot_data and self.plot_data['calibration']:
                distances = distances * self.plot_data['calibration']

            # Plot with custom style
            pen = pg.mkPen(color=settings['line_color'], width=settings['line_width'])
            self.preview_plot.plot(distances, values, pen=pen)

            # Add statistics if enabled
            if settings['show_statistics'] and len(values) > 0:
                mean_val = np.mean(values)
                std_val = np.std(values)
                min_val = np.min(values)
                max_val = np.max(values)

                stats_text = f"Mean: {mean_val:.3f} | Std: {std_val:.3f} | Min: {min_val:.3f} | Max: {max_val:.3f}"

                text_item = pg.TextItem(stats_text, color=text_color, anchor=(0.5, 1))
                text_item.setFont(QFont("Arial", 9))
                self.preview_plot.addItem(text_item)

                # Position at bottom
                view_range = self.preview_plot.viewRange()
                if view_range:
                    x_center = (view_range[0][0] + view_range[0][1]) / 2
                    y_bottom = view_range[1][0] + (view_range[1][1] - view_range[1][0]) * 0.05
                    text_item.setPos(x_center, y_bottom)

    def _update_settings(self):
        """Update export settings from UI."""
        self.export_settings['export_type'] = 'image' if self.image_radio.isChecked() else 'csv'
        self.export_settings['file_path'] = self.file_path_edit.text()

        # Image-specific settings
        if self.image_radio.isChecked():
            self.export_settings['width'] = self.width_spin.value()
            self.export_settings['height'] = self.height_spin.value()
            self.export_settings['show_grid'] = self.grid_check.isChecked()
            self.export_settings['grid_alpha'] = self.grid_alpha_spin.value()
            self.export_settings['title'] = self.title_edit.text()
            self.export_settings['x_label'] = self.x_label_edit.text()
            self.export_settings['y_label'] = self.y_label_edit.text()
            self.export_settings['line_width'] = self.line_width_spin.value()
            self.export_settings['show_statistics'] = self.stats_check.isChecked()

    def _on_accept(self):
        """Handle dialog acceptance."""
        if not self.file_path_edit.text():
            # Prompt for file if not selected
            self._on_browse()
            if not self.file_path_edit.text():
                return

        self._update_settings()

        # If CSV export, perform the export here
        if self.csv_radio.isChecked():
            self._export_csv()

        self.accept()

    def _export_csv(self):
        """Export the line profile data to CSV."""
        try:
            if 'values' in self.plot_data and 'distances' in self.plot_data:
                values = np.array(self.plot_data['values'])
                distances = np.array(self.plot_data['distances'])

                # Apply unit conversion if needed
                unit = self.plot_data.get('unit', 'px')
                if unit == 'nm' and 'calibration' in self.plot_data and self.plot_data['calibration']:
                    distances = distances * self.plot_data['calibration']

                # Add metadata as comments and data
                file_path = self.export_settings['file_path']
                with open(file_path, 'w', newline='') as f:
                    # Write metadata as comments
                    f.write(f"# Line Profile Data\n")
                    if 'start' in self.plot_data and 'end' in self.plot_data:
                        start = self.plot_data['start']
                        end = self.plot_data['end']
                        f.write(f"# Start: ({start[0]:.2f}, {start[1]:.2f})\n")
                        f.write(f"# End: ({end[0]:.2f}, {end[1]:.2f})\n")
                    if 'width' in self.plot_data:
                        f.write(f"# Profile Width: {self.plot_data['width']:.1f} pixels\n")
                    f.write(f"# Number of Points: {len(values)}\n")
                    f.write(f"# Mean Intensity: {np.mean(values):.3f}\n")
                    f.write(f"# Std Deviation: {np.std(values):.3f}\n")
                    f.write(f"# Min Intensity: {np.min(values):.3f}\n")
                    f.write(f"# Max Intensity: {np.max(values):.3f}\n")
                    f.write("#\n")

                    # Write the CSV data
                    writer = csv.writer(f)
                    # Header
                    writer.writerow([f'Distance ({unit})', 'Intensity'])
                    # Data rows
                    for dist, val in zip(distances, values):
                        writer.writerow([dist, val])

                QMessageBox.information(
                    self,
                    "Export Successful",
                    f"Line profile data exported to:\n{file_path}"
                )

        except Exception as e:
            QMessageBox.critical(
                self,
                "Export Failed",
                f"Failed to export CSV:\n{str(e)}"
            )

    def get_export_settings(self) -> Dict[str, Any]:
        """Get the export settings."""
        return self.export_settings