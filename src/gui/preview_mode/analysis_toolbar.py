"""
Analysis toolbar for preview mode.
Provides tools for examining and analyzing nhdf data.
"""

from PySide6.QtWidgets import QToolBar, QWidget, QSpinBox, QLabel, QComboBox
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QIcon


class AnalysisToolBar(QToolBar):
    """
    Toolbar for analysis tools in preview mode.
    """

    # Signals
    create_line_profile = Signal()  # Emitted when create line profile is clicked
    clear_requested = Signal()  # Emitted when clear button is clicked
    width_changed = Signal(int)  # Emitted when line width is changed
    unit_changed = Signal(str)  # Emitted when x-axis unit is changed
    export_requested = Signal()  # Emitted when export button is clicked
    show_histogram = Signal()  # Emitted when show histogram is clicked

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

        # Line width control
        width_label = QLabel(" Width: ")
        self.addWidget(width_label)

        self._width_spinbox = QSpinBox()
        self._width_spinbox.setMinimum(1)
        self._width_spinbox.setMaximum(50)
        self._width_spinbox.setValue(5)  # Default width
        self._width_spinbox.setSuffix(" px")
        self._width_spinbox.setToolTip("Line profile averaging width in pixels")
        self._width_spinbox.valueChanged.connect(self._on_width_changed)
        self.addWidget(self._width_spinbox)

        self.addSeparator()

        # X-axis unit selector
        unit_label = QLabel(" Unit: ")
        self.addWidget(unit_label)

        self._unit_combo = QComboBox()
        self._unit_combo.addItems(["nm", "px"])
        self._unit_combo.setCurrentText("nm")  # Default to nm
        self._unit_combo.setToolTip("X-axis unit for line profile")
        self._unit_combo.currentTextChanged.connect(self._on_unit_changed)
        self.addWidget(self._unit_combo)

        self.addSeparator()

        # Export button
        self._export_action = QAction("Export Plot", self)
        self._export_action.setToolTip("Export line profile plot as image")
        self._export_action.triggered.connect(self._on_export)
        self.addAction(self._export_action)

        self.addSeparator()

        # Clear all button
        self._clear_action = QAction("Clear Line Profiles", self)
        self._clear_action.setToolTip("Clear all line profiles")
        self._clear_action.triggered.connect(self._on_clear_all)
        self.addAction(self._clear_action)

        self.addSeparator()

        # Show Histogram button
        self._histogram_action = QAction("Show Histogram", self)
        self._histogram_action.setToolTip("Show intensity histogram (H)")
        self._histogram_action.setShortcut("H")
        self._histogram_action.triggered.connect(self._on_show_histogram)
        self.addAction(self._histogram_action)

    def _on_create_line_profile(self):
        """Handle create line profile button click."""
        self.create_line_profile.emit()

    def _on_clear_all(self):
        """Clear all analysis overlays."""
        self.clear_requested.emit()

    def _on_width_changed(self, value):
        """Handle width spinbox value change."""
        self.width_changed.emit(value)

    def _on_unit_changed(self, unit):
        """Handle unit combo box change."""
        self.unit_changed.emit(unit)

    def _on_export(self):
        """Handle export button click."""
        self.export_requested.emit()

    def _on_show_histogram(self):
        """Handle show histogram button click."""
        self.show_histogram.emit()

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