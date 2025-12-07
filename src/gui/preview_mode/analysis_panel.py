"""
Analysis results panel for displaying analysis data.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTabWidget, QTextEdit, QTreeWidget,
    QTreeWidgetItem, QHeaderView, QLabel
)
from PySide6.QtCore import Qt, Signal
from typing import Optional, Dict, Any, List
import numpy as np


class AnalysisResultsPanel(QWidget):
    """
    Panel for displaying analysis results from various tools.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_dark_mode = True
        self._setup_ui()
        self._apply_theme()

    def _setup_ui(self):
        """Set up the UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Tab widget for different result types
        self._tabs = QTabWidget()
        layout.addWidget(self._tabs)

        # Line Profiles tab
        self._line_profiles_widget = QTreeWidget()
        self._line_profiles_widget.setHeaderLabels(["Property", "Value"])
        self._line_profiles_widget.header().setStretchLastSection(True)
        self._tabs.addTab(self._line_profiles_widget, "Line Profiles")

        # ROI Statistics tab
        self._roi_stats_widget = QTreeWidget()
        self._roi_stats_widget.setHeaderLabels(["ROI", "Mean", "Std", "Min", "Max", "Area"])
        self._roi_stats_widget.header().setStretchLastSection(False)
        self._tabs.addTab(self._roi_stats_widget, "ROI Statistics")

        # Measurements tab
        self._measurements_widget = QTreeWidget()
        self._measurements_widget.setHeaderLabels(["Measurement", "Value", "Unit"])
        self._measurements_widget.header().setStretchLastSection(False)
        self._tabs.addTab(self._measurements_widget, "Measurements")

        # Summary tab (text view)
        self._summary_widget = QTextEdit()
        self._summary_widget.setReadOnly(True)
        self._tabs.addTab(self._summary_widget, "Summary")

        # Start with summary tab
        self._tabs.setCurrentIndex(3)

    def clear_all(self):
        """Clear all analysis results."""
        self._line_profiles_widget.clear()
        self._roi_stats_widget.clear()
        self._measurements_widget.clear()
        self._summary_widget.clear()

    def add_line_profile(self, profile_id: str, data: Dict[str, Any]):
        """
        Add a line profile result.

        Args:
            profile_id: Unique identifier for the profile
            data: Dictionary with profile data (start, end, values, distance, etc.)
        """
        item = QTreeWidgetItem(self._line_profiles_widget)
        item.setText(0, f"Profile {profile_id}")
        item.setExpanded(True)

        # Add sub-items for profile properties
        if 'start' in data and 'end' in data:
            start_item = QTreeWidgetItem(item)
            start_item.setText(0, "Start")
            start_item.setText(1, f"({data['start'][0]:.1f}, {data['start'][1]:.1f})")

            end_item = QTreeWidgetItem(item)
            end_item.setText(0, "End")
            end_item.setText(1, f"({data['end'][0]:.1f}, {data['end'][1]:.1f})")

        if 'distance' in data:
            dist_item = QTreeWidgetItem(item)
            dist_item.setText(0, "Distance")
            dist_item.setText(1, f"{data['distance']:.2f} {data.get('unit', 'px')}")

        if 'values' in data and len(data['values']) > 0:
            values = data['values']
            stats_item = QTreeWidgetItem(item)
            stats_item.setText(0, "Statistics")
            stats_item.setExpanded(True)

            mean_item = QTreeWidgetItem(stats_item)
            mean_item.setText(0, "Mean")
            mean_item.setText(1, f"{np.mean(values):.3f}")

            std_item = QTreeWidgetItem(stats_item)
            std_item.setText(0, "Std Dev")
            std_item.setText(1, f"{np.std(values):.3f}")

            min_item = QTreeWidgetItem(stats_item)
            min_item.setText(0, "Min")
            min_item.setText(1, f"{np.min(values):.3f}")

            max_item = QTreeWidgetItem(stats_item)
            max_item.setText(0, "Max")
            max_item.setText(1, f"{np.max(values):.3f}")

        # Switch to line profiles tab
        self._tabs.setCurrentIndex(0)

    def add_roi_statistics(self, roi_id: str, stats: Dict[str, Any]):
        """
        Add ROI statistics.

        Args:
            roi_id: Unique identifier for the ROI
            stats: Dictionary with statistics (mean, std, min, max, area, etc.)
        """
        item = QTreeWidgetItem(self._roi_stats_widget)
        item.setText(0, roi_id)
        item.setText(1, f"{stats.get('mean', 0):.3f}")
        item.setText(2, f"{stats.get('std', 0):.3f}")
        item.setText(3, f"{stats.get('min', 0):.3f}")
        item.setText(4, f"{stats.get('max', 0):.3f}")
        item.setText(5, f"{stats.get('area', 0):.1f}")

        # Switch to ROI stats tab
        self._tabs.setCurrentIndex(1)

    def add_measurement(self, measurement_id: str, value: float, unit: str, measurement_type: str):
        """
        Add a measurement result.

        Args:
            measurement_id: Unique identifier for the measurement
            value: The measured value
            unit: Unit of measurement
            measurement_type: Type of measurement (distance, angle, etc.)
        """
        item = QTreeWidgetItem(self._measurements_widget)
        item.setText(0, f"{measurement_type} {measurement_id}")
        item.setText(1, f"{value:.3f}")
        item.setText(2, unit)

        # Switch to measurements tab
        self._tabs.setCurrentIndex(2)

    def update_summary(self, panel_id: str, summary_text: str):
        """
        Update the summary text for a panel.

        Args:
            panel_id: Identifier of the panel
            summary_text: Summary text to display
        """
        current_text = self._summary_widget.toPlainText()
        if current_text:
            self._summary_widget.setText(current_text + "\n\n" + f"=== Panel: {panel_id} ===\n{summary_text}")
        else:
            self._summary_widget.setText(f"=== Panel: {panel_id} ===\n{summary_text}")

    def set_theme(self, is_dark: bool):
        """Update the panel theme."""
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
                QTabWidget::pane {
                    border: 1px solid #555;
                    background-color: #2b2b2b;
                }
                QTabBar::tab {
                    background-color: #3a3a3a;
                    color: #e0e0e0;
                    padding: 8px 12px;
                    margin-right: 2px;
                }
                QTabBar::tab:selected {
                    background-color: #0d7377;
                    color: white;
                }
                QTreeWidget {
                    background-color: #1e1e1e;
                    border: none;
                    outline: none;
                }
                QTreeWidget::item {
                    padding: 4px;
                }
                QTreeWidget::item:selected {
                    background-color: #0d7377;
                }
                QTextEdit {
                    background-color: #1e1e1e;
                    border: none;
                }
                QHeaderView::section {
                    background-color: #3a3a3a;
                    border: none;
                    padding: 4px 8px;
                    border-right: 1px solid #555;
                }
            """)
        else:
            # Light theme
            self.setStyleSheet("""
                QWidget {
                    background-color: #f5f5f5;
                    color: #333;
                }
                QTabWidget::pane {
                    border: 1px solid #ccc;
                    background-color: #f5f5f5;
                }
                QTabBar::tab {
                    background-color: #e0e0e0;
                    color: #333;
                    padding: 8px 12px;
                    margin-right: 2px;
                }
                QTabBar::tab:selected {
                    background-color: #14a085;
                    color: white;
                }
                QTreeWidget {
                    background-color: white;
                    border: none;
                    outline: none;
                }
                QTreeWidget::item {
                    padding: 4px;
                }
                QTreeWidget::item:selected {
                    background-color: #14a085;
                    color: white;
                }
                QTextEdit {
                    background-color: white;
                    border: none;
                }
                QHeaderView::section {
                    background-color: #e0e0e0;
                    border: none;
                    padding: 4px 8px;
                    border-right: 1px solid #ccc;
                }
            """)