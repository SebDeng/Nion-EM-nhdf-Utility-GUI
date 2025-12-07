"""
Analysis toolbar for preview mode.
Provides tools for examining and analyzing nhdf data.
"""

from PySide6.QtWidgets import QToolBar, QWidget
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QIcon


class AnalysisToolBar(QToolBar):
    """
    Toolbar for analysis tools in preview mode.
    """

    # Signals
    create_line_profile = Signal()  # Emitted when create line profile is clicked
    clear_requested = Signal()  # Emitted when clear button is clicked

    def __init__(self, parent=None):
        super().__init__("Analysis Tools", parent)
        self.setObjectName("AnalysisToolBar")
        self._is_dark_mode = True

        self._setup_tools()
        self._apply_theme()

    def _setup_tools(self):
        """Set up the analysis tools."""
        # Create Line Profile button (not checkable - one-click action)
        self._create_line_action = QAction("Create Line Profile", self)
        self._create_line_action.setCheckable(False)  # Not a toggle, just a button
        self._create_line_action.setToolTip("Create a line profile (L)")
        self._create_line_action.setShortcut("L")
        self._create_line_action.triggered.connect(self._on_create_line_profile)
        self.addAction(self._create_line_action)

        self.addSeparator()

        # Clear all button
        self._clear_action = QAction("Clear Line Profiles", self)
        self._clear_action.setToolTip("Clear all line profiles")
        self._clear_action.triggered.connect(self._on_clear_all)
        self.addAction(self._clear_action)

    def _on_create_line_profile(self):
        """Handle create line profile button click."""
        self.create_line_profile.emit()

    def _on_clear_all(self):
        """Clear all analysis overlays."""
        self.clear_requested.emit()

    def set_theme(self, is_dark: bool):
        """Update toolbar theme."""
        self._is_dark_mode = is_dark
        self._apply_theme()

    def _apply_theme(self):
        """Apply the current theme to the toolbar."""
        if self._is_dark_mode:
            # Dark theme
            self.setStyleSheet("""
                QToolBar {
                    background-color: #2b2b2b;
                    border: none;
                    padding: 4px;
                    spacing: 4px;
                }
                QToolBar::separator {
                    background-color: #555;
                    width: 1px;
                    margin: 4px 8px;
                }
                QToolButton {
                    background-color: transparent;
                    border: 1px solid transparent;
                    border-radius: 4px;
                    padding: 6px 12px;
                    color: #e0e0e0;
                    font-size: 13px;
                }
                QToolButton:hover {
                    background-color: #3a3a3a;
                    border-color: #555;
                }
                QToolButton:checked {
                    background-color: #0d7377;
                    border-color: #14a085;
                    color: white;
                }
                QToolButton:pressed {
                    background-color: #0a5d61;
                }
            """)
        else:
            # Light theme
            self.setStyleSheet("""
                QToolBar {
                    background-color: #f5f5f5;
                    border: none;
                    padding: 4px;
                    spacing: 4px;
                }
                QToolBar::separator {
                    background-color: #ccc;
                    width: 1px;
                    margin: 4px 8px;
                }
                QToolButton {
                    background-color: transparent;
                    border: 1px solid transparent;
                    border-radius: 4px;
                    padding: 6px 12px;
                    color: #333;
                    font-size: 13px;
                }
                QToolButton:hover {
                    background-color: #e0e0e0;
                    border-color: #bbb;
                }
                QToolButton:checked {
                    background-color: #14a085;
                    border-color: #0d7377;
                    color: white;
                }
                QToolButton:pressed {
                    background-color: #0d7377;
                }
            """)