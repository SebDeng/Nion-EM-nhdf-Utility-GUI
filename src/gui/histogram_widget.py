"""
Histogram widget for displaying image intensity distribution using pyqtgraph.
"""

import pyqtgraph as pg
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox, QCheckBox
from PySide6.QtCore import Qt, Signal
import numpy as np
from typing import Optional, Dict, Any


class HistogramWidget(QWidget):
    """Widget that displays a histogram of image intensities."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_dark_mode = True
        self._current_data = None
        self._num_bins = 256
        self._log_scale = False
        self._setup_ui()
        self._apply_theme()

    def _setup_ui(self):
        """Set up the histogram widget."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # Title and controls
        title_layout = QHBoxLayout()

        self._title_label = QLabel("Intensity Histogram")
        self._title_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._title_label.setStyleSheet("QLabel { font-weight: bold; font-size: 14px; padding: 4px; }")
        title_layout.addWidget(self._title_label)

        title_layout.addStretch()

        # Bins control
        bins_label = QLabel("Bins:")
        title_layout.addWidget(bins_label)

        self._bins_spinbox = QSpinBox()
        self._bins_spinbox.setMinimum(16)
        self._bins_spinbox.setMaximum(1024)
        self._bins_spinbox.setValue(256)
        self._bins_spinbox.setSingleStep(16)
        self._bins_spinbox.setFixedWidth(70)
        self._bins_spinbox.valueChanged.connect(self._on_bins_changed)
        title_layout.addWidget(self._bins_spinbox)

        # Log scale checkbox
        self._log_checkbox = QCheckBox("Log Scale")
        self._log_checkbox.setChecked(False)
        self._log_checkbox.toggled.connect(self._on_log_scale_changed)
        title_layout.addWidget(self._log_checkbox)

        layout.addLayout(title_layout)

        # Create plot widget
        self._plot_widget = pg.PlotWidget()
        self._plot_widget.setLabel('left', 'Count')
        self._plot_widget.setLabel('bottom', 'Intensity')
        self._plot_widget.showGrid(x=True, y=True, alpha=0.3)

        # Enable mouse for zooming/panning in histogram (useful for exploration)
        self._plot_widget.setMouseEnabled(x=True, y=True)
        self._plot_widget.setMenuEnabled(True)

        # Create histogram bar graph (initialize without stepMode, set when data is available)
        self._histogram_item = pg.PlotCurveItem(
            fillLevel=0,
            brush=pg.mkBrush(color=(100, 150, 255, 150))
        )
        self._plot_widget.addItem(self._histogram_item)

        # Create vertical lines for display range indicators
        self._min_line = pg.InfiniteLine(
            pos=0,
            angle=90,
            movable=False,
            pen=pg.mkPen(color='green', width=2, style=Qt.DashLine)
        )
        self._max_line = pg.InfiniteLine(
            pos=1,
            angle=90,
            movable=False,
            pen=pg.mkPen(color='red', width=2, style=Qt.DashLine)
        )
        self._plot_widget.addItem(self._min_line)
        self._plot_widget.addItem(self._max_line)
        self._min_line.setVisible(False)
        self._max_line.setVisible(False)

        layout.addWidget(self._plot_widget)

        # Statistics info label
        self._info_label = QLabel("")
        self._info_label.setAlignment(Qt.AlignCenter)
        self._info_label.setStyleSheet("QLabel { font-size: 11px; color: #888; padding: 2px; }")
        layout.addWidget(self._info_label)

    def update_histogram(self, image_data: np.ndarray, display_range: Optional[tuple] = None):
        """
        Update the histogram with new image data.

        Args:
            image_data: 2D numpy array of image intensities
            display_range: Optional tuple of (min, max) display range to show as vertical lines
        """
        if image_data is None or image_data.size == 0:
            self.clear_histogram()
            return

        self._current_data = image_data.flatten()

        # Calculate histogram
        self._compute_and_display_histogram()

        # Update display range indicators
        if display_range:
            self._min_line.setPos(display_range[0])
            self._max_line.setPos(display_range[1])
            self._min_line.setVisible(True)
            self._max_line.setVisible(True)
        else:
            self._min_line.setVisible(False)
            self._max_line.setVisible(False)

        # Update statistics
        self._update_statistics()

    def _compute_and_display_histogram(self):
        """Compute and display the histogram."""
        if self._current_data is None:
            return

        # Filter out NaN values
        data = self._current_data[~np.isnan(self._current_data)]
        if len(data) == 0:
            return

        # Compute histogram
        counts, bin_edges = np.histogram(data, bins=self._num_bins)

        # Apply log scale if enabled
        if self._log_scale:
            counts = np.log10(counts + 1)  # +1 to avoid log(0)

        # Plot histogram using step mode
        # Use bin edges for x-axis (stepMode needs n+1 x values for n y values)
        self._histogram_item.setData(bin_edges, counts, stepMode='center')
        self._histogram_item.setVisible(True)

        # Update y-axis label
        if self._log_scale:
            self._plot_widget.setLabel('left', 'Log(Count + 1)')
        else:
            self._plot_widget.setLabel('left', 'Count')

        # Auto-range to fit
        self._plot_widget.enableAutoRange()

    def _update_statistics(self):
        """Update the statistics label."""
        if self._current_data is None:
            self._info_label.setText("")
            return

        data = self._current_data[~np.isnan(self._current_data)]
        if len(data) == 0:
            self._info_label.setText("")
            return

        mean_val = np.mean(data)
        std_val = np.std(data)
        min_val = np.min(data)
        max_val = np.max(data)
        median_val = np.median(data)

        info_text = f"Min: {min_val:.2f} | Max: {max_val:.2f} | Mean: {mean_val:.2f} | Median: {median_val:.2f} | Std: {std_val:.2f}"
        self._info_label.setText(info_text)

    def _on_bins_changed(self, value: int):
        """Handle bins spinbox change."""
        self._num_bins = value
        if self._current_data is not None:
            self._compute_and_display_histogram()

    def _on_log_scale_changed(self, checked: bool):
        """Handle log scale checkbox change."""
        self._log_scale = checked
        if self._current_data is not None:
            self._compute_and_display_histogram()

    def clear_histogram(self):
        """Clear the histogram display."""
        # Clear the histogram - with stepMode=True, X must be len(Y)+1
        # Cannot use empty arrays, so use dummy data and hide
        self._histogram_item.setData([0, 1], [0])
        self._histogram_item.setVisible(False)
        self._info_label.setText("")
        self._current_data = None
        self._min_line.setVisible(False)
        self._max_line.setVisible(False)

    def set_display_range(self, min_val: float, max_val: float):
        """
        Update the display range indicator lines.

        Args:
            min_val: Minimum display value
            max_val: Maximum display value
        """
        self._min_line.setPos(min_val)
        self._max_line.setPos(max_val)
        self._min_line.setVisible(True)
        self._max_line.setVisible(True)

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
                QLabel {
                    color: #e0e0e0;
                }
                QSpinBox {
                    background-color: #3a3a3a;
                    border: 1px solid #555;
                    color: #e0e0e0;
                    padding: 2px;
                }
                QCheckBox {
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

            # Update histogram fill color
            self._histogram_item.setBrush(pg.mkBrush(color=(100, 180, 255, 150)))
            self._histogram_item.setPen(pg.mkPen(color=(100, 180, 255, 200), width=1))

            # Update grid
            self._plot_widget.showGrid(x=True, y=True, alpha=0.3)

        else:
            # Light theme
            self.setStyleSheet("""
                QWidget {
                    background-color: #f5f5f5;
                    color: #333;
                }
                QLabel {
                    color: #333;
                }
                QSpinBox {
                    background-color: white;
                    border: 1px solid #ccc;
                    color: #333;
                    padding: 2px;
                }
                QCheckBox {
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

            # Update histogram fill color
            self._histogram_item.setBrush(pg.mkBrush(color=(50, 100, 200, 150)))
            self._histogram_item.setPen(pg.mkPen(color=(50, 100, 200, 200), width=1))

            # Update grid
            self._plot_widget.showGrid(x=True, y=True, alpha=0.4)
