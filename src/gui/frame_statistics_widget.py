"""
Frame statistics widget for displaying time series of frame statistics.
Shows Mean, Sum, Std, Min, Max per frame across a sequence.
"""

import pyqtgraph as pg
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QCheckBox
)
from PySide6.QtCore import Qt, Signal
import numpy as np
from typing import Optional, Dict, Any


class FrameStatisticsWidget(QWidget):
    """Widget that displays frame statistics as a time series plot."""

    # Signals
    roi_mode_requested = Signal()  # Request to create/toggle ROI on image
    roi_clear_requested = Signal()  # Request to clear ROI
    export_requested = Signal()  # Request to export data

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_dark_mode = True
        self._current_data: Optional[Dict[str, Any]] = None
        self._selected_stat = 'mean'  # Default statistic to display
        self._roi_active = False
        self._setup_ui()
        self._apply_theme()

    def _setup_ui(self):
        """Set up the widget UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # Title and controls row
        title_layout = QHBoxLayout()

        self._title_label = QLabel("Frame Statistics")
        self._title_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._title_label.setStyleSheet("QLabel { font-weight: bold; font-size: 14px; padding: 4px; }")
        title_layout.addWidget(self._title_label)

        title_layout.addStretch()

        # Statistic selector
        stat_label = QLabel("Show:")
        title_layout.addWidget(stat_label)

        self._stat_combo = QComboBox()
        self._stat_combo.addItems(['Mean', 'Sum (Integral)', 'Std', 'Min', 'Max'])
        self._stat_combo.setCurrentIndex(0)
        self._stat_combo.setFixedWidth(120)
        self._stat_combo.currentIndexChanged.connect(self._on_stat_changed)
        title_layout.addWidget(self._stat_combo)

        # ROI toggle button
        self._roi_btn = QPushButton("ROI")
        self._roi_btn.setCheckable(True)
        self._roi_btn.setChecked(False)
        self._roi_btn.setFixedWidth(50)
        self._roi_btn.setToolTip("Draw rectangle ROI to analyze a region")
        self._roi_btn.toggled.connect(self._on_roi_toggled)
        title_layout.addWidget(self._roi_btn)

        # Export button
        self._export_btn = QPushButton("Export")
        self._export_btn.setFixedWidth(60)
        self._export_btn.setToolTip("Export statistics to CSV or image")
        self._export_btn.clicked.connect(self._on_export_clicked)
        title_layout.addWidget(self._export_btn)

        layout.addLayout(title_layout)

        # Create plot widget
        self._plot_widget = pg.PlotWidget()
        self._plot_widget.setLabel('left', 'Mean Intensity')
        self._plot_widget.setLabel('bottom', 'Frame Number')
        self._plot_widget.showGrid(x=True, y=True, alpha=0.3)

        # Enable mouse for zooming/panning
        self._plot_widget.setMouseEnabled(x=True, y=True)
        self._plot_widget.setMenuEnabled(True)

        # Create the data curve
        self._data_curve = pg.PlotCurveItem(
            pen=pg.mkPen(color=(100, 180, 255), width=2)
        )
        self._plot_widget.addItem(self._data_curve)

        # Create scatter points for data markers
        self._scatter_item = pg.ScatterPlotItem(
            size=6,
            pen=pg.mkPen(color=(100, 180, 255)),
            brush=pg.mkBrush(color=(100, 180, 255, 200))
        )
        self._plot_widget.addItem(self._scatter_item)

        layout.addWidget(self._plot_widget)

        # Info label row
        self._info_label = QLabel("")
        self._info_label.setAlignment(Qt.AlignCenter)
        self._info_label.setStyleSheet("QLabel { font-size: 11px; color: #888; padding: 2px; }")
        layout.addWidget(self._info_label)

    def update_statistics(self, stats_data: Dict[str, Any]):
        """
        Update the plot with new frame statistics.

        Args:
            stats_data: Dictionary containing:
                - 'frame_numbers': np.ndarray of frame indices
                - 'mean': np.ndarray of mean values per frame
                - 'sum': np.ndarray of sum values per frame
                - 'std': np.ndarray of std values per frame
                - 'min': np.ndarray of min values per frame
                - 'max': np.ndarray of max values per frame
                - 'roi_bounds': Optional tuple (x, y, w, h) if ROI active
                - 'total_frames': int
                - 'file_name': str (optional)
        """
        if stats_data is None:
            self.clear_statistics()
            return

        self._current_data = stats_data
        self._update_plot()
        self._update_info_label()

    def _update_plot(self):
        """Update the plot with current data and selected statistic."""
        if self._current_data is None:
            return

        frame_numbers = self._current_data.get('frame_numbers', np.array([]))
        if len(frame_numbers) == 0:
            self.clear_statistics()
            return

        # Get the selected statistic
        stat_key = self._get_stat_key()
        values = self._current_data.get(stat_key, np.array([]))

        if len(values) == 0:
            return

        # Update plot data
        self._data_curve.setData(frame_numbers, values)
        self._scatter_item.setData(frame_numbers, values)

        # Update Y-axis label
        y_labels = {
            'mean': 'Mean Intensity',
            'sum': 'Sum (Integral)',
            'std': 'Std Deviation',
            'min': 'Min Intensity',
            'max': 'Max Intensity'
        }
        self._plot_widget.setLabel('left', y_labels.get(stat_key, stat_key.capitalize()))

        # Auto-range to fit data
        self._plot_widget.enableAutoRange()

    def _get_stat_key(self) -> str:
        """Get the dictionary key for the selected statistic."""
        index = self._stat_combo.currentIndex()
        keys = ['mean', 'sum', 'std', 'min', 'max']
        return keys[index] if index < len(keys) else 'mean'

    def _update_info_label(self):
        """Update the info label with summary statistics."""
        if self._current_data is None:
            self._info_label.setText("")
            return

        total_frames = self._current_data.get('total_frames', 0)
        roi_bounds = self._current_data.get('roi_bounds')

        # Get selected statistic values for summary
        stat_key = self._get_stat_key()
        values = self._current_data.get(stat_key, np.array([]))

        if len(values) == 0:
            self._info_label.setText("")
            return

        # Compute summary of the time series
        mean_val = np.mean(values)
        std_val = np.std(values)
        min_val = np.min(values)
        max_val = np.max(values)

        # Build info text
        roi_text = "Full Frame"
        if roi_bounds:
            x, y, w, h = roi_bounds
            roi_text = f"ROI: ({x:.0f}, {y:.0f}, {w:.0f}x{h:.0f})"

        info_text = (
            f"Frames: {total_frames} | {roi_text} | "
            f"Mean: {mean_val:.2f} | Std: {std_val:.2f} | "
            f"Range: [{min_val:.2f}, {max_val:.2f}]"
        )
        self._info_label.setText(info_text)

    def _on_stat_changed(self, index: int):
        """Handle statistic dropdown change."""
        self._update_plot()
        self._update_info_label()

    def _on_roi_toggled(self, checked: bool):
        """Handle ROI button toggle."""
        self._roi_active = checked
        if checked:
            self.roi_mode_requested.emit()
        else:
            self.roi_clear_requested.emit()

    def _on_export_clicked(self):
        """Handle export button click."""
        self.export_requested.emit()

    def set_roi_active(self, active: bool):
        """Set the ROI button state (called externally)."""
        self._roi_btn.blockSignals(True)
        self._roi_btn.setChecked(active)
        self._roi_active = active
        self._roi_btn.blockSignals(False)

    def clear_statistics(self):
        """Clear the display."""
        self._data_curve.setData([], [])
        self._scatter_item.setData([])
        self._info_label.setText("")
        self._current_data = None

    def get_current_data(self) -> Optional[Dict[str, Any]]:
        """Get the current statistics data for export."""
        return self._current_data

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
                QComboBox {
                    background-color: #3a3a3a;
                    border: 1px solid #555;
                    color: #e0e0e0;
                    padding: 4px;
                }
                QComboBox::drop-down {
                    border: none;
                }
                QComboBox QAbstractItemView {
                    background-color: #3a3a3a;
                    color: #e0e0e0;
                    selection-background-color: #0d7377;
                }
                QPushButton {
                    background-color: #3a3a3a;
                    border: 1px solid #555;
                    color: #e0e0e0;
                    padding: 4px 8px;
                    border-radius: 3px;
                }
                QPushButton:hover {
                    background-color: #4a4a4a;
                }
                QPushButton:checked {
                    background-color: #0d7377;
                    border-color: #14a085;
                }
                QPushButton:pressed {
                    background-color: #0a5d61;
                }
            """)
            self._plot_widget.setBackground('#1e1e1e')

            # Update plot colors
            axis_color = '#888'
            self._plot_widget.getAxis('left').setPen(axis_color)
            self._plot_widget.getAxis('bottom').setPen(axis_color)
            self._plot_widget.getAxis('left').setTextPen(axis_color)
            self._plot_widget.getAxis('bottom').setTextPen(axis_color)

            # Update curve color
            self._data_curve.setPen(pg.mkPen(color=(100, 180, 255), width=2))
            self._scatter_item.setPen(pg.mkPen(color=(100, 180, 255)))
            self._scatter_item.setBrush(pg.mkBrush(color=(100, 180, 255, 200)))

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
                QComboBox {
                    background-color: white;
                    border: 1px solid #ccc;
                    color: #333;
                    padding: 4px;
                }
                QComboBox::drop-down {
                    border: none;
                }
                QComboBox QAbstractItemView {
                    background-color: white;
                    color: #333;
                    selection-background-color: #14a085;
                }
                QPushButton {
                    background-color: white;
                    border: 1px solid #ccc;
                    color: #333;
                    padding: 4px 8px;
                    border-radius: 3px;
                }
                QPushButton:hover {
                    background-color: #e0e0e0;
                }
                QPushButton:checked {
                    background-color: #14a085;
                    border-color: #0d7377;
                    color: white;
                }
                QPushButton:pressed {
                    background-color: #0d7377;
                }
            """)
            self._plot_widget.setBackground('w')

            # Update plot colors
            axis_color = '#333'
            self._plot_widget.getAxis('left').setPen(axis_color)
            self._plot_widget.getAxis('bottom').setPen(axis_color)
            self._plot_widget.getAxis('left').setTextPen(axis_color)
            self._plot_widget.getAxis('bottom').setTextPen(axis_color)

            # Update curve color
            self._data_curve.setPen(pg.mkPen(color=(50, 100, 200), width=2))
            self._scatter_item.setPen(pg.mkPen(color=(50, 100, 200)))
            self._scatter_item.setBrush(pg.mkBrush(color=(50, 100, 200, 200)))

            # Update grid
            self._plot_widget.showGrid(x=True, y=True, alpha=0.4)
