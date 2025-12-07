"""
Analysis results panel for displaying analysis data.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTreeWidget,
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

        # Title label
        title_label = QLabel("Line Profile Analysis")
        title_label.setStyleSheet("QLabel { font-size: 14px; font-weight: bold; padding: 8px; }")
        layout.addWidget(title_label)

        # Line Profiles tree widget
        self._line_profiles_widget = QTreeWidget()
        self._line_profiles_widget.setHeaderLabels(["Property", "Value"])
        self._line_profiles_widget.header().setStretchLastSection(True)
        layout.addWidget(self._line_profiles_widget)

    def clear_all(self):
        """Clear all analysis results."""
        self._line_profiles_widget.clear()

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
                QHeaderView::section {
                    background-color: #e0e0e0;
                    border: none;
                    padding: 4px 8px;
                    border-right: 1px solid #ccc;
                }
            """)