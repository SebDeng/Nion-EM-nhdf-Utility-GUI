"""
Analysis results panel for displaying analysis data.
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QTabWidget
from PySide6.QtCore import Qt, Signal
from typing import Optional, Dict, Any, List
import numpy as np
from src.gui.line_profile_widget import LineProfileWidget
from src.gui.histogram_widget import HistogramWidget


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

        # Create tab widget for different analysis views
        self._tab_widget = QTabWidget()
        self._tab_widget.setDocumentMode(True)

        # Line profile plot widget
        self._line_profile_widget = LineProfileWidget()
        self._tab_widget.addTab(self._line_profile_widget, "Line Profile")

        # Histogram widget
        self._histogram_widget = HistogramWidget()
        self._tab_widget.addTab(self._histogram_widget, "Histogram")

        layout.addWidget(self._tab_widget)

    def clear_all(self):
        """Clear all analysis results."""
        self._line_profile_widget.clear_plot()
        self._histogram_widget.clear_histogram()

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


    def update_histogram(self, image_data, display_range: tuple = None):
        """
        Update the histogram with new image data.

        Args:
            image_data: 2D numpy array of image intensities
            display_range: Optional tuple of (min, max) for display range indicators
        """
        self._histogram_widget.update_histogram(image_data, display_range)

    def show_histogram_tab(self):
        """Switch to the histogram tab."""
        self._tab_widget.setCurrentWidget(self._histogram_widget)

    def show_line_profile_tab(self):
        """Switch to the line profile tab."""
        self._tab_widget.setCurrentWidget(self._line_profile_widget)

    def set_theme(self, is_dark: bool):
        """Update the panel theme."""
        self._is_dark_mode = is_dark
        self._apply_theme()
        # Also update child widget themes
        self._line_profile_widget.set_theme(is_dark)
        self._histogram_widget.set_theme(is_dark)

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
                    border: 1px solid #3c3c3c;
                    background-color: #2b2b2b;
                }
                QTabBar::tab {
                    background-color: #3a3a3a;
                    color: #e0e0e0;
                    padding: 6px 12px;
                    border: 1px solid #3c3c3c;
                    border-bottom: none;
                    margin-right: 2px;
                }
                QTabBar::tab:selected {
                    background-color: #2b2b2b;
                    border-bottom: 1px solid #2b2b2b;
                }
                QTabBar::tab:hover {
                    background-color: #4a4a4a;
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
                QTabWidget::pane {
                    border: 1px solid #ccc;
                    background-color: #f5f5f5;
                }
                QTabBar::tab {
                    background-color: #e0e0e0;
                    color: #333;
                    padding: 6px 12px;
                    border: 1px solid #ccc;
                    border-bottom: none;
                    margin-right: 2px;
                }
                QTabBar::tab:selected {
                    background-color: #f5f5f5;
                    border-bottom: 1px solid #f5f5f5;
                }
                QTabBar::tab:hover {
                    background-color: #d0d0d0;
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