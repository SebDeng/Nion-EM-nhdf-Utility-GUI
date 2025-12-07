"""
Analysis results panel for displaying analysis data.
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtCore import Qt, Signal
from typing import Optional, Dict, Any, List
import numpy as np
from src.gui.line_profile_widget import LineProfileWidget


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

        # Line profile plot widget
        self._line_profile_widget = LineProfileWidget()
        layout.addWidget(self._line_profile_widget)

    def clear_all(self):
        """Clear all analysis results."""
        self._line_profile_widget.clear_plot()

    def add_line_profile(self, profile_id: str, data: Dict[str, Any]):
        """
        Add/update a line profile result.

        Args:
            profile_id: Unique identifier for the profile
            data: Dictionary with profile data (start, end, values, distances, etc.)
        """
        # Need to have both values and distances for plotting
        if 'values' in data:
            # If distances not provided, create them
            if 'distances' not in data:
                values = data['values']
                if 'distance' in data:
                    # Create distances from 0 to total distance
                    data['distances'] = np.linspace(0, data['distance'], len(values))
                else:
                    # Just use indices
                    data['distances'] = np.arange(len(values))

            # Update the plot
            self._line_profile_widget.update_profile(profile_id, data)


    def set_theme(self, is_dark: bool):
        """Update the panel theme."""
        self._is_dark_mode = is_dark
        self._apply_theme()
        # Also update the line profile widget theme
        self._line_profile_widget.set_theme(is_dark)

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