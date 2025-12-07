"""
Analysis toolbar for preview mode.
Provides tools for examining and analyzing nhdf data.
"""

from PySide6.QtWidgets import QToolBar, QWidget
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QIcon, QActionGroup
from enum import Enum


class AnalysisTool(Enum):
    """Available analysis tools."""
    NONE = "none"
    LINE_PROFILE = "line_profile"
    ROI_RECTANGLE = "roi_rectangle"
    ROI_CIRCLE = "roi_circle"
    ROI_POLYGON = "roi_polygon"
    MEASURE_DISTANCE = "measure_distance"
    MEASURE_ANGLE = "measure_angle"


class AnalysisToolBar(QToolBar):
    """
    Toolbar for analysis tools in preview mode.
    """

    # Signals
    tool_changed = Signal(AnalysisTool)  # Emitted when tool selection changes

    def __init__(self, parent=None):
        super().__init__("Analysis Tools", parent)
        self.setObjectName("AnalysisToolBar")

        # Track current tool
        self._current_tool = AnalysisTool.NONE
        self._is_dark_mode = True

        # Create tool group for exclusive selection
        self._tool_group = QActionGroup(self)
        self._tool_group.setExclusive(True)

        self._setup_tools()
        self._apply_theme()

    def _setup_tools(self):
        """Set up the analysis tools."""
        # Selection/Navigation tool (default)
        self._select_action = QAction("Select", self)
        self._select_action.setCheckable(True)
        self._select_action.setChecked(True)
        self._select_action.setToolTip("Select and navigate (Esc)")
        self._select_action.setData(AnalysisTool.NONE)
        self._select_action.triggered.connect(lambda: self._on_tool_selected(AnalysisTool.NONE))
        self._tool_group.addAction(self._select_action)
        self.addAction(self._select_action)

        self.addSeparator()

        # Line Profile tool
        self._line_profile_action = QAction("Line Profile", self)
        self._line_profile_action.setCheckable(True)
        self._line_profile_action.setToolTip("Draw line profile (L)")
        self._line_profile_action.setShortcut("L")
        self._line_profile_action.setData(AnalysisTool.LINE_PROFILE)
        self._line_profile_action.triggered.connect(lambda: self._on_tool_selected(AnalysisTool.LINE_PROFILE))
        self._tool_group.addAction(self._line_profile_action)
        self.addAction(self._line_profile_action)

        self.addSeparator()

        # ROI tools
        self._roi_rect_action = QAction("Rectangle ROI", self)
        self._roi_rect_action.setCheckable(True)
        self._roi_rect_action.setToolTip("Draw rectangular ROI (R)")
        self._roi_rect_action.setShortcut("R")
        self._roi_rect_action.setData(AnalysisTool.ROI_RECTANGLE)
        self._roi_rect_action.triggered.connect(lambda: self._on_tool_selected(AnalysisTool.ROI_RECTANGLE))
        self._tool_group.addAction(self._roi_rect_action)
        self.addAction(self._roi_rect_action)

        self._roi_circle_action = QAction("Circle ROI", self)
        self._roi_circle_action.setCheckable(True)
        self._roi_circle_action.setToolTip("Draw circular ROI (C)")
        self._roi_circle_action.setShortcut("C")
        self._roi_circle_action.setData(AnalysisTool.ROI_CIRCLE)
        self._roi_circle_action.triggered.connect(lambda: self._on_tool_selected(AnalysisTool.ROI_CIRCLE))
        self._tool_group.addAction(self._roi_circle_action)
        self.addAction(self._roi_circle_action)

        self._roi_polygon_action = QAction("Polygon ROI", self)
        self._roi_polygon_action.setCheckable(True)
        self._roi_polygon_action.setToolTip("Draw polygon ROI (P)")
        self._roi_polygon_action.setShortcut("P")
        self._roi_polygon_action.setData(AnalysisTool.ROI_POLYGON)
        self._roi_polygon_action.triggered.connect(lambda: self._on_tool_selected(AnalysisTool.ROI_POLYGON))
        self._tool_group.addAction(self._roi_polygon_action)
        self.addAction(self._roi_polygon_action)

        self.addSeparator()

        # Measurement tools
        self._measure_distance_action = QAction("Measure Distance", self)
        self._measure_distance_action.setCheckable(True)
        self._measure_distance_action.setToolTip("Measure distance (D)")
        self._measure_distance_action.setShortcut("D")
        self._measure_distance_action.setData(AnalysisTool.MEASURE_DISTANCE)
        self._measure_distance_action.triggered.connect(lambda: self._on_tool_selected(AnalysisTool.MEASURE_DISTANCE))
        self._tool_group.addAction(self._measure_distance_action)
        self.addAction(self._measure_distance_action)

        self._measure_angle_action = QAction("Measure Angle", self)
        self._measure_angle_action.setCheckable(True)
        self._measure_angle_action.setToolTip("Measure angle (A)")
        self._measure_angle_action.setShortcut("A")
        self._measure_angle_action.setData(AnalysisTool.MEASURE_ANGLE)
        self._measure_angle_action.triggered.connect(lambda: self._on_tool_selected(AnalysisTool.MEASURE_ANGLE))
        self._tool_group.addAction(self._measure_angle_action)
        self.addAction(self._measure_angle_action)

        self.addSeparator()

        # Clear all button
        self._clear_action = QAction("Clear All", self)
        self._clear_action.setToolTip("Clear all analysis overlays")
        self._clear_action.triggered.connect(self._on_clear_all)
        self.addAction(self._clear_action)

    def _on_tool_selected(self, tool: AnalysisTool):
        """Handle tool selection."""
        if tool != self._current_tool:
            self._current_tool = tool
            self.tool_changed.emit(tool)

    def _on_clear_all(self):
        """Clear all analysis overlays."""
        # This will be connected to display panels
        pass

    def get_current_tool(self) -> AnalysisTool:
        """Get the currently selected tool."""
        return self._current_tool

    def set_tool(self, tool: AnalysisTool):
        """Set the active tool programmatically."""
        for action in self._tool_group.actions():
            if action.data() == tool:
                action.setChecked(True)
                self._on_tool_selected(tool)
                break

    def reset_tool(self):
        """Reset to selection tool."""
        self.set_tool(AnalysisTool.NONE)

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