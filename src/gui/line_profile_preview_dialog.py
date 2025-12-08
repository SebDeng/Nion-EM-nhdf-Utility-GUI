"""
Preview dialog for line profile plot export.
"""

from PySide6.QtWidgets import QDialog, QVBoxLayout, QPushButton
from PySide6.QtCore import Qt
import pyqtgraph as pg
import numpy as np
from typing import Dict, Any


class LineProfilePreviewDialog(QDialog):
    """Dialog showing a preview of the line profile plot with export settings."""

    def __init__(self, plot_data: Dict[str, Any], settings: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.plot_data = plot_data
        self.settings = settings
        self.setWindowTitle("Line Profile Preview")
        self.setModal(True)
        self.resize(settings.get('width', 800), settings.get('height', 600) + 50)

        self._setup_ui()
        self._apply_settings()

    def _setup_ui(self):
        """Set up the preview UI."""
        layout = QVBoxLayout(self)

        # Create plot widget
        self.plot_widget = pg.PlotWidget()
        layout.addWidget(self.plot_widget)

        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    def _apply_settings(self):
        """Apply the export settings to the preview plot."""
        settings = self.settings

        # Apply theme settings
        if settings['theme'] == 'light':
            self.plot_widget.setBackground('w')
            text_color = 'k'
        elif settings['theme'] == 'dark':
            self.plot_widget.setBackground('#1e1e1e')
            text_color = 'w'
        else:
            # Default to dark
            self.plot_widget.setBackground('#1e1e1e')
            text_color = 'w'

        # Set title and labels
        self.plot_widget.setTitle(settings['title'], color=text_color, size='14pt')
        self.plot_widget.setLabel('left', settings['y_label'], color=text_color)

        # X-axis with unit
        x_unit = self.plot_data.get('unit', 'px')
        self.plot_widget.setLabel('bottom', settings['x_label'], units=x_unit, color=text_color)

        # Set grid
        if settings['show_grid']:
            self.plot_widget.showGrid(x=True, y=True, alpha=settings['grid_alpha'])

        # Plot the data
        if 'values' in self.plot_data and 'distances' in self.plot_data:
            values = np.array(self.plot_data['values'])
            distances = np.array(self.plot_data['distances'])

            # Apply unit conversion if needed
            if x_unit == 'nm' and 'calibration' in self.plot_data and self.plot_data['calibration']:
                distances = distances * self.plot_data['calibration']

            # Plot with custom line style
            pen = pg.mkPen(color=settings['line_color'], width=settings['line_width'])
            self.plot_widget.plot(distances, values, pen=pen)

            # Set axis ranges if specified
            if settings['x_range']:
                self.plot_widget.setXRange(settings['x_range'][0], settings['x_range'][1])
            else:
                self.plot_widget.enableAutoRange(axis='x')

            if settings['y_range']:
                self.plot_widget.setYRange(settings['y_range'][0], settings['y_range'][1])
            else:
                self.plot_widget.enableAutoRange(axis='y')

            # Add statistics if requested
            if settings['show_statistics'] and len(values) > 0:
                self._add_statistics(values, text_color)

    def _add_statistics(self, values, text_color):
        """Add statistics text to the plot."""
        mean_val = np.mean(values)
        std_val = np.std(values)
        min_val = np.min(values)
        max_val = np.max(values)

        stats_text = f"Mean: {mean_val:.3f} | Std: {std_val:.3f} | Min: {min_val:.3f} | Max: {max_val:.3f}"

        # Create text item
        from PySide6.QtGui import QFont
        text_item = pg.TextItem(stats_text, color=text_color, anchor=(0.5, 1))
        text_item.setFont(QFont("Arial", 10))
        self.plot_widget.addItem(text_item)

        # Position at bottom center
        view_range = self.plot_widget.viewRange()
        if view_range:
            x_center = (view_range[0][0] + view_range[0][1]) / 2
            y_bottom = view_range[1][0] + (view_range[1][1] - view_range[1][0]) * 0.05
            text_item.setPos(x_center, y_bottom)