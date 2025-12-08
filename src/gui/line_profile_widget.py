"""
Line profile plotting widget using pyqtgraph.
"""

import pyqtgraph as pg
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFileDialog, QMessageBox
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QFont
import numpy as np
from typing import Optional, Dict, Any
import pyqtgraph.exporters
from src.gui.line_profile_export_dialog import LineProfileExportDialog


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
        """Export the current plot as an image file with customization options."""
        if not self._current_data:
            QMessageBox.warning(self, "No Data", "No line profile data to export.")
            return

        # Prepare plot data for the dialog
        plot_data = self._current_data.copy()
        plot_data['unit'] = self._current_unit

        # Open export dialog
        dialog = LineProfileExportDialog(plot_data, self)

        if dialog.exec_() == LineProfileExportDialog.Accepted:
            settings = dialog.get_export_settings()
            self._export_with_settings(settings)

    def _export_with_settings(self, settings: Dict[str, Any]):
        """Export the plot with custom settings."""
        try:
            # Create a new plot widget for export with custom settings
            export_plot = pg.PlotWidget()

            # Apply theme settings
            if settings['theme'] == 'light':
                export_plot.setBackground('w')
                text_color = 'k'
                grid_color = (100, 100, 100)
            elif settings['theme'] == 'dark':
                export_plot.setBackground('#1e1e1e')
                text_color = 'w'
                grid_color = (200, 200, 200)
            else:
                # Use current theme
                export_plot.setBackground(self._plot_widget.backgroundBrush().color())
                text_color = 'w' if self._is_dark_mode else 'k'
                grid_color = (200, 200, 200) if self._is_dark_mode else (100, 100, 100)

            # Set title and labels
            export_plot.setTitle(settings['title'], color=text_color, size='14pt')

            # Determine unit for x-axis
            unit_label = self._current_unit if hasattr(self, '_current_unit') else 'px'
            export_plot.setLabel('left', settings['y_label'], color=text_color)
            export_plot.setLabel('bottom', settings['x_label'], units=unit_label, color=text_color)

            # Set grid
            if settings['show_grid']:
                export_plot.showGrid(x=True, y=True, alpha=settings['grid_alpha'])

            # Prepare data
            if 'values' in self._current_data and 'distances' in self._current_data:
                values = np.array(self._current_data['values'])
                distances = np.array(self._current_data['distances'])

                # Apply unit conversion
                if self._current_unit == "nm" and 'calibration' in self._current_data and self._current_data['calibration']:
                    distances = distances * self._current_data['calibration']

                # Plot the data with custom line style
                pen = pg.mkPen(color=settings['line_color'], width=settings['line_width'])
                export_plot.plot(distances, values, pen=pen)

                # Set axis ranges if specified
                if settings['x_range']:
                    export_plot.setXRange(settings['x_range'][0], settings['x_range'][1])
                else:
                    export_plot.enableAutoRange(axis='x')

                if settings['y_range']:
                    export_plot.setYRange(settings['y_range'][0], settings['y_range'][1])
                else:
                    export_plot.enableAutoRange(axis='y')

                # Add statistics text if requested
                if settings['show_statistics'] and len(values) > 0:
                    mean_val = np.mean(values)
                    std_val = np.std(values)
                    min_val = np.min(values)
                    max_val = np.max(values)

                    stats_text = f"Mean: {mean_val:.3f} | Std: {std_val:.3f} | Min: {min_val:.3f} | Max: {max_val:.3f}"

                    # Add text item at the bottom
                    text_item = pg.TextItem(stats_text, color=text_color, anchor=(0.5, 1))
                    text_item.setFont(QFont("Arial", 10))
                    export_plot.addItem(text_item)

                    # Position at bottom center
                    view_range = export_plot.viewRange()
                    if view_range:
                        x_center = (view_range[0][0] + view_range[0][1]) / 2
                        y_bottom = view_range[1][0] + (view_range[1][1] - view_range[1][0]) * 0.05
                        text_item.setPos(x_center, y_bottom)

            # Export the plot
            exporter = pg.exporters.ImageExporter(export_plot.plotItem)
            exporter.parameters()['width'] = settings['width']
            exporter.parameters()['height'] = settings['height']
            exporter.export(settings['file_path'])

            # Show success message
            QMessageBox.information(
                self,
                "Export Successful",
                f"Line profile plot exported to:\n{settings['file_path']}"
            )

        except Exception as e:
            QMessageBox.critical(
                self,
                "Export Failed",
                f"Failed to export plot:\n{str(e)}"
            )

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