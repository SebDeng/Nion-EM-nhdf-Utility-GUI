"""
Export dialog for frame statistics data with customization options.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QCheckBox, QComboBox,
    QSpinBox, QGroupBox, QDialogButtonBox,
    QFileDialog, QSplitter, QRadioButton,
    QButtonGroup, QMessageBox, QWidget
)
from PySide6.QtCore import Qt
import pyqtgraph as pg
import pyqtgraph.exporters
import numpy as np
import csv
from datetime import datetime
from typing import Optional, Dict, Any


class FrameStatisticsExportDialog(QDialog):
    """Dialog for exporting frame statistics as CSV or image."""

    def __init__(self, stats_data: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.stats_data = stats_data
        self.setWindowTitle("Export Frame Statistics")
        self.setModal(True)
        self.resize(900, 600)

        self._is_dark_mode = True

        # Store export settings
        self.export_settings = {
            'export_type': 'csv',  # 'image' or 'csv'
            'file_path': '',
            'width': 800,
            'height': 600,
            'theme': 'current',
            'show_grid': True,
            'statistic': 'mean',  # Which stat to plot for image export
        }

        self._setup_ui()
        self._update_preview()

    def _setup_ui(self):
        """Set up the dialog UI."""
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
        self.csv_radio = QRadioButton("Export as CSV (All Statistics)")
        self.csv_radio.setChecked(True)
        self.image_radio = QRadioButton("Export as Image (PNG)")

        self.export_type_group.addButton(self.csv_radio)
        self.export_type_group.addButton(self.image_radio)

        type_layout.addWidget(self.csv_radio)
        type_layout.addWidget(self.image_radio)

        self.csv_radio.toggled.connect(self._on_export_type_changed)

        left_layout.addWidget(type_group)

        # File selection
        file_group = QGroupBox("Export Settings")
        file_layout = QGridLayout(file_group)

        file_layout.addWidget(QLabel("File:"), 0, 0)
        self.file_path_edit = QLineEdit()
        self.file_path_edit.setPlaceholderText("Choose export location...")
        file_layout.addWidget(self.file_path_edit, 0, 1)

        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.clicked.connect(self._on_browse)
        file_layout.addWidget(self.browse_btn, 0, 2)

        left_layout.addWidget(file_group)

        # Image-specific options
        self.image_options_group = QGroupBox("Image Options")
        image_layout = QGridLayout(self.image_options_group)

        image_layout.addWidget(QLabel("Statistic:"), 0, 0)
        self.stat_combo = QComboBox()
        self.stat_combo.addItems(['Mean', 'Sum (Integral)', 'Std', 'Min', 'Max'])
        self.stat_combo.currentIndexChanged.connect(self._update_preview)
        image_layout.addWidget(self.stat_combo, 0, 1)

        image_layout.addWidget(QLabel("Width:"), 1, 0)
        self.width_spin = QSpinBox()
        self.width_spin.setRange(400, 2000)
        self.width_spin.setValue(800)
        self.width_spin.setSuffix(" px")
        image_layout.addWidget(self.width_spin, 1, 1)

        image_layout.addWidget(QLabel("Height:"), 2, 0)
        self.height_spin = QSpinBox()
        self.height_spin.setRange(300, 1500)
        self.height_spin.setValue(600)
        self.height_spin.setSuffix(" px")
        image_layout.addWidget(self.height_spin, 2, 1)

        self.grid_check = QCheckBox("Show Grid")
        self.grid_check.setChecked(True)
        self.grid_check.toggled.connect(self._update_preview)
        image_layout.addWidget(self.grid_check, 3, 0, 1, 2)

        left_layout.addWidget(self.image_options_group)

        # Data summary
        summary_group = QGroupBox("Data Summary")
        summary_layout = QVBoxLayout(summary_group)

        total_frames = self.stats_data.get('total_frames', 0)
        roi_bounds = self.stats_data.get('roi_bounds')
        file_name = self.stats_data.get('file_name', 'Unknown')

        summary_layout.addWidget(QLabel(f"File: {file_name}"))
        summary_layout.addWidget(QLabel(f"Total Frames: {total_frames}"))

        roi_text = "Full Frame"
        if roi_bounds:
            x, y, w, h = roi_bounds
            roi_text = f"ROI: ({x:.0f}, {y:.0f}, {w:.0f}x{h:.0f})"
        summary_layout.addWidget(QLabel(roi_text))

        left_layout.addWidget(summary_group)

        left_layout.addStretch()

        # Button box
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        left_layout.addWidget(button_box)

        # Right panel - Preview
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        preview_label = QLabel("Preview")
        preview_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        right_layout.addWidget(preview_label)

        self.preview_plot = pg.PlotWidget()
        self.preview_plot.setLabel('left', 'Mean Intensity')
        self.preview_plot.setLabel('bottom', 'Frame Number')
        self.preview_plot.showGrid(x=True, y=True, alpha=0.3)
        right_layout.addWidget(self.preview_plot)

        # Add to splitter
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([350, 550])

        main_layout.addWidget(splitter)

        # Initial state
        self._on_export_type_changed()
        self._apply_theme()

    def _on_export_type_changed(self):
        """Handle export type change."""
        is_image = self.image_radio.isChecked()
        self.image_options_group.setVisible(is_image)
        self.preview_plot.setVisible(is_image)
        self.export_settings['export_type'] = 'image' if is_image else 'csv'

    def _on_browse(self):
        """Open file browser dialog."""
        if self.csv_radio.isChecked():
            file_path, _ = QFileDialog.getSaveFileName(
                self, "Save CSV File", "", "CSV Files (*.csv)"
            )
        else:
            file_path, _ = QFileDialog.getSaveFileName(
                self, "Save Image File", "", "PNG Files (*.png);;JPEG Files (*.jpg)"
            )

        if file_path:
            self.file_path_edit.setText(file_path)

    def _update_preview(self):
        """Update the preview plot."""
        if self.stats_data is None:
            return

        frame_numbers = self.stats_data.get('frame_numbers', np.array([]))
        if len(frame_numbers) == 0:
            return

        # Get selected statistic
        stat_keys = ['mean', 'sum', 'std', 'min', 'max']
        stat_key = stat_keys[self.stat_combo.currentIndex()]
        values = self.stats_data.get(stat_key, np.array([]))

        if len(values) == 0:
            return

        # Clear and update plot
        self.preview_plot.clear()

        # Add data curve
        pen = pg.mkPen(color=(100, 180, 255), width=2)
        self.preview_plot.plot(frame_numbers, values, pen=pen)

        # Add scatter points
        scatter = pg.ScatterPlotItem(
            x=frame_numbers, y=values,
            size=6,
            pen=pg.mkPen(color=(100, 180, 255)),
            brush=pg.mkBrush(color=(100, 180, 255, 200))
        )
        self.preview_plot.addItem(scatter)

        # Update labels
        y_labels = {
            'mean': 'Mean Intensity',
            'sum': 'Sum (Integral)',
            'std': 'Std Deviation',
            'min': 'Min Intensity',
            'max': 'Max Intensity'
        }
        self.preview_plot.setLabel('left', y_labels.get(stat_key, stat_key))

        # Update grid
        self.preview_plot.showGrid(
            x=self.grid_check.isChecked(),
            y=self.grid_check.isChecked(),
            alpha=0.3
        )

    def _on_accept(self):
        """Handle OK button click - perform export."""
        file_path = self.file_path_edit.text().strip()

        if not file_path:
            QMessageBox.warning(self, "No File", "Please select an export file path.")
            return

        try:
            if self.csv_radio.isChecked():
                self._export_csv(file_path)
            else:
                self._export_image(file_path)

            QMessageBox.information(
                self, "Export Complete",
                f"Frame statistics exported to:\n{file_path}"
            )
            self.accept()

        except Exception as e:
            QMessageBox.critical(
                self, "Export Failed",
                f"Failed to export:\n{str(e)}"
            )

    def _export_csv(self, file_path: str):
        """Export statistics to CSV file."""
        if not file_path.lower().endswith('.csv'):
            file_path += '.csv'

        frame_numbers = self.stats_data.get('frame_numbers', np.array([]))
        means = self.stats_data.get('mean', np.array([]))
        sums = self.stats_data.get('sum', np.array([]))
        stds = self.stats_data.get('std', np.array([]))
        mins = self.stats_data.get('min', np.array([]))
        maxs = self.stats_data.get('max', np.array([]))

        with open(file_path, 'w', newline='') as f:
            writer = csv.writer(f)

            # Write metadata as comments
            writer.writerow(['# Frame Statistics Export'])
            writer.writerow([f'# File: {self.stats_data.get("file_name", "Unknown")}'])
            writer.writerow([f'# Export Date: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'])
            writer.writerow([f'# Total Frames: {self.stats_data.get("total_frames", 0)}'])

            roi_bounds = self.stats_data.get('roi_bounds')
            if roi_bounds:
                x, y, w, h = roi_bounds
                writer.writerow([f'# ROI: (x={x:.0f}, y={y:.0f}, w={w:.0f}, h={h:.0f})'])
            else:
                writer.writerow(['# ROI: Full Frame'])

            writer.writerow([])

            # Write header
            writer.writerow(['Frame', 'Mean', 'Sum', 'Std', 'Min', 'Max'])

            # Write data rows
            for i in range(len(frame_numbers)):
                writer.writerow([
                    int(frame_numbers[i]),
                    f'{means[i]:.6f}',
                    f'{sums[i]:.6f}',
                    f'{stds[i]:.6f}',
                    f'{mins[i]:.6f}',
                    f'{maxs[i]:.6f}'
                ])

    def _export_image(self, file_path: str):
        """Export plot to image file."""
        # Ensure proper extension
        if not (file_path.lower().endswith('.png') or file_path.lower().endswith('.jpg')):
            file_path += '.png'

        # Update preview with current settings
        self._update_preview()

        # Create exporter
        exporter = pg.exporters.ImageExporter(self.preview_plot.plotItem)
        exporter.parameters()['width'] = self.width_spin.value()
        exporter.parameters()['height'] = self.height_spin.value()

        # Export
        exporter.export(file_path)

    def _apply_theme(self):
        """Apply theme to the dialog."""
        if self._is_dark_mode:
            self.setStyleSheet("""
                QDialog {
                    background-color: #2b2b2b;
                    color: #e0e0e0;
                }
                QGroupBox {
                    font-weight: bold;
                    border: 1px solid #555;
                    border-radius: 4px;
                    margin-top: 8px;
                    padding-top: 8px;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 10px;
                    padding: 0 5px;
                }
                QLabel {
                    color: #e0e0e0;
                }
                QLineEdit, QSpinBox, QComboBox {
                    background-color: #3a3a3a;
                    border: 1px solid #555;
                    color: #e0e0e0;
                    padding: 4px;
                }
                QPushButton {
                    background-color: #3a3a3a;
                    border: 1px solid #555;
                    color: #e0e0e0;
                    padding: 6px 12px;
                    border-radius: 3px;
                }
                QPushButton:hover {
                    background-color: #4a4a4a;
                }
                QPushButton:pressed {
                    background-color: #0a5d61;
                }
                QRadioButton, QCheckBox {
                    color: #e0e0e0;
                }
            """)
            self.preview_plot.setBackground('#1e1e1e')
            axis_color = '#888'
        else:
            self.setStyleSheet("")
            self.preview_plot.setBackground('w')
            axis_color = '#333'

        self.preview_plot.getAxis('left').setPen(axis_color)
        self.preview_plot.getAxis('bottom').setPen(axis_color)
        self.preview_plot.getAxis('left').setTextPen(axis_color)
        self.preview_plot.getAxis('bottom').setTextPen(axis_color)

    def set_theme(self, is_dark: bool):
        """Set the dialog theme."""
        self._is_dark_mode = is_dark
        self._apply_theme()
