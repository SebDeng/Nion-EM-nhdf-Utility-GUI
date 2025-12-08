"""
Line profile plotting widget using pyqtgraph.
"""

import pyqtgraph as pg
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFileDialog
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
import numpy as np
from typing import Optional, Dict, Any
import pyqtgraph.exporters


class LineProfileWidget(QWidget):
    """Widget that displays a line profile plot."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_dark_mode = True
        self._current_profile_id = None
        self._current_unit = "nm"  # Default unit
        self._current_data = None  # Store data for unit changes
        self._setup_ui()
        self._apply_theme()

    def _setup_ui(self):
        """Set up the plot widget."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # Title
        self._title_label = QLabel("Line Profile")
        self._title_label.setAlignment(Qt.AlignCenter)
        self._title_label.setStyleSheet("QLabel { font-weight: bold; font-size: 14px; padding: 4px; }")
        layout.addWidget(self._title_label)

        # Create plot widget
        self._plot_widget = pg.PlotWidget()
        self._plot_widget.setLabel('left', 'Intensity')
        self._plot_widget.setLabel('bottom', 'Distance', units='px')
        self._plot_widget.showGrid(x=True, y=True, alpha=0.3)

        # Create plot curve (will set color in _apply_theme)
        self._plot_curve = self._plot_widget.plot([], [])

        layout.addWidget(self._plot_widget)

        # Info label
        self._info_label = QLabel("")
        self._info_label.setAlignment(Qt.AlignCenter)
        self._info_label.setStyleSheet("QLabel { font-size: 12px; color: #888; padding: 2px; }")
        layout.addWidget(self._info_label)

    def update_profile(self, profile_id: str, data: Dict[str, Any]):
        """
        Update the plot with new profile data.

        Args:
            profile_id: Profile identifier
            data: Dictionary containing 'distances' and 'values' arrays, optionally 'calibration'
        """
        self._current_profile_id = profile_id
        self._current_data = data  # Store for unit changes

        if 'values' in data and 'distances' in data:
            values = np.array(data['values'])
            distances = np.array(data['distances']) if len(data['distances']) == len(values) else np.arange(len(values))

            # Convert distances based on current unit setting
            display_distances = distances.copy()
            unit_label = "px"

            if self._current_unit == "nm" and 'calibration' in data and data['calibration']:
                # Convert from pixels to nm
                display_distances = distances * data['calibration']
                unit_label = "nm"
            else:
                # Keep in pixels
                unit_label = "px"

            # Update plot
            self._plot_curve.setData(display_distances, values)

            # Update axis label with correct unit
            self._plot_widget.setLabel('bottom', 'Distance', units=unit_label)

            # Auto-range to fit data
            self._plot_widget.enableAutoRange()

            # Update info
            if len(values) > 0:
                mean_val = np.mean(values)
                std_val = np.std(values)
                min_val = np.min(values)
                max_val = np.max(values)

                # Include width info if available
                width_text = f" | Width: {data.get('width', 1):.0f}px" if 'width' in data and data['width'] > 1 else ""
                info_text = f"Mean: {mean_val:.3f} | Std: {std_val:.3f} | Min: {min_val:.3f} | Max: {max_val:.3f}{width_text}"
                self._info_label.setText(info_text)

                # Update title with endpoints if available
                if 'start' in data and 'end' in data:
                    start = data['start']
                    end = data['end']
                    self._title_label.setText(f"Line Profile: ({start[0]:.1f}, {start[1]:.1f}) → ({end[0]:.1f}, {end[1]:.1f})")
        else:
            # Clear if no valid data
            self.clear_plot()

    def clear_plot(self):
        """Clear the plot."""
        self._plot_curve.setData([], [])
        self._info_label.setText("")
        self._title_label.setText("Line Profile")
        self._current_profile_id = None
        self._current_data = None

    def set_unit(self, unit: str):
        """Change the display unit (px or nm)."""
        if unit != self._current_unit:
            self._current_unit = unit
            # Re-plot with new units if we have data
            if self._current_data and self._current_profile_id:
                self.update_profile(self._current_profile_id, self._current_data)

    def export_plot(self):
        """Export the current plot as an image file."""
        if not self._current_data:
            return

        # Open file dialog
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Line Profile Plot",
            "line_profile.png",
            "PNG Files (*.png);;JPEG Files (*.jpg *.jpeg);;All Files (*)"
        )

        if file_path:
            # Create an exporter based on file extension
            if file_path.lower().endswith(('.jpg', '.jpeg')):
                # Use ImageExporter for JPEG
                exporter = pg.exporters.ImageExporter(self._plot_widget.plotItem)
                exporter.parameters()['width'] = 800  # Set resolution
                exporter.parameters()['height'] = 600
                exporter.export(file_path)
            else:
                # Default to PNG
                if not file_path.lower().endswith('.png'):
                    file_path += '.png'
                exporter = pg.exporters.ImageExporter(self._plot_widget.plotItem)
                exporter.parameters()['width'] = 800
                exporter.parameters()['height'] = 600
                exporter.export(file_path)

            print(f"Line profile exported to: {file_path}")

    def set_theme(self, is_dark: bool):
        """Update the widget theme."""
        self._is_dark_mode = is_dark
        self._apply_theme()

    def _apply_theme(self):
        """Apply the current theme."""
        if self._is_dark_mode:
            # Dark theme
            self.setStyleSheet("""
                QWidget {
                    background-color: #2b2b2b;
                    color: #e0e0e0;
                }
            """)
            self._plot_widget.setBackground('#1e1e1e')

            # Update plot colors
            axis_color = '#888'
            self._plot_widget.getAxis('left').setPen(axis_color)
            self._plot_widget.getAxis('bottom').setPen(axis_color)
            self._plot_widget.getAxis('left').setTextPen(axis_color)
            self._plot_widget.getAxis('bottom').setTextPen(axis_color)

            # Yellow line for dark mode (good contrast)
            self._plot_curve.setPen(pg.mkPen(color='yellow', width=2))

            # Update grid for dark mode
            self._plot_widget.showGrid(x=True, y=True, alpha=0.3)

        else:
            # Light theme
            self.setStyleSheet("""
                QWidget {
                    background-color: #f5f5f5;
                    color: #333;
                }
            """)
            self._plot_widget.setBackground('w')

            # Update plot colors
            axis_color = '#333'
            self._plot_widget.getAxis('left').setPen(axis_color)
            self._plot_widget.getAxis('bottom').setPen(axis_color)
            self._plot_widget.getAxis('left').setTextPen(axis_color)
            self._plot_widget.getAxis('bottom').setTextPen(axis_color)

            # Dark blue line for light mode (good contrast with white background)
            self._plot_curve.setPen(pg.mkPen(color='#0055cc', width=2))

            # Update grid for light mode (slightly darker)
            self._plot_widget.showGrid(x=True, y=True, alpha=0.4)