"""
Line profile plotting widget using pyqtgraph.
"""

import pyqtgraph as pg
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFileDialog, QMessageBox, QHBoxLayout, QPushButton, QCheckBox
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QFont
import numpy as np
from typing import Optional, Dict, Any
import pyqtgraph.exporters
from src.gui.line_profile_export_dialog import LineProfileExportDialog


class LineProfileWidget(QWidget):
    """Widget that displays a line profile plot."""

    # Signal emitted when reference marker is added (index, x, y)
    reference_marker_added = Signal(int, float, float)
    # Signal to clear all reference markers
    reference_markers_cleared = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_dark_mode = True
        self._current_profile_id = None
        self._current_unit = "nm"  # Default unit
        self._current_data = None  # Store data for unit changes
        self._reference_lines = []  # List of reference lines
        self._reference_labels = []  # List of reference labels
        self._reference_enabled = False
        self._reference_colors = ['red', 'green', 'blue', 'magenta', 'cyan', 'orange']
        self._color_index = 0
        self._setup_ui()
        self._apply_theme()

    def _setup_ui(self):
        """Set up the plot widget."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # Title with reference controls
        title_layout = QHBoxLayout()

        self._title_label = QLabel("Line Profile")
        self._title_label.setAlignment(Qt.AlignCenter)
        self._title_label.setStyleSheet("QLabel { font-weight: bold; font-size: 14px; padding: 4px; }")
        title_layout.addWidget(self._title_label)

        # Reference line controls
        self._add_ref_btn = QPushButton("Add Reference")
        self._add_ref_btn.setCheckable(True)
        self._add_ref_btn.toggled.connect(self._toggle_reference_mode)
        self._add_ref_btn.setMaximumWidth(100)
        title_layout.addWidget(self._add_ref_btn)

        self._clear_ref_btn = QPushButton("Clear All")
        self._clear_ref_btn.clicked.connect(self._clear_all_references)
        self._clear_ref_btn.setMaximumWidth(80)
        title_layout.addWidget(self._clear_ref_btn)

        layout.addLayout(title_layout)

        # Create plot widget
        self._plot_widget = pg.PlotWidget()
        self._plot_widget.setLabel('left', 'Intensity')
        self._plot_widget.setLabel('bottom', 'Distance', units='px')
        self._plot_widget.showGrid(x=True, y=True, alpha=0.3)

        # Completely disable all mouse interactions except clicking
        self._plot_widget.setMouseEnabled(x=False, y=False)

        # Disable menu on right-click
        self._plot_widget.setMenuEnabled(False)

        # Get the ViewBox and disable all default mouse interactions
        vb = self._plot_widget.getViewBox()
        vb.setMouseMode(pg.ViewBox.PanMode)  # Set to pan mode but it's disabled
        vb.setMouseEnabled(x=False, y=False)

        # Disable wheel events for zooming
        vb.wheelEvent = lambda ev: None

        # Create plot curve (will set color in _apply_theme)
        self._plot_curve = self._plot_widget.plot([], [])

        # Create start marker (green dot at beginning of profile)
        self._start_marker = pg.ScatterPlotItem(
            pos=[],
            size=12,
            pen=pg.mkPen('green', width=2),
            brush=pg.mkBrush('green'),
            symbol='o'
        )
        self._plot_widget.addItem(self._start_marker)

        # Connect mouse click for adding reference lines
        self._plot_widget.scene().sigMouseClicked.connect(self._on_plot_clicked)

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

            # Update start marker to show beginning of profile
            if len(display_distances) > 0 and len(values) > 0:
                self._start_marker.setData(pos=[(display_distances[0], values[0])])

            # Update axis label with correct unit
            self._plot_widget.setLabel('bottom', 'Distance', units=unit_label)

            # Auto-range to fit data
            self._plot_widget.enableAutoRange()

            # Ensure mouse interactions remain disabled after data update
            self._plot_widget.setMouseEnabled(x=False, y=False)
            self._plot_widget.getViewBox().setMouseEnabled(x=False, y=False)

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
                    # Add visual indicators for start and end
                    self._title_label.setText(f"Line Profile: 🟢 ({start[0]:.1f}, {start[1]:.1f}) → 🔴 ({end[0]:.1f}, {end[1]:.1f})")
        else:
            # Clear if no valid data
            self.clear_plot()

    def clear_plot(self):
        """Clear the plot."""
        self._plot_curve.setData([], [])
        self._start_marker.setData(pos=[])
        self._info_label.setText("")
        self._title_label.setText("Line Profile")
        self._current_profile_id = None
        self._current_data = None
        # Also clear reference lines when clearing plot
        self._clear_all_references()

    def set_unit(self, unit: str):
        """Change the display unit (px or nm)."""
        if unit != self._current_unit:
            self._current_unit = unit
            # Re-plot with new units if we have data
            if self._current_data and self._current_profile_id:
                self.update_profile(self._current_profile_id, self._current_data)
                # Ensure mouse interactions remain disabled
                self._plot_widget.setMouseEnabled(x=False, y=False)
                self._plot_widget.getViewBox().setMouseEnabled(x=False, y=False)

    def export_plot(self):
        """Export the current plot as an image file or CSV with customization options."""
        if not self._current_data:
            QMessageBox.warning(self, "No Data", "No line profile data to export.")
            return

        # Prepare plot data for the dialog
        plot_data = self._current_data.copy()
        plot_data['unit'] = self._current_unit

        # Open export dialog (handles both image and CSV export)
        dialog = LineProfileExportDialog(plot_data, self)

        if dialog.exec_() == LineProfileExportDialog.Accepted:
            settings = dialog.get_export_settings()
            # Only export image if image type was selected (CSV is handled in dialog)
            if settings.get('export_type') == 'image':
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

    def _toggle_reference_mode(self, checked: bool):
        """Toggle reference line addition mode."""
        self._reference_enabled = checked
        if checked:
            self._add_ref_btn.setText("Click Plot")
            self._add_ref_btn.setStyleSheet("QPushButton { background-color: #4a90d9; }")
        else:
            self._add_ref_btn.setText("Add Reference")
            self._add_ref_btn.setStyleSheet("")

    def _clear_all_references(self):
        """Clear all reference lines."""
        # Remove all reference lines and labels
        for line in self._reference_lines:
            self._plot_widget.removeItem(line)
        for label in self._reference_labels:
            self._plot_widget.removeItem(label)

        self._reference_lines.clear()
        self._reference_labels.clear()
        self._color_index = 0

        # Emit signal to clear markers on image
        self.reference_markers_cleared.emit()

    def _on_plot_clicked(self, event):
        """Handle mouse clicks on the plot to add reference lines."""
        if not self._reference_enabled or not self._current_data:
            return

        # Get the position in data coordinates
        pos = event.scenePos()
        mouse_point = self._plot_widget.plotItem.vb.mapSceneToView(pos)
        x_pos = mouse_point.x()

        # Check if click is within data range
        distances = np.array(self._current_data['distances'])
        if len(distances) == 0:
            return

        # Apply unit conversion if needed
        display_distances = distances.copy()
        if self._current_unit == "nm" and 'calibration' in self._current_data and self._current_data['calibration']:
            display_distances = distances * self._current_data['calibration']

        # Check if click is within the data range
        if x_pos < display_distances[0] or x_pos > display_distances[-1]:
            return

        # Add a new reference line at this position
        self._add_reference_at_position(x_pos)

        # Turn off reference mode after adding
        self._add_ref_btn.setChecked(False)
        self._reference_enabled = False

    def _add_reference_at_position(self, x_pos):
        """Add a reference line at the specified x position."""
        if not self._current_data:
            return

        # Get the next color
        color = self._reference_colors[self._color_index % len(self._reference_colors)]
        self._color_index += 1

        # Create a new reference line (non-movable)
        ref_line = pg.InfiniteLine(
            pos=x_pos,
            angle=90,
            movable=False,  # Fixed position
            pen=pg.mkPen(color=color, width=2, style=Qt.DashLine)
        )
        self._plot_widget.addItem(ref_line)
        self._reference_lines.append(ref_line)

        # Find the corresponding intensity value
        values = np.array(self._current_data['values'])
        distances = np.array(self._current_data['distances'])

        # Apply unit conversion
        display_distances = distances.copy()
        if self._current_unit == "nm" and 'calibration' in self._current_data and self._current_data['calibration']:
            display_distances = distances * self._current_data['calibration']

        # Find closest data point
        idx = np.argmin(np.abs(display_distances - x_pos))

        if 0 <= idx < len(values):
            intensity = values[idx]
            distance_val = display_distances[idx]

            # Create label
            unit_str = "nm" if self._current_unit == "nm" else "px"
            label_text = f"{distance_val:.1f} {unit_str}\n{intensity:.1f}"

            ref_label = pg.TextItem(
                text=label_text,
                color=color,
                anchor=(0, 1)
            )
            ref_label.setPos(x_pos, intensity)
            self._plot_widget.addItem(ref_label)
            self._reference_labels.append(ref_label)

            # Calculate image position and emit signal
            if 'start' in self._current_data and 'end' in self._current_data:
                start = np.array(self._current_data['start'])
                end = np.array(self._current_data['end'])

                # Calculate position along line (0 to 1)
                t = idx / (len(distances) - 1) if len(distances) > 1 else 0

                # Interpolate position on image
                image_x = start[0] + t * (end[0] - start[0])
                image_y = start[1] + t * (end[1] - start[1])

                # Emit signal with position info and color index
                self.reference_marker_added.emit(self._color_index - 1, image_x, image_y)

